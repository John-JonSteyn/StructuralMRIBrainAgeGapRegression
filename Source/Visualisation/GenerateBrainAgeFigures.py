"""Generate the four brain-age PNG artefacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, mean_absolute_error, r2_score


ProjectRoot = Path(__file__).resolve().parents[2]
DefaultResultsDirectory = ProjectRoot / "Data" / "Processed" / "Analysis" / "BrainAgeResults"
DefaultOutputDirectory = ProjectRoot / "Outputs" / "Figures" / "BrainAge"
DiagnosisOrder = ["CN", "MCI", "AD"]


def ParseArguments() -> argparse.Namespace:
    """Parse result and figure output directories."""

    Parser = argparse.ArgumentParser(description="Generate brain-age PNG figures.")
    Parser.add_argument("--results-directory", type=Path, default=DefaultResultsDirectory)
    Parser.add_argument("--output-directory", type=Path, default=DefaultOutputDirectory)
    return Parser.parse_args()


def SaveFigure(Figure: plt.Figure, OutputPath: Path) -> None:
    """Save one tightly cropped PNG; captions belong in the README, not the image."""

    Figure.savefig(OutputPath, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(Figure)
    print(f"Wrote: {OutputPath}")


def DemographicCharacteristics(Subjects: pd.DataFrame, OutputDirectory: Path) -> None:
    """Render final-cohort demographic characteristics."""

    Rows: list[list[str]] = []
    for Diagnosis in DiagnosisOrder:
        Group = Subjects.loc[Subjects["Diagnosis"].eq(Diagnosis)]
        FemaleN = int(Group["Sex"].astype(str).str.casefold().eq("female").sum())
        MaleN = int(Group["Sex"].astype(str).str.casefold().eq("male").sum())
        N = len(Group)
        Rows.append(
            [
                Diagnosis,
                str(N),
                f"{Group['Age'].mean():.1f} ({Group['Age'].std():.1f})",
                f"{FemaleN} ({100 * FemaleN / N:.1f}%)",
                f"{MaleN} ({100 * MaleN / N:.1f}%)",
                f"{Group['Education'].mean():.1f} ({Group['Education'].std():.1f})",
            ]
        )

    Figure, Axis = plt.subplots(figsize=(9.2, 2.0))
    Axis.axis("off")
    Table = Axis.table(
        cellText=Rows,
        colLabels=[
            "Diagnosis",
            "N",
            "Age, mean (SD)",
            "Female, n (%)",
            "Male, n (%)",
            "Education, mean (SD)",
        ],
        cellLoc="left",
        colLoc="left",
        loc="center",
        colWidths=[0.13, 0.07, 0.20, 0.18, 0.17, 0.25],
    )
    Table.auto_set_font_size(False)
    Table.set_fontsize(10)
    Table.scale(1.0, 1.45)
    for (Row, _), Cell in Table.get_celld().items():
        Cell.set_edgecolor("black")
        Cell.set_linewidth(0.8)
        if Row == 0:
            Cell.set_facecolor("#F2F2F2")
            Cell.set_text_props(weight="bold")
    SaveFigure(Figure, OutputDirectory / "table1_demographic_characteristics.png")


def PredictedVersusActual(Subjects: pd.DataFrame, OutputDirectory: Path) -> None:
    """Plot CN out-of-fold age estimates against chronological age."""

    CN = Subjects.loc[Subjects["Diagnosis"].eq("CN")]
    Actual = CN["Age"].to_numpy(dtype=float)
    Predicted = CN["PredictedBrainAge"].to_numpy(dtype=float)
    Gap = CN["BrainAgeGap"].to_numpy(dtype=float)
    MAE = mean_absolute_error(Actual, Predicted)
    R2 = r2_score(Actual, Predicted)

    Figure, Axis = plt.subplots(figsize=(6.2, 5.4))
    Axis.scatter(Actual, Predicted, alpha=0.72, s=34)
    Limits = [min(Actual.min(), Predicted.min()) - 1, max(Actual.max(), Predicted.max()) + 1]
    Axis.plot(Limits, Limits, linestyle="--", linewidth=1.1)
    Axis.set(
        xlim=Limits,
        ylim=Limits,
        xlabel="Chronological age, years",
        ylabel="Predicted brain age, years",
        title="Predicted vs actual age in CN participants",
    )
    Axis.text(
        0.05,
        0.95,
        f"MAE = {MAE:.2f} years\nR² = {R2:.3f}\nMean gap = {Gap.mean():+.2f} years",
        transform=Axis.transAxes,
        va="top",
    )
    SaveFigure(Figure, OutputDirectory / "figure1_predicted_vs_actual_age.png")


def GapDistribution(Subjects: pd.DataFrame, OutputDirectory: Path) -> None:
    """Plot scalar-gap density by diagnosis."""

    Figure, Axis = plt.subplots(figsize=(6.4, 4.8))
    for Diagnosis in DiagnosisOrder:
        Values = Subjects.loc[Subjects["Diagnosis"].eq(Diagnosis), "BrainAgeGap"]
        Axis.hist(Values, bins=20, density=True, alpha=0.5, label=Diagnosis)
    Axis.axvline(0, linestyle=":", linewidth=1.1)
    Axis.set(
        xlabel="Scalar brain-age gap, years",
        ylabel="Density",
        title="Brain-age gap distribution by diagnosis",
    )
    Axis.legend()
    SaveFigure(Figure, OutputDirectory / "figure2_gap_distribution_by_diagnosis.png")


def CalibrationCurves(Predictions: pd.DataFrame, OutputDirectory: Path) -> None:
    """Plot CN-versus-MCI/AD calibration curves."""

    Data = Predictions.loc[Predictions["Target"].eq("CN vs MCI+AD")]
    Y = Data["TargetValue"].to_numpy(dtype=int)
    Figure, Axis = plt.subplots(figsize=(6.4, 5.2))
    Axis.plot([0, 1], [0, 1], linestyle="--", linewidth=1.0, label="Ideal")
    for Column, Label in [
        ("Baseline", "Demographics"),
        ("Scalar gap", "Scalar gap"),
        ("Regional gap", "Regional gap"),
        ("Raw features", "Raw regional"),
    ]:
        Probability = Data[Column].to_numpy(dtype=float)
        Observed, Predicted = calibration_curve(
            Y, Probability, n_bins=10, strategy="quantile"
        )
        Brier = brier_score_loss(Y, Probability)
        Axis.plot(
            Predicted,
            Observed,
            marker="o",
            linewidth=1.5,
            label=f"{Label} (Brier {Brier:.4f})",
        )
    Axis.set(
        xlim=(0, 1),
        ylim=(0, 1),
        xlabel="Predicted probability",
        ylabel="Observed proportion",
        title="Calibration curves: CN vs MCI+AD",
    )
    Axis.legend()
    SaveFigure(Figure, OutputDirectory / "figure3_calibration_curves.png")


def Main() -> None:
    """Load model results and generate the four required PNG artefacts."""

    Arguments = ParseArguments()
    Required = {
        "subjects": Arguments.results_directory / "BrainAgeSubjectResults.csv",
        "predictions": Arguments.results_directory / "DiagnosisOutOfFoldPredictions.csv",
    }
    Missing = [str(PathValue) for PathValue in Required.values() if not PathValue.exists()]
    if Missing:
        raise FileNotFoundError("Missing result files:\n" + "\n".join(Missing))
    Arguments.output_directory.mkdir(parents=True, exist_ok=True)

    Subjects = pd.read_csv(Required["subjects"])
    Predictions = pd.read_csv(Required["predictions"])
    DemographicCharacteristics(Subjects, Arguments.output_directory)
    PredictedVersusActual(Subjects, Arguments.output_directory)
    GapDistribution(Subjects, Arguments.output_directory)
    CalibrationCurves(Predictions, Arguments.output_directory)


if __name__ == "__main__":
    try:
        Main()
    except Exception as Error:
        print(f"Figure generation failed: {Error}", file=sys.stderr)
        raise
