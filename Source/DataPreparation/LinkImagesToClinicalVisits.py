"""Link MRI image manifest rows to nearest ADNI clinical visits.

Reads ImageManifest.csv and ClinicalVisits.csv, then writes one linked row per
image to Data/Interim/Linkage/ using same-subject nearest-date matching.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path


MaximumAllowedDaysBetweenImageAndClinicalVisit = 90

OutputFieldNames = [
    "ImageId",
    "ImageIdKey",
    "SubjectId",
    "RID",
    "ImageStudyDate",
    "ClinicalExamDate",
    "DaysBetweenImageAndClinicalVisit",
    "AbsoluteDaysBetweenImageAndClinicalVisit",
    "VisitCode",
    "VisitCode2",
    "Age",
    "Sex",
    "Education",
    "Diagnosis",
    "DiagnosisBaseline",
    "Diagnosis3Class",
    "MMSE",
    "ADAS11",
    "ADAS13",
    "CDRSB",
    "FAQ",
    "ImageDescription",
    "FieldStrength",
    "Weighting",
    "AcquisitionType",
    "AcquisitionPlane",
    "Manufacturer",
    "ScannerModel",
    "MprageRank",
    "InStandardised3TList",
    "IdaMetadataMatchCount",
    "Mri3MetaMatchCount",
    "MriQcMatchCount",
    "MprageRankMatchCount",
    "ImageFileName",
    "ImageRelativePath",
    "ImageDirectory",
    "ImageSizeMegabytes",
    "LinkStatus",
]


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def NormaliseText(TextValue: object) -> str:
    return str(TextValue).strip() if TextValue is not None else ""


def NormaliseSubjectId(SubjectIdValue: object) -> str:
    """Normalise ADNI subject identifiers for matching."""
    SubjectIdText = NormaliseText(SubjectIdValue).upper()
    return SubjectIdText.replace("-", "_")


def ParseDate(DateValue: str) -> date | None:
    """Parse common ADNI date formats into a Python date."""
    DateText = NormaliseText(DateValue)

    if not DateText:
        return None

    DateFormats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m/%d/%y",
        "%d/%m/%y",
    ]

    for DateFormat in DateFormats:
        try:
            return datetime.strptime(DateText, DateFormat).date()
        except ValueError:
            continue

    return None


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


def BuildClinicalVisitsBySubject(
    ClinicalVisitRows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Group clinical visit rows by normalised ADNI subject ID."""
    ClinicalVisitsBySubject: dict[str, list[dict[str, str]]] = {}

    for ClinicalVisitRow in ClinicalVisitRows:
        SubjectId = NormaliseSubjectId(ClinicalVisitRow.get("SubjectId", ""))

        if not SubjectId:
            continue

        if SubjectId not in ClinicalVisitsBySubject:
            ClinicalVisitsBySubject[SubjectId] = []

        ClinicalVisitsBySubject[SubjectId].append(ClinicalVisitRow)

    return ClinicalVisitsBySubject


def FindNearestClinicalVisit(
    ImageManifestRow: dict[str, str],
    ClinicalVisitsBySubject: dict[str, list[dict[str, str]]],
) -> tuple[dict[str, str] | None, int | None, str]:
    """Find the nearest clinical visit for the same subject by date."""
    ImageSubjectId = NormaliseSubjectId(ImageManifestRow.get("SubjectId", ""))
    ImageStudyDate = ParseDate(ImageManifestRow.get("StudyDate", ""))

    if not ImageSubjectId:
        return None, None, "MissingImageSubjectId"

    if ImageStudyDate is None:
        return None, None, "MissingOrInvalidImageStudyDate"

    CandidateClinicalVisitRows = ClinicalVisitsBySubject.get(ImageSubjectId, [])

    if not CandidateClinicalVisitRows:
        return None, None, "NoClinicalVisitsForSubject"

    BestClinicalVisitRow: dict[str, str] | None = None
    BestDaysBetweenImageAndClinicalVisit: int | None = None
    BestAbsoluteDaysBetweenImageAndClinicalVisit: int | None = None

    for ClinicalVisitRow in CandidateClinicalVisitRows:
        ClinicalExamDate = ParseDate(ClinicalVisitRow.get("ExamDate", ""))

        if ClinicalExamDate is None:
            continue

        DaysBetweenImageAndClinicalVisit = (ImageStudyDate - ClinicalExamDate).days
        AbsoluteDaysBetweenImageAndClinicalVisit = abs(DaysBetweenImageAndClinicalVisit)

        if (
            BestAbsoluteDaysBetweenImageAndClinicalVisit is None
            or AbsoluteDaysBetweenImageAndClinicalVisit < BestAbsoluteDaysBetweenImageAndClinicalVisit
        ):
            BestClinicalVisitRow = ClinicalVisitRow
            BestDaysBetweenImageAndClinicalVisit = DaysBetweenImageAndClinicalVisit
            BestAbsoluteDaysBetweenImageAndClinicalVisit = AbsoluteDaysBetweenImageAndClinicalVisit

    if BestClinicalVisitRow is None or BestDaysBetweenImageAndClinicalVisit is None:
        return None, None, "NoClinicalVisitsWithValidExamDate"

    if BestAbsoluteDaysBetweenImageAndClinicalVisit is None:
        return None, None, "NoClinicalVisitsWithValidExamDate"

    if BestAbsoluteDaysBetweenImageAndClinicalVisit > MaximumAllowedDaysBetweenImageAndClinicalVisit:
        return (
            BestClinicalVisitRow,
            BestDaysBetweenImageAndClinicalVisit,
            "NearestClinicalVisitOutsideAllowedWindow",
        )

    return BestClinicalVisitRow, BestDaysBetweenImageAndClinicalVisit, "Linked"


def BuildLinkedRow(
    ImageManifestRow: dict[str, str],
    ClinicalVisitRow: dict[str, str] | None,
    DaysBetweenImageAndClinicalVisit: int | None,
    LinkStatus: str,
) -> dict[str, object]:
    """Combine one image row with its nearest clinical visit row."""
    if DaysBetweenImageAndClinicalVisit is None:
        DaysBetweenText = ""
        AbsoluteDaysText = ""
    else:
        DaysBetweenText = DaysBetweenImageAndClinicalVisit
        AbsoluteDaysText = abs(DaysBetweenImageAndClinicalVisit)

    if ClinicalVisitRow is None:
        ClinicalVisitRow = {}

    return {
        "ImageId": ImageManifestRow.get("ImageId", ""),
        "ImageIdKey": ImageManifestRow.get("ImageIdKey", ""),
        "SubjectId": ImageManifestRow.get("SubjectId", ""),
        "RID": ClinicalVisitRow.get("RID", ""),
        "ImageStudyDate": ImageManifestRow.get("StudyDate", ""),
        "ClinicalExamDate": ClinicalVisitRow.get("ExamDate", ""),
        "DaysBetweenImageAndClinicalVisit": DaysBetweenText,
        "AbsoluteDaysBetweenImageAndClinicalVisit": AbsoluteDaysText,
        "VisitCode": ClinicalVisitRow.get("VisitCode", ""),
        "VisitCode2": ClinicalVisitRow.get("VisitCode2", ""),
        "Age": ClinicalVisitRow.get("Age", ""),
        "Sex": ClinicalVisitRow.get("Sex", ""),
        "Education": ClinicalVisitRow.get("Education", ""),
        "Diagnosis": ClinicalVisitRow.get("Diagnosis", ""),
        "DiagnosisBaseline": ClinicalVisitRow.get("DiagnosisBaseline", ""),
        "Diagnosis3Class": ClinicalVisitRow.get("Diagnosis3Class", ""),
        "MMSE": ClinicalVisitRow.get("MMSE", ""),
        "ADAS11": ClinicalVisitRow.get("ADAS11", ""),
        "ADAS13": ClinicalVisitRow.get("ADAS13", ""),
        "CDRSB": ClinicalVisitRow.get("CDRSB", ""),
        "FAQ": ClinicalVisitRow.get("FAQ", ""),
        "ImageDescription": ImageManifestRow.get("ImageDescription", ""),
        "FieldStrength": ImageManifestRow.get("FieldStrength", ""),
        "Weighting": ImageManifestRow.get("Weighting", ""),
        "AcquisitionType": ImageManifestRow.get("AcquisitionType", ""),
        "AcquisitionPlane": ImageManifestRow.get("AcquisitionPlane", ""),
        "Manufacturer": ImageManifestRow.get("Manufacturer", ""),
        "ScannerModel": ImageManifestRow.get("ScannerModel", ""),
        "MprageRank": ImageManifestRow.get("MprageRank", ""),
        "InStandardised3TList": ImageManifestRow.get("InStandardised3TList", ""),
        "IdaMetadataMatchCount": ImageManifestRow.get("IdaMetadataMatchCount", ""),
        "Mri3MetaMatchCount": ImageManifestRow.get("Mri3MetaMatchCount", ""),
        "MriQcMatchCount": ImageManifestRow.get("MriQcMatchCount", ""),
        "MprageRankMatchCount": ImageManifestRow.get("MprageRankMatchCount", ""),
        "ImageFileName": ImageManifestRow.get("ImageFileName", ""),
        "ImageRelativePath": ImageManifestRow.get("ImageRelativePath", ""),
        "ImageDirectory": ImageManifestRow.get("ImageDirectory", ""),
        "ImageSizeMegabytes": ImageManifestRow.get("ImageSizeMegabytes", ""),
        "LinkStatus": LinkStatus,
    }


def BuildImageClinicalLinkageRows(
    ImageManifestRows: list[dict[str, str]],
    ClinicalVisitRows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Link every image row to the nearest same-subject clinical visit."""
    ClinicalVisitsBySubject = BuildClinicalVisitsBySubject(ClinicalVisitRows)
    LinkedRows: list[dict[str, object]] = []

    for ImageManifestRow in ImageManifestRows:
        ClinicalVisitRow, DaysBetweenImageAndClinicalVisit, LinkStatus = FindNearestClinicalVisit(
            ImageManifestRow=ImageManifestRow,
            ClinicalVisitsBySubject=ClinicalVisitsBySubject,
        )

        LinkedRows.append(
            BuildLinkedRow(
                ImageManifestRow=ImageManifestRow,
                ClinicalVisitRow=ClinicalVisitRow,
                DaysBetweenImageAndClinicalVisit=DaysBetweenImageAndClinicalVisit,
                LinkStatus=LinkStatus,
            )
        )

    return LinkedRows


def CountRowsWithField(DataRows: list[dict[str, object]], FieldName: str) -> int:
    return sum(1 for DataRow in DataRows if NormaliseText(DataRow.get(FieldName, "")))


def CountValueOccurrences(DataRows: list[dict[str, object]], FieldName: str) -> dict[str, int]:
    """Count values in one output field."""
    ValueCounts: dict[str, int] = {}

    for DataRow in DataRows:
        FieldValue = NormaliseText(DataRow.get(FieldName, "")) or "Missing"
        ValueCounts[FieldValue] = ValueCounts.get(FieldValue, 0) + 1

    return ValueCounts


def FormatValueCounts(ValueCounts: dict[str, int]) -> str:
    """Format value counts as a compact semicolon-separated string."""
    return "; ".join(f"{Value}: {Count}" for Value, Count in sorted(ValueCounts.items()))


def CalculateMaximumAbsoluteDaysForLinkedRows(LinkedRows: list[dict[str, object]]) -> str:
    """Calculate the maximum image-clinical date distance among linked rows."""
    AbsoluteDayValues: list[int] = []

    for LinkedRow in LinkedRows:
        if LinkedRow.get("LinkStatus") != "Linked":
            continue

        AbsoluteDaysValue = NormaliseText(LinkedRow.get("AbsoluteDaysBetweenImageAndClinicalVisit", ""))

        if not AbsoluteDaysValue:
            continue

        try:
            AbsoluteDayValues.append(int(AbsoluteDaysValue))
        except ValueError:
            continue

    if not AbsoluteDayValues:
        return ""

    return str(max(AbsoluteDayValues))


def BuildSummaryRows(LinkedRows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build summary metrics for the image-clinical linkage output."""
    LinkStatusCounts = CountValueOccurrences(LinkedRows, "LinkStatus")

    return [
        {"Metric": "ImageRows", "Value": len(LinkedRows)},
        {"Metric": "LinkedRowsWithinAllowedWindow", "Value": LinkStatusCounts.get("Linked", 0)},
        {
            "Metric": "NearestClinicalVisitOutsideAllowedWindow",
            "Value": LinkStatusCounts.get("NearestClinicalVisitOutsideAllowedWindow", 0),
        },
        {"Metric": "NoClinicalVisitsForSubject", "Value": LinkStatusCounts.get("NoClinicalVisitsForSubject", 0)},
        {
            "Metric": "MissingOrInvalidImageStudyDate",
            "Value": LinkStatusCounts.get("MissingOrInvalidImageStudyDate", 0),
        },
        {"Metric": "MissingImageSubjectId", "Value": LinkStatusCounts.get("MissingImageSubjectId", 0)},
        {
            "Metric": "NoClinicalVisitsWithValidExamDate",
            "Value": LinkStatusCounts.get("NoClinicalVisitsWithValidExamDate", 0),
        },
        {"Metric": "RowsWithRID", "Value": CountRowsWithField(LinkedRows, "RID")},
        {"Metric": "RowsWithAge", "Value": CountRowsWithField(LinkedRows, "Age")},
        {"Metric": "RowsWithDiagnosis3Class", "Value": CountRowsWithField(LinkedRows, "Diagnosis3Class")},
        {"Metric": "RowsWithMMSE", "Value": CountRowsWithField(LinkedRows, "MMSE")},
        {"Metric": "RowsWithADAS13", "Value": CountRowsWithField(LinkedRows, "ADAS13")},
        {"Metric": "RowsWithCDRSB", "Value": CountRowsWithField(LinkedRows, "CDRSB")},
        {"Metric": "RowsWithFAQ", "Value": CountRowsWithField(LinkedRows, "FAQ")},
        {
            "Metric": "MaximumAbsoluteDaysAmongLinkedRows",
            "Value": CalculateMaximumAbsoluteDaysForLinkedRows(LinkedRows),
        },
        {"Metric": "LinkStatusCounts", "Value": FormatValueCounts(LinkStatusCounts)},
        {
            "Metric": "Diagnosis3ClassCounts",
            "Value": FormatValueCounts(CountValueOccurrences(LinkedRows, "Diagnosis3Class")),
        },
    ]


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRows: list[dict[str, object]]) -> None:
    """Write a brief Markdown summary for the image-clinical linkage build."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# Image-Clinical Linkage Summary\n\n")
        OutputFile.write(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`\n\n")
        OutputFile.write(f"Allowed matching window: `±{MaximumAllowedDaysBetweenImageAndClinicalVisit} days`\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def ParseArguments() -> argparse.Namespace:
    """Parse command-line arguments for image-clinical linkage."""
    ArgumentParser = argparse.ArgumentParser(
        description="Link image manifest rows to nearest same-subject clinical visits."
    )

    ArgumentParser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data"),
        help="Path to the repository Data directory. Default: Data",
    )

    ArgumentParser.add_argument(
        "--image-manifest",
        type=Path,
        default=Path("Data") / "Interim" / "Imaging" / "ImageManifest.csv",
        help="Path to ImageManifest.csv.",
    )

    ArgumentParser.add_argument(
        "--clinical-visits",
        type=Path,
        default=Path("Data") / "Interim" / "Clinical" / "ClinicalVisits.csv",
        help="Path to ClinicalVisits.csv.",
    )

    ArgumentParser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("Data") / "Interim" / "Linkage",
        help="Directory for linkage outputs. Default: Data/Interim/Linkage",
    )

    return ArgumentParser.parse_args()


def Main() -> None:
    Arguments = ParseArguments()

    OutputDirectory = Arguments.output_directory
    EnsureDirectory(OutputDirectory)

    ImageManifestRows = ReadCsvRows(Arguments.image_manifest)
    ClinicalVisitRows = ReadCsvRows(Arguments.clinical_visits)

    LinkedRows = BuildImageClinicalLinkageRows(
        ImageManifestRows=ImageManifestRows,
        ClinicalVisitRows=ClinicalVisitRows,
    )

    SummaryRows = BuildSummaryRows(LinkedRows)

    WriteCsv(
        OutputFilePath=OutputDirectory / "ImageClinicalLinkage.csv",
        FieldNames=OutputFieldNames,
        DataRows=LinkedRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ImageClinicalLinkageSummary.csv",
        FieldNames=["Metric", "Value"],
        DataRows=SummaryRows,
    )

    WriteMarkdownSummary(
        OutputFilePath=OutputDirectory / "ImageClinicalLinkageSummary.md",
        SummaryRows=SummaryRows,
    )

    print("Image-clinical linkage build complete.")
    print(f"Output directory: {OutputDirectory}")
    print(f"Linked image rows: {len(LinkedRows)}")


if __name__ == "__main__":
    Main()