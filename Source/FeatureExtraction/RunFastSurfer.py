"""Run FastSurfer for the selected cohort, prioritising AD and CN.

Reads the FastSurfer input manifest, builds a worklist of non-complete scans,
runs AD and CN before MCI, removes incomplete outputs, and writes progress
summaries after each scan.
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
FastSurferRunLogPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferRunLog.csv"
FastSurferRunSummaryPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferRunSummary.csv"
FastSurferRunMarkdownSummaryPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferRunSummary.md"
FastSurferWorklistPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferCurrentWorklist.csv"

DataDirectory = Path("Data")
FastSurferOutputRootDirectory = Path("Data") / "Processed" / "FastSurfer"
FreeSurferLicenseDirectory = Path("LocalOnly") / "FreeSurfer"
FreeSurferLicensePath = FreeSurferLicenseDirectory / "license.txt"

DockerDataMountPath = "/data"
DockerOutputMountPath = "/output"
DockerLicenseMountPath = "/fs_license"
DockerLicensePath = "/fs_license/license.txt"

FastSurferThreadCount = "4"

RequiredStatsFileNames = [
    "aseg.stats",
    "brainvol.stats",
    "lh.aparc.DKTatlas.mapped.stats",
    "rh.aparc.DKTatlas.mapped.stats",
    "wmparc.DKTatlas.mapped.stats",
]


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
    """Check that required local inputs exist before running FastSurfer."""
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


def GetStatsDirectory(FastSurferSubjectId: str) -> Path:
    """Return the stats directory for one FastSurfer subject."""
    return GetSubjectOutputDirectory(FastSurferSubjectId) / "stats"


def GetMissingRequiredStatsFiles(FastSurferSubjectId: str) -> list[str]:
    """List required stats files that are missing for one subject."""
    StatsDirectory = GetStatsDirectory(FastSurferSubjectId)

    MissingStatsFileNames: list[str] = []

    for RequiredStatsFileName in RequiredStatsFileNames:
        RequiredStatsFilePath = StatsDirectory / RequiredStatsFileName

        if not RequiredStatsFilePath.exists():
            MissingStatsFileNames.append(RequiredStatsFileName)

    return MissingStatsFileNames


def FastSurferOutputIsComplete(FastSurferSubjectId: str) -> bool:
    """Check whether all required FastSurfer stats files exist."""
    return len(GetMissingRequiredStatsFiles(FastSurferSubjectId)) == 0


def GetProcessingStatus(FastSurferSubjectId: str) -> str:
    """Return Complete, Incomplete, or NotStarted for one subject."""
    SubjectOutputDirectory = GetSubjectOutputDirectory(FastSurferSubjectId)

    if FastSurferOutputIsComplete(FastSurferSubjectId):
        return "Complete"

    if SubjectOutputDirectory.exists():
        return "Incomplete"

    return "NotStarted"


def GetDiagnosisPriority(Diagnosis3Class: str) -> int:
    """Return processing priority by diagnosis."""
    Diagnosis3Class = NormaliseText(Diagnosis3Class)

    if Diagnosis3Class == "AD":
        return 1

    if Diagnosis3Class == "CN":
        return 2

    if Diagnosis3Class == "MCI":
        return 3

    return 4


def RemoveIncompleteSubjectOutput(FastSurferSubjectId: str) -> bool:
    """Remove an incomplete previous FastSurfer output directory."""
    SubjectOutputDirectory = GetSubjectOutputDirectory(FastSurferSubjectId)

    if not SubjectOutputDirectory.exists():
        return False

    if FastSurferOutputIsComplete(FastSurferSubjectId):
        return False

    print()
    print(f"Removing incomplete previous FastSurfer output: {SubjectOutputDirectory}")
    shutil.rmtree(SubjectOutputDirectory)

    return True


def BuildDockerCommand(FastSurferInputRow: dict[str, str], UseGpu: bool) -> list[str]:
    """Build the Docker command for one FastSurfer scan."""
    FastSurferSubjectId = NormaliseText(FastSurferInputRow.get("FastSurferSubjectId", ""))
    ContainerT1Path = NormaliseText(FastSurferInputRow.get("ContainerT1Path", ""))

    if not FastSurferSubjectId:
        raise RuntimeError("FastSurfer input row has no FastSurferSubjectId.")

    if not ContainerT1Path:
        raise RuntimeError("FastSurfer input row has no ContainerT1Path.")

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


def SecondsToDurationText(DurationSeconds: float) -> str:
    """Convert elapsed seconds into HH:MM:SS text."""
    RoundedSeconds = int(round(DurationSeconds))
    Hours = RoundedSeconds // 3600
    Minutes = (RoundedSeconds % 3600) // 60
    Seconds = RoundedSeconds % 60

    return f"{Hours:02d}:{Minutes:02d}:{Seconds:02d}"


def BuildRunLogRow(
    FastSurferInputRow: dict[str, str],
    RunStatus: str,
    UseGpu: bool,
    FastSurferImageName: str,
    StartTime: datetime,
    EndTime: datetime,
    RemovedIncompleteOutput: bool,
    ErrorMessage: str = "",
) -> dict[str, object]:
    """Build one run-log row for one FastSurfer subject."""
    FastSurferSubjectId = NormaliseText(FastSurferInputRow.get("FastSurferSubjectId", ""))
    DurationSeconds = (EndTime - StartTime).total_seconds()
    MissingRequiredStatsFiles = GetMissingRequiredStatsFiles(FastSurferSubjectId)

    return {
        "StartedAt": StartTime.isoformat(timespec="seconds"),
        "EndedAt": EndTime.isoformat(timespec="seconds"),
        "DurationSeconds": round(DurationSeconds, 3),
        "Duration": SecondsToDurationText(DurationSeconds),
        "RunStatus": RunStatus,
        "UseGpu": UseGpu,
        "FastSurferImageName": FastSurferImageName,
        "RID": FastSurferInputRow.get("RID", ""),
        "SubjectId": FastSurferInputRow.get("SubjectId", ""),
        "ImageId": FastSurferInputRow.get("ImageId", ""),
        "Diagnosis3Class": FastSurferInputRow.get("Diagnosis3Class", ""),
        "FastSurferSubjectId": FastSurferSubjectId,
        "ContainerT1Path": FastSurferInputRow.get("ContainerT1Path", ""),
        "FastSurferOutputDirectory": str(GetSubjectOutputDirectory(FastSurferSubjectId)),
        "RemovedIncompleteOutput": RemovedIncompleteOutput,
        "RequiredStatsFilesFound": len(MissingRequiredStatsFiles) == 0,
        "MissingRequiredStatsFiles": "; ".join(MissingRequiredStatsFiles),
        "ErrorMessage": ErrorMessage,
    }


def GetRunLogFieldNames() -> list[str]:
    """Return the CSV schema for the FastSurfer run log."""
    return [
        "StartedAt",
        "EndedAt",
        "DurationSeconds",
        "Duration",
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
        "RemovedIncompleteOutput",
        "RequiredStatsFilesFound",
        "MissingRequiredStatsFiles",
        "ErrorMessage",
    ]


def AppendRunLogRow(RunLogRow: dict[str, object]) -> None:
    """Append one row to the persistent FastSurfer run log."""
    EnsureDirectory(FastSurferRunLogPath.parent)

    FileAlreadyExists = FastSurferRunLogPath.exists()

    with FastSurferRunLogPath.open("a", newline="", encoding="utf-8") as OutputFile:
        CsvWriter = csv.DictWriter(OutputFile, fieldnames=GetRunLogFieldNames(), extrasaction="ignore")

        if not FileAlreadyExists:
            CsvWriter.writeheader()

        CsvWriter.writerow(RunLogRow)


def CountRowsByValue(DataRows: list[dict[str, object]], FieldName: str) -> dict[str, int]:
    """Count row occurrences by one field."""
    ValueCounts: dict[str, int] = {}

    for DataRow in DataRows:
        FieldValue = NormaliseText(DataRow.get(FieldName, "")) or "Missing"
        ValueCounts[FieldValue] = ValueCounts.get(FieldValue, 0) + 1

    return ValueCounts


def FormatValueCounts(ValueCounts: dict[str, int]) -> str:
    """Format value counts as a compact semicolon-separated string."""
    return "; ".join(f"{Value}: {Count}" for Value, Count in sorted(ValueCounts.items()))


def BuildStatusRows(FastSurferInputRows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Build one current processing-status row per manifest row."""
    StatusRows: list[dict[str, object]] = []

    for RowIndex, FastSurferInputRow in enumerate(FastSurferInputRows, start=1):
        FastSurferSubjectId = NormaliseText(FastSurferInputRow.get("FastSurferSubjectId", ""))
        ProcessingStatus = GetProcessingStatus(FastSurferSubjectId)

        StatusRows.append(
            {
                "ManifestRowNumber": RowIndex,
                "RID": FastSurferInputRow.get("RID", ""),
                "SubjectId": FastSurferInputRow.get("SubjectId", ""),
                "ImageId": FastSurferInputRow.get("ImageId", ""),
                "Diagnosis3Class": FastSurferInputRow.get("Diagnosis3Class", ""),
                "FastSurferSubjectId": FastSurferSubjectId,
                "ProcessingStatus": ProcessingStatus,
            }
        )

    return StatusRows


def BuildWorkRows(FastSurferInputRows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Build prioritised work rows for non-complete scans only."""
    WorkRows: list[dict[str, object]] = []

    for RowIndex, FastSurferInputRow in enumerate(FastSurferInputRows, start=1):
        FastSurferSubjectId = NormaliseText(FastSurferInputRow.get("FastSurferSubjectId", ""))
        ProcessingStatus = GetProcessingStatus(FastSurferSubjectId)

        if ProcessingStatus == "Complete":
            continue

        WorkRows.append(
            {
                "ManifestRowNumber": RowIndex,
                "ProcessingStatus": ProcessingStatus,
                "DiagnosisPriority": GetDiagnosisPriority(FastSurferInputRow.get("Diagnosis3Class", "")),
                "FastSurferInputRow": FastSurferInputRow,
            }
        )

    WorkRows.sort(
        key=lambda WorkRow: (
            WorkRow["DiagnosisPriority"],
            WorkRow["ManifestRowNumber"],
        )
    )

    return WorkRows


def BuildWorklistOutputRows(WorkRows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build CSV rows for the current prioritised worklist."""
    WorklistOutputRows: list[dict[str, object]] = []

    for WorkIndex, WorkRow in enumerate(WorkRows, start=1):
        FastSurferInputRow = WorkRow["FastSurferInputRow"]

        WorklistOutputRows.append(
            {
                "WorklistRowNumber": WorkIndex,
                "ManifestRowNumber": WorkRow["ManifestRowNumber"],
                "ProcessingStatus": WorkRow["ProcessingStatus"],
                "RID": FastSurferInputRow.get("RID", ""),
                "SubjectId": FastSurferInputRow.get("SubjectId", ""),
                "ImageId": FastSurferInputRow.get("ImageId", ""),
                "Diagnosis3Class": FastSurferInputRow.get("Diagnosis3Class", ""),
                "FastSurferSubjectId": FastSurferInputRow.get("FastSurferSubjectId", ""),
                "ContainerT1Path": FastSurferInputRow.get("ContainerT1Path", ""),
            }
        )

    return WorklistOutputRows


def WriteCurrentWorklist(WorkRows: list[dict[str, object]]) -> None:
    """Write the current prioritised FastSurfer worklist."""
    WorklistOutputRows = BuildWorklistOutputRows(WorkRows)

    WriteCsv(
        OutputFilePath=FastSurferWorklistPath,
        FieldNames=[
            "WorklistRowNumber",
            "ManifestRowNumber",
            "ProcessingStatus",
            "RID",
            "SubjectId",
            "ImageId",
            "Diagnosis3Class",
            "FastSurferSubjectId",
            "ContainerT1Path",
        ],
        DataRows=WorklistOutputRows,
    )


def GetDiagnosisStatusCounts(StatusRows: list[dict[str, object]]) -> dict[str, int]:
    """Count rows by diagnosis and processing status."""
    DiagnosisStatusCounts: dict[str, int] = {}

    for StatusRow in StatusRows:
        Diagnosis3Class = NormaliseText(StatusRow.get("Diagnosis3Class", "")) or "Missing"
        ProcessingStatus = NormaliseText(StatusRow.get("ProcessingStatus", "")) or "Missing"
        CountKey = f"{Diagnosis3Class}, {ProcessingStatus}"
        DiagnosisStatusCounts[CountKey] = DiagnosisStatusCounts.get(CountKey, 0) + 1

    return DiagnosisStatusCounts


def BuildCurrentSummaryRows(
    FastSurferInputRows: list[dict[str, str]],
    WorkRows: list[dict[str, object]],
    UseGpu: bool,
    FastSurferImageName: str,
    RunLogRowsFromThisInvocation: list[dict[str, object]],
    WorkflowStartedAt: datetime,
) -> list[dict[str, object]]:
    """Build summary rows for the full FastSurfer run."""
    StatusRows = BuildStatusRows(FastSurferInputRows)

    CompletedOutputCount = sum(1 for StatusRow in StatusRows if StatusRow["ProcessingStatus"] == "Complete")
    IncompleteOutputCount = sum(1 for StatusRow in StatusRows if StatusRow["ProcessingStatus"] == "Incomplete")
    NotStartedCount = sum(1 for StatusRow in StatusRows if StatusRow["ProcessingStatus"] == "NotStarted")

    WorkflowEndedAt = datetime.now()
    WorkflowDurationSeconds = (WorkflowEndedAt - WorkflowStartedAt).total_seconds()

    SuccessfulRunDurations = [
        float(RunLogRow["DurationSeconds"])
        for RunLogRow in RunLogRowsFromThisInvocation
        if RunLogRow.get("RunStatus") == "Complete"
    ]

    MeanSuccessfulRunDurationSeconds = (
        sum(SuccessfulRunDurations) / len(SuccessfulRunDurations)
        if SuccessfulRunDurations
        else 0
    )

    return [
        {"Metric": "GeneratedAt", "Value": WorkflowEndedAt.isoformat(timespec="seconds")},
        {"Metric": "WorkflowDuration", "Value": SecondsToDurationText(WorkflowDurationSeconds)},
        {"Metric": "ManifestRows", "Value": len(FastSurferInputRows)},
        {"Metric": "CompletedOutputCount", "Value": CompletedOutputCount},
        {"Metric": "IncompleteOutputCount", "Value": IncompleteOutputCount},
        {"Metric": "NotStartedCount", "Value": NotStartedCount},
        {"Metric": "WorklistRowsAtStart", "Value": len(WorkRows)},
        {"Metric": "UseGpu", "Value": UseGpu},
        {"Metric": "FastSurferImageName", "Value": FastSurferImageName},
        {"Metric": "RunsAttemptedThisInvocation", "Value": len(RunLogRowsFromThisInvocation)},
        {
            "Metric": "RunStatusCountsThisInvocation",
            "Value": FormatValueCounts(CountRowsByValue(RunLogRowsFromThisInvocation, "RunStatus")),
        },
        {
            "Metric": "MeanSuccessfulRunDurationThisInvocation",
            "Value": SecondsToDurationText(MeanSuccessfulRunDurationSeconds),
        },
        {
            "Metric": "Diagnosis3ClassCounts",
            "Value": FormatValueCounts(CountRowsByValue(FastSurferInputRows, "Diagnosis3Class")),
        },
        {
            "Metric": "DiagnosisStatusCounts",
            "Value": FormatValueCounts(GetDiagnosisStatusCounts(StatusRows)),
        },
    ]


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRows: list[dict[str, object]]) -> None:
    """Write a brief Markdown summary for the full FastSurfer run."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# FastSurfer Full Run Summary\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def WriteRunSummary(
    FastSurferInputRows: list[dict[str, str]],
    WorkRows: list[dict[str, object]],
    UseGpu: bool,
    FastSurferImageName: str,
    RunLogRowsFromThisInvocation: list[dict[str, object]],
    WorkflowStartedAt: datetime,
) -> None:
    """Write CSV and Markdown summaries for the full FastSurfer run."""
    SummaryRows = BuildCurrentSummaryRows(
        FastSurferInputRows=FastSurferInputRows,
        WorkRows=WorkRows,
        UseGpu=UseGpu,
        FastSurferImageName=FastSurferImageName,
        RunLogRowsFromThisInvocation=RunLogRowsFromThisInvocation,
        WorkflowStartedAt=WorkflowStartedAt,
    )

    WriteCsv(
        OutputFilePath=FastSurferRunSummaryPath,
        FieldNames=["Metric", "Value"],
        DataRows=SummaryRows,
    )

    WriteMarkdownSummary(
        OutputFilePath=FastSurferRunMarkdownSummaryPath,
        SummaryRows=SummaryRows,
    )


def RunOneFastSurferSubject(
    FastSurferInputRow: dict[str, str],
    UseGpu: bool,
    FastSurferImageName: str,
) -> dict[str, object]:
    """Run FastSurfer for one subject and return the run-log row."""
    FastSurferSubjectId = NormaliseText(FastSurferInputRow.get("FastSurferSubjectId", ""))

    if not FastSurferSubjectId:
        raise RuntimeError("FastSurfer input row has no FastSurferSubjectId.")

    StartTime = datetime.now()

    if FastSurferOutputIsComplete(FastSurferSubjectId):
        EndTime = datetime.now()

        return BuildRunLogRow(
            FastSurferInputRow=FastSurferInputRow,
            RunStatus="SkippedComplete",
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
            StartTime=StartTime,
            EndTime=EndTime,
            RemovedIncompleteOutput=False,
        )

    RemovedIncompleteOutput = RemoveIncompleteSubjectOutput(FastSurferSubjectId)
    DockerCommand = BuildDockerCommand(
        FastSurferInputRow=FastSurferInputRow,
        UseGpu=UseGpu,
    )

    try:
        RunCommand(DockerCommand)

    except subprocess.CalledProcessError as Error:
        EndTime = datetime.now()

        return BuildRunLogRow(
            FastSurferInputRow=FastSurferInputRow,
            RunStatus="Failed",
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
            StartTime=StartTime,
            EndTime=EndTime,
            RemovedIncompleteOutput=RemovedIncompleteOutput,
            ErrorMessage=f"Docker command failed with exit code {Error.returncode}.",
        )

    EndTime = datetime.now()

    if not FastSurferOutputIsComplete(FastSurferSubjectId):
        return BuildRunLogRow(
            FastSurferInputRow=FastSurferInputRow,
            RunStatus="CompletedButRequiredStatsMissing",
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
            StartTime=StartTime,
            EndTime=EndTime,
            RemovedIncompleteOutput=RemovedIncompleteOutput,
            ErrorMessage="FastSurfer command finished, but required stats files were missing.",
        )

    return BuildRunLogRow(
        FastSurferInputRow=FastSurferInputRow,
        RunStatus="Complete",
        UseGpu=UseGpu,
        FastSurferImageName=FastSurferImageName,
        StartTime=StartTime,
        EndTime=EndTime,
        RemovedIncompleteOutput=RemovedIncompleteOutput,
    )


def PrintStartingStatus(
    FastSurferInputRows: list[dict[str, str]],
    WorkRows: list[dict[str, object]],
    UseGpu: bool,
    FastSurferImageName: str,
) -> None:
    """Print the current FastSurfer processing status."""
    StatusRows = BuildStatusRows(FastSurferInputRows)
    StatusCounts = CountRowsByValue(StatusRows, "ProcessingStatus")
    DiagnosisStatusCounts = GetDiagnosisStatusCounts(StatusRows)

    print()
    print("Starting prioritised FastSurfer run")
    print("Priority order: AD -> CN -> MCI")
    print(f"Manifest rows: {len(FastSurferInputRows)}")
    print(f"Complete: {StatusCounts.get('Complete', 0)}")
    print(f"Incomplete: {StatusCounts.get('Incomplete', 0)}")
    print(f"Not started: {StatusCounts.get('NotStarted', 0)}")
    print(f"Subjects still requiring processing: {len(WorkRows)}")
    print(f"Used GPU: {UseGpu}")
    print(f"FastSurfer image: {FastSurferImageName}")

    print()
    print("Diagnosis/status counts:")
    for CountKey, CountValue in sorted(DiagnosisStatusCounts.items()):
        print(f"  {CountKey}: {CountValue}")

    if WorkRows:
        FirstWorkRow = WorkRows[0]
        FirstFastSurferInputRow = FirstWorkRow["FastSurferInputRow"]

        print()
        print("First subject to process:")
        print(f"  Worklist row: 1 of {len(WorkRows)}")
        print(f"  Manifest row: {FirstWorkRow['ManifestRowNumber']}")
        print(f"  Diagnosis: {FirstFastSurferInputRow.get('Diagnosis3Class', '')}")
        print(f"  FastSurfer subject: {FirstFastSurferInputRow.get('FastSurferSubjectId', '')}")

    print()


def Main() -> None:
    ValidateRequiredPaths()
    EnsureDirectory(FastSurferOutputRootDirectory)

    WorkflowStartedAt = datetime.now()
    FastSurferInputRows = ReadCsvRows(FastSurferInputManifestPath)
    WorkRows = BuildWorkRows(FastSurferInputRows)
    WriteCurrentWorklist(WorkRows)

    CheckDockerAvailable()
    UseGpu = DetectDockerGpuAvailable()
    FastSurferImageName = FastSurferGpuImageName if UseGpu else FastSurferCpuImageName

    PrintStartingStatus(
        FastSurferInputRows=FastSurferInputRows,
        WorkRows=WorkRows,
        UseGpu=UseGpu,
        FastSurferImageName=FastSurferImageName,
    )

    RunLogRowsFromThisInvocation: list[dict[str, object]] = []

    WriteRunSummary(
        FastSurferInputRows=FastSurferInputRows,
        WorkRows=WorkRows,
        UseGpu=UseGpu,
        FastSurferImageName=FastSurferImageName,
        RunLogRowsFromThisInvocation=RunLogRowsFromThisInvocation,
        WorkflowStartedAt=WorkflowStartedAt,
    )

    for WorkIndex, WorkRow in enumerate(WorkRows, start=1):
        ManifestRowNumber = WorkRow["ManifestRowNumber"]
        FastSurferInputRow = WorkRow["FastSurferInputRow"]
        FastSurferSubjectId = NormaliseText(FastSurferInputRow.get("FastSurferSubjectId", ""))

        print()
        print("=" * 80)
        print(f"Processing worklist row {WorkIndex} of {len(WorkRows)}")
        print(f"Manifest row: {ManifestRowNumber} of {len(FastSurferInputRows)}")
        print(f"Diagnosis: {FastSurferInputRow.get('Diagnosis3Class', '')}")
        print(f"Current status: {WorkRow['ProcessingStatus']}")
        print(f"FastSurfer subject: {FastSurferSubjectId}")
        print("=" * 80)

        RunLogRow = RunOneFastSurferSubject(
            FastSurferInputRow=FastSurferInputRow,
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
        )

        RunLogRowsFromThisInvocation.append(RunLogRow)
        AppendRunLogRow(RunLogRow)

        print()
        print(f"Run status: {RunLogRow['RunStatus']}")
        print(f"Duration: {RunLogRow['Duration']}")

        WriteRunSummary(
            FastSurferInputRows=FastSurferInputRows,
            WorkRows=WorkRows,
            UseGpu=UseGpu,
            FastSurferImageName=FastSurferImageName,
            RunLogRowsFromThisInvocation=RunLogRowsFromThisInvocation,
            WorkflowStartedAt=WorkflowStartedAt,
        )

    print()
    print("Prioritised FastSurfer run complete.")
    print(f"Run log: {FastSurferRunLogPath}")
    print(f"Summary: {FastSurferRunMarkdownSummaryPath}")
    print(f"Worklist: {FastSurferWorklistPath}")


if __name__ == "__main__":
    try:
        Main()

    except KeyboardInterrupt:
        print()
        print("FastSurfer run interrupted by user or system shutdown.")
        sys.exit(130)

    except Exception as Error:
        print()
        print("FastSurfer run failed.")
        print(str(Error))
        sys.exit(1)