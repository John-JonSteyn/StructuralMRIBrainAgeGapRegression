"""Run the interim-data preparation workflow with visible progress timing."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


def ResolveRepositoryRoot() -> Path:
    """Resolve the repository root from this script location."""
    return Path(__file__).resolve().parents[2]


def FormatDuration(DurationSeconds: float) -> str:
    RoundedSeconds = int(round(DurationSeconds))
    Hours = RoundedSeconds // 3600
    Minutes = (RoundedSeconds % 3600) // 60
    Seconds = RoundedSeconds % 60
    return f"{Hours:02d}:{Minutes:02d}:{Seconds:02d}"


def PrintProgress(Message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {Message}", flush=True)


def RunPythonScript(ScriptPath: Path) -> None:
    """Run one Python script and stop the workflow if it fails."""
    Command = [sys.executable, str(ScriptPath)]
    StartedAt = datetime.now()

    print()
    PrintProgress(f"Starting: {ScriptPath.name}")
    print(f"Running: {' '.join(Command)}", flush=True)
    print("-" * 80, flush=True)

    subprocess.run(Command, check=True)

    DurationSeconds = (datetime.now() - StartedAt).total_seconds()
    PrintProgress(f"Finished: {ScriptPath.name} in {FormatDuration(DurationSeconds)}")


def Main() -> None:
    WorkflowStartedAt = datetime.now()
    RepositoryRoot = ResolveRepositoryRoot()
    DataPreparationDirectory = RepositoryRoot / "Source" / "DataPreparation"

    ScriptPaths = [
        DataPreparationDirectory / "InspectRawData.py",
        DataPreparationDirectory / "BuildImageManifest.py",
        DataPreparationDirectory / "BuildClinicalVisits.py",
        DataPreparationDirectory / "LinkImagesToClinicalVisits.py",
        DataPreparationDirectory / "SelectBaselineCohort.py",
    ]

    PrintProgress("Preparing interim data.")
    print(f"Repository root: {RepositoryRoot}", flush=True)
    print("Scripts to run:", flush=True)

    for ScriptPath in ScriptPaths:
        print(f"  - {ScriptPath}", flush=True)

    for ScriptPath in ScriptPaths:
        if not ScriptPath.exists():
            raise FileNotFoundError(f"Required script not found: {ScriptPath}")

        RunPythonScript(ScriptPath=ScriptPath)

    WorkflowDurationSeconds = (datetime.now() - WorkflowStartedAt).total_seconds()
    print()
    PrintProgress(f"Interim-data preparation complete in {FormatDuration(WorkflowDurationSeconds)}.")


if __name__ == "__main__":
    try:
        Main()
    except KeyboardInterrupt:
        print()
        PrintProgress("Stopped by user before completion.")
        sys.exit(130)
    except subprocess.CalledProcessError as Error:
        print()
        PrintProgress(f"Interim-data preparation failed with exit code {Error.returncode}.")
        sys.exit(Error.returncode)
    except Exception as Error:
        print()
        PrintProgress("Interim-data preparation failed.")
        print(str(Error), flush=True)
        sys.exit(1)
