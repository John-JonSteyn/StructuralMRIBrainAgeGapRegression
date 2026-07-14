"""Repeat the primary brain-age pipeline across four SurfaceHoles QC rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from BrainAgePipeline import (
    BootstrapMetricDifference,
    BuildRepresentations,
    CsvFloatFormat,
    DefaultInputPath,
    DefaultOutputDirectory,
    EvaluateDiagnosisTarget,
    FitBrainAgeModels,
    OutOfFoldPrediction,
    PrepareDataset,
    PrintProgress,
)


QCRules = ["none", "p97.5", "p95", "median+3mad"]


def ParseArguments() -> argparse.Namespace:
    """Parse sensitivity-analysis inputs and execution parameters."""

    Parser = argparse.ArgumentParser(
        description="Repeat the complete brain-age fit at four reconstruction-QC thresholds."
    )
    Parser.add_argument("--input", type=Path, default=DefaultInputPath)
    Parser.add_argument("--output-directory", type=Path, default=DefaultOutputDirectory)
    Parser.add_argument("--bootstrap-resamples", type=int, default=9999)
    Parser.add_argument("--jobs", type=int, default=1)
    return Parser.parse_args()


def PairedDifference(
    Y: np.ndarray,
    Predictions: pd.DataFrame,
    ModelA: str,
    ModelB: str,
    Resamples: int,
) -> dict[str, object]:
    """Compare two AUCs with a paired subject-level bootstrap interval."""

    PredictionA = Predictions[ModelA].to_numpy()
    PredictionB = Predictions[ModelB].to_numpy()
    Difference = roc_auc_score(Y, PredictionA) - roc_auc_score(Y, PredictionB)
    Low, High = BootstrapMetricDifference(
        Y, PredictionA, PredictionB, roc_auc_score, Resamples
    )
    return {
        "ModelA": ModelA,
        "ModelB": ModelB,
        "Difference": Difference,
        "CILow": Low,
        "CIHigh": High,
        "CIExcludesZero": bool(Low > 0 or High < 0),
    }


def RunLevel(
    InputPath: Path,
    QCRule: str,
    BootstrapResamples: int,
    Jobs: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Refit and evaluate the complete model at one QC threshold."""

    Data = PrepareDataset(InputPath, QCRule)
    Estimates = FitBrainAgeModels(Data)
    Representations = BuildRepresentations(Data, Estimates)
    OrderedRids = Data.OrderedData["RID"].to_numpy()

    DiagnosisMetrics, DiagnosisPredictions = EvaluateDiagnosisTarget(
        "CN vs MCI+AD",
        Data.DiagnosisBinary,
        Data.Covariates,
        Representations,
        OrderedRids,
        BootstrapResamples,
        Jobs,
    )
    Rows: list[dict[str, object]] = []
    for _, Result in DiagnosisMetrics.iterrows():
        Rows.append(
            {
                "QCRule": QCRule,
                "Threshold": Data.QCThreshold,
                "N": len(Data.OrderedData),
                "NCN": len(Data.AgeCN),
                "NAD": int(Data.OrderedData["Diagnosis"].eq("AD").sum()),
                "BrainAgeMAE": Estimates.MAE,
                "BrainAgeR2": Estimates.R2,
                "Analysis": "Diagnosis incremental",
                "Target": "CN vs MCI+AD",
                "Model": Result["Model"],
                "Estimate": Result["DeltaAUC"],
                "CILow": Result["CILow"],
                "CIHigh": Result["CIHigh"],
                "CIExcludesZero": Result["CIExcludesZero"],
            }
        )

    Comparisons = []
    for ModelA, ModelB in [
        ("Regional gap", "Scalar gap"),
        ("Regional gap", "Hippocampal volume"),
    ]:
        Comparison = PairedDifference(
            Data.DiagnosisBinary,
            DiagnosisPredictions,
            ModelA,
            ModelB,
            BootstrapResamples,
        )
        Comparison.update({"QCRule": QCRule, "Target": "CN vs MCI+AD"})
        Comparisons.append(Comparison)

    CNADMask = Data.OrderedData["Diagnosis"].isin(["CN", "AD"]).to_numpy()
    CNADTarget = Data.OrderedData.loc[CNADMask, "Diagnosis"].eq("AD").astype(int).to_numpy()
    CNADRepresentations = {
        Name: Values[CNADMask]
        for Name, Values in Representations.items()
        if Name in ["Scalar gap", "Regional gap", "Hippocampal volume"]
    }
    _, CNADPredictions = EvaluateDiagnosisTarget(
        "CN vs AD",
        CNADTarget,
        Data.Covariates[CNADMask],
        CNADRepresentations,
        OrderedRids[CNADMask],
        BootstrapResamples,
        Jobs,
    )
    for ModelA, ModelB in [
        ("Regional gap", "Scalar gap"),
        ("Regional gap", "Hippocampal volume"),
    ]:
        Comparison = PairedDifference(
            CNADTarget,
            CNADPredictions,
            ModelA,
            ModelB,
            BootstrapResamples,
        )
        Comparison.update({"QCRule": QCRule, "Target": "CN vs AD"})
        Comparisons.append(Comparison)

    for Outcome in ["MMSE", "CDRSB"]:
        Complete = Data.OrderedData[Outcome].notna().to_numpy()
        Y = Data.OrderedData.loc[Complete, Outcome].to_numpy(dtype=float)
        Baseline = Data.Covariates[Complete]
        Stratification = Data.DiagnosisBinary[Complete]
        Folds = list(
            StratifiedKFold(n_splits=5, shuffle=True, random_state=42).split(
                np.zeros(len(Y)), Stratification
            )
        )
        BaselinePrediction = OutOfFoldPrediction(Baseline, Y, Folds, Jobs)
        BaselineR2 = r2_score(Y, BaselinePrediction)
        for ModelName in ["Scalar gap", "Regional gap"]:
            Prediction = OutOfFoldPrediction(
                np.column_stack([Baseline, Representations[ModelName][Complete]]),
                Y,
                Folds,
                Jobs,
            )
            Rows.append(
                {
                    "QCRule": QCRule,
                    "Threshold": Data.QCThreshold,
                    "N": len(Data.OrderedData),
                    "NCN": len(Data.AgeCN),
                "NAD": int(Data.OrderedData["Diagnosis"].eq("AD").sum()),
                    "BrainAgeMAE": Estimates.MAE,
                    "BrainAgeR2": Estimates.R2,
                    "Analysis": "Cognition incremental",
                    "Target": Outcome,
                    "Model": ModelName,
                    "Estimate": r2_score(Y, Prediction) - BaselineR2,
                    "CILow": np.nan,
                    "CIHigh": np.nan,
                    "CIExcludesZero": np.nan,
                }
            )

    return Rows, Comparisons


def Main() -> None:
    """Run all QC thresholds and write sensitivity result tables."""

    Arguments = ParseArguments()
    if Arguments.bootstrap_resamples < 100:
        raise ValueError("--bootstrap-resamples must be at least 100")
    if not Arguments.input.exists():
        raise FileNotFoundError(f"Input dataset not found: {Arguments.input}")

    ResultRows: list[dict[str, object]] = []
    ComparisonRows: list[dict[str, object]] = []
    for Index, QCRule in enumerate(QCRules, start=1):
        PrintProgress(f"QC sensitivity {Index}/{len(QCRules)}: {QCRule}")
        Rows, Comparisons = RunLevel(
            Arguments.input,
            QCRule,
            Arguments.bootstrap_resamples,
            Arguments.jobs,
        )
        ResultRows.extend(Rows)
        ComparisonRows.extend(Comparisons)

    Arguments.output_directory.mkdir(parents=True, exist_ok=True)
    ResultsPath = Arguments.output_directory / "QcSensitivityResults.csv"
    ComparisonsPath = Arguments.output_directory / "QcSensitivityHeadToHead.csv"
    pd.DataFrame(ResultRows).to_csv(ResultsPath, index=False, float_format=CsvFloatFormat)
    pd.DataFrame(ComparisonRows).to_csv(ComparisonsPath, index=False, float_format=CsvFloatFormat)
    PrintProgress(f"Wrote: {ResultsPath}")
    PrintProgress(f"Wrote: {ComparisonsPath}")


if __name__ == "__main__":
    try:
        Main()
    except Exception as Error:
        print(f"QC-sensitivity analysis failed: {Error}", file=sys.stderr)
        raise
