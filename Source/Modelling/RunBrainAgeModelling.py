"""Run the structural MRI brain-age analyses."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from BrainAgePipeline import (
    DefaultInputPath,
    DefaultOutputDirectory,
    FitBrainAgeModels,
    PrepareDataset,
    PrintProgress,
    WritePrimaryOutputs,
)
from ExploratoryAnalysis import WriteExploratoryOutputs


def ParseArguments() -> argparse.Namespace:
    """Parse modelling inputs, QC settings, and execution parameters."""

    Parser = argparse.ArgumentParser(
        description="Run the structural MRI brain-age analyses and write out-of-fold results."
    )
    Parser.add_argument("--input", type=Path, default=DefaultInputPath)
    Parser.add_argument("--output-directory", type=Path, default=DefaultOutputDirectory)
    Parser.add_argument(
        "--qc-rule",
        choices=["none", "p97.5", "p95", "median+3mad"],
        default="median+3mad",
    )
    Parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=9999,
        help="Paired percentile-bootstrap resamples; the primary setting is 9999.",
    )
    Parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel outer cross-validation jobs. Use -1 for all available processors.",
    )
    return Parser.parse_args()


def Main() -> None:
    """Execute exploratory and primary modelling and write all results."""

    Arguments = ParseArguments()
    if Arguments.bootstrap_resamples < 100:
        raise ValueError("--bootstrap-resamples must be at least 100")
    if not Arguments.input.exists():
        raise FileNotFoundError(f"Input dataset not found: {Arguments.input}")

    PrintProgress(f"Reading and QC-filtering: {Arguments.input}")
    Data = PrepareDataset(Arguments.input, Arguments.qc_rule)
    PrintProgress(
        f"Analysis cohort: {len(Data.OrderedData)} rows; "
        f"{len(Data.FeatureColumns)} features; {len(Data.RegionalGroups)} regions"
    )

    PrintProgress("Running exploratory fixed-alpha and bias-correction analyses")
    ExploratoryOutputs = WriteExploratoryOutputs(Data, Arguments.output_directory)

    PrintProgress("Fitting primary RidgeCV brain-age models")
    Estimates = FitBrainAgeModels(Data)
    PrintProgress(
        f"CN out-of-fold brain-age performance: MAE={Estimates.MAE:.2f} years; "
        f"R2={Estimates.R2:.3f}"
    )
    PrimaryOutputs = WritePrimaryOutputs(
        Data,
        Estimates,
        Arguments.output_directory,
        Arguments.bootstrap_resamples,
        Arguments.jobs,
    )
    PrintProgress("Brain-age analysis complete")
    for Name, OutputPath in ExploratoryOutputs.items():
        print(f"  {Name}: {OutputPath}")
    for Name, OutputPath in PrimaryOutputs.items():
        print(f"  {Name}: {OutputPath}")


if __name__ == "__main__":
    try:
        Main()
    except Exception as Error:
        print(f"Brain-age analysis failed: {Error}", file=sys.stderr)
        raise