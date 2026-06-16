"""Prepare the FastSurfer input manifest.

Reads the selected baseline cohort and writes one FastSurfer processing row per
selected scan to Data/Processed/FeatureExtraction/.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path


SelectedBaselineCohortPath = Path("Data") / "Interim" / "Cohort" / "SelectedBaselineCohort.csv"
FeatureExtractionOutputDirectory = Path("Data") / "Processed" / "FeatureExtraction"
FastSurferOutputRootDirectory = Path("Data") / "Processed" / "FastSurfer"
FastSurferInputManifestPath = FeatureExtractionOutputDirectory / "FastSurferInputManifest.csv"
FastSurferInputManifestSummaryPath = FeatureExtractionOutputDirectory / "FastSurferInputManifestSummary.csv"
FastSurferInputManifestMarkdownSummaryPath = FeatureExtractionOutputDirectory / "FastSurferInputManifestSummary.md"

DockerDataMountPath = "/data"
DockerFastSurferOutputMountPath = "/output"
LocalLicensePath = Path("LocalOnly") / "FreeSurfer" / "license.txt"

OutputFieldNames = [
    "RID",
    "SubjectId",
    "ImageId",
    "ImageIdKey",
    "Diagnosis3Class",
    "Age",
    "Sex",
    "Education",
    "ImageRelativePath",
    "ContainerT1Path",
    "FastSurferSubjectId",
    "FastSurferOutputDirectory",
    "ContainerFastSurferOutputDirectory",
    "ExpectedStatsDirectory",
    "ProcessingStatus",
]


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def PrintProgress(Message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {Message}", flush=True)


def FormatDuration(DurationSeconds: float) -> str:
    RoundedSeconds = int(round(DurationSeconds))
    Hours = RoundedSeconds // 3600
    Minutes = (RoundedSeconds % 3600) // 60
    Seconds = RoundedSeconds % 60
    return f"{Hours:02d}:{Minutes:02d}:{Seconds:02d}"


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


def MakeSafePathPart(PathPartValue: object) -> str:
    """Convert a value into a safe folder-name component."""
    PathPartText = NormaliseText(PathPartValue)

    if not PathPartText:
        return "Missing"

    SafePathPart = re.sub(r"[^A-Za-z0-9_-]", "_", PathPartText)
    SafePathPart = re.sub(r"_+", "_", SafePathPart)

    return SafePathPart.strip("_") or "Missing"


def BuildFastSurferSubjectId(CohortRow: dict[str, str]) -> str:
    """Build a deterministic FastSurfer subject folder name."""
    RidValue = MakeSafePathPart(CohortRow.get("RID", ""))
    ImageIdValue = MakeSafePathPart(CohortRow.get("ImageId", ""))

    return f"RID_{RidValue}_{ImageIdValue}"


def ConvertRelativePathToContainerPath(RelativePathValue: object) -> str:
    """Convert a repository-relative Data path to the container /data path."""
    RelativePathText = NormaliseText(RelativePathValue).replace("\\", "/")

    if RelativePathText.startswith("Data/"):
        RelativePathText = RelativePathText[len("Data/") :]

    return f"{DockerDataMountPath}/{RelativePathText}"


def GetRelativePath(FilePath: Path) -> str:
    try:
        return str(FilePath.relative_to(Path.cwd()))
    except ValueError:
        return str(FilePath)


def ValidateLicenseFile() -> bool:
    """Check that the local FreeSurfer license file is present and non-empty."""
    if not LocalLicensePath.exists():
        raise FileNotFoundError("FreeSurfer license file was not found.")

    if not LocalLicensePath.is_file():
        raise FileNotFoundError("FreeSurfer license path is not a file.")

    if LocalLicensePath.stat().st_size == 0:
        raise RuntimeError("FreeSurfer license file is empty.")

    return True


def DetermineProcessingStatus(FastSurferSubjectOutputDirectory: Path) -> str:
    """Classify whether a FastSurfer subject output appears complete or pending."""
    StatsDirectory = FastSurferSubjectOutputDirectory / "stats"

    if StatsDirectory.exists() and any(StatsDirectory.glob("*.stats")):
        return "Complete"

    if FastSurferSubjectOutputDirectory.exists():
        return "OutputDirectoryExists"

    return "Pending"


def BuildFastSurferInputRows(CohortRows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Build one FastSurfer manifest row per selected cohort row."""
    FastSurferInputRows: list[dict[str, object]] = []

    for CohortRow in CohortRows:
        FastSurferSubjectId = BuildFastSurferSubjectId(CohortRow)
        FastSurferSubjectOutputDirectory = FastSurferOutputRootDirectory / FastSurferSubjectId
        ExpectedStatsDirectory = FastSurferSubjectOutputDirectory / "stats"

        FastSurferInputRows.append(
            {
                "RID": CohortRow.get("RID", ""),
                "SubjectId": CohortRow.get("SubjectId", ""),
                "ImageId": CohortRow.get("ImageId", ""),
                "ImageIdKey": CohortRow.get("ImageIdKey", ""),
                "Diagnosis3Class": CohortRow.get("Diagnosis3Class", ""),
                "Age": CohortRow.get("Age", ""),
                "Sex": CohortRow.get("Sex", ""),
                "Education": CohortRow.get("Education", ""),
                "ImageRelativePath": CohortRow.get("ImageRelativePath", ""),
                "ContainerT1Path": ConvertRelativePathToContainerPath(CohortRow.get("ImageRelativePath", "")),
                "FastSurferSubjectId": FastSurferSubjectId,
                "FastSurferOutputDirectory": str(FastSurferSubjectOutputDirectory),
                "ContainerFastSurferOutputDirectory": DockerFastSurferOutputMountPath,
                "ExpectedStatsDirectory": str(ExpectedStatsDirectory),
                "ProcessingStatus": DetermineProcessingStatus(FastSurferSubjectOutputDirectory),
            }
        )

    return FastSurferInputRows


def CountRowsWithValue(DataRows: list[dict[str, object]], FieldName: str) -> int:
    return sum(1 for DataRow in DataRows if NormaliseText(DataRow.get(FieldName, "")))


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


def BuildSummaryRows(FastSurferInputRows: list[dict[str, object]], LicenseFound: bool) -> list[dict[str, object]]:
    """Build summary rows for the FastSurfer input manifest."""
    return [
        {"Metric": "FastSurferInputRows", "Value": len(FastSurferInputRows)},
        {"Metric": "RowsWithRID", "Value": CountRowsWithValue(FastSurferInputRows, "RID")},
        {"Metric": "RowsWithImageId", "Value": CountRowsWithValue(FastSurferInputRows, "ImageId")},
        {"Metric": "RowsWithImageRelativePath", "Value": CountRowsWithValue(FastSurferInputRows, "ImageRelativePath")},
        {"Metric": "RowsWithContainerT1Path", "Value": CountRowsWithValue(FastSurferInputRows, "ContainerT1Path")},
        {"Metric": "RowsWithFastSurferSubjectId", "Value": CountRowsWithValue(FastSurferInputRows, "FastSurferSubjectId")},
        {"Metric": "LicenseFound", "Value": LicenseFound},
        {"Metric": "LicensePath", "Value": GetRelativePath(LocalLicensePath)},
        {
            "Metric": "ProcessingStatusCounts",
            "Value": FormatValueCounts(CountRowsByValue(FastSurferInputRows, "ProcessingStatus")),
        },
        {
            "Metric": "Diagnosis3ClassCounts",
            "Value": FormatValueCounts(CountRowsByValue(FastSurferInputRows, "Diagnosis3Class")),
        },
    ]


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRows: list[dict[str, object]]) -> None:
    """Write a brief Markdown summary for the FastSurfer input manifest."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# FastSurfer Input Manifest Summary\n\n")
        OutputFile.write(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def Main() -> None:
    StartedAt = datetime.now()
    PrintProgress("Starting FastSurfer input manifest build.")
    EnsureDirectory(FeatureExtractionOutputDirectory)

    if not SelectedBaselineCohortPath.exists():
        raise FileNotFoundError(f"Selected baseline cohort file not found: {SelectedBaselineCohortPath}")

    PrintProgress(f"Checking FreeSurfer licence: {LocalLicensePath}")
    LicenseFound = ValidateLicenseFile()

    PrintProgress(f"Reading selected baseline cohort: {SelectedBaselineCohortPath}")
    CohortRows = ReadCsvRows(SelectedBaselineCohortPath)
    PrintProgress(f"Selected baseline cohort rows loaded: {len(CohortRows)}")

    PrintProgress("Building FastSurfer input rows.")
    FastSurferInputRows = BuildFastSurferInputRows(CohortRows)
    SummaryRows = BuildSummaryRows(
        FastSurferInputRows=FastSurferInputRows,
        LicenseFound=LicenseFound,
    )

    PrintProgress(f"Writing manifest: {FastSurferInputManifestPath}")
    WriteCsv(
        OutputFilePath=FastSurferInputManifestPath,
        FieldNames=OutputFieldNames,
        DataRows=FastSurferInputRows,
    )

    PrintProgress(f"Writing summary: {FastSurferInputManifestSummaryPath}")
    WriteCsv(
        OutputFilePath=FastSurferInputManifestSummaryPath,
        FieldNames=["Metric", "Value"],
        DataRows=SummaryRows,
    )

    PrintProgress(f"Writing Markdown summary: {FastSurferInputManifestMarkdownSummaryPath}")
    WriteMarkdownSummary(
        OutputFilePath=FastSurferInputManifestMarkdownSummaryPath,
        SummaryRows=SummaryRows,
    )

    DurationSeconds = (datetime.now() - StartedAt).total_seconds()
    PrintProgress(f"FastSurfer input manifest build complete in {FormatDuration(DurationSeconds)}.")
    print(f"Input cohort rows: {len(CohortRows)}")
    print(f"Manifest rows: {len(FastSurferInputRows)}")
    print(f"License found: {LicenseFound}")
    print(f"Output: {FastSurferInputManifestPath}")


if __name__ == "__main__":
    try:
        Main()
    except Exception as Error:
        print()
        print("FastSurfer input manifest build failed.")
        print(str(Error))
        sys.exit(1)