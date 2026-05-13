"""Run FastSurfer on one selected test scan.

Reads the FastSurfer input manifest, selects one pending scan, removes any
incomplete previous output for that scan, and runs FastSurfer once.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


FastSurferCpuImageName = "deepmi/fastsurfer:cpu-v2.4.2"
FastSurferGpuImageName = "deepmi/fastsurfer:cuda-v2.4.2"
CudaTestImageName = "nvidia/cuda:12.4.1-base-ubuntu22.04"

FastSurferInputManifestPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferInputManifest.csv"
FastSurferTestRunSummaryPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferTestScanSummary.csv"
FastSurferTestRunMarkdownSummaryPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferTestScanSummary.md"

DataDirectory = Path("Data")
FastSurferOutputRootDirectory = Path("Data") / "Processed" / "FastSurfer"
FreeSurferLicenseDirectory = Path("LocalOnly") / "FreeSurfer"
FreeSurferLicensePath = FreeSurferLicenseDirectory / "license.txt"

DockerDataMountPath = "/data"
DockerOutputMountPath = "/output"
DockerLicenseMountPath = "/fs_license"
DockerLicensePath = "/fs_license/license.txt"

FastSurferThreadCount = "4"


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def NormaliseText(TextValue: object) -> str:
    return str(TextValue).strip() if TextValue is not None else ""


def ReadCsvRows(CsvFilePath: Path) -> list[dict[str, str]]:
    """Read a CSV file into dictionaries, falling back to latin-1 when required."""
    try:
        with CsvFilePath.open("r", newline="", encoding="utf-8-sig") as CsvFile:
            CsvReader = csv.DictReader(CsvFile)
            return [dict(CsvRow) for CsvRow in CsvReader]

    except UnicodeDecodeError:
        with CsvFilePath.open("r", newline="", encoding="latin-1") as CsvFile:
            CsvReader = csv.DictReader(CsvFile)
            return [dict(CsvRow) for CsvRow in CsvReader]


def WriteCsv(OutputFilePath: Path, FieldNames: list[str], DataRows: list[dict[str, object]]) -> None:
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", newline="", encoding="utf-8") as OutputFile:
        CsvWriter = csv.DictWriter(OutputFile, fieldnames=FieldNames, extrasaction="ignore")
        CsvWriter.writeheader()

        for DataRow in DataRows:
            CsvWriter.writerow(DataRow)


def ValidateRequiredPaths() -> None:
    """Check that Docker inputs required for the test run exist."""
    if not FastSurferInputManifestPath.exists():
        raise FileNotFoundError(f"FastSurfer input manifest not found: {FastSurferInputManifestPath}")

    if not DataDirectory.exists():
        raise FileNotFoundError(f"Data directory not found: {DataDirectory}")

    if not FreeSurferLicensePath.exists():
        raise FileNotFoundError(f"FreeSurfer license file not found: {FreeSurferLicensePath}")

    if not FreeSurferLicensePath.is_file():
        raise FileNotFoundError(f"FreeSurfer license path is not a file: {FreeSurferLicensePath}")

    if FreeSurferLicensePath.stat().st_size == 0:
        raise RuntimeError(f"FreeSurfer license file is empty: {FreeSurferLicensePath}")


def SelectTestScanRow(FastSurferInputRows: list[dict[str, str]]) -> dict[str, str]:
    """Select the first pending scan row from the FastSurfer input manifest."""
    for FastSurferInputRow in FastSurferInputRows:
        ProcessingStatus = NormaliseText(FastSurferInputRow.get("ProcessingStatus", ""))

        if ProcessingStatus == "Pending":
            return FastSurferInputRow

    raise RuntimeError("No pending FastSurfer input rows were found.")


def ConvertToDockerVolumePath(HostPath: Path) -> str:
    """Convert a host path to an absolute path string for Docker volume mounting."""
    return str(HostPath.resolve())


def RunCommand(Command: list[str]) -> None:
    """Run a command and stop if it fails."""
    print()
    print(f"Running: {' '.join(Command)}")
    print("-" * 80)

    subprocess.run(Command, check=True)


def CheckDockerAvailable() -> None:
    """Check that Docker is available before running FastSurfer."""
    RunCommand(["docker", "--version"])


def DetectDockerGpuAvailable() -> bool:
    """Check whether Docker can run a CUDA GPU test container."""
    GpuTestCommand = [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        CudaTestImageName,
        "nvidia-smi",
    ]

    print()
    print("Checking Docker GPU availability...")
    print(f"Running: {' '.join(GpuTestCommand)}")
    print("-" * 80)

    try:
        subprocess.run(
            GpuTestCommand,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Docker GPU available: True")
        return True
    except FileNotFoundError:
        print("Docker GPU available: False")
        return False
    except subprocess.CalledProcessError:
        print("Docker GPU available: False")
        return False


def GetSubjectOutputDirectory(FastSurferSubjectId: str) -> Path:
    """Return the local FastSurfer output directory for one subject."""
    return FastSurferOutputRootDirectory / FastSurferSubjectId


def FastSurferStatsExist(FastSurferSubjectId: str) -> bool:
    """Check whether the FastSurfer stats directory contains stats files."""
    StatsDirectory = GetSubjectOutputDirectory(FastSurferSubjectId) / "stats"

    return StatsDirectory.exists() and any(StatsDirectory.glob("*.stats"))


def PrepareSubjectOutputDirectoryForRerun(FastSurferSubjectId: str) -> None:
    """Remove an incomplete previous FastSurfer output directory for the selected subject."""
    SubjectOutputDirectory = GetSubjectOutputDirectory(FastSurferSubjectId)

    if not SubjectOutputDirectory.exists():
        return

    if FastSurferStatsExist(FastSurferSubjectId):
        raise RuntimeError(
            "Selected test scan already has completed FastSurfer stats output. "
            "Rerun PrepareFastSurferInputs.py to refresh ProcessingStatus before selecting another pending scan."
        )

    print()
    print(f"Removing incomplete previous FastSurfer output: {SubjectOutputDirectory}")
    shutil.rmtree(SubjectOutputDirectory)


def BuildDockerCommand(TestScanRow: dict[str, str], UseGpu: bool) -> list[str]:
    """Build the Docker command for one FastSurfer scan."""
    FastSurferSubjectId = NormaliseText(TestScanRow.get("FastSurferSubjectId", ""))
    ContainerT1Path = NormaliseText(TestScanRow.get("ContainerT1Path", ""))

    if not FastSurferSubjectId:
        raise RuntimeError("Selected test scan row has no FastSurferSubjectId.")

    if not ContainerT1Path:
        raise RuntimeError("Selected test scan row has no ContainerT1Path.")

    DockerCommand = [
        "docker",
        "run",
        "--rm",
        "--user",
        "root",
    ]

    if UseGpu:
        DockerCommand.extend(["--gpus", "all"])

    DockerCommand.extend(
        [
            "-v",
            f"{ConvertToDockerVolumePath(DataDirectory)}:{DockerDataMountPath}",
            "-v",
            f"{ConvertToDockerVolumePath(FastSurferOutputRootDirectory)}:{DockerOutputMountPath}",
            "-v",
            f"{ConvertToDockerVolumePath(FreeSurferLicenseDirectory)}:{DockerLicenseMountPath}",
            FastSurferGpuImageName if UseGpu else FastSurferCpuImageName,
            "--fs_license",
            DockerLicensePath,
            "--t1",
            ContainerT1Path,
            "--sid",
            FastSurferSubjectId,
            "--sd",
            DockerOutputMountPath,
            "--threads",
            FastSurferThreadCount,
            "--3T",
            "--allow_root",
        ]
    )

    return DockerCommand


def BuildSummaryRow(
    TestScanRow: dict[str, str],
    RunStatus: str,
    UseGpu: bool,
    FastSurferImageName: str,
    ErrorMessage: str = "",
) -> dict[str, object]:
    """Build one summary row for the test scan run."""
    FastSurferSubjectId = NormaliseText(TestScanRow.get("FastSurferSubjectId", ""))

    return {
        "GeneratedAt": datetime.now().isoformat(timespec="seconds"),
        "RunStatus": RunStatus,
        "UseGpu": UseGpu,
        "FastSurferImageName": FastSurferImageName,
        "RID": TestScanRow.get("RID", ""),
        "SubjectId": TestScanRow.get("SubjectId", ""),
        "ImageId": TestScanRow.get("ImageId", ""),
        "Diagnosis3Class": TestScanRow.get("Diagnosis3Class", ""),
        "FastSurferSubjectId": FastSurferSubjectId,
        "ContainerT1Path": TestScanRow.get("ContainerT1Path", ""),
        "FastSurferOutputDirectory": str(GetSubjectOutputDirectory(FastSurferSubjectId)),
        "StatsFilesFound": FastSurferStatsExist(FastSurferSubjectId),
        "ErrorMessage": ErrorMessage,
    }


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRow: dict[str, object]) -> None:
    """Write a brief Markdown summary for the test scan run."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# FastSurfer Test Scan Summary\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for FieldName, FieldValue in SummaryRow.items():
            OutputFile.write(f"| {FieldName} | {FieldValue} |\n")


def WriteTestRunSummary(SummaryRow: dict[str, object]) -> None:
    """Write CSV and Markdown summaries for the test scan run."""
    FieldNames = [
        "GeneratedAt",
        "RunStatus",
        "UseGpu",
        "FastSurferImageName",
        "RID",
        "SubjectId",
        "ImageId",
        "Diagnosis3Class",
        "FastSurferSubjectId",
        "ContainerT1Path",
        "FastSurferOutputDirectory",
        "StatsFilesFound",
        "ErrorMessage",
    ]

    WriteCsv(
        OutputFilePath=FastSurferTestRunSummaryPath,
        FieldNames=FieldNames,
        DataRows=[SummaryRow],
    )

    WriteMarkdownSummary(
        OutputFilePath=FastSurferTestRunMarkdownSummaryPath,
        SummaryRow=SummaryRow,
    )


def Main() -> None:
    ValidateRequiredPaths()
    EnsureDirectory(FastSurferOutputRootDirectory)

    FastSurferInputRows = ReadCsvRows(FastSurferInputManifestPath)
    TestScanRow = SelectTestScanRow(FastSurferInputRows)

    FastSurferSubjectId = NormaliseText(TestScanRow.get("FastSurferSubjectId", ""))

    if not FastSurferSubjectId:
        raise RuntimeError("Selected test scan row has no FastSurferSubjectId.")

    PrepareSubjectOutputDirectoryForRerun(FastSurferSubjectId)

    CheckDockerAvailable()
    UseGpu = DetectDockerGpuAvailable()
    FastSurferImageName = FastSurferGpuImageName if UseGpu else FastSurferCpuImageName

    DockerCommand = BuildDockerCommand(
        TestScanRow=TestScanRow,
        UseGpu=UseGpu,
    )

    try:
        RunCommand(DockerCommand)
    except subprocess.CalledProcessError as Error:
        SummaryRow = BuildSummaryRow(
            TestScanRow=TestScanRow,
            RunStatus="Failed",
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
            ErrorMessage=f"Docker command failed with exit code {Error.returncode}.",
        )
        WriteTestRunSummary(SummaryRow)
        raise

    if not FastSurferStatsExist(FastSurferSubjectId):
        SummaryRow = BuildSummaryRow(
            TestScanRow=TestScanRow,
            RunStatus="CompletedButStatsMissing",
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
            ErrorMessage="FastSurfer command finished, but no stats files were found.",
        )
        WriteTestRunSummary(SummaryRow)
        raise RuntimeError("FastSurfer command finished, but no stats files were found.")

    SummaryRow = BuildSummaryRow(
        TestScanRow=TestScanRow,
        RunStatus="Complete",
        UseGpu=UseGpu,
        FastSurferImageName=FastSurferImageName,
    )
    WriteTestRunSummary(SummaryRow)

    print()
    print("FastSurfer test scan complete.")
    print(f"Used GPU: {UseGpu}")
    print(f"FastSurfer image: {FastSurferImageName}")
    print(f"Subject output: {GetSubjectOutputDirectory(FastSurferSubjectId)}")
    print(f"Summary: {FastSurferTestRunMarkdownSummaryPath}")


if __name__ == "__main__":
    try:
        Main()
    except Exception as Error:
        print()
        print("FastSurfer test scan failed.")
        print(str(Error))
        sys.exit(1)