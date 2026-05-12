"""Run the interim-data preparation workflow.

Runs raw-data inspection, image manifest construction, clinical visit
construction, image-clinical linkage, and baseline cohort selection in sequence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def ResolveRepositoryRoot() -> Path:
    """Resolve the repository root from this script location."""
    return Path(__file__).resolve().parents[2]


def RunPythonScript(ScriptPath: Path) -> None:
    """Run one Python script and stop the workflow if it fails."""
    Command = [sys.executable, str(ScriptPath)]

    print()
    print(f"Running: {' '.join(Command)}")
    print("-" * 80)

    subprocess.run(Command, check=True)


def Main() -> None:
    RepositoryRoot = ResolveRepositoryRoot()
    DataPreparationDirectory = RepositoryRoot / "Source" / "DataPreparation"

    ScriptPaths = [
        DataPreparationDirectory / "InspectRawData.py",
        DataPreparationDirectory / "BuildImageManifest.py",
        DataPreparationDirectory / "BuildClinicalVisits.py",
        DataPreparationDirectory / "LinkImagesToClinicalVisits.py",
        DataPreparationDirectory / "SelectBaselineCohort.py",
    ]

    print("Preparing interim data")
    print(f"Repository root: {RepositoryRoot}")

    for ScriptPath in ScriptPaths:
        if not ScriptPath.exists():
            raise FileNotFoundError(f"Required script not found: {ScriptPath}")

        RunPythonScript(ScriptPath=ScriptPath)

    print()
    print("Interim-data preparation complete.")


if __name__ == "__main__":
    Main()