"""Inspect unpacked raw ADNI data and write local inventory files.

Reads Data/Raw and writes inspection outputs to Data/Interim/Inspection. The
outputs are derived from restricted ADNI data and must not be committed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path


RequiredClinicalTableTypes = [
    "ADAS",
    "ADNIMERGE",
    "ADNI_3T_MRI_Standardized_Lists",
    "CDR",
    "DATADIC",
    "DXSUM",
    "FAQ",
    "MMSE",
    "MRI3META",
    "MRIMPRANK",
    "MRIQC",
    "NEUROBAT",
    "PTDEMOG",
    "REGISTRY",
    "ROSTER",
]


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def CountFiles(DirectoryPath: Path) -> int:
    if not DirectoryPath.exists():
        return 0

    return sum(1 for FilePath in DirectoryPath.rglob("*") if FilePath.is_file())


def IsNiftiFile(FilePath: Path) -> bool:
    FileName = FilePath.name.lower()
    return FileName.endswith(".nii") or FileName.endswith(".nii.gz")


def GetFileSizeMegabytes(FilePath: Path) -> float:
    return FilePath.stat().st_size / (1024 * 1024)


def GetRelativePath(FilePath: Path, RootDirectory: Path) -> str:
    try:
        return str(FilePath.relative_to(RootDirectory))
    except ValueError:
        return str(FilePath)


def GetCompoundFileExtension(FilePath: Path) -> str:
    """Return .nii.gz as a compound extension instead of only .gz."""
    FileNameLower = FilePath.name.lower()

    if FileNameLower.endswith(".nii.gz"):
        return ".nii.gz"

    if FileNameLower.endswith(".tar.gz"):
        return ".tar.gz"

    return FilePath.suffix.lower()


def WriteCsv(OutputFilePath: Path, FieldNames: list[str], Rows: list[dict[str, object]]) -> None:
    """Write dictionaries to a CSV file with a fixed column order."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", newline="", encoding="utf-8") as OutputFile:
        CsvWriter = csv.DictWriter(OutputFile, fieldnames=FieldNames)
        CsvWriter.writeheader()

        for Row in Rows:
            CsvWriter.writerow(Row)


def InspectCsvFile(CsvFilePath: Path, DataRootDirectory: Path) -> dict[str, object]:
    """Read a CSV header and count rows, falling back to latin-1 when required."""
    ColumnCount = 0
    RowCount = 0
    ColumnsPreview = ""
    ReadStatus = "Readable"
    ErrorMessage = ""

    try:
        with CsvFilePath.open("r", newline="", encoding="utf-8-sig") as CsvFile:
            CsvReader = csv.reader(CsvFile)
            HeaderRow = next(CsvReader, None)

            if HeaderRow is not None:
                ColumnCount = len(HeaderRow)
                ColumnsPreview = "; ".join(HeaderRow[:20])

                for _ in CsvReader:
                    RowCount += 1

    except UnicodeDecodeError:
        try:
            with CsvFilePath.open("r", newline="", encoding="latin-1") as CsvFile:
                CsvReader = csv.reader(CsvFile)
                HeaderRow = next(CsvReader, None)

                if HeaderRow is not None:
                    ColumnCount = len(HeaderRow)
                    ColumnsPreview = "; ".join(HeaderRow[:20])

                    for _ in CsvReader:
                        RowCount += 1

                ReadStatus = "ReadableWithLatin1"

        except Exception as Error:
            ReadStatus = "Unreadable"
            ErrorMessage = str(Error)

    except Exception as Error:
        ReadStatus = "Unreadable"
        ErrorMessage = str(Error)

    return {
        "FileName": CsvFilePath.name,
        "RelativePath": GetRelativePath(CsvFilePath, DataRootDirectory),
        "Directory": GetRelativePath(CsvFilePath.parent, DataRootDirectory),
        "SizeMegabytes": round(GetFileSizeMegabytes(CsvFilePath), 3),
        "RowCount": RowCount,
        "ColumnCount": ColumnCount,
        "ColumnsPreview": ColumnsPreview,
        "ReadStatus": ReadStatus,
        "ErrorMessage": ErrorMessage,
    }


def GetClinicalFileType(FilePath: Path) -> str:
    """Map a clinical filename or path to a known ADNI table family."""
    FileNameLower = FilePath.name.lower()
    RelativePathLower = str(FilePath).lower()

    ClinicalFilePatterns = {
        "ADAS": ["adas"],
        "ADNIMERGE": ["adnimerge"],
        "ADNI_3T_MRI_Standardized_Lists": ["adni_3t_mri_standardized_lists", "standardized"],
        "CDR": ["cdr"],
        "DATADIC": ["datadic"],
        "DXSUM": ["dxsum"],
        "FAQ": ["faq"],
        "MMSE": ["mmse"],
        "MRI3META": ["mri3meta"],
        "MRIMPRANK": ["mrimprank"],
        "MRIQC": ["mriqc"],
        "NEUROBAT": ["neurobat"],
        "PTDEMOG": ["ptdemog"],
        "REGISTRY": ["registry"],
        "ROSTER": ["roster"],
    }

    for ClinicalFileType, PatternList in ClinicalFilePatterns.items():
        for Pattern in PatternList:
            if Pattern in FileNameLower or Pattern in RelativePathLower:
                return ClinicalFileType

    return "Other"


def BuildRawDataInventory(DataRootDirectory: Path) -> list[dict[str, object]]:
    """Inventory every file under Data/Raw."""
    RawDirectory = DataRootDirectory / "Raw"

    if not RawDirectory.exists():
        return []

    RawDataInventoryRows: list[dict[str, object]] = []

    for RawFilePath in sorted(RawDirectory.rglob("*")):
        if not RawFilePath.is_file():
            continue

        RawDataInventoryRows.append(
            {
                "FileName": RawFilePath.name,
                "RelativePath": GetRelativePath(RawFilePath, DataRootDirectory),
                "Directory": GetRelativePath(RawFilePath.parent, DataRootDirectory),
                "SizeMegabytes": round(GetFileSizeMegabytes(RawFilePath), 3),
                "FileExtension": GetCompoundFileExtension(RawFilePath),
            }
        )

    return RawDataInventoryRows


def InspectClinicalCsvTables(DataRootDirectory: Path) -> list[dict[str, object]]:
    """Inspect only clinical CSV tables, excluding extracted support files."""
    ClinicalStudyDataDirectory = DataRootDirectory / "Raw" / "Clinical" / "StudyData"

    if not ClinicalStudyDataDirectory.exists():
        return []

    ClinicalCsvTableRows: list[dict[str, object]] = []

    for ClinicalCsvFilePath in sorted(ClinicalStudyDataDirectory.rglob("*.csv")):
        ClinicalCsvTableRow = InspectCsvFile(
            CsvFilePath=ClinicalCsvFilePath,
            DataRootDirectory=DataRootDirectory,
        )

        ClinicalCsvTableRow["FileType"] = GetClinicalFileType(ClinicalCsvFilePath)
        ClinicalCsvTableRows.append(ClinicalCsvTableRow)

    return ClinicalCsvTableRows


def InspectClinicalSupportFiles(DataRootDirectory: Path) -> list[dict[str, object]]:
    """Inventory non-CSV clinical files extracted from the clinical bundle."""
    ClinicalStudyDataDirectory = DataRootDirectory / "Raw" / "Clinical" / "StudyData"

    if not ClinicalStudyDataDirectory.exists():
        return []

    ClinicalSupportFileRows: list[dict[str, object]] = []

    for ClinicalFilePath in sorted(ClinicalStudyDataDirectory.rglob("*")):
        if not ClinicalFilePath.is_file():
            continue

        if ClinicalFilePath.suffix.lower() == ".csv":
            continue

        ClinicalSupportFileRows.append(
            {
                "FileName": ClinicalFilePath.name,
                "RelativePath": GetRelativePath(ClinicalFilePath, DataRootDirectory),
                "Directory": GetRelativePath(ClinicalFilePath.parent, DataRootDirectory),
                "SizeMegabytes": round(GetFileSizeMegabytes(ClinicalFilePath), 3),
                "FileExtension": GetCompoundFileExtension(ClinicalFilePath),
                "FileType": GetClinicalFileType(ClinicalFilePath),
            }
        )

    return ClinicalSupportFileRows


def InspectManifestFiles(DataRootDirectory: Path) -> list[dict[str, object]]:
    """Inventory IDA manifest and metadata files."""
    ImagingManifestDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Manifest"

    if not ImagingManifestDirectory.exists():
        return []

    ManifestFileRows: list[dict[str, object]] = []

    for ManifestFilePath in sorted(ImagingManifestDirectory.rglob("*")):
        if not ManifestFilePath.is_file():
            continue

        ManifestFileRows.append(
            {
                "FileName": ManifestFilePath.name,
                "RelativePath": GetRelativePath(ManifestFilePath, DataRootDirectory),
                "Directory": GetRelativePath(ManifestFilePath.parent, DataRootDirectory),
                "SizeMegabytes": round(GetFileSizeMegabytes(ManifestFilePath), 3),
                "FileExtension": GetCompoundFileExtension(ManifestFilePath),
            }
        )

    return ManifestFileRows


def InspectImagingFiles(DataRootDirectory: Path) -> list[dict[str, object]]:
    """Inventory extracted MRI image files."""
    ImagingImagesDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Images"

    if not ImagingImagesDirectory.exists():
        return []

    ImagingFileRows: list[dict[str, object]] = []

    for ImagingFilePath in sorted(ImagingImagesDirectory.rglob("*")):
        if not ImagingFilePath.is_file():
            continue

        ImagingFileRows.append(
            {
                "FileName": ImagingFilePath.name,
                "RelativePath": GetRelativePath(ImagingFilePath, DataRootDirectory),
                "Directory": GetRelativePath(ImagingFilePath.parent, DataRootDirectory),
                "SizeMegabytes": round(GetFileSizeMegabytes(ImagingFilePath), 3),
                "IsNifti": IsNiftiFile(ImagingFilePath),
                "FileExtension": GetCompoundFileExtension(ImagingFilePath),
            }
        )

    return ImagingFileRows


def CountClinicalTableTypes(ClinicalCsvTableRows: list[dict[str, object]]) -> dict[str, int]:
    """Count known clinical table families among clinical CSV files."""
    ClinicalTableTypeCounts: dict[str, int] = {}

    for ClinicalCsvTableRow in ClinicalCsvTableRows:
        ClinicalFileType = str(ClinicalCsvTableRow["FileType"])
        ClinicalTableTypeCounts[ClinicalFileType] = ClinicalTableTypeCounts.get(ClinicalFileType, 0) + 1

    return ClinicalTableTypeCounts


def BuildSummaryRows(
    DataRootDirectory: Path,
    RawDataInventoryRows: list[dict[str, object]],
    ClinicalCsvTableRows: list[dict[str, object]],
    ClinicalSupportFileRows: list[dict[str, object]],
    ManifestFileRows: list[dict[str, object]],
    ImagingFileRows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build summary metrics for the raw-data inspection outputs."""
    ClinicalStudyDataDirectory = DataRootDirectory / "Raw" / "Clinical" / "StudyData"
    ImagingManifestDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Manifest"
    ImagingArchivesDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Archives"
    ImagingImagesDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Images"

    ClinicalTableTypeCounts = CountClinicalTableTypes(ClinicalCsvTableRows)
    PresentRequiredClinicalTableTypes = [
        RequiredClinicalTableType
        for RequiredClinicalTableType in RequiredClinicalTableTypes
        if ClinicalTableTypeCounts.get(RequiredClinicalTableType, 0) > 0
    ]

    MissingRequiredClinicalTableTypes = [
        RequiredClinicalTableType
        for RequiredClinicalTableType in RequiredClinicalTableTypes
        if ClinicalTableTypeCounts.get(RequiredClinicalTableType, 0) == 0
    ]

    NiftiFileCount = sum(1 for ImagingFileRow in ImagingFileRows if ImagingFileRow["IsNifti"] is True)
    NonNiftiImageFileCount = len(ImagingFileRows) - NiftiFileCount

    return [
        {"Metric": "ClinicalStudyDataDirectoryExists", "Value": ClinicalStudyDataDirectory.exists()},
        {"Metric": "ImagingManifestDirectoryExists", "Value": ImagingManifestDirectory.exists()},
        {"Metric": "ImagingArchivesDirectoryExists", "Value": ImagingArchivesDirectory.exists()},
        {"Metric": "ImagingImagesDirectoryExists", "Value": ImagingImagesDirectory.exists()},
        {"Metric": "RawFileCount", "Value": len(RawDataInventoryRows)},
        {"Metric": "ClinicalCsvTableCount", "Value": len(ClinicalCsvTableRows)},
        {"Metric": "ClinicalSupportFileCount", "Value": len(ClinicalSupportFileRows)},
        {"Metric": "RequiredClinicalTableTypesPresent", "Value": len(PresentRequiredClinicalTableTypes)},
        {"Metric": "RequiredClinicalTableTypesExpected", "Value": len(RequiredClinicalTableTypes)},
        {"Metric": "MissingRequiredClinicalTableTypes", "Value": "; ".join(MissingRequiredClinicalTableTypes)},
        {"Metric": "ManifestFileCount", "Value": len(ManifestFileRows)},
        {"Metric": "RemainingArchiveFileCount", "Value": CountFiles(ImagingArchivesDirectory)},
        {"Metric": "ExtractedImageFileCount", "Value": len(ImagingFileRows)},
        {"Metric": "ExtractedNiftiFileCount", "Value": NiftiFileCount},
        {"Metric": "NonNiftiImageFileCount", "Value": NonNiftiImageFileCount},
    ]


def WriteMarkdownSummary(
    OutputFilePath: Path,
    SummaryRows: list[dict[str, object]],
    ClinicalCsvTableRows: list[dict[str, object]],
) -> None:
    """Write a concise Markdown summary of the inspection results."""
    EnsureDirectory(OutputFilePath.parent)

    SummaryByMetric = {str(SummaryRow["Metric"]): SummaryRow["Value"] for SummaryRow in SummaryRows}
    ClinicalTableTypeCounts = CountClinicalTableTypes(ClinicalCsvTableRows)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# Raw Data Inspection Summary\n\n")
        OutputFile.write(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`\n\n")

        OutputFile.write("## Key counts\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")
        OutputFile.write(f"| Clinical CSV tables | {SummaryByMetric.get('ClinicalCsvTableCount', 0)} |\n")
        OutputFile.write(f"| Clinical support files | {SummaryByMetric.get('ClinicalSupportFileCount', 0)} |\n")
        OutputFile.write(
            f"| Required clinical table types present | "
            f"{SummaryByMetric.get('RequiredClinicalTableTypesPresent', 0)} / "
            f"{SummaryByMetric.get('RequiredClinicalTableTypesExpected', 0)} |\n"
        )
        OutputFile.write(f"| Manifest files | {SummaryByMetric.get('ManifestFileCount', 0)} |\n")
        OutputFile.write(f"| Extracted image files | {SummaryByMetric.get('ExtractedImageFileCount', 0)} |\n")
        OutputFile.write(f"| Extracted NIfTI files | {SummaryByMetric.get('ExtractedNiftiFileCount', 0)} |\n")
        OutputFile.write(f"| Non-NIfTI image files | {SummaryByMetric.get('NonNiftiImageFileCount', 0)} |\n")
        OutputFile.write(f"| Remaining image archives | {SummaryByMetric.get('RemainingArchiveFileCount', 0)} |\n")

        MissingRequiredClinicalTableTypes = str(SummaryByMetric.get("MissingRequiredClinicalTableTypes", ""))

        if MissingRequiredClinicalTableTypes:
            OutputFile.write("\n## Missing required clinical table types\n\n")
            OutputFile.write(f"`{MissingRequiredClinicalTableTypes}`\n")
        else:
            OutputFile.write("\nAll required clinical table types were detected.\n")

        OutputFile.write("\n## Clinical table type counts\n\n")
        OutputFile.write("| File type | CSV count |\n")
        OutputFile.write("|---|---:|\n")

        for RequiredClinicalTableType in RequiredClinicalTableTypes:
            OutputFile.write(
                f"| {RequiredClinicalTableType} | "
                f"{ClinicalTableTypeCounts.get(RequiredClinicalTableType, 0)} |\n"
            )

        OtherClinicalTableCount = ClinicalTableTypeCounts.get("Other", 0)

        if OtherClinicalTableCount:
            OutputFile.write(f"| Other | {OtherClinicalTableCount} |\n")


def ParseArguments() -> argparse.Namespace:
    """Parse command-line arguments for raw-data inspection."""
    ArgumentParser = argparse.ArgumentParser(
        description="Inspect unpacked raw ADNI data and write local interim inventory files."
    )

    ArgumentParser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data"),
        help="Path to the repository Data directory. Default: Data",
    )

    ArgumentParser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("Data") / "Interim" / "Inspection",
        help="Directory for inspection outputs. Default: Data/Interim/Inspection",
    )

    return ArgumentParser.parse_args()


def Main() -> None:
    Arguments = ParseArguments()

    DataRootDirectory = Arguments.data_root
    OutputDirectory = Arguments.output_directory

    EnsureDirectory(OutputDirectory)

    RawDataInventoryRows = BuildRawDataInventory(DataRootDirectory)
    ClinicalCsvTableRows = InspectClinicalCsvTables(DataRootDirectory)
    ClinicalSupportFileRows = InspectClinicalSupportFiles(DataRootDirectory)
    ManifestFileRows = InspectManifestFiles(DataRootDirectory)
    ImagingFileRows = InspectImagingFiles(DataRootDirectory)

    SummaryRows = BuildSummaryRows(
        DataRootDirectory=DataRootDirectory,
        RawDataInventoryRows=RawDataInventoryRows,
        ClinicalCsvTableRows=ClinicalCsvTableRows,
        ClinicalSupportFileRows=ClinicalSupportFileRows,
        ManifestFileRows=ManifestFileRows,
        ImagingFileRows=ImagingFileRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "RawDataInventory.csv",
        FieldNames=["FileName", "RelativePath", "Directory", "SizeMegabytes", "FileExtension"],
        Rows=RawDataInventoryRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ClinicalCsvTableInventory.csv",
        FieldNames=[
            "FileName",
            "RelativePath",
            "Directory",
            "SizeMegabytes",
            "RowCount",
            "ColumnCount",
            "ColumnsPreview",
            "ReadStatus",
            "ErrorMessage",
            "FileType",
        ],
        Rows=ClinicalCsvTableRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ClinicalSupportFileInventory.csv",
        FieldNames=[
            "FileName",
            "RelativePath",
            "Directory",
            "SizeMegabytes",
            "FileExtension",
            "FileType",
        ],
        Rows=ClinicalSupportFileRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ManifestInventory.csv",
        FieldNames=["FileName", "RelativePath", "Directory", "SizeMegabytes", "FileExtension"],
        Rows=ManifestFileRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ImagingInventory.csv",
        FieldNames=["FileName", "RelativePath", "Directory", "SizeMegabytes", "IsNifti", "FileExtension"],
        Rows=ImagingFileRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "RawDataInspectionSummary.csv",
        FieldNames=["Metric", "Value"],
        Rows=SummaryRows,
    )

    WriteMarkdownSummary(
        OutputFilePath=OutputDirectory / "RawDataInspectionSummary.md",
        SummaryRows=SummaryRows,
        ClinicalCsvTableRows=ClinicalCsvTableRows,
    )

    print("Raw data inspection complete.")
    print(f"Output directory: {OutputDirectory}")


if __name__ == "__main__":
    Main()