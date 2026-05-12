"""Build a visit-level clinical table from unpacked ADNI study-data files.

Reads clinical CSV tables from Data/Raw/Clinical/StudyData and writes a local
visit-level table to Data/Interim/Clinical/.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import date, datetime
from pathlib import Path


RequiredOutputFields = [
    "RID",
    "SubjectId",
    "VisitCode",
    "VisitCode2",
    "ExamDate",
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
    "SourceTable",
]


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def NormaliseColumnName(ColumnName: str) -> str:
    """Normalise column names so ADNI table variants can be matched consistently."""
    return re.sub(r"[^A-Z0-9]", "", ColumnName.upper())


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


def FindClinicalCsvFilesContaining(ClinicalStudyDataDirectory: Path, FileNameFragment: str) -> list[Path]:
    """Find clinical CSV files whose names contain a given fragment."""
    if not ClinicalStudyDataDirectory.exists():
        return []

    FileNameFragmentLower = FileNameFragment.lower()

    return sorted(
        ClinicalCsvFilePath
        for ClinicalCsvFilePath in ClinicalStudyDataDirectory.rglob("*.csv")
        if FileNameFragmentLower in ClinicalCsvFilePath.name.lower()
    )


def BuildNormalisedRowLookup(TableRow: dict[str, str]) -> dict[str, str]:
    """Create a case-insensitive lookup from normalised column names to cell values."""
    NormalisedRowLookup: dict[str, str] = {}

    for ColumnName, ColumnValue in TableRow.items():
        NormalisedRowLookup[NormaliseColumnName(ColumnName)] = NormaliseText(ColumnValue)

    return NormalisedRowLookup


def GetFirstAvailableValue(TableRow: dict[str, str] | None, CandidateColumnNames: list[str]) -> str:
    """Return the first non-empty value matching any candidate column name."""
    if TableRow is None:
        return ""

    NormalisedRowLookup = BuildNormalisedRowLookup(TableRow)

    for CandidateColumnName in CandidateColumnNames:
        NormalisedCandidateColumnName = NormaliseColumnName(CandidateColumnName)
        CandidateValue = NormalisedRowLookup.get(NormalisedCandidateColumnName, "")

        if CandidateValue:
            return CandidateValue

    return ""


def GetFirstAvailableValueContaining(
    TableRow: dict[str, str] | None,
    CandidateColumnFragments: list[str],
) -> str:
    """Return the first non-empty value from a column whose name contains a fragment."""
    if TableRow is None:
        return ""

    NormalisedCandidateColumnFragments = [
        NormaliseColumnName(CandidateColumnFragment)
        for CandidateColumnFragment in CandidateColumnFragments
    ]

    for ColumnName, ColumnValue in TableRow.items():
        NormalisedColumnNameValue = NormaliseColumnName(ColumnName)

        if not any(Fragment in NormalisedColumnNameValue for Fragment in NormalisedCandidateColumnFragments):
            continue

        NormalisedColumnValue = NormaliseText(ColumnValue)

        if NormalisedColumnValue:
            return NormalisedColumnValue

    return ""


def GetRidValue(TableRow: dict[str, str] | None) -> str:
    return GetFirstAvailableValue(TableRow, ["RID", "RosterID", "ParticipantRID"])


def GetSubjectIdValue(TableRow: dict[str, str] | None) -> str:
    return GetFirstAvailableValue(
        TableRow,
        ["PTID", "SubjectID", "Subject ID", "Subject", "ParticipantID"],
    )


def GetVisitCodeValue(TableRow: dict[str, str] | None) -> str:
    return GetFirstAvailableValue(TableRow, ["VISCODE", "VisitCode", "Visit", "Visit_Code"])


def GetVisitCode2Value(TableRow: dict[str, str] | None) -> str:
    return GetFirstAvailableValue(TableRow, ["VISCODE2", "VisitCode2", "VISCODE"])


def GetExamDateValue(TableRow: dict[str, str] | None) -> str:
    return GetFirstAvailableValue(
        TableRow,
        ["EXAMDATE", "ExamDate", "EXAM_DATE", "USERDATE", "USERDATE2", "Date", "StudyDate"],
    )


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
        "%Y",
    ]

    for DateFormat in DateFormats:
        try:
            ParsedDate = datetime.strptime(DateText, DateFormat).date()

            if DateFormat == "%Y":
                return date(ParsedDate.year, 7, 1)

            return ParsedDate

        except ValueError:
            continue

    YearMatch = re.search(r"\d{4}", DateText)

    if YearMatch is not None:
        return date(int(YearMatch.group(0)), 7, 1)

    return None


def GetBirthDateFromDemographicsRow(DemographicsRow: dict[str, str] | None) -> date | None:
    """Estimate birth date from PTDOB or PTDOBYY."""
    if DemographicsRow is None:
        return None

    BirthDateValue = GetFirstAvailableValue(
        DemographicsRow,
        ["PTDOB", "BirthDate", "Birth Date", "DOB"],
    )

    ParsedBirthDate = ParseDate(BirthDateValue)

    if ParsedBirthDate is not None:
        return ParsedBirthDate

    BirthYearValue = GetFirstAvailableValue(
        DemographicsRow,
        ["PTDOBYY", "BirthYear", "Birth Year", "DOBYY"],
    )

    if not BirthYearValue:
        return None

    BirthYearMatch = re.search(r"\d{4}", BirthYearValue)

    if BirthYearMatch is None:
        return None

    BirthYear = int(BirthYearMatch.group(0))

    return date(BirthYear, 7, 1)


def CalculateAgeAtExamDate(ExamDateValue: str, DemographicsRow: dict[str, str] | None) -> str:
    """Calculate age at visit using exam date and available birth-date information."""
    ExamDate = ParseDate(ExamDateValue)
    BirthDate = GetBirthDateFromDemographicsRow(DemographicsRow)

    if ExamDate is None or BirthDate is None:
        return ""

    AgeYears = (ExamDate - BirthDate).days / 365.25

    if AgeYears <= 0 or AgeYears > 120:
        return ""

    return f"{AgeYears:.2f}"


def BuildVisitKeyFromValues(RidValue: str, VisitCodeValue: str, VisitCode2Value: str, ExamDateValue: str) -> str:
    """Build a stable visit key using RID plus the best available visit/date identifier."""
    VisitIdentifier = VisitCode2Value or VisitCodeValue or ExamDateValue

    if not RidValue or not VisitIdentifier:
        return ""

    return f"{RidValue}::{VisitIdentifier}"


def BuildVisitKeyFromRow(TableRow: dict[str, str]) -> str:
    """Build a visit key from an ADNI table row."""
    RidValue = GetRidValue(TableRow)
    VisitCodeValue = GetVisitCodeValue(TableRow)
    VisitCode2Value = GetVisitCode2Value(TableRow)
    ExamDateValue = GetExamDateValue(TableRow)

    return BuildVisitKeyFromValues(
        RidValue=RidValue,
        VisitCodeValue=VisitCodeValue,
        VisitCode2Value=VisitCode2Value,
        ExamDateValue=ExamDateValue,
    )


def BuildRidIndex(TableRows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Index rows by RID and keep the first row for each participant."""
    RidIndex: dict[str, dict[str, str]] = {}

    for TableRow in TableRows:
        RidValue = GetRidValue(TableRow)

        if not RidValue:
            continue

        if RidValue not in RidIndex:
            RidIndex[RidValue] = TableRow

    return RidIndex


def BuildVisitIndex(TableRows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Index rows by RID and visit code/date."""
    VisitIndex: dict[str, list[dict[str, str]]] = {}

    for TableRow in TableRows:
        VisitKey = BuildVisitKeyFromRow(TableRow)

        if not VisitKey:
            continue

        if VisitKey not in VisitIndex:
            VisitIndex[VisitKey] = []

        VisitIndex[VisitKey].append(TableRow)

    return VisitIndex


def GetFirstVisitIndexedRow(VisitKey: str, VisitIndex: dict[str, list[dict[str, str]]]) -> dict[str, str] | None:
    MatchingRows = VisitIndex.get(VisitKey, [])

    if not MatchingRows:
        return None

    return MatchingRows[0]


def ChooseLargestCsvFile(CsvFilePaths: list[Path]) -> Path | None:
    """Choose the largest matching CSV file when ADNI provides duplicate table variants."""
    if not CsvFilePaths:
        return None

    return max(CsvFilePaths, key=lambda CsvFilePath: CsvFilePath.stat().st_size)


def RowHasRequiredAdniMergeColumns(TableRow: dict[str, str]) -> bool:
    """Check whether a row looks like an ADNIMERGE-style visit table row."""
    ColumnNames = {NormaliseColumnName(ColumnName) for ColumnName in TableRow.keys()}

    HasRid = "RID" in ColumnNames
    HasSubject = "PTID" in ColumnNames or "SUBJECTID" in ColumnNames
    HasVisit = "VISCODE" in ColumnNames or "VISCODE2" in ColumnNames
    HasAge = "AGE" in ColumnNames or "PTAGE" in ColumnNames
    HasDiagnosis = "DX" in ColumnNames or "DXBL" in ColumnNames or "DXCHANGE" in ColumnNames

    return HasRid and HasSubject and HasVisit and HasAge and HasDiagnosis


def FindAdniMergeCandidateCsvFiles(ClinicalStudyDataDirectory: Path) -> list[Path]:
    """Find CSV files that could be a flat ADNIMERGE-style table."""
    if not ClinicalStudyDataDirectory.exists():
        return []

    CandidateCsvFilePaths: list[Path] = []

    for ClinicalCsvFilePath in ClinicalStudyDataDirectory.rglob("*.csv"):
        FileNameLower = ClinicalCsvFilePath.name.lower()
        ParentPathLower = str(ClinicalCsvFilePath.parent).lower()

        if "adnimerge" in FileNameLower or "adnimerge" in ParentPathLower:
            CandidateCsvFilePaths.append(ClinicalCsvFilePath)

    return sorted(CandidateCsvFilePaths, key=lambda CsvFilePath: CsvFilePath.stat().st_size, reverse=True)


def ReadAdniMergeTable(ClinicalStudyDataDirectory: Path) -> tuple[list[dict[str, str]], str]:
    """Read a flat ADNIMERGE-style CSV if one exists."""
    CandidateCsvFilePaths = FindAdniMergeCandidateCsvFiles(ClinicalStudyDataDirectory)

    for CandidateCsvFilePath in CandidateCsvFilePaths:
        try:
            CandidateRows = ReadCsvRows(CandidateCsvFilePath)
        except Exception:
            continue

        if not CandidateRows:
            continue

        if RowHasRequiredAdniMergeColumns(CandidateRows[0]):
            return CandidateRows, CandidateCsvFilePath.name

    return [], ""


def ReadLargestClinicalTable(ClinicalStudyDataDirectory: Path, FileNameFragment: str) -> tuple[list[dict[str, str]], str]:
    """Read the largest CSV matching a clinical table name fragment."""
    CandidateCsvFilePaths = FindClinicalCsvFilesContaining(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment=FileNameFragment,
    )

    SelectedCsvFilePath = ChooseLargestCsvFile(CandidateCsvFilePaths)

    if SelectedCsvFilePath is None:
        return [], ""

    return ReadCsvRows(SelectedCsvFilePath), SelectedCsvFilePath.name


def NormaliseSex(SexValue: str) -> str:
    SexText = SexValue.strip().upper()

    if SexText in {"M", "MALE", "1"}:
        return "Male"

    if SexText in {"F", "FEMALE", "2"}:
        return "Female"

    return SexValue.strip()


def NormaliseDiagnosis(DiagnosisValue: str) -> str:
    """Map ADNI diagnosis encodings to CN, MCI, AD, or the original value."""
    DiagnosisText = DiagnosisValue.strip()

    if not DiagnosisText:
        return ""

    DiagnosisUpper = DiagnosisText.upper()

    NumericDiagnosisMap = {
        "1": "CN",
        "2": "MCI",
        "3": "AD",
        "4": "CN",
        "5": "MCI",
        "6": "AD",
        "7": "CN",
        "8": "MCI",
        "9": "AD",
    }

    if DiagnosisUpper in NumericDiagnosisMap:
        return NumericDiagnosisMap[DiagnosisUpper]

    if DiagnosisUpper in {"CN", "NL", "NORMAL", "COGNITIVELY NORMAL"}:
        return "CN"

    if "NORMAL" in DiagnosisUpper and "ABNORMAL" not in DiagnosisUpper:
        return "CN"

    if DiagnosisUpper in {"MCI", "EMCI", "LMCI"}:
        return "MCI"

    if "MCI" in DiagnosisUpper:
        return "MCI"

    if DiagnosisUpper in {"AD", "DEMENTIA"}:
        return "AD"

    if "ALZHEIMER" in DiagnosisUpper:
        return "AD"

    if "DEMENTIA" in DiagnosisUpper:
        return "AD"

    return DiagnosisText


def GetDiagnosisValue(AdniMergeRow: dict[str, str] | None, DxSumRow: dict[str, str] | None) -> str:
    """Select diagnosis from ADNIMERGE first and DXSUM second."""
    DiagnosisValue = GetFirstAvailableValue(
        AdniMergeRow,
        ["DX", "DX_bl", "DXBL", "DXCHANGE", "DXCURREN", "DiagnosticGroup", "Diagnosis"],
    )

    if DiagnosisValue:
        return DiagnosisValue

    return GetFirstAvailableValue(
        DxSumRow,
        ["DX", "DX_bl", "DXBL", "DXCHANGE", "DXCURREN", "DIAGNOSIS", "DiagnosticGroup", "Diagnosis"],
    )


def BuildBaseClinicalVisitRows(
    AdniMergeRows: list[dict[str, str]],
    AdniMergeSourceFileName: str,
) -> list[dict[str, object]]:
    """Create initial visit rows from a flat ADNIMERGE-style table."""
    ClinicalVisitRows: list[dict[str, object]] = []

    for AdniMergeRow in AdniMergeRows:
        RidValue = GetRidValue(AdniMergeRow)
        VisitCodeValue = GetVisitCodeValue(AdniMergeRow)
        VisitCode2Value = GetVisitCode2Value(AdniMergeRow)
        ExamDateValue = GetExamDateValue(AdniMergeRow)

        if not RidValue:
            continue

        DiagnosisValue = GetDiagnosisValue(AdniMergeRow=AdniMergeRow, DxSumRow=None)

        ClinicalVisitRows.append(
            {
                "RID": RidValue,
                "SubjectId": GetSubjectIdValue(AdniMergeRow),
                "VisitCode": VisitCodeValue,
                "VisitCode2": VisitCode2Value,
                "ExamDate": ExamDateValue,
                "Age": GetFirstAvailableValue(AdniMergeRow, ["AGE", "Age", "PTAGE"]),
                "Sex": NormaliseSex(GetFirstAvailableValue(AdniMergeRow, ["PTGENDER", "Sex", "Gender"])),
                "Education": GetFirstAvailableValue(AdniMergeRow, ["PTEDUCAT", "Education", "Educ", "YearsEducation"]),
                "Diagnosis": DiagnosisValue,
                "DiagnosisBaseline": GetFirstAvailableValue(
                    AdniMergeRow,
                    ["DX_bl", "DXBL", "BaselineDiagnosis", "DiagnosisBaseline"],
                ),
                "Diagnosis3Class": NormaliseDiagnosis(DiagnosisValue),
                "MMSE": GetFirstAvailableValue(AdniMergeRow, ["MMSE", "MMSCORE", "MMSETOTAL"]),
                "ADAS11": GetFirstAvailableValue(AdniMergeRow, ["ADAS11", "ADASQ4", "ADAS11TOTAL"]),
                "ADAS13": GetFirstAvailableValue(AdniMergeRow, ["ADAS13", "ADAS13TOTAL"]),
                "CDRSB": GetFirstAvailableValue(AdniMergeRow, ["CDRSB", "CDR_SOB", "SUMBOX", "CDRSUM"]),
                "FAQ": GetFirstAvailableValue(AdniMergeRow, ["FAQ", "FAQTOTAL", "FAQTOT"]),
                "SourceTable": AdniMergeSourceFileName,
            }
        )

    return ClinicalVisitRows


def BuildFallbackClinicalVisitRows(
    TableRows: list[dict[str, str]],
    SourceFileName: str,
) -> list[dict[str, object]]:
    """Create minimal visit rows when no flat ADNIMERGE-style CSV is available."""
    ClinicalVisitRows: list[dict[str, object]] = []
    SeenVisitKeys: set[str] = set()

    for TableRow in TableRows:
        RidValue = GetRidValue(TableRow)
        VisitCodeValue = GetVisitCodeValue(TableRow)
        VisitCode2Value = GetVisitCode2Value(TableRow)
        ExamDateValue = GetExamDateValue(TableRow)

        if not RidValue:
            continue

        VisitKey = BuildVisitKeyFromValues(
            RidValue=RidValue,
            VisitCodeValue=VisitCodeValue,
            VisitCode2Value=VisitCode2Value,
            ExamDateValue=ExamDateValue,
        )

        if VisitKey in SeenVisitKeys:
            continue

        SeenVisitKeys.add(VisitKey)

        DiagnosisValue = GetDiagnosisValue(AdniMergeRow=None, DxSumRow=TableRow)

        ClinicalVisitRows.append(
            {
                "RID": RidValue,
                "SubjectId": GetSubjectIdValue(TableRow),
                "VisitCode": VisitCodeValue,
                "VisitCode2": VisitCode2Value,
                "ExamDate": ExamDateValue,
                "Age": "",
                "Sex": "",
                "Education": "",
                "Diagnosis": DiagnosisValue,
                "DiagnosisBaseline": "",
                "Diagnosis3Class": NormaliseDiagnosis(DiagnosisValue),
                "MMSE": "",
                "ADAS11": "",
                "ADAS13": "",
                "CDRSB": "",
                "FAQ": "",
                "SourceTable": SourceFileName,
            }
        )

    return ClinicalVisitRows


def FillMissingValue(ClinicalVisitRow: dict[str, object], FieldName: str, CandidateValue: str) -> None:
    """Fill a clinical visit field only when it is currently empty."""
    CurrentValue = NormaliseText(ClinicalVisitRow.get(FieldName, ""))

    if CurrentValue:
        return

    if CandidateValue:
        ClinicalVisitRow[FieldName] = CandidateValue


def SupplementDemographics(
    ClinicalVisitRows: list[dict[str, object]],
    DemographicsRidIndex: dict[str, dict[str, str]],
) -> None:
    """Fill subject ID, sex, education, and age from PTDEMOG when available."""
    for ClinicalVisitRow in ClinicalVisitRows:
        RidValue = str(ClinicalVisitRow["RID"])
        DemographicsRow = DemographicsRidIndex.get(RidValue)

        if DemographicsRow is None:
            continue

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName="SubjectId",
            CandidateValue=GetSubjectIdValue(DemographicsRow),
        )

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName="Sex",
            CandidateValue=NormaliseSex(GetFirstAvailableValue(DemographicsRow, ["PTGENDER", "Sex", "Gender"])),
        )

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName="Education",
            CandidateValue=GetFirstAvailableValue(DemographicsRow, ["PTEDUCAT", "Education", "Educ", "YearsEducation"]),
        )

        CalculatedAge = CalculateAgeAtExamDate(
            ExamDateValue=str(ClinicalVisitRow.get("ExamDate", "")),
            DemographicsRow=DemographicsRow,
        )

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName="Age",
            CandidateValue=CalculatedAge,
        )


def SupplementDiagnosis(
    ClinicalVisitRows: list[dict[str, object]],
    DxSumVisitIndex: dict[str, list[dict[str, str]]],
) -> None:
    """Fill diagnosis fields from DXSUM when missing."""
    for ClinicalVisitRow in ClinicalVisitRows:
        VisitKey = BuildVisitKeyFromValues(
            RidValue=str(ClinicalVisitRow["RID"]),
            VisitCodeValue=str(ClinicalVisitRow["VisitCode"]),
            VisitCode2Value=str(ClinicalVisitRow["VisitCode2"]),
            ExamDateValue=str(ClinicalVisitRow["ExamDate"]),
        )

        DxSumRow = GetFirstVisitIndexedRow(VisitKey, DxSumVisitIndex)

        if DxSumRow is None:
            continue

        DiagnosisValue = GetDiagnosisValue(AdniMergeRow=None, DxSumRow=DxSumRow)

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName="Diagnosis",
            CandidateValue=DiagnosisValue,
        )

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName="Diagnosis3Class",
            CandidateValue=NormaliseDiagnosis(str(ClinicalVisitRow.get("Diagnosis", "")) or DiagnosisValue),
        )


def SupplementCognitiveScore(
    ClinicalVisitRows: list[dict[str, object]],
    VisitIndex: dict[str, list[dict[str, str]]],
    OutputFieldName: str,
    CandidateColumnNames: list[str],
    CandidateColumnFragments: list[str],
) -> None:
    """Fill one cognitive score field from a visit-indexed cognitive table."""
    for ClinicalVisitRow in ClinicalVisitRows:
        VisitKey = BuildVisitKeyFromValues(
            RidValue=str(ClinicalVisitRow["RID"]),
            VisitCodeValue=str(ClinicalVisitRow["VisitCode"]),
            VisitCode2Value=str(ClinicalVisitRow["VisitCode2"]),
            ExamDateValue=str(ClinicalVisitRow["ExamDate"]),
        )

        CognitiveRow = GetFirstVisitIndexedRow(VisitKey, VisitIndex)

        if CognitiveRow is None:
            continue

        CandidateValue = GetFirstAvailableValue(CognitiveRow, CandidateColumnNames)

        if not CandidateValue:
            CandidateValue = GetFirstAvailableValueContaining(CognitiveRow, CandidateColumnFragments)

        FillMissingValue(
            ClinicalVisitRow=ClinicalVisitRow,
            FieldName=OutputFieldName,
            CandidateValue=CandidateValue,
        )


def FinaliseDiagnosis3Class(ClinicalVisitRows: list[dict[str, object]]) -> None:
    """Recompute the harmonised three-class diagnosis after supplementation."""
    for ClinicalVisitRow in ClinicalVisitRows:
        ClinicalVisitRow["Diagnosis3Class"] = NormaliseDiagnosis(str(ClinicalVisitRow.get("Diagnosis", "")))


def SortClinicalVisitRows(ClinicalVisitRows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Sort visit rows by RID, exam date, and visit code."""
    return sorted(
        ClinicalVisitRows,
        key=lambda ClinicalVisitRow: (
            str(ClinicalVisitRow.get("RID", "")),
            str(ClinicalVisitRow.get("ExamDate", "")),
            str(ClinicalVisitRow.get("VisitCode2", "")),
            str(ClinicalVisitRow.get("VisitCode", "")),
        ),
    )


def BuildClinicalVisitRows(DataRootDirectory: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Build the visit-level clinical table from available ADNI clinical tables."""
    ClinicalStudyDataDirectory = DataRootDirectory / "Raw" / "Clinical" / "StudyData"

    AdniMergeRows, AdniMergeSourceFileName = ReadAdniMergeTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
    )

    DxSumRows, DxSumSourceFileName = ReadLargestClinicalTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment="DXSUM",
    )

    DemographicsRows, DemographicsSourceFileName = ReadLargestClinicalTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment="PTDEMOG",
    )

    MmseRows, MmseSourceFileName = ReadLargestClinicalTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment="MMSE",
    )

    AdasRows, AdasSourceFileName = ReadLargestClinicalTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment="ADAS",
    )

    CdrRows, CdrSourceFileName = ReadLargestClinicalTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment="CDR",
    )

    FaqRows, FaqSourceFileName = ReadLargestClinicalTable(
        ClinicalStudyDataDirectory=ClinicalStudyDataDirectory,
        FileNameFragment="FAQ",
    )

    if AdniMergeRows:
        ClinicalVisitRows = BuildBaseClinicalVisitRows(
            AdniMergeRows=AdniMergeRows,
            AdniMergeSourceFileName=AdniMergeSourceFileName,
        )
    else:
        ClinicalVisitRows = BuildFallbackClinicalVisitRows(
            TableRows=DxSumRows,
            SourceFileName=DxSumSourceFileName,
        )

    DemographicsRidIndex = BuildRidIndex(DemographicsRows)
    DxSumVisitIndex = BuildVisitIndex(DxSumRows)
    MmseVisitIndex = BuildVisitIndex(MmseRows)
    AdasVisitIndex = BuildVisitIndex(AdasRows)
    CdrVisitIndex = BuildVisitIndex(CdrRows)
    FaqVisitIndex = BuildVisitIndex(FaqRows)

    SupplementDemographics(
        ClinicalVisitRows=ClinicalVisitRows,
        DemographicsRidIndex=DemographicsRidIndex,
    )

    SupplementDiagnosis(
        ClinicalVisitRows=ClinicalVisitRows,
        DxSumVisitIndex=DxSumVisitIndex,
    )

    SupplementCognitiveScore(
        ClinicalVisitRows=ClinicalVisitRows,
        VisitIndex=MmseVisitIndex,
        OutputFieldName="MMSE",
        CandidateColumnNames=["MMSE", "MMSCORE", "MMSCORE_TOTAL", "MMSETOTAL"],
        CandidateColumnFragments=["MMSE", "MMSCORE"],
    )

    SupplementCognitiveScore(
        ClinicalVisitRows=ClinicalVisitRows,
        VisitIndex=AdasVisitIndex,
        OutputFieldName="ADAS11",
        CandidateColumnNames=["ADAS11", "TOTAL11", "ADAS11TOTAL", "Q4SCORE"],
        CandidateColumnFragments=["ADAS11", "TOTAL11"],
    )

    SupplementCognitiveScore(
        ClinicalVisitRows=ClinicalVisitRows,
        VisitIndex=AdasVisitIndex,
        OutputFieldName="ADAS13",
        CandidateColumnNames=["ADAS13", "TOTAL13", "ADAS13TOTAL"],
        CandidateColumnFragments=["ADAS13", "TOTAL13"],
    )

    SupplementCognitiveScore(
        ClinicalVisitRows=ClinicalVisitRows,
        VisitIndex=CdrVisitIndex,
        OutputFieldName="CDRSB",
        CandidateColumnNames=["CDRSB", "CDR_SOB", "SUMBOX", "CDRSUM"],
        CandidateColumnFragments=["CDRSB", "SUMBOX", "CDRSUM"],
    )

    SupplementCognitiveScore(
        ClinicalVisitRows=ClinicalVisitRows,
        VisitIndex=FaqVisitIndex,
        OutputFieldName="FAQ",
        CandidateColumnNames=["FAQ", "FAQTOTAL", "FAQTOT"],
        CandidateColumnFragments=["FAQTOTAL", "FAQTOT"],
    )

    FinaliseDiagnosis3Class(ClinicalVisitRows)
    ClinicalVisitRows = SortClinicalVisitRows(ClinicalVisitRows)

    SummaryValues = {
        "ClinicalVisitRowCount": len(ClinicalVisitRows),
        "UniqueRidCount": len({str(ClinicalVisitRow["RID"]) for ClinicalVisitRow in ClinicalVisitRows}),
        "RowsWithSubjectId": CountRowsWithField(ClinicalVisitRows, "SubjectId"),
        "RowsWithExamDate": CountRowsWithField(ClinicalVisitRows, "ExamDate"),
        "RowsWithAge": CountRowsWithField(ClinicalVisitRows, "Age"),
        "RowsWithSex": CountRowsWithField(ClinicalVisitRows, "Sex"),
        "RowsWithEducation": CountRowsWithField(ClinicalVisitRows, "Education"),
        "RowsWithDiagnosis": CountRowsWithField(ClinicalVisitRows, "Diagnosis"),
        "RowsWithDiagnosis3Class": CountRowsWithField(ClinicalVisitRows, "Diagnosis3Class"),
        "RowsWithMMSE": CountRowsWithField(ClinicalVisitRows, "MMSE"),
        "RowsWithADAS11": CountRowsWithField(ClinicalVisitRows, "ADAS11"),
        "RowsWithADAS13": CountRowsWithField(ClinicalVisitRows, "ADAS13"),
        "RowsWithCDRSB": CountRowsWithField(ClinicalVisitRows, "CDRSB"),
        "RowsWithFAQ": CountRowsWithField(ClinicalVisitRows, "FAQ"),
        "Diagnosis3ClassCounts": FormatValueCounts(CountValueOccurrences(ClinicalVisitRows, "Diagnosis3Class")),
        "AdniMergeSourceFile": AdniMergeSourceFileName,
        "DxSumSourceFile": DxSumSourceFileName,
        "DemographicsSourceFile": DemographicsSourceFileName,
        "MmseSourceFile": MmseSourceFileName,
        "AdasSourceFile": AdasSourceFileName,
        "CdrSourceFile": CdrSourceFileName,
        "FaqSourceFile": FaqSourceFileName,
    }

    return ClinicalVisitRows, SummaryValues


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


def BuildSummaryRows(SummaryValues: dict[str, object]) -> list[dict[str, object]]:
    """Convert summary values to CSV-friendly metric rows."""
    MetricNames = [
        "ClinicalVisitRowCount",
        "UniqueRidCount",
        "RowsWithSubjectId",
        "RowsWithExamDate",
        "RowsWithAge",
        "RowsWithSex",
        "RowsWithEducation",
        "RowsWithDiagnosis",
        "RowsWithDiagnosis3Class",
        "RowsWithMMSE",
        "RowsWithADAS11",
        "RowsWithADAS13",
        "RowsWithCDRSB",
        "RowsWithFAQ",
        "Diagnosis3ClassCounts",
        "AdniMergeSourceFile",
        "DxSumSourceFile",
        "DemographicsSourceFile",
        "MmseSourceFile",
        "AdasSourceFile",
        "CdrSourceFile",
        "FaqSourceFile",
    ]

    return [{"Metric": MetricName, "Value": SummaryValues.get(MetricName, "")} for MetricName in MetricNames]


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRows: list[dict[str, object]]) -> None:
    """Write a brief Markdown summary for the clinical visits build."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# Clinical Visits Summary\n\n")
        OutputFile.write(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def ParseArguments() -> argparse.Namespace:
    """Parse command-line arguments for clinical visit construction."""
    ArgumentParser = argparse.ArgumentParser(
        description="Build a visit-level clinical table from unpacked ADNI study-data files."
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
        default=Path("Data") / "Interim" / "Clinical",
        help="Directory for clinical visit outputs. Default: Data/Interim/Clinical",
    )

    return ArgumentParser.parse_args()


def Main() -> None:
    Arguments = ParseArguments()

    OutputDirectory = Arguments.output_directory
    EnsureDirectory(OutputDirectory)

    ClinicalVisitRows, SummaryValues = BuildClinicalVisitRows(DataRootDirectory=Arguments.data_root)
    SummaryRows = BuildSummaryRows(SummaryValues)

    WriteCsv(
        OutputFilePath=OutputDirectory / "ClinicalVisits.csv",
        FieldNames=RequiredOutputFields,
        DataRows=ClinicalVisitRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ClinicalVisitsSummary.csv",
        FieldNames=["Metric", "Value"],
        DataRows=SummaryRows,
    )

    WriteMarkdownSummary(
        OutputFilePath=OutputDirectory / "ClinicalVisitsSummary.md",
        SummaryRows=SummaryRows,
    )

    print("Clinical visits build complete.")
    print(f"Output directory: {OutputDirectory}")
    print(f"Clinical visit rows: {len(ClinicalVisitRows)}")


if __name__ == "__main__":
    Main()