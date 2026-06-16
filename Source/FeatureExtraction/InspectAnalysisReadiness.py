"""Inspect FastSurfer completion and cohort readiness before modelling."""

from __future__ import annotations

import csv
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


PrepareFastSurferInputsScriptPath = Path("Source") / "FeatureExtraction" / "PrepareFastSurferInputs.py"

SelectedBaselineCohortPath = Path("Data") / "Interim" / "Cohort" / "SelectedBaselineCohort.csv"
FastSurferInputManifestPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferInputManifest.csv"
FastSurferOutputRootDirectory = Path("Data") / "Processed" / "FastSurfer"

OutputDirectory = Path("Data") / "Processed" / "QualityControl"
AnalysisReadinessSummaryPath = OutputDirectory / "AnalysisReadinessSummary.csv"
AnalysisReadinessMarkdownSummaryPath = OutputDirectory / "AnalysisReadinessSummary.md"
DiagnosisCountsPath = OutputDirectory / "DiagnosisCounts.csv"
DiagnosisFastSurferStatusCountsPath = OutputDirectory / "DiagnosisFastSurferStatusCounts.csv"
CognitiveCoveragePath = OutputDirectory / "CognitiveCoverage.csv"
CohortDuplicateRowsPath = OutputDirectory / "CohortDuplicateRows.csv"
FastSurferIncompleteRowsPath = OutputDirectory / "FastSurferIncompleteRows.csv"
QcFlaggedRowsPath = OutputDirectory / "QcFlaggedRows.csv"
QcFieldInventoryPath = OutputDirectory / "QcFieldInventory.csv"
AgeDateCheckRowsPath = OutputDirectory / "AgeDateChecks.csv"
ColumnInventoryPath = OutputDirectory / "AnalysisReadinessColumnInventory.csv"

RequiredStatsFileNames = [
    "aseg.stats",
    "brainvol.stats",
    "lh.aparc.DKTatlas.mapped.stats",
    "rh.aparc.DKTatlas.mapped.stats",
    "wmparc.DKTatlas.mapped.stats",
]

RequiredCohortFields = [
    "RID",
    "ImageId",
    "Age",
    "Diagnosis3Class",
    "ImageStudyDate",
]

CognitiveMeasureFieldCandidates = {
    "MMSE": ["MMSE", "MMSCORE", "MMSEScore"],
    "ADAS13": ["ADAS13", "ADAS13Score"],
    "CDRSB": ["CDRSB", "CDRSumOfBoxes"],
    "FAQ": ["FAQ", "FAQScore"],
}

ImageStudyDateFieldCandidates = [
    "ImageStudyDate",
    "StudyDate",
    "MRIStudyDate",
]

ClinicalDateFieldCandidates = [
    "ExamDate",
    "ClinicalExamDate",
    "VisitDate",
    "EXAMDATE",
]

BirthYearFieldCandidates = [
    "BirthYear",
    "PTDOBYY",
    "YearOfBirth",
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


def RunPrepareFastSurferInputs() -> None:
    """Regenerate the FastSurfer input manifest before checking status."""
    if not PrepareFastSurferInputsScriptPath.exists():
        raise FileNotFoundError(f"Script not found: {PrepareFastSurferInputsScriptPath}")

    subprocess.run(
        [sys.executable, str(PrepareFastSurferInputsScriptPath)],
        check=True,
    )


def ValidateInputs() -> None:
    if not SelectedBaselineCohortPath.exists():
        raise FileNotFoundError(f"Selected cohort file not found: {SelectedBaselineCohortPath}")

    if not FastSurferInputManifestPath.exists():
        raise FileNotFoundError(f"FastSurfer manifest file not found: {FastSurferInputManifestPath}")


def GetHeaders(DataRows: list[dict[str, str]]) -> list[str]:
    if not DataRows:
        return []

    return list(DataRows[0].keys())


def GetFirstExistingField(Headers: list[str], CandidateFields: list[str]) -> str:
    HeaderLookup = {Header.lower(): Header for Header in Headers}

    for CandidateField in CandidateFields:
        MatchingHeader = HeaderLookup.get(CandidateField.lower())

        if MatchingHeader:
            return MatchingHeader

    return ""


def FieldIsPresent(DataRow: dict[str, str], FieldName: str) -> bool:
    return bool(NormaliseText(DataRow.get(FieldName, "")))


def ParseDate(DateText: str) -> datetime | None:
    DateText = NormaliseText(DateText)

    if not DateText:
        return None

    DateFormats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m-%d-%Y",
    ]

    for DateFormat in DateFormats:
        try:
            return datetime.strptime(DateText, DateFormat)
        except ValueError:
            continue

    return None


def ParseFloat(NumberText: str) -> float | None:
    NumberText = NormaliseText(NumberText)

    if not NumberText:
        return None

    try:
        return float(NumberText)
    except ValueError:
        return None


def GetSubjectOutputDirectory(FastSurferSubjectId: str) -> Path:
    return FastSurferOutputRootDirectory / FastSurferSubjectId


def GetStatsDirectory(FastSurferSubjectId: str) -> Path:
    return GetSubjectOutputDirectory(FastSurferSubjectId) / "stats"


def GetMissingRequiredStatsFiles(FastSurferSubjectId: str) -> list[str]:
    StatsDirectory = GetStatsDirectory(FastSurferSubjectId)
    MissingStatsFileNames: list[str] = []

    for RequiredStatsFileName in RequiredStatsFileNames:
        RequiredStatsFilePath = StatsDirectory / RequiredStatsFileName

        if not RequiredStatsFilePath.exists():
            MissingStatsFileNames.append(RequiredStatsFileName)

    return MissingStatsFileNames


def GetFastSurferStatus(FastSurferSubjectId: str) -> str:
    SubjectOutputDirectory = GetSubjectOutputDirectory(FastSurferSubjectId)
    MissingRequiredStatsFiles = GetMissingRequiredStatsFiles(FastSurferSubjectId)

    if len(MissingRequiredStatsFiles) == 0:
        return "Complete"

    if SubjectOutputDirectory.exists():
        return "Incomplete"

    return "NotStarted"


def CountByField(DataRows: list[dict[str, str]], FieldName: str) -> dict[str, int]:
    ValueCounter: Counter[str] = Counter()

    for DataRow in DataRows:
        FieldValue = NormaliseText(DataRow.get(FieldName, "")) or "Missing"
        ValueCounter[FieldValue] += 1

    return dict(sorted(ValueCounter.items()))


def CountByFields(DataRows: list[dict[str, object]], FieldNames: list[str]) -> dict[str, int]:
    ValueCounter: Counter[str] = Counter()

    for DataRow in DataRows:
        FieldValues = [NormaliseText(DataRow.get(FieldName, "")) or "Missing" for FieldName in FieldNames]
        CountKey = ", ".join(FieldValues)
        ValueCounter[CountKey] += 1

    return dict(sorted(ValueCounter.items()))


def BuildCountRows(CountName: str, ValueCounts: dict[str, int]) -> list[dict[str, object]]:
    return [
        {
            "CountName": CountName,
            "Value": Value,
            "Count": Count,
        }
        for Value, Count in ValueCounts.items()
    ]


def BuildDuplicateRows(DataRows: list[dict[str, str]], FieldName: str) -> list[dict[str, object]]:
    FieldValueCounts = Counter(NormaliseText(DataRow.get(FieldName, "")) for DataRow in DataRows)
    DuplicateRows: list[dict[str, object]] = []

    for RowIndex, DataRow in enumerate(DataRows, start=1):
        FieldValue = NormaliseText(DataRow.get(FieldName, ""))

        if FieldValue and FieldValueCounts[FieldValue] > 1:
            DuplicateRow = {"RowNumber": RowIndex, "DuplicateField": FieldName, "DuplicateValue": FieldValue}
            DuplicateRow.update(DataRow)
            DuplicateRows.append(DuplicateRow)

    return DuplicateRows


def BuildFastSurferStatusRows(FastSurferManifestRows: list[dict[str, str]]) -> list[dict[str, object]]:
    StatusRows: list[dict[str, object]] = []

    for RowIndex, ManifestRow in enumerate(FastSurferManifestRows, start=1):
        FastSurferSubjectId = NormaliseText(ManifestRow.get("FastSurferSubjectId", ""))
        MissingRequiredStatsFiles = GetMissingRequiredStatsFiles(FastSurferSubjectId)
        FastSurferStatus = GetFastSurferStatus(FastSurferSubjectId)

        StatusRows.append(
            {
                "RowNumber": RowIndex,
                "RID": ManifestRow.get("RID", ""),
                "SubjectId": ManifestRow.get("SubjectId", ""),
                "ImageId": ManifestRow.get("ImageId", ""),
                "Diagnosis3Class": ManifestRow.get("Diagnosis3Class", ""),
                "FastSurferSubjectId": FastSurferSubjectId,
                "FastSurferStatus": FastSurferStatus,
                "MissingRequiredStatsFiles": "; ".join(MissingRequiredStatsFiles),
                "FastSurferOutputDirectory": str(GetSubjectOutputDirectory(FastSurferSubjectId)),
            }
        )

    return StatusRows


def BuildCognitiveCoverageRows(CohortRows: list[dict[str, str]]) -> list[dict[str, object]]:
    Headers = GetHeaders(CohortRows)
    CoverageRows: list[dict[str, object]] = []

    for MeasureName, CandidateFields in CognitiveMeasureFieldCandidates.items():
        FieldName = GetFirstExistingField(Headers, CandidateFields)

        if not FieldName:
            CoverageRows.append(
                {
                    "Measure": MeasureName,
                    "FieldName": "",
                    "RowsWithValue": 0,
                    "RowsMissingValue": len(CohortRows),
                    "CoveragePercent": 0,
                    "FieldFound": False,
                }
            )
            continue

        RowsWithValue = sum(1 for CohortRow in CohortRows if FieldIsPresent(CohortRow, FieldName))
        RowsMissingValue = len(CohortRows) - RowsWithValue
        CoveragePercent = round((RowsWithValue / len(CohortRows)) * 100, 2) if CohortRows else 0

        CoverageRows.append(
            {
                "Measure": MeasureName,
                "FieldName": FieldName,
                "RowsWithValue": RowsWithValue,
                "RowsMissingValue": RowsMissingValue,
                "CoveragePercent": CoveragePercent,
                "FieldFound": True,
            }
        )

    return CoverageRows


def FieldLooksLikeQcStatusField(FieldName: str) -> bool:
    FieldName = FieldName.lower()

    ExcludedTerms = [
        "matchcount",
        "match_count",
        "count",
        "matched",
        "sourcefile",
        "source_file",
        "path",
        "directory",
        "id",
    ]

    if any(ExcludedTerm in FieldName for ExcludedTerm in ExcludedTerms):
        return False

    IncludedTerms = [
        "qc",
        "quality",
        "pass",
        "fail",
        "usable",
        "selected",
    ]

    return any(IncludedTerm in FieldName for IncludedTerm in IncludedTerms)


def FindQcFields(Headers: list[str]) -> list[str]:
    QcFields: list[str] = []

    for Header in Headers:
        if FieldLooksLikeQcStatusField(Header):
            QcFields.append(Header)

    return QcFields


def ValueLooksQcFailed(Value: str) -> bool:
    Value = NormaliseText(Value).lower()

    if not Value:
        return False

    FailedTerms = [
        "fail",
        "failed",
        "unusable",
        "reject",
        "rejected",
        "exclude",
        "excluded",
        "bad",
        "no",
        "0",
        "false",
    ]

    PassedTerms = [
        "pass",
        "passed",
        "usable",
        "include",
        "included",
        "good",
        "yes",
        "1",
        "true",
    ]

    if Value in PassedTerms:
        return False

    return any(FailedTerm in Value for FailedTerm in FailedTerms)


def BuildQcFieldInventoryRows(CohortRows: list[dict[str, str]]) -> list[dict[str, object]]:
    Headers = GetHeaders(CohortRows)
    QcFields = FindQcFields(Headers)
    QcFieldInventoryRows: list[dict[str, object]] = []

    for QcField in QcFields:
        ValueCounts = CountByField(CohortRows, QcField)

        for FieldValue, Count in ValueCounts.items():
            QcFieldInventoryRows.append(
                {
                    "QcField": QcField,
                    "Value": FieldValue,
                    "Count": Count,
                }
            )

    return QcFieldInventoryRows


def BuildQcFlaggedRows(CohortRows: list[dict[str, str]]) -> list[dict[str, object]]:
    Headers = GetHeaders(CohortRows)
    QcFields = FindQcFields(Headers)
    QcFlaggedRows: list[dict[str, object]] = []

    for RowIndex, CohortRow in enumerate(CohortRows, start=1):
        FailedQcFields = []

        for QcField in QcFields:
            QcValue = NormaliseText(CohortRow.get(QcField, ""))

            if ValueLooksQcFailed(QcValue):
                FailedQcFields.append(f"{QcField}={QcValue}")

        if FailedQcFields:
            QcFlaggedRows.append(
                {
                    "RowNumber": RowIndex,
                    "RID": CohortRow.get("RID", ""),
                    "SubjectId": CohortRow.get("SubjectId", ""),
                    "ImageId": CohortRow.get("ImageId", ""),
                    "Diagnosis3Class": CohortRow.get("Diagnosis3Class", ""),
                    "FailedQcFields": "; ".join(FailedQcFields),
                }
            )

    return QcFlaggedRows


def BuildAgeDateCheckRows(CohortRows: list[dict[str, str]]) -> list[dict[str, object]]:
    Headers = GetHeaders(CohortRows)
    AgeField = GetFirstExistingField(Headers, ["Age"])
    ImageStudyDateField = GetFirstExistingField(Headers, ImageStudyDateFieldCandidates)
    ClinicalDateField = GetFirstExistingField(Headers, ClinicalDateFieldCandidates)
    BirthYearField = GetFirstExistingField(Headers, BirthYearFieldCandidates)

    AgeDateCheckRows: list[dict[str, object]] = []

    for RowIndex, CohortRow in enumerate(CohortRows, start=1):
        AgeValue = ParseFloat(CohortRow.get(AgeField, "")) if AgeField else None
        ImageStudyDate = ParseDate(CohortRow.get(ImageStudyDateField, "")) if ImageStudyDateField else None
        ClinicalDate = ParseDate(CohortRow.get(ClinicalDateField, "")) if ClinicalDateField else None
        BirthYearValue = ParseFloat(CohortRow.get(BirthYearField, "")) if BirthYearField else None

        ImageClinicalDateDifferenceDays = ""
        ApproximateImageAgeFromBirthYear = ""
        AgeMinusApproximateImageAge = ""

        if ImageStudyDate is not None and ClinicalDate is not None:
            ImageClinicalDateDifferenceDays = (ImageStudyDate - ClinicalDate).days

        if ImageStudyDate is not None and BirthYearValue is not None:
            ApproximateImageAgeFromBirthYear = ImageStudyDate.year - int(BirthYearValue)

            if AgeValue is not None:
                AgeMinusApproximateImageAge = round(AgeValue - ApproximateImageAgeFromBirthYear, 4)

        AgeDateCheckRows.append(
            {
                "RowNumber": RowIndex,
                "RID": CohortRow.get("RID", ""),
                "SubjectId": CohortRow.get("SubjectId", ""),
                "ImageId": CohortRow.get("ImageId", ""),
                "Diagnosis3Class": CohortRow.get("Diagnosis3Class", ""),
                "AgeField": AgeField,
                "Age": CohortRow.get(AgeField, "") if AgeField else "",
                "ImageStudyDateField": ImageStudyDateField,
                "ImageStudyDate": CohortRow.get(ImageStudyDateField, "") if ImageStudyDateField else "",
                "ClinicalDateField": ClinicalDateField,
                "ClinicalDate": CohortRow.get(ClinicalDateField, "") if ClinicalDateField else "",
                "BirthYearField": BirthYearField,
                "BirthYear": CohortRow.get(BirthYearField, "") if BirthYearField else "",
                "ImageClinicalDateDifferenceDays": ImageClinicalDateDifferenceDays,
                "ApproximateImageAgeFromBirthYear": ApproximateImageAgeFromBirthYear,
                "AgeMinusApproximateImageAge": AgeMinusApproximateImageAge,
            }
        )

    return AgeDateCheckRows


def BuildColumnInventoryRows(CohortRows: list[dict[str, str]], ManifestRows: list[dict[str, str]]) -> list[dict[str, object]]:
    ColumnInventoryRows: list[dict[str, object]] = []

    for SourceName, DataRows in [("SelectedBaselineCohort", CohortRows), ("FastSurferInputManifest", ManifestRows)]:
        for ColumnName in GetHeaders(DataRows):
            RowsWithValue = sum(1 for DataRow in DataRows if FieldIsPresent(DataRow, ColumnName))
            ColumnInventoryRows.append(
                {
                    "Source": SourceName,
                    "ColumnName": ColumnName,
                    "RowsWithValue": RowsWithValue,
                    "RowsMissingValue": len(DataRows) - RowsWithValue,
                }
            )

    return ColumnInventoryRows


def BuildSummaryRows(
    CohortRows: list[dict[str, str]],
    ManifestRows: list[dict[str, str]],
    FastSurferStatusRows: list[dict[str, object]],
    CognitiveCoverageRows: list[dict[str, object]],
    QcFlaggedRows: list[dict[str, object]],
    QcFieldInventoryRows: list[dict[str, object]],
    AgeDateCheckRows: list[dict[str, object]],
    DuplicateRidRows: list[dict[str, object]],
    DuplicateImageRows: list[dict[str, object]],
) -> list[dict[str, object]]:
    CohortDiagnosisCounts = CountByField(CohortRows, "Diagnosis3Class")
    ManifestDiagnosisCounts = CountByField(ManifestRows, "Diagnosis3Class")
    FastSurferStatusCounts = CountByFields(FastSurferStatusRows, ["FastSurferStatus"])
    DiagnosisStatusCounts = CountByFields(FastSurferStatusRows, ["Diagnosis3Class", "FastSurferStatus"])

    RequiredFieldPresence = {
        RequiredField: sum(1 for CohortRow in CohortRows if FieldIsPresent(CohortRow, RequiredField))
        for RequiredField in RequiredCohortFields
    }

    AgeDateDifferences = [
        Row["ImageClinicalDateDifferenceDays"]
        for Row in AgeDateCheckRows
        if Row["ImageClinicalDateDifferenceDays"] != ""
    ]

    MaximumAbsoluteImageClinicalDateDifference = (
        max(abs(int(DateDifference)) for DateDifference in AgeDateDifferences)
        if AgeDateDifferences
        else ""
    )

    QcStatusFieldNames = sorted(set(NormaliseText(Row.get("QcField", "")) for Row in QcFieldInventoryRows))

    SummaryRows = [
        {"Metric": "GeneratedAt", "Value": datetime.now().isoformat(timespec="seconds")},
        {"Metric": "SelectedBaselineCohortRows", "Value": len(CohortRows)},
        {"Metric": "FastSurferInputManifestRows", "Value": len(ManifestRows)},
        {
            "Metric": "UniqueRidCount",
            "Value": len(set(NormaliseText(Row.get("RID", "")) for Row in CohortRows if NormaliseText(Row.get("RID", "")))),
        },
        {"Metric": "DuplicateRidRows", "Value": len(DuplicateRidRows)},
        {"Metric": "DuplicateImageRows", "Value": len(DuplicateImageRows)},
        {"Metric": "QcStatusFieldsFound", "Value": "; ".join(QcStatusFieldNames)},
        {"Metric": "QcFlaggedSelectedRows", "Value": len(QcFlaggedRows)},
        {"Metric": "MaximumAbsoluteImageClinicalDateDifferenceDays", "Value": MaximumAbsoluteImageClinicalDateDifference},
        {"Metric": "CohortDiagnosisCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in CohortDiagnosisCounts.items())},
        {"Metric": "ManifestDiagnosisCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in ManifestDiagnosisCounts.items())},
        {"Metric": "FastSurferStatusCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in FastSurferStatusCounts.items())},
        {
            "Metric": "DiagnosisFastSurferStatusCounts",
            "Value": "; ".join(f"{Key}: {Value}" for Key, Value in DiagnosisStatusCounts.items()),
        },
    ]

    for RequiredField, RowsWithValue in RequiredFieldPresence.items():
        SummaryRows.append({"Metric": f"RowsWith{RequiredField}", "Value": RowsWithValue})

    for CognitiveCoverageRow in CognitiveCoverageRows:
        SummaryRows.append(
            {
                "Metric": f"RowsWith{CognitiveCoverageRow['Measure']}",
                "Value": CognitiveCoverageRow["RowsWithValue"],
            }
        )

    return SummaryRows


def WriteMarkdownSummary(SummaryRows: list[dict[str, object]]) -> None:
    EnsureDirectory(AnalysisReadinessMarkdownSummaryPath.parent)

    with AnalysisReadinessMarkdownSummaryPath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# Analysis Readiness Summary\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def PrintSection(SectionTitle: str) -> None:
    print()
    print("=" * 80)
    print(SectionTitle)
    print("=" * 80)


def PrintMetricRows(SummaryRows: list[dict[str, object]]) -> None:
    for SummaryRow in SummaryRows:
        print(f"{SummaryRow['Metric']}: {SummaryRow['Value']}")


def PrintCountTable(Title: str, ValueCounts: dict[str, int]) -> None:
    PrintSection(Title)

    if not ValueCounts:
        print("No rows.")
        return

    LongestValueLength = max(len(Value) for Value in ValueCounts.keys())

    for Value, Count in ValueCounts.items():
        print(f"{Value:<{LongestValueLength}}  {Count}")


def PrintRows(Title: str, Rows: list[dict[str, object]], FieldNames: list[str], MaximumRows: int = 25) -> None:
    PrintSection(Title)

    if not Rows:
        print("No rows.")
        return

    DisplayRows = Rows[:MaximumRows]

    ColumnWidths = {}
    for FieldName in FieldNames:
        ColumnWidths[FieldName] = max(
            len(FieldName),
            max(len(NormaliseText(Row.get(FieldName, ""))) for Row in DisplayRows),
        )

    HeaderLine = "  ".join(FieldName.ljust(ColumnWidths[FieldName]) for FieldName in FieldNames)
    SeparatorLine = "  ".join("-" * ColumnWidths[FieldName] for FieldName in FieldNames)

    print(HeaderLine)
    print(SeparatorLine)

    for Row in DisplayRows:
        print("  ".join(NormaliseText(Row.get(FieldName, "")).ljust(ColumnWidths[FieldName]) for FieldName in FieldNames))

    if len(Rows) > MaximumRows:
        print(f"... {len(Rows) - MaximumRows} additional rows not shown.")


def PrintConsoleReport(
    SummaryRows: list[dict[str, object]],
    CohortRows: list[dict[str, str]],
    ManifestRows: list[dict[str, str]],
    FastSurferStatusRows: list[dict[str, object]],
    CognitiveCoverageRows: list[dict[str, object]],
    QcFlaggedRows: list[dict[str, object]],
    QcFieldInventoryRows: list[dict[str, object]],
    FastSurferIncompleteRows: list[dict[str, object]],
    DuplicateRidRows: list[dict[str, object]],
    DuplicateImageRows: list[dict[str, object]],
) -> None:
    PrintSection("Analysis Readiness Summary")
    PrintMetricRows(SummaryRows)

    PrintCountTable(
        "SelectedBaselineCohort diagnosis counts",
        CountByField(CohortRows, "Diagnosis3Class"),
    )

    PrintCountTable(
        "FastSurferInputManifest diagnosis counts",
        CountByField(ManifestRows, "Diagnosis3Class"),
    )

    PrintCountTable(
        "FastSurfer status counts",
        CountByFields(FastSurferStatusRows, ["FastSurferStatus"]),
    )

    PrintCountTable(
        "Diagnosis by FastSurfer status",
        CountByFields(FastSurferStatusRows, ["Diagnosis3Class", "FastSurferStatus"]),
    )

    PrintRows(
        "Cognitive-score coverage",
        CognitiveCoverageRows,
        ["Measure", "FieldName", "RowsWithValue", "RowsMissingValue", "CoveragePercent", "FieldFound"],
    )

    PrintRows(
        "FastSurfer incomplete rows",
        FastSurferIncompleteRows,
        ["RowNumber", "RID", "SubjectId", "ImageId", "Diagnosis3Class", "FastSurferStatus", "MissingRequiredStatsFiles"],
    )

    PrintRows(
        "QC status field inventory",
        QcFieldInventoryRows,
        ["QcField", "Value", "Count"],
    )

    PrintRows(
        "QC flagged selected rows",
        QcFlaggedRows,
        ["RowNumber", "RID", "SubjectId", "ImageId", "Diagnosis3Class", "FailedQcFields"],
    )

    PrintRows(
        "Duplicate RID rows",
        DuplicateRidRows,
        ["RowNumber", "DuplicateField", "DuplicateValue", "RID", "SubjectId", "ImageId", "Diagnosis3Class"],
    )

    PrintRows(
        "Duplicate ImageId rows",
        DuplicateImageRows,
        ["RowNumber", "DuplicateField", "DuplicateValue", "RID", "SubjectId", "ImageId", "Diagnosis3Class"],
    )


def Main() -> None:
    EnsureDirectory(OutputDirectory)

    print("Regenerating FastSurfer input manifest...")
    RunPrepareFastSurferInputs()

    ValidateInputs()

    CohortRows = ReadCsvRows(SelectedBaselineCohortPath)
    ManifestRows = ReadCsvRows(FastSurferInputManifestPath)

    FastSurferStatusRows = BuildFastSurferStatusRows(ManifestRows)
    FastSurferIncompleteRows = [
        StatusRow for StatusRow in FastSurferStatusRows if StatusRow["FastSurferStatus"] != "Complete"
    ]

    CognitiveCoverageRows = BuildCognitiveCoverageRows(CohortRows)
    QcFlaggedRows = BuildQcFlaggedRows(CohortRows)
    QcFieldInventoryRows = BuildQcFieldInventoryRows(CohortRows)
    AgeDateCheckRows = BuildAgeDateCheckRows(CohortRows)
    DuplicateRidRows = BuildDuplicateRows(CohortRows, "RID")
    DuplicateImageRows = BuildDuplicateRows(CohortRows, "ImageId")
    ColumnInventoryRows = BuildColumnInventoryRows(CohortRows, ManifestRows)

    SummaryRows = BuildSummaryRows(
        CohortRows=CohortRows,
        ManifestRows=ManifestRows,
        FastSurferStatusRows=FastSurferStatusRows,
        CognitiveCoverageRows=CognitiveCoverageRows,
        QcFlaggedRows=QcFlaggedRows,
        QcFieldInventoryRows=QcFieldInventoryRows,
        AgeDateCheckRows=AgeDateCheckRows,
        DuplicateRidRows=DuplicateRidRows,
        DuplicateImageRows=DuplicateImageRows,
    )

    WriteCsv(AnalysisReadinessSummaryPath, ["Metric", "Value"], SummaryRows)
    WriteMarkdownSummary(SummaryRows)

    DiagnosisCountRows: list[dict[str, object]] = []
    DiagnosisCountRows.extend(BuildCountRows("SelectedBaselineCohort", CountByField(CohortRows, "Diagnosis3Class")))
    DiagnosisCountRows.extend(BuildCountRows("FastSurferInputManifest", CountByField(ManifestRows, "Diagnosis3Class")))

    WriteCsv(DiagnosisCountsPath, ["CountName", "Value", "Count"], DiagnosisCountRows)

    DiagnosisStatusRows = [
        {
            "Diagnosis3ClassAndFastSurferStatus": DiagnosisStatus,
            "Count": Count,
        }
        for DiagnosisStatus, Count in CountByFields(FastSurferStatusRows, ["Diagnosis3Class", "FastSurferStatus"]).items()
    ]

    WriteCsv(
        DiagnosisFastSurferStatusCountsPath,
        ["Diagnosis3ClassAndFastSurferStatus", "Count"],
        DiagnosisStatusRows,
    )

    WriteCsv(
        CognitiveCoveragePath,
        ["Measure", "FieldName", "RowsWithValue", "RowsMissingValue", "CoveragePercent", "FieldFound"],
        CognitiveCoverageRows,
    )

    WriteCsv(
        CohortDuplicateRowsPath,
        ["RowNumber", "DuplicateField", "DuplicateValue", *GetHeaders(CohortRows)],
        DuplicateRidRows + DuplicateImageRows,
    )

    WriteCsv(
        FastSurferIncompleteRowsPath,
        [
            "RowNumber",
            "RID",
            "SubjectId",
            "ImageId",
            "Diagnosis3Class",
            "FastSurferSubjectId",
            "FastSurferStatus",
            "MissingRequiredStatsFiles",
            "FastSurferOutputDirectory",
        ],
        FastSurferIncompleteRows,
    )

    WriteCsv(
        QcFlaggedRowsPath,
        ["RowNumber", "RID", "SubjectId", "ImageId", "Diagnosis3Class", "FailedQcFields"],
        QcFlaggedRows,
    )

    WriteCsv(
        QcFieldInventoryPath,
        ["QcField", "Value", "Count"],
        QcFieldInventoryRows,
    )

    WriteCsv(
        AgeDateCheckRowsPath,
        [
            "RowNumber",
            "RID",
            "SubjectId",
            "ImageId",
            "Diagnosis3Class",
            "AgeField",
            "Age",
            "ImageStudyDateField",
            "ImageStudyDate",
            "ClinicalDateField",
            "ClinicalDate",
            "BirthYearField",
            "BirthYear",
            "ImageClinicalDateDifferenceDays",
            "ApproximateImageAgeFromBirthYear",
            "AgeMinusApproximateImageAge",
        ],
        AgeDateCheckRows,
    )

    WriteCsv(
        ColumnInventoryPath,
        ["Source", "ColumnName", "RowsWithValue", "RowsMissingValue"],
        ColumnInventoryRows,
    )

    PrintConsoleReport(
        SummaryRows=SummaryRows,
        CohortRows=CohortRows,
        ManifestRows=ManifestRows,
        FastSurferStatusRows=FastSurferStatusRows,
        CognitiveCoverageRows=CognitiveCoverageRows,
        QcFlaggedRows=QcFlaggedRows,
        QcFieldInventoryRows=QcFieldInventoryRows,
        FastSurferIncompleteRows=FastSurferIncompleteRows,
        DuplicateRidRows=DuplicateRidRows,
        DuplicateImageRows=DuplicateImageRows,
    )

    print()
    print("Analysis readiness inspection complete.")
    print(f"Summary: {AnalysisReadinessMarkdownSummaryPath}")
    print(f"FastSurfer incomplete rows: {FastSurferIncompleteRowsPath}")
    print(f"Cognitive coverage: {CognitiveCoveragePath}")
    print(f"QC flagged rows: {QcFlaggedRowsPath}")
    print(f"QC field inventory: {QcFieldInventoryPath}")
    print(f"Age/date checks: {AgeDateCheckRowsPath}")
    print(f"Column inventory: {ColumnInventoryPath}")


if __name__ == "__main__":
    try:
        Main()
    except subprocess.CalledProcessError as Error:
        print(f"Command failed with exit code {Error.returncode}.")
        sys.exit(Error.returncode)
    except Exception as Error:
        print(str(Error))
        sys.exit(1)