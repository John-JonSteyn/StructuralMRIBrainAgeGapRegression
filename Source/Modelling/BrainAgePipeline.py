"""Reusable modelling functions for the structural MRI brain-age analysis.

The module implements the primary structural MRI design as ordinary Python functions:

* reconstruction QC using whole-brain ``SurfaceHoles``;
* CN-only, out-of-fold RidgeCV brain-age estimation;
* a 171-region brain-age-gap representation;
* nested, out-of-fold diagnosis and cognition evaluation; and
* paired bootstrap confidence intervals for incremental and head-to-head tests.

All preprocessing estimators are fitted within their respective training folds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd
from scipy.stats import bootstrap
from sklearn.linear_model import LogisticRegressionCV, RidgeCV
from sklearn.metrics import (
    brier_score_loss,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ProjectRoot = Path(__file__).resolve().parents[2]
DefaultInputPath = ProjectRoot / "Data" / "Processed" / "Analysis" / "FastSurferModellingDataset.csv"
DefaultOutputDirectory = ProjectRoot / "Data" / "Processed" / "Analysis" / "BrainAgeResults"
CsvFloatFormat = "%.17g"

MetadataColumns = [
    "RID",
    "Age",
    "Sex",
    "Education",
    "Diagnosis",
    "MMSE",
    "ADAS",
    "CDRSB",
    "FAQ",
]
OutcomeColumns = ["MMSE", "CDRSB", "ADAS", "FAQ"]
FailedFastSurferRids = [4377]
SurfaceHolesColumn = "FastSurfer_Aseg_Measure_SurfaceHoles"
AlphaGrid = np.array([0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0])
MetricSuffixes = [
    "_NVoxels",
    "_Volume_mm3",
    "_normMax",
    "_normMean",
    "_normMin",
    "_normRange",
    "_normStdDev",
    "_CurvInd",
    "_FoldInd",
    "_GausCurv",
    "_GrayVol",
    "_MeanCurv",
    "_NumVert",
    "_SurfArea",
    "_ThickAvg",
    "_ThickStd",
]

RepresentationLabels = {
    "scalar": "Scalar gap",
    "regional": "Regional gap",
    "raw": "Raw features",
    "hippo": "Hippocampal volume",
    "gm": "Normalised grey matter",
}


@dataclass
class PreparedData:
    """Validated, QC-filtered matrices in the fixed CN-first analysis order."""

    CleanData: pd.DataFrame
    OrderedData: pd.DataFrame
    FeatureColumns: list[str]
    RegionalGroups: dict[str, list[str]]
    QCThreshold: float
    QCSummary: pd.DataFrame
    XCN: np.ndarray
    XOther: np.ndarray
    AgeCN: np.ndarray
    AgeOther: np.ndarray
    RidCN: np.ndarray
    XAll: np.ndarray
    Covariates: np.ndarray
    DiagnosisBinary: np.ndarray
    HippocampalVolume: np.ndarray
    NormalisedGreyMatter: np.ndarray


@dataclass
class BrainAgeEstimates:
    """Out-of-fold scalar and regional brain-age estimates."""

    ScalarGap: np.ndarray
    PredictedAge: np.ndarray
    RegionalGap: np.ndarray
    RegionNames: list[str]
    ChosenAlphas: list[float]
    MAE: float
    R2: float


def PrintProgress(Message: str) -> None:
    print(Message, flush=True)


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def ValidateDataset(DataFrame: pd.DataFrame) -> None:
    """Reject incomplete metadata, invalid diagnoses, and duplicate participants."""

    MissingColumns = [Column for Column in MetadataColumns if Column not in DataFrame.columns]
    if SurfaceHolesColumn not in DataFrame.columns:
        MissingColumns.append(SurfaceHolesColumn)
    if MissingColumns:
        raise ValueError("Dataset is missing required columns: " + ", ".join(MissingColumns))

    InvalidDiagnoses = sorted(set(DataFrame["Diagnosis"].dropna()) - {"CN", "MCI", "AD"})
    if InvalidDiagnoses:
        raise ValueError("Unexpected diagnosis values: " + ", ".join(map(str, InvalidDiagnoses)))
    if DataFrame["RID"].duplicated().any():
        DuplicateRids = DataFrame.loc[DataFrame["RID"].duplicated(), "RID"].tolist()
        raise ValueError(f"RID must be unique; duplicate values found: {DuplicateRids[:10]}")


def CalculateQCThreshold(DataFrame: pd.DataFrame, Rule: str) -> float:
    """Calculate a SurfaceHoles threshold after the processing-failure exclusion."""

    Values = DataFrame[SurfaceHolesColumn]
    if Rule == "none":
        return float("inf")
    if Rule == "p97.5":
        return float(np.percentile(Values, 97.5))
    if Rule == "p95":
        return float(np.percentile(Values, 95.0))
    if Rule == "median+3mad":
        Median = float(Values.median())
        MedianAbsoluteDeviation = float((Values - Median).abs().median())
        return Median + (3.0 * 1.4826 * MedianAbsoluteDeviation)
    raise ValueError("QC rule must be one of: none, p97.5, p95, median+3mad")


def BuildRegionalGroups(FeatureColumns: Sequence[str]) -> dict[str, list[str]]:
    """Group FastSurfer features by region using known metric suffixes."""

    RegionGroups: dict[str, list[str]] = {}
    for Column in FeatureColumns:
        RegionName = Column
        for Suffix in MetricSuffixes:
            if Column.endswith(Suffix):
                RegionName = Column[: -len(Suffix)]
                break
        RegionGroups.setdefault(RegionName, []).append(Column)

    return {
        RegionName: Columns
        for RegionName, Columns in RegionGroups.items()
        if len(Columns) >= 4
    }


def PrepareDataset(InputPath: Path, QCRule: str = "median+3mad") -> PreparedData:
    """Read, validate, QC-filter, and order the modelling dataset."""

    DataFrame = pd.read_csv(InputPath, low_memory=False)
    ValidateDataset(DataFrame)

    AfterProcessingDrop = DataFrame.loc[
        ~DataFrame["RID"].isin(FailedFastSurferRids)
    ].reset_index(drop=True)
    Threshold = CalculateQCThreshold(AfterProcessingDrop, QCRule)
    QCFailure = AfterProcessingDrop[SurfaceHolesColumn] > Threshold

    BeforeCounts = AfterProcessingDrop["Diagnosis"].value_counts()
    DroppedCounts = AfterProcessingDrop.loc[QCFailure, "Diagnosis"].value_counts()
    AfterCounts = AfterProcessingDrop.loc[~QCFailure, "Diagnosis"].value_counts()
    QCSummary = pd.DataFrame(
        {
            "Diagnosis": ["CN", "MCI", "AD"],
            "Before": [int(BeforeCounts.get(Value, 0)) for Value in ["CN", "MCI", "AD"]],
            "Dropped": [int(DroppedCounts.get(Value, 0)) for Value in ["CN", "MCI", "AD"]],
            "After": [int(AfterCounts.get(Value, 0)) for Value in ["CN", "MCI", "AD"]],
        }
    )
    QCSummary["DroppedPercent"] = (
        100.0 * QCSummary["Dropped"] / QCSummary["Before"]
    ).round(1)
    QCSummary["QCRule"] = QCRule
    QCSummary["Threshold"] = Threshold

    CleanData = AfterProcessingDrop.loc[~QCFailure].reset_index(drop=True)
    SurfaceHolesColumns = [Column for Column in CleanData.columns if "SurfaceHoles" in Column]
    FeatureColumns = [
        Column
        for Column in CleanData.columns
        if Column.startswith("FastSurfer_") and Column not in SurfaceHolesColumns
    ]
    if not FeatureColumns:
        raise ValueError("No FastSurfer predictor columns were found")
    if CleanData[FeatureColumns].isna().any().any():
        MissingCount = int(CleanData[FeatureColumns].isna().sum().sum())
        raise ValueError(f"QC-filtered feature matrix contains {MissingCount} missing values")

    RegionalGroups = BuildRegionalGroups(FeatureColumns)
    CNMask = CleanData["Diagnosis"].eq("CN").to_numpy()
    OtherMask = CleanData["Diagnosis"].isin(["MCI", "AD"]).to_numpy()
    OrderedData = pd.concat(
        [CleanData.loc[CNMask], CleanData.loc[OtherMask]], ignore_index=True
    )

    # Direct construction preserves a consistent float64 memory layout across
    # repeated deterministic fits.
    XCN = CleanData.loc[CNMask, FeatureColumns].to_numpy()
    XOther = CleanData.loc[OtherMask, FeatureColumns].to_numpy()
    AgeCN = CleanData.loc[CNMask, "Age"].to_numpy(dtype=float)
    AgeOther = CleanData.loc[OtherMask, "Age"].to_numpy(dtype=float)
    RidCN = CleanData.loc[CNMask, "RID"].to_numpy()
    XAll = np.vstack([XCN, XOther])

    Sex = OrderedData["Sex"].astype(str).str.casefold()
    UnknownSex = sorted(set(Sex) - {"male", "female"})
    if UnknownSex:
        raise ValueError("Unexpected Sex values: " + ", ".join(UnknownSex))
    if OrderedData[["Age", "Education"]].isna().any().any():
        raise ValueError("Age and Education must be complete for the analysis baseline")

    Covariates = np.column_stack(
        [
            OrderedData["Age"].to_numpy(dtype=float),
            Sex.eq("male").astype(int).to_numpy(),
            OrderedData["Education"].to_numpy(dtype=float),
        ]
    )
    DiagnosisBinary = OrderedData["Diagnosis"].ne("CN").astype(int).to_numpy()
    HippocampalVolume = (
        OrderedData["FastSurfer_Aseg_Left_Hippocampus_Volume_mm3"]
        + OrderedData["FastSurfer_Aseg_Right_Hippocampus_Volume_mm3"]
    ).to_numpy(dtype=float)
    NormalisedGreyMatter = (
        OrderedData["FastSurfer_Aseg_Measure_TotalGrayVol"]
        / OrderedData["FastSurfer_Aseg_Measure_eTIV"]
    ).to_numpy(dtype=float)

    return PreparedData(
        CleanData=CleanData,
        OrderedData=OrderedData,
        FeatureColumns=FeatureColumns,
        RegionalGroups=RegionalGroups,
        QCThreshold=Threshold,
        QCSummary=QCSummary,
        XCN=XCN,
        XOther=XOther,
        AgeCN=AgeCN,
        AgeOther=AgeOther,
        RidCN=RidCN,
        XAll=XAll,
        Covariates=Covariates,
        DiagnosisBinary=DiagnosisBinary,
        HippocampalVolume=HippocampalVolume,
        NormalisedGreyMatter=NormalisedGreyMatter,
    )


def FitBrainAgeModels(Data: PreparedData) -> BrainAgeEstimates:
    """Fit scalar and per-region RidgeCV models with CN-only nested validation."""

    Splitter = GroupKFold(n_splits=5)
    ScalarGapCN = np.full(len(Data.AgeCN), np.nan)
    ScalarGapOtherFolds: list[np.ndarray] = []
    ChosenAlphas: list[float] = []

    for TrainIndices, TestIndices in Splitter.split(
        Data.XCN, Data.AgeCN, groups=Data.RidCN
    ):
        Scaler = StandardScaler()
        XTrain = Scaler.fit_transform(Data.XCN[TrainIndices])
        XTest = Scaler.transform(Data.XCN[TestIndices])
        XOther = Scaler.transform(Data.XOther)
        Model = RidgeCV(alphas=AlphaGrid, cv=5)
        Model.fit(XTrain, Data.AgeCN[TrainIndices])
        ChosenAlphas.append(float(Model.alpha_))
        ScalarGapCN[TestIndices] = Model.predict(XTest) - Data.AgeCN[TestIndices]
        ScalarGapOtherFolds.append(Model.predict(XOther) - Data.AgeOther)

    ScalarGapOther = np.mean(ScalarGapOtherFolds, axis=0)
    ScalarGap = np.concatenate([ScalarGapCN, ScalarGapOther])
    PredictedAge = ScalarGap + Data.OrderedData["Age"].to_numpy(dtype=float)
    MAE = mean_absolute_error(Data.AgeCN, PredictedAge[: len(Data.AgeCN)])
    R2 = r2_score(Data.AgeCN, PredictedAge[: len(Data.AgeCN)])

    RegionNames = list(Data.RegionalGroups)
    RegionColumns = {
        Region: [
            Data.FeatureColumns.index(Column)
            for Column in Data.RegionalGroups[Region]
        ]
        for Region in RegionNames
    }
    RegionalGapCN = np.full((len(Data.AgeCN), len(RegionNames)), np.nan)
    RegionalGapOtherFolds = [
        np.full((len(Data.AgeOther), len(RegionNames)), np.nan)
        for _ in range(Splitter.get_n_splits())
    ]

    for FoldIndex, (TrainIndices, TestIndices) in enumerate(
        Splitter.split(Data.XCN, Data.AgeCN, groups=Data.RidCN)
    ):
        for RegionIndex, Region in enumerate(RegionNames):
            Columns = RegionColumns[Region]
            Scaler = StandardScaler()
            XTrain = Scaler.fit_transform(Data.XCN[TrainIndices][:, Columns])
            XTest = Scaler.transform(Data.XCN[TestIndices][:, Columns])
            XOther = Scaler.transform(Data.XOther[:, Columns])
            Model = RidgeCV(alphas=AlphaGrid, cv=5)
            Model.fit(XTrain, Data.AgeCN[TrainIndices])
            RegionalGapCN[TestIndices, RegionIndex] = (
                Model.predict(XTest) - Data.AgeCN[TestIndices]
            )
            RegionalGapOtherFolds[FoldIndex][:, RegionIndex] = (
                Model.predict(XOther) - Data.AgeOther
            )

    RegionalGap = np.vstack(
        [RegionalGapCN, np.mean(RegionalGapOtherFolds, axis=0)]
    )
    return BrainAgeEstimates(
        ScalarGap=ScalarGap,
        PredictedAge=PredictedAge,
        RegionalGap=RegionalGap,
        RegionNames=RegionNames,
        ChosenAlphas=ChosenAlphas,
        MAE=float(MAE),
        R2=float(R2),
    )


def MakeClassifier() -> Pipeline:
    """Construct the scaled cross-validated logistic diagnosis model."""

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegressionCV(
                    Cs=10,
                    cv=5,
                    penalty="l2",
                    class_weight="balanced",
                    scoring="neg_log_loss",
                    max_iter=2000,
                ),
            ),
        ]
    )


def MakeRegressor() -> Pipeline:
    """Construct the scaled cross-validated Ridge cognition model."""

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("regressor", RidgeCV(alphas=AlphaGrid, cv=5)),
        ]
    )


def OutOfFoldProbability(
    X: np.ndarray,
    Y: np.ndarray,
    Folds: list[tuple[np.ndarray, np.ndarray]],
    Jobs: int,
) -> np.ndarray:
    """Generate positive-class probabilities using fixed external folds."""

    return cross_val_predict(
        MakeClassifier(), X, Y, cv=Folds, method="predict_proba", n_jobs=Jobs
    )[:, 1]


def OutOfFoldPrediction(
    X: np.ndarray,
    Y: np.ndarray,
    Folds: list[tuple[np.ndarray, np.ndarray]],
    Jobs: int,
) -> np.ndarray:
    """Generate continuous predictions using fixed external folds."""

    return cross_val_predict(MakeRegressor(), X, Y, cv=Folds, n_jobs=Jobs)


def BootstrapMetricDifference(
    Y: np.ndarray,
    PredictionA: np.ndarray,
    PredictionB: np.ndarray,
    Metric: Callable[[np.ndarray, np.ndarray], float],
    Resamples: int,
    Seed: int = 0,
) -> tuple[float, float]:
    """Use a paired SciPy percentile bootstrap with a deterministic seed."""

    Indices = np.arange(len(Y))
    Result = bootstrap(
        (Indices,),
        lambda Sample: Metric(Y[Sample], PredictionA[Sample])
        - Metric(Y[Sample], PredictionB[Sample]),
        n_resamples=Resamples,
        confidence_level=0.95,
        method="percentile",
        vectorized=False,
        random_state=Seed,
    )
    return (
        float(Result.confidence_interval.low),
        float(Result.confidence_interval.high),
    )


def BuildRepresentations(
    Data: PreparedData, Estimates: BrainAgeEstimates
) -> dict[str, np.ndarray]:
    """Assemble the feature matrix used by each downstream representation."""

    return {
        RepresentationLabels["scalar"]: Estimates.ScalarGap.reshape(-1, 1),
        RepresentationLabels["regional"]: Estimates.RegionalGap,
        RepresentationLabels["raw"]: Data.XAll,
        RepresentationLabels["hippo"]: Data.HippocampalVolume.reshape(-1, 1),
        RepresentationLabels["gm"]: Data.NormalisedGreyMatter.reshape(-1, 1),
    }


def EvaluateDiagnosisTarget(
    TargetName: str,
    Y: np.ndarray,
    Baseline: np.ndarray,
    Representations: dict[str, np.ndarray],
    Rids: np.ndarray,
    BootstrapResamples: int,
    Jobs: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate baseline and baseline-plus-representation diagnosis models."""

    Splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    Folds = list(Splitter.split(np.zeros(len(Y)), Y))
    BaselinePrediction = OutOfFoldProbability(Baseline, Y, Folds, Jobs)
    BaselineAUC = roc_auc_score(Y, BaselinePrediction)
    Rows = [
        {
            "Target": TargetName,
            "Model": "Baseline",
            "N": len(Y),
            "AUC": BaselineAUC,
            "Brier": brier_score_loss(Y, BaselinePrediction),
            "DeltaAUC": 0.0,
            "CILow": np.nan,
            "CIHigh": np.nan,
            "CIExcludesZero": False,
        }
    ]
    Predictions = {"Baseline": BaselinePrediction}

    for Name, Representation in Representations.items():
        Prediction = OutOfFoldProbability(
            np.column_stack([Baseline, Representation]), Y, Folds, Jobs
        )
        Predictions[Name] = Prediction
        AUC = roc_auc_score(Y, Prediction)
        Low, High = BootstrapMetricDifference(
            Y,
            Prediction,
            BaselinePrediction,
            roc_auc_score,
            BootstrapResamples,
        )
        Rows.append(
            {
                "Target": TargetName,
                "Model": Name,
                "N": len(Y),
                "AUC": AUC,
                "Brier": brier_score_loss(Y, Prediction),
                "DeltaAUC": AUC - BaselineAUC,
                "CILow": Low,
                "CIHigh": High,
                "CIExcludesZero": bool(Low > 0 or High < 0),
            }
        )

    PredictionFrame = pd.DataFrame({"RID": Rids, "TargetValue": Y, **Predictions})
    PredictionFrame.insert(0, "Target", TargetName)
    return pd.DataFrame(Rows), PredictionFrame


def EvaluateCognitionOutcome(
    OutcomeName: str,
    Y: np.ndarray,
    Baseline: np.ndarray,
    StratificationTarget: np.ndarray,
    Representations: dict[str, np.ndarray],
    Rids: np.ndarray,
    BootstrapResamples: int,
    Jobs: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate baseline and baseline-plus-representation cognition models."""

    Splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    Folds = list(Splitter.split(np.zeros(len(Y)), StratificationTarget))
    BaselinePrediction = OutOfFoldPrediction(Baseline, Y, Folds, Jobs)
    BaselineR2 = r2_score(Y, BaselinePrediction)
    Rows = [
        {
            "Outcome": OutcomeName,
            "Model": "Baseline",
            "N": len(Y),
            "R2": BaselineR2,
            "DeltaR2": 0.0,
            "CILow": np.nan,
            "CIHigh": np.nan,
            "CIExcludesZero": False,
        }
    ]
    Predictions = {"Baseline": BaselinePrediction}

    for Name, Representation in Representations.items():
        Prediction = OutOfFoldPrediction(
            np.column_stack([Baseline, Representation]), Y, Folds, Jobs
        )
        Predictions[Name] = Prediction
        R2 = r2_score(Y, Prediction)
        Low, High = BootstrapMetricDifference(
            Y,
            Prediction,
            BaselinePrediction,
            r2_score,
            BootstrapResamples,
        )
        Rows.append(
            {
                "Outcome": OutcomeName,
                "Model": Name,
                "N": len(Y),
                "R2": R2,
                "DeltaR2": R2 - BaselineR2,
                "CILow": Low,
                "CIHigh": High,
                "CIExcludesZero": bool(Low > 0 or High < 0),
            }
        )

    PredictionFrame = pd.DataFrame({"RID": Rids, "TargetValue": Y, **Predictions})
    PredictionFrame.insert(0, "Outcome", OutcomeName)
    return pd.DataFrame(Rows), PredictionFrame


def EvaluateHeadToHead(
    TargetName: str,
    Y: np.ndarray,
    Predictions: pd.DataFrame,
    MetricName: str,
    Metric: Callable[[np.ndarray, np.ndarray], float],
    BootstrapResamples: int,
) -> pd.DataFrame:
    """Compare selected representation pairs using the same OOF subjects."""

    Pairs = [
        ("Regional gap", "Scalar gap"),
        ("Regional gap", "Hippocampal volume"),
        ("Raw features", "Scalar gap"),
        ("Raw features", "Regional gap"),
        ("Scalar gap", "Hippocampal volume"),
    ]
    Rows: list[dict[str, object]] = []
    for ModelA, ModelB in Pairs:
        PredictionA = Predictions[ModelA].to_numpy()
        PredictionB = Predictions[ModelB].to_numpy()
        Difference = Metric(Y, PredictionA) - Metric(Y, PredictionB)
        Low, High = BootstrapMetricDifference(
            Y, PredictionA, PredictionB, Metric, BootstrapResamples
        )
        Rows.append(
            {
                "Target": TargetName,
                "Metric": MetricName,
                "ModelA": ModelA,
                "ModelB": ModelB,
                "Difference": Difference,
                "CILow": Low,
                "CIHigh": High,
                "CIExcludesZero": bool(Low > 0 or High < 0),
            }
        )
    return pd.DataFrame(Rows)


def BuildCohortSummary(Data: PreparedData) -> pd.DataFrame:
    """Summarise cohort size, age, sex, and education by diagnosis."""

    Rows: list[dict[str, object]] = []
    for Diagnosis in ["CN", "MCI", "AD", "All"]:
        Group = Data.OrderedData if Diagnosis == "All" else Data.OrderedData.loc[
            Data.OrderedData["Diagnosis"].eq(Diagnosis)
        ]
        Rows.append(
            {
                "Diagnosis": Diagnosis,
                "N": len(Group),
                "AgeMean": Group["Age"].mean(),
                "AgeSD": Group["Age"].std(),
                "FemaleN": int(Group["Sex"].astype(str).str.casefold().eq("female").sum()),
                "EducationMean": Group["Education"].mean(),
                "EducationSD": Group["Education"].std(),
            }
        )
    return pd.DataFrame(Rows)


def WritePrimaryOutputs(
    Data: PreparedData,
    Estimates: BrainAgeEstimates,
    OutputDirectory: Path,
    BootstrapResamples: int,
    Jobs: int = 1,
) -> dict[str, Path]:
    """Evaluate the primary models and write all machine-readable outputs."""

    EnsureDirectory(OutputDirectory)
    Representations = BuildRepresentations(Data, Estimates)
    OrderedRids = Data.OrderedData["RID"].to_numpy()

    PrintProgress("Evaluating diagnosis targets")
    DiagnosisFrames: list[pd.DataFrame] = []
    DiagnosisPredictionFrames: list[pd.DataFrame] = []
    HeadToHeadFrames: list[pd.DataFrame] = []

    PrimaryMetrics, PrimaryPredictions = EvaluateDiagnosisTarget(
        "CN vs MCI+AD",
        Data.DiagnosisBinary,
        Data.Covariates,
        Representations,
        OrderedRids,
        BootstrapResamples,
        Jobs,
    )
    DiagnosisFrames.append(PrimaryMetrics)
    DiagnosisPredictionFrames.append(PrimaryPredictions)
    HeadToHeadFrames.append(
        EvaluateHeadToHead(
            "CN vs MCI+AD",
            Data.DiagnosisBinary,
            PrimaryPredictions,
            "AUC",
            roc_auc_score,
            BootstrapResamples,
        )
    )

    CNADMask = Data.OrderedData["Diagnosis"].isin(["CN", "AD"]).to_numpy()
    CNADTarget = Data.OrderedData.loc[CNADMask, "Diagnosis"].eq("AD").astype(int).to_numpy()
    CNADRepresentations = {
        Name: Values[CNADMask] for Name, Values in Representations.items()
    }
    CNADMetrics, CNADPredictions = EvaluateDiagnosisTarget(
        "CN vs AD",
        CNADTarget,
        Data.Covariates[CNADMask],
        CNADRepresentations,
        OrderedRids[CNADMask],
        BootstrapResamples,
        Jobs,
    )
    DiagnosisFrames.append(CNADMetrics)
    DiagnosisPredictionFrames.append(CNADPredictions)
    HeadToHeadFrames.append(
        EvaluateHeadToHead(
            "CN vs AD",
            CNADTarget,
            CNADPredictions,
            "AUC",
            roc_auc_score,
            BootstrapResamples,
        )
    )

    PrintProgress("Evaluating cognition outcomes")
    CognitionFrames: list[pd.DataFrame] = []
    CognitionPredictionFrames: list[pd.DataFrame] = []
    for Outcome in OutcomeColumns:
        Complete = Data.OrderedData[Outcome].notna().to_numpy()
        OutcomeMetrics, OutcomePredictions = EvaluateCognitionOutcome(
            Outcome,
            Data.OrderedData.loc[Complete, Outcome].to_numpy(dtype=float),
            Data.Covariates[Complete],
            Data.DiagnosisBinary[Complete],
            {Name: Values[Complete] for Name, Values in Representations.items()},
            OrderedRids[Complete],
            BootstrapResamples,
            Jobs,
        )
        CognitionFrames.append(OutcomeMetrics)
        CognitionPredictionFrames.append(OutcomePredictions)
        HeadToHeadFrames.append(
            EvaluateHeadToHead(
                Outcome,
                Data.OrderedData.loc[Complete, Outcome].to_numpy(dtype=float),
                OutcomePredictions,
                "R2",
                r2_score,
                BootstrapResamples,
            )
        )

    SubjectResults = Data.OrderedData[MetadataColumns].copy()
    SubjectResults["PredictedBrainAge"] = Estimates.PredictedAge
    SubjectResults["BrainAgeGap"] = Estimates.ScalarGap
    SubjectResults["MeanRegionalGap"] = Estimates.RegionalGap.mean(axis=1)

    RegionalColumnNames = [
        Region.replace("FastSurfer_", "", 1) for Region in Estimates.RegionNames
    ]
    RegionalResults = pd.DataFrame(Estimates.RegionalGap, columns=RegionalColumnNames)
    RegionalResults.insert(0, "RID", OrderedRids)
    RegionalSummary = pd.DataFrame(
        {
            "Region": RegionalColumnNames,
            "MeanGapAll": Estimates.RegionalGap.mean(axis=0),
            "MeanGapCN": Estimates.RegionalGap[
                Data.OrderedData["Diagnosis"].eq("CN").to_numpy()
            ].mean(axis=0),
            "MeanGapMCIAD": Estimates.RegionalGap[
                Data.OrderedData["Diagnosis"].isin(["MCI", "AD"]).to_numpy()
            ].mean(axis=0),
        }
    )
    RegionalSummary["AbsoluteMeanGapMCIAD"] = RegionalSummary["MeanGapMCIAD"].abs()
    RegionalSummary["RankByAbsoluteMCIADGap"] = (
        RegionalSummary["AbsoluteMeanGapMCIAD"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    RegionalSummary = RegionalSummary.sort_values("RankByAbsoluteMCIADGap")

    ModelSummary = pd.DataFrame(
        [
            {"Metric": "CohortRows", "Value": len(Data.OrderedData)},
            {"Metric": "CNRows", "Value": len(Data.AgeCN)},
            {"Metric": "FastSurferFeatures", "Value": len(Data.FeatureColumns)},
            {"Metric": "RegionalModels", "Value": len(Estimates.RegionNames)},
            {"Metric": "QCThreshold", "Value": Data.QCThreshold},
            {"Metric": "BrainAgeMAE", "Value": Estimates.MAE},
            {"Metric": "BrainAgeR2", "Value": Estimates.R2},
            {
                "Metric": "ChosenAlphas",
                "Value": ";".join(f"{Value:g}" for Value in Estimates.ChosenAlphas),
            },
            {"Metric": "BootstrapResamples", "Value": BootstrapResamples},
        ]
    )

    Outputs = {
        "SubjectResults": OutputDirectory / "BrainAgeSubjectResults.csv",
        "RegionalGaps": OutputDirectory / "RegionalBrainAgeGaps.csv",
        "RegionalSummary": OutputDirectory / "RegionalGapSummary.csv",
        "ModelSummary": OutputDirectory / "BrainAgeModelSummary.csv",
        "CohortSummary": OutputDirectory / "CohortSummary.csv",
        "QCSummary": OutputDirectory / "QCSummary.csv",
        "DiagnosisResults": OutputDirectory / "DiagnosisModelResults.csv",
        "DiagnosisPredictions": OutputDirectory / "DiagnosisOutOfFoldPredictions.csv",
        "CognitionResults": OutputDirectory / "CognitionModelResults.csv",
        "CognitionPredictions": OutputDirectory / "CognitionOutOfFoldPredictions.csv",
        "HeadToHeadResults": OutputDirectory / "HeadToHeadModelResults.csv",
    }
    SubjectResults.to_csv(Outputs["SubjectResults"], index=False, float_format=CsvFloatFormat)
    RegionalResults.to_csv(Outputs["RegionalGaps"], index=False, float_format=CsvFloatFormat)
    RegionalSummary.to_csv(Outputs["RegionalSummary"], index=False, float_format=CsvFloatFormat)
    ModelSummary.to_csv(Outputs["ModelSummary"], index=False, float_format=CsvFloatFormat)
    BuildCohortSummary(Data).to_csv(Outputs["CohortSummary"], index=False, float_format=CsvFloatFormat)
    Data.QCSummary.to_csv(Outputs["QCSummary"], index=False, float_format=CsvFloatFormat)
    pd.concat(DiagnosisFrames, ignore_index=True).to_csv(
        Outputs["DiagnosisResults"], index=False, float_format=CsvFloatFormat
    )
    pd.concat(DiagnosisPredictionFrames, ignore_index=True).to_csv(
        Outputs["DiagnosisPredictions"], index=False, float_format=CsvFloatFormat
    )
    pd.concat(CognitionFrames, ignore_index=True).to_csv(
        Outputs["CognitionResults"], index=False, float_format=CsvFloatFormat
    )
    pd.concat(CognitionPredictionFrames, ignore_index=True).to_csv(
        Outputs["CognitionPredictions"], index=False, float_format=CsvFloatFormat
    )
    pd.concat(HeadToHeadFrames, ignore_index=True).to_csv(
        Outputs["HeadToHeadResults"], index=False, float_format=CsvFloatFormat
    )
    return Outputs
