"""Exploratory fixed-alpha brain-age and age-bias analyses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from BrainAgePipeline import CsvFloatFormat, MetadataColumns, PreparedData


@dataclass
class FixedAlphaEstimates:
    """Results from the exploratory Ridge(alpha=1.0) analyses."""

    PredictedAgeCN: np.ndarray
    PredictedAgeOther: np.ndarray
    GapCN: dict[str, np.ndarray]
    GapOther: dict[str, np.ndarray]
    RegionalGap: np.ndarray
    RegionNames: list[str]
    MAE: float
    R2: float


def FitFixedAlphaAnalysis(Data: PreparedData) -> FixedAlphaEstimates:
    """Fit fixed-alpha age models, bias corrections, and regional models."""

    Splitter = GroupKFold(n_splits=5)
    PredictedAgeCN = np.full(len(Data.AgeCN), np.nan)
    PredictedAgeOtherFolds: list[np.ndarray] = []
    for TrainIndices, TestIndices in Splitter.split(
        Data.XCN, Data.AgeCN, groups=Data.RidCN
    ):
        Scaler = StandardScaler()
        XTrain = Scaler.fit_transform(Data.XCN[TrainIndices])
        XTest = Scaler.transform(Data.XCN[TestIndices])
        XOther = Scaler.transform(Data.XOther)
        Model = Ridge(alpha=1.0)
        Model.fit(XTrain, Data.AgeCN[TrainIndices])
        PredictedAgeCN[TestIndices] = Model.predict(XTest)
        PredictedAgeOtherFolds.append(Model.predict(XOther))
    PredictedAgeOther = np.mean(PredictedAgeOtherFolds, axis=0)
    FixedMAE = float(mean_absolute_error(Data.AgeCN, PredictedAgeCN))
    FixedR2 = float(r2_score(Data.AgeCN, PredictedAgeCN))

    GapCN = {
        "A (raw)": np.full(len(Data.AgeCN), np.nan),
        "B (linear)": np.full(len(Data.AgeCN), np.nan),
        "C (non-linear)": np.full(len(Data.AgeCN), np.nan),
    }
    GapOtherFolds: dict[str, list[np.ndarray]] = {
        Name: [] for Name in GapCN
    }

    for TrainIndices, TestIndices in Splitter.split(
        Data.XCN, Data.AgeCN, groups=Data.RidCN
    ):
        Scaler = StandardScaler()
        XTrain = Scaler.fit_transform(Data.XCN[TrainIndices])
        XTest = Scaler.transform(Data.XCN[TestIndices])
        XOther = Scaler.transform(Data.XOther)
        Model = Ridge(alpha=1.0)
        Model.fit(XTrain, Data.AgeCN[TrainIndices])

        PredictedTrain = Model.predict(XTrain)
        PredictedTest = Model.predict(XTest)
        PredictedOther = Model.predict(XOther)
        GapTrainRaw = PredictedTrain - Data.AgeCN[TrainIndices]
        GapTestRaw = PredictedTest - Data.AgeCN[TestIndices]
        GapOtherRaw = PredictedOther - Data.AgeOther
        GapCN["A (raw)"][TestIndices] = GapTestRaw
        GapOtherFolds["A (raw)"].append(GapOtherRaw)

        LinearCorrector = LinearRegression()
        LinearCorrector.fit(
            Data.AgeCN[TrainIndices].reshape(-1, 1), GapTrainRaw
        )
        GapCN["B (linear)"][TestIndices] = GapTestRaw - LinearCorrector.predict(
            Data.AgeCN[TestIndices].reshape(-1, 1)
        )
        GapOtherFolds["B (linear)"].append(
            GapOtherRaw - LinearCorrector.predict(Data.AgeOther.reshape(-1, 1))
        )

        TrainQuadratic = np.column_stack(
            [Data.AgeCN[TrainIndices], Data.AgeCN[TrainIndices] ** 2]
        )
        TestQuadratic = np.column_stack(
            [Data.AgeCN[TestIndices], Data.AgeCN[TestIndices] ** 2]
        )
        OtherQuadratic = np.column_stack([Data.AgeOther, Data.AgeOther ** 2])
        QuadraticCorrector = LinearRegression()
        QuadraticCorrector.fit(TrainQuadratic, GapTrainRaw)
        GapCN["C (non-linear)"][TestIndices] = (
            GapTestRaw - QuadraticCorrector.predict(TestQuadratic)
        )
        GapOtherFolds["C (non-linear)"].append(
            GapOtherRaw - QuadraticCorrector.predict(OtherQuadratic)
        )

    GapOther = {
        Name: np.mean(FoldValues, axis=0)
        for Name, FoldValues in GapOtherFolds.items()
    }

    RegionNames = list(Data.RegionalGroups)
    RegionalGapCN = np.full((len(Data.AgeCN), len(RegionNames)), np.nan)
    RegionalGapOtherFolds = [
        np.full((len(Data.AgeOther), len(RegionNames)), np.nan)
        for _ in range(5)
    ]
    for FoldIndex, (TrainIndices, TestIndices) in enumerate(
        Splitter.split(Data.XCN, Data.AgeCN, groups=Data.RidCN)
    ):
        for RegionIndex, Region in enumerate(RegionNames):
            Columns = Data.RegionalGroups[Region]
            ColumnIndices = [
                Data.FeatureColumns.index(Column) for Column in Columns
            ]
            XRegionCN = Data.XCN[:, ColumnIndices]
            XRegionOther = Data.XOther[:, ColumnIndices]
            Scaler = StandardScaler()
            XTrain = Scaler.fit_transform(XRegionCN[TrainIndices])
            XTest = Scaler.transform(XRegionCN[TestIndices])
            XOther = Scaler.transform(XRegionOther)
            Model = Ridge(alpha=1.0)
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

    return FixedAlphaEstimates(
        PredictedAgeCN=PredictedAgeCN,
        PredictedAgeOther=PredictedAgeOther,
        GapCN=GapCN,
        GapOther=GapOther,
        RegionalGap=RegionalGap,
        RegionNames=RegionNames,
        MAE=FixedMAE,
        R2=FixedR2,
    )


def WriteExploratoryOutputs(
    Data: PreparedData,
    OutputDirectory: Path,
) -> dict[str, Path]:
    """Write fixed-alpha, bias-correction, and representation results."""

    OutputDirectory.mkdir(parents=True, exist_ok=True)
    Estimates = FitFixedAlphaAnalysis(Data)
    OrderedRids = Data.OrderedData["RID"].to_numpy()

    ModelResults = pd.DataFrame(
        [
            {"Metric": "OutOfFoldMAE", "Value": Estimates.MAE},
            {"Metric": "OutOfFoldR2", "Value": Estimates.R2},
            {"Metric": "CNPredictionMinimum", "Value": Estimates.PredictedAgeCN.min()},
            {"Metric": "CNPredictionMaximum", "Value": Estimates.PredictedAgeCN.max()},
            {"Metric": "OtherPredictionMinimum", "Value": Estimates.PredictedAgeOther.min()},
            {"Metric": "OtherPredictionMaximum", "Value": Estimates.PredictedAgeOther.max()},
        ]
    )

    FixedPredictions = Data.OrderedData[["RID", "Age", "Diagnosis"]].copy()
    FixedPredictions["PredictedAge"] = np.concatenate(
        [
            Estimates.GapCN["A (raw)"] + Data.AgeCN,
            Estimates.GapOther["A (raw)"] + Data.AgeOther,
        ]
    )

    BiasRows: list[dict[str, object]] = []
    BiasSubjectResults = Data.OrderedData[MetadataColumns].copy()
    for Variant, GapCN in Estimates.GapCN.items():
        GapAll = np.concatenate([GapCN, Estimates.GapOther[Variant]])
        ColumnName = {
            "A (raw)": "GapA_Raw",
            "B (linear)": "GapB_Linear",
            "C (non-linear)": "GapC_NonLinear",
        }[Variant]
        BiasSubjectResults[ColumnName] = GapAll
        for Diagnosis in ["CN", "MCI", "AD", "MCI/AD"]:
            if Diagnosis == "CN":
                Values = GapCN
            elif Diagnosis == "MCI/AD":
                Values = Estimates.GapOther[Variant]
            else:
                Mask = Data.OrderedData["Diagnosis"].eq(Diagnosis).to_numpy()
                Values = GapAll[Mask]
            BiasRows.append(
                {
                    "Variant": Variant,
                    "Diagnosis": Diagnosis,
                    "N": len(Values),
                    "MeanGap": float(np.mean(Values)),
                    "SDGap": float(np.std(Values)),
                }
            )

    RegionalColumns = [
        Region.replace("FastSurfer_", "", 1) for Region in Estimates.RegionNames
    ]
    FixedRegionalGaps = pd.DataFrame(
        Estimates.RegionalGap, columns=RegionalColumns
    )
    FixedRegionalGaps.insert(0, "RID", OrderedRids)
    CNCount = len(Data.AgeCN)
    RepresentationSummary = pd.DataFrame(
        [
            {"Metric": "ScalarRows", "Value": len(Data.OrderedData)},
            {"Metric": "ScalarVariants", "Value": 3},
            {"Metric": "RawCNRows", "Value": Data.XCN.shape[0]},
            {"Metric": "RawOtherRows", "Value": Data.XOther.shape[0]},
            {"Metric": "RawFeatures", "Value": Data.XAll.shape[1]},
            {"Metric": "RegionalModels", "Value": len(Estimates.RegionNames)},
            {"Metric": "RegionalCNMeanGap", "Value": Estimates.RegionalGap[:CNCount].mean()},
            {"Metric": "RegionalOtherMeanGap", "Value": Estimates.RegionalGap[CNCount:].mean()},
        ]
    )

    Outputs = {
        "FixedAlphaModelResults": OutputDirectory / "FixedAlphaModelResults.csv",
        "FixedAlphaPredictions": OutputDirectory / "FixedAlphaPredictions.csv",
        "BiasCorrectionResults": OutputDirectory / "BiasCorrectionResults.csv",
        "BiasCorrectedGaps": OutputDirectory / "BiasCorrectedGaps.csv",
        "RepresentationSummary": OutputDirectory / "RepresentationSummary.csv",
        "FixedAlphaRegionalGaps": OutputDirectory / "FixedAlphaRegionalGaps.csv",
    }
    ModelResults.to_csv(Outputs["FixedAlphaModelResults"], index=False, float_format=CsvFloatFormat)
    FixedPredictions.to_csv(Outputs["FixedAlphaPredictions"], index=False, float_format=CsvFloatFormat)
    pd.DataFrame(BiasRows).to_csv(Outputs["BiasCorrectionResults"], index=False, float_format=CsvFloatFormat)
    BiasSubjectResults.to_csv(Outputs["BiasCorrectedGaps"], index=False, float_format=CsvFloatFormat)
    RepresentationSummary.to_csv(Outputs["RepresentationSummary"], index=False, float_format=CsvFloatFormat)
    FixedRegionalGaps.to_csv(Outputs["FixedAlphaRegionalGaps"], index=False, float_format=CsvFloatFormat)
    return Outputs