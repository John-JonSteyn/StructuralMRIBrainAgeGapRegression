"""Select one baseline-linked MRI row per ADNI participant.

Reads ImageClinicalLinkage.csv and writes a one-row-per-participant baseline
cohort table to Data/Interim/Cohort/.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path


RequiredOutputFields = [
    "RID",
    "SubjectId",
    "ImageId",
    "ImageIdKey",
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
    "QcStatus",
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
    "SelectionPriority",
    "SelectionReason",
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


def ParseInteger(IntegerValue: object, DefaultValue: int) -> int:
    """Parse an integer-like value and return a default when parsing fails."""
    IntegerText = NormaliseText(IntegerValue)

    if not IntegerText:
        return DefaultValue

    try:
        return int(float(IntegerText))
    except ValueError:
        return DefaultValue


def ParseFloat(FloatValue: object, DefaultValue: float) -> float:
    """Parse a float-like value and return a default when parsing fails."""
    FloatText = NormaliseText(FloatValue)

    if not FloatText:
        return DefaultValue

    try:
        return float(FloatText)
    except ValueError:
        return DefaultValue


def ParseBoolean(BooleanValue: object) -> bool:
    """Parse common text representations of booleans."""
    BooleanText = NormaliseText(BooleanValue).upper()

    return BooleanText in {"TRUE", "1", "YES", "Y"}


def IsBaselineLikeVisit(VisitCode: object, VisitCode2: object) -> bool:
    """Identify screening, baseline, and initial visit codes."""
    VisitCodeText = NormaliseText(VisitCode).lower()
    VisitCode2Text = NormaliseText(VisitCode2).lower()
    CombinedVisitText = f"{VisitCodeText} {VisitCode2Text}"

    BaselineTerms = [
        "bl",
        "sc",
        "screen",
        "screening",
        "baseline",
        "init",
        "initial",
    ]

    return any(BaselineTerm in CombinedVisitText for BaselineTerm in BaselineTerms)


def CountAvailableCognitiveScores(LinkedRow: dict[str, str]) -> int:
    """Count available cognitive or functional outcome fields for tie-breaking."""
    CognitiveFieldNames = ["MMSE", "ADAS11", "ADAS13", "CDRSB", "FAQ"]

    return sum(1 for CognitiveFieldName in CognitiveFieldNames if NormaliseText(LinkedRow.get(CognitiveFieldName, "")))


def RowHasRequiredAnalysisFields(LinkedRow: dict[str, str]) -> bool:
    """Check whether a linked row has the required minimum cohort fields."""
    RequiredFieldNames = ["RID", "SubjectId", "ImageId", "ImageStudyDate", "ClinicalExamDate", "Age", "Diagnosis3Class"]

    return all(NormaliseText(LinkedRow.get(RequiredFieldName, "")) for RequiredFieldName in RequiredFieldNames)


def RowIsEligibleForBaselineCohort(LinkedRow: dict[str, str]) -> bool:
    """Apply the minimum eligibility criteria before participant-level selection."""
    if NormaliseText(LinkedRow.get("LinkStatus", "")) != "Linked":
        return False

    if not RowHasRequiredAnalysisFields(LinkedRow):
        return False

    if not IsBaselineLikeVisit(
        VisitCode=LinkedRow.get("VisitCode", ""),
        VisitCode2=LinkedRow.get("VisitCode2", ""),
    ):
        return False

    return True


def BuildSelectionSortKey(LinkedRow: dict[str, str]) -> tuple[int, int, int, int, float, str]:
    """Rank candidate rows so the best baseline image is selected first."""
    InStandardised3TListPriority = 0 if ParseBoolean(LinkedRow.get("InStandardised3TList", "")) else 1
    AbsoluteDateDifference = ParseInteger(
        IntegerValue=LinkedRow.get("AbsoluteDaysBetweenImageAndClinicalVisit", ""),
        DefaultValue=999999,
    )
    CognitiveCompletenessPriority = -CountAvailableCognitiveScores(LinkedRow)
    MprageRankValue = ParseInteger(
        IntegerValue=LinkedRow.get("MprageRank", ""),
        DefaultValue=999999,
    )
    ImageSizeMegabytes = -ParseFloat(
        FloatValue=LinkedRow.get("ImageSizeMegabytes", ""),
        DefaultValue=0.0,
    )
    ImageId = NormaliseText(LinkedRow.get("ImageId", ""))

    return (
        InStandardised3TListPriority,
        AbsoluteDateDifference,
        CognitiveCompletenessPriority,
        MprageRankValue,
        ImageSizeMegabytes,
        ImageId,
    )


def BuildSelectionReason(LinkedRow: dict[str, str]) -> str:
    """Create a compact reason string for the selected participant row."""
    ReasonParts = [
        "LinkStatus=Linked",
        "RequiredFieldsPresent",
        "BaselineLikeVisit",
        f"InStandardised3TList={NormaliseText(LinkedRow.get('InStandardised3TList', ''))}",
        (
            "AbsoluteDaysBetweenImageAndClinicalVisit="
            f"{NormaliseText(LinkedRow.get('AbsoluteDaysBetweenImageAndClinicalVisit', ''))}"
        ),
        f"AvailableCognitiveScores={CountAvailableCognitiveScores(LinkedRow)}",
    ]

    MprageRank = NormaliseText(LinkedRow.get("MprageRank", ""))

    if MprageRank:
        ReasonParts.append(f"MprageRank={MprageRank}")

    return "; ".join(ReasonParts)


def GroupRowsByRid(LinkedRows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group linked rows by ADNI RID."""
    RowsByRid: dict[str, list[dict[str, str]]] = {}

    for LinkedRow in LinkedRows:
        RidValue = NormaliseText(LinkedRow.get("RID", ""))

        if not RidValue:
            continue

        if RidValue not in RowsByRid:
            RowsByRid[RidValue] = []

        RowsByRid[RidValue].append(LinkedRow)

    return RowsByRid


def SelectOneBaselineRowPerParticipant(LinkedRows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Select the highest-ranked eligible baseline row for each participant."""
    EligibleRows = [LinkedRow for LinkedRow in LinkedRows if RowIsEligibleForBaselineCohort(LinkedRow)]
    EligibleRowsByRid = GroupRowsByRid(EligibleRows)

    SelectedRows: list[dict[str, object]] = []

    for RidValue, CandidateRowsForRid in sorted(EligibleRowsByRid.items()):
        SortedCandidateRows = sorted(CandidateRowsForRid, key=BuildSelectionSortKey)
        SelectedRow = dict(SortedCandidateRows[0])

        SelectedRow["SelectionPriority"] = 1
        SelectedRow["SelectionReason"] = BuildSelectionReason(SortedCandidateRows[0])

        SelectedRows.append(SelectedRow)

    return SelectedRows


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


def CountEligibleRows(LinkedRows: list[dict[str, str]]) -> int:
    """Count linked rows satisfying the minimum baseline-cohort criteria."""
    return sum(1 for LinkedRow in LinkedRows if RowIsEligibleForBaselineCohort(LinkedRow))


def CountUniqueRidValues(DataRows: list[dict[str, object]]) -> int:
    """Count unique non-empty RID values."""
    return len(
        {
            NormaliseText(DataRow.get("RID", ""))
            for DataRow in DataRows
            if NormaliseText(DataRow.get("RID", ""))
        }
    )


def CalculateMaximumAbsoluteDays(DataRows: list[dict[str, object]]) -> str:
    """Calculate the maximum image-clinical date difference in selected rows."""
    AbsoluteDayValues: list[int] = []

    for DataRow in DataRows:
        AbsoluteDaysText = NormaliseText(DataRow.get("AbsoluteDaysBetweenImageAndClinicalVisit", ""))

        if not AbsoluteDaysText:
            continue

        try:
            AbsoluteDayValues.append(int(float(AbsoluteDaysText)))
        except ValueError:
            continue

    if not AbsoluteDayValues:
        return ""

    return str(max(AbsoluteDayValues))


def CalculateMedianAbsoluteDays(DataRows: list[dict[str, object]]) -> str:
    """Calculate the median image-clinical date difference in selected rows."""
    AbsoluteDayValues: list[int] = []

    for DataRow in DataRows:
        AbsoluteDaysText = NormaliseText(DataRow.get("AbsoluteDaysBetweenImageAndClinicalVisit", ""))

        if not AbsoluteDaysText:
            continue

        try:
            AbsoluteDayValues.append(int(float(AbsoluteDaysText)))
        except ValueError:
            continue

    if not AbsoluteDayValues:
        return ""

    SortedAbsoluteDayValues = sorted(AbsoluteDayValues)
    MiddleIndex = len(SortedAbsoluteDayValues) // 2

    if len(SortedAbsoluteDayValues) % 2 == 1:
        return str(SortedAbsoluteDayValues[MiddleIndex])

    MedianValue = (SortedAbsoluteDayValues[MiddleIndex - 1] + SortedAbsoluteDayValues[MiddleIndex]) / 2

    return f"{MedianValue:.1f}"


def BuildSummaryRows(
    LinkedRows: list[dict[str, str]],
    SelectedRows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build summary metrics for the selected baseline cohort."""
    LinkStatusCounts = CountValueOccurrences(LinkedRows, "LinkStatus")
    DiagnosisCounts = CountValueOccurrences(SelectedRows, "Diagnosis3Class")

    return [
        {"Metric": "InputImageClinicalRows", "Value": len(LinkedRows)},
        {"Metric": "LinkedRowsWithinAllowedWindow", "Value": LinkStatusCounts.get("Linked", 0)},
        {"Metric": "EligibleBaselineRows", "Value": CountEligibleRows(LinkedRows)},
        {"Metric": "SelectedParticipantRows", "Value": len(SelectedRows)},
        {"Metric": "UniqueRidCount", "Value": CountUniqueRidValues(SelectedRows)},
        {"Metric": "RowsWithAge", "Value": CountRowsWithField(SelectedRows, "Age")},
        {"Metric": "RowsWithSex", "Value": CountRowsWithField(SelectedRows, "Sex")},
        {"Metric": "RowsWithEducation", "Value": CountRowsWithField(SelectedRows, "Education")},
        {"Metric": "RowsWithDiagnosis3Class", "Value": CountRowsWithField(SelectedRows, "Diagnosis3Class")},
        {"Metric": "RowsWithMMSE", "Value": CountRowsWithField(SelectedRows, "MMSE")},
        {"Metric": "RowsWithADAS13", "Value": CountRowsWithField(SelectedRows, "ADAS13")},
        {"Metric": "RowsWithCDRSB", "Value": CountRowsWithField(SelectedRows, "CDRSB")},
        {"Metric": "RowsWithFAQ", "Value": CountRowsWithField(SelectedRows, "FAQ")},
        {
            "Metric": "RowsInStandardised3TList",
            "Value": sum(1 for SelectedRow in SelectedRows if ParseBoolean(SelectedRow.get("InStandardised3TList", ""))),
        },
        {"Metric": "MaximumAbsoluteDays", "Value": CalculateMaximumAbsoluteDays(SelectedRows)},
        {"Metric": "MedianAbsoluteDays", "Value": CalculateMedianAbsoluteDays(SelectedRows)},
        {"Metric": "Diagnosis3ClassCounts", "Value": FormatValueCounts(DiagnosisCounts)},
    ]


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRows: list[dict[str, object]]) -> None:
    """Write a brief Markdown summary for the selected baseline cohort."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# Selected Baseline Cohort Summary\n\n")
        OutputFile.write(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def ParseArguments() -> argparse.Namespace:
    """Parse command-line arguments for baseline cohort selection."""
    ArgumentParser = argparse.ArgumentParser(
        description="Select one baseline-linked MRI row per ADNI participant."
    )

    ArgumentParser.add_argument(
        "--image-clinical-linkage",
        type=Path,
        default=Path("Data") / "Interim" / "Linkage" / "ImageClinicalLinkage.csv",
        help="Path to ImageClinicalLinkage.csv.",
    )

    ArgumentParser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("Data") / "Interim" / "Cohort",
        help="Directory for selected cohort outputs. Default: Data/Interim/Cohort",
    )

    return ArgumentParser.parse_args()


def Main() -> None:
    Arguments = ParseArguments()

    OutputDirectory = Arguments.output_directory
    EnsureDirectory(OutputDirectory)

    LinkedRows = ReadCsvRows(Arguments.image_clinical_linkage)
    SelectedRows = SelectOneBaselineRowPerParticipant(LinkedRows)
    SummaryRows = BuildSummaryRows(
        LinkedRows=LinkedRows,
        SelectedRows=SelectedRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "SelectedBaselineCohort.csv",
        FieldNames=RequiredOutputFields,
        DataRows=SelectedRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "SelectedBaselineCohortSummary.csv",
        FieldNames=["Metric", "Value"],
        DataRows=SummaryRows,
    )

    WriteMarkdownSummary(
        OutputFilePath=OutputDirectory / "SelectedBaselineCohortSummary.md",
        SummaryRows=SummaryRows,
    )

    print("Selected baseline cohort build complete.")
    print(f"Output directory: {OutputDirectory}")
    print(f"Selected participant rows: {len(SelectedRows)}")


if __name__ == "__main__":
    Main()