"""Build an image-level manifest for the unpacked ADNI MRI files.

Reads extracted NIfTI files, IDA metadata, and ADNI MRI metadata tables. Writes
one local manifest row per extracted NIfTI image to Data/Interim/Imaging/.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


ImageIdPattern = re.compile(r"(?:^|[^A-Z0-9])I(?P<ImageNumber>\d{3,})(?:[^A-Z0-9]|$)", re.IGNORECASE)
SubjectIdPattern = re.compile(r"(?P<SubjectId>\d{3}_S_\d{4})", re.IGNORECASE)
DatePattern = re.compile(r"(?P<Date>\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})")

ProgressPrintEvery = 100


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def PrintProgress(Message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {Message}", flush=True)


def GetRelativePath(FilePath: Path, RootDirectory: Path) -> str:
    try:
        return str(FilePath.relative_to(RootDirectory))
    except ValueError:
        return str(FilePath)


def GetFileSizeMegabytes(FilePath: Path) -> float:
    return FilePath.stat().st_size / (1024 * 1024)


def IsNiftiFile(FilePath: Path) -> bool:
    FileNameLower = FilePath.name.lower()
    return FileNameLower.endswith(".nii") or FileNameLower.endswith(".nii.gz")


def NormaliseColumnName(ColumnName: str) -> str:
    """Normalise column names so table variants can be matched consistently."""
    return re.sub(r"[^A-Z0-9]", "", ColumnName.upper())


def NormaliseText(TextValue: object) -> str:
    return str(TextValue).strip() if TextValue is not None else ""


def NormaliseImageId(ImageIdValue: object, ColumnName: str = "") -> str:
    """Convert image identifiers such as I12345 and 12345 to the same key."""
    ImageIdText = NormaliseText(ImageIdValue)

    if not ImageIdText:
        return ""

    ExplicitImageIdMatch = re.search(r"\bI(\d{3,})\b", ImageIdText, flags=re.IGNORECASE)

    if ExplicitImageIdMatch is not None:
        return ExplicitImageIdMatch.group(1)

    NormalisedColumnName = NormaliseColumnName(ColumnName)
    ColumnLooksLikeImageIdentifier = AnyTextInValue(
        NormalisedColumnName,
        [
            "IMAGE",
            "IMAGEID",
            "IMAGEUID",
            "IMAGEDATAID",
            "IMG",
            "IMGID",
            "IMGUID",
            "LONIUID",
            "SCANID",
            "SERIESID",
            "UID",
        ],
    )

    if ColumnLooksLikeImageIdentifier:
        NumericImageIdMatch = re.fullmatch(r"\d{3,}", ImageIdText)

        if NumericImageIdMatch is not None:
            return NumericImageIdMatch.group(0)

    return ""


def FormatImageId(ImageIdKey: str) -> str:
    if not ImageIdKey:
        return ""

    return f"I{ImageIdKey}"


def AnyTextInValue(TextValue: str, CandidateTextValues: list[str]) -> bool:
    return any(CandidateTextValue in TextValue for CandidateTextValue in CandidateTextValues)


def ExtractImageIdFromText(TextValue: object) -> str:
    """Extract an explicit ADNI image identifier from free text."""
    Text = NormaliseText(TextValue)
    ImageIdMatch = ImageIdPattern.search(Text)

    if ImageIdMatch is None:
        return ""

    return ImageIdMatch.group("ImageNumber")


def ExtractSubjectIdFromText(TextValue: object) -> str:
    """Extract an ADNI subject identifier from free text."""
    Text = NormaliseText(TextValue)
    SubjectIdMatch = SubjectIdPattern.search(Text)

    if SubjectIdMatch is None:
        return ""

    return SubjectIdMatch.group("SubjectId")


def ExtractDateFromText(TextValue: object) -> str:
    """Extract a simple date string from free text."""
    Text = NormaliseText(TextValue)
    DateMatch = DatePattern.search(Text)

    if DateMatch is None:
        return ""

    return DateMatch.group("Date")


def ReadTextFile(FilePath: Path) -> str:
    """Read a metadata text file with a tolerant encoding fallback."""
    try:
        return FilePath.read_text(encoding="utf-8-sig", errors="replace")
    except UnicodeDecodeError:
        return FilePath.read_text(encoding="latin-1", errors="replace")


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


def FindClinicalCsvFiles(ClinicalStudyDataDirectory: Path, FileNamePattern: str) -> list[Path]:
    """Find clinical CSV files by filename pattern inside the extracted study-data folder."""
    if not ClinicalStudyDataDirectory.exists():
        return []

    return sorted(ClinicalStudyDataDirectory.rglob(FileNamePattern))


def FindStandardisedListCsvFiles(ClinicalStudyDataDirectory: Path) -> list[Path]:
    """Find extracted ADNI 3T MRI standardised-list CSV files."""
    if not ClinicalStudyDataDirectory.exists():
        return []

    StandardisedListDirectory = ClinicalStudyDataDirectory / "ADNI_3T_MRI_Standardized_Lists"

    if StandardisedListDirectory.exists():
        return sorted(StandardisedListDirectory.rglob("*.csv"))

    return sorted(ClinicalStudyDataDirectory.rglob("*Standardized*.csv"))


def FindIdaMetadataFiles(DataRootDirectory: Path) -> list[Path]:
    """Find extracted IDA metadata files under the imaging manifest folder."""
    ImagingManifestDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Manifest"

    if not ImagingManifestDirectory.exists():
        return []

    return sorted(FilePath for FilePath in ImagingManifestDirectory.rglob("*") if FilePath.is_file())


def GetCandidateImageIdColumns(ColumnNames: list[str]) -> list[str]:
    """Identify likely image-ID columns in ADNI or IDA metadata tables."""
    CandidateImageIdColumns: list[str] = []

    for ColumnName in ColumnNames:
        NormalisedColumnName = NormaliseColumnName(ColumnName)

        ColumnLooksLikeImageIdentifier = AnyTextInValue(
            NormalisedColumnName,
            [
                "IMAGE",
                "IMAGEID",
                "IMAGEUID",
                "IMAGEDATAID",
                "IMG",
                "IMGID",
                "IMGUID",
                "LONIUID",
                "SCANID",
                "SERIESID",
                "UID",
            ],
        )

        if ColumnLooksLikeImageIdentifier:
            CandidateImageIdColumns.append(ColumnName)

    return CandidateImageIdColumns


def BuildImageIdIndex(TableRows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Index table rows by image identifiers found in likely columns or explicit I-prefixed cells."""
    ImageIdIndex: dict[str, list[dict[str, str]]] = {}

    if not TableRows:
        return ImageIdIndex

    ColumnNames = list(TableRows[0].keys())
    CandidateImageIdColumns = GetCandidateImageIdColumns(ColumnNames)

    for TableRow in TableRows:
        RowImageIdKeys: set[str] = set()

        for CandidateImageIdColumn in CandidateImageIdColumns:
            ImageIdKey = NormaliseImageId(
                ImageIdValue=TableRow.get(CandidateImageIdColumn, ""),
                ColumnName=CandidateImageIdColumn,
            )

            if ImageIdKey:
                RowImageIdKeys.add(ImageIdKey)

        for ColumnValue in TableRow.values():
            ExplicitImageIdKey = ExtractImageIdFromText(ColumnValue)

            if ExplicitImageIdKey:
                RowImageIdKeys.add(ExplicitImageIdKey)

        for RowImageIdKey in RowImageIdKeys:
            if RowImageIdKey not in ImageIdIndex:
                ImageIdIndex[RowImageIdKey] = []

            ImageIdIndex[RowImageIdKey].append(TableRow)

    return ImageIdIndex


def BuildImageIdSetFromTables(CsvFilePaths: list[Path]) -> set[str]:
    """Build a set of image identifiers found in one or more metadata CSV files."""
    ImageIdSet: set[str] = set()

    for CsvFilePath in CsvFilePaths:
        TableRows = ReadCsvRows(CsvFilePath)

        for TableRow in TableRows:
            ColumnNames = list(TableRow.keys())
            CandidateImageIdColumns = GetCandidateImageIdColumns(ColumnNames)

            for CandidateImageIdColumn in CandidateImageIdColumns:
                ImageIdKey = NormaliseImageId(
                    ImageIdValue=TableRow.get(CandidateImageIdColumn, ""),
                    ColumnName=CandidateImageIdColumn,
                )

                if ImageIdKey:
                    ImageIdSet.add(ImageIdKey)

            for ColumnValue in TableRow.values():
                ExplicitImageIdKey = ExtractImageIdFromText(ColumnValue)

                if ExplicitImageIdKey:
                    ImageIdSet.add(ExplicitImageIdKey)

    return ImageIdSet


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


def GetFirstIndexedRow(ImageIdKey: str, ImageIdIndex: dict[str, list[dict[str, str]]]) -> dict[str, str] | None:
    MatchingRows = ImageIdIndex.get(ImageIdKey, [])

    if not MatchingRows:
        return None

    return MatchingRows[0]


def CountIndexedRows(ImageIdKey: str, ImageIdIndex: dict[str, list[dict[str, str]]]) -> int:
    return len(ImageIdIndex.get(ImageIdKey, []))


def NormaliseSubjectId(SubjectIdValue: object) -> str:
    SubjectIdText = NormaliseText(SubjectIdValue).upper()
    return SubjectIdText.replace("-", "_")


def NormaliseDateValue(DateValue: object) -> str:
    DateText = NormaliseText(DateValue)

    if not DateText:
        return ""

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
            return datetime.strptime(DateText, DateFormat).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return DateText


def GetSubjectDateKey(SubjectIdValue: object, DateValue: object) -> str:
    SubjectId = NormaliseSubjectId(SubjectIdValue)
    DateText = NormaliseDateValue(DateValue)

    if not SubjectId or not DateText:
        return ""

    return f"{SubjectId}::{DateText}"


def GetSubjectDateKeyFromRow(TableRow: dict[str, str], SubjectColumns: list[str], DateColumns: list[str]) -> str:
    SubjectId = GetFirstAvailableValue(TableRow, SubjectColumns)
    DateText = GetFirstAvailableValue(TableRow, DateColumns)
    return GetSubjectDateKey(SubjectId, DateText)


def BuildSubjectDateIndex(
    TableRows: list[dict[str, str]],
    SubjectColumns: list[str],
    DateColumns: list[str],
) -> dict[str, list[dict[str, str]]]:
    SubjectDateIndex: dict[str, list[dict[str, str]]] = {}

    for TableRow in TableRows:
        SubjectDateKey = GetSubjectDateKeyFromRow(
            TableRow=TableRow,
            SubjectColumns=SubjectColumns,
            DateColumns=DateColumns,
        )

        if not SubjectDateKey:
            continue

        if SubjectDateKey not in SubjectDateIndex:
            SubjectDateIndex[SubjectDateKey] = []

        SubjectDateIndex[SubjectDateKey].append(TableRow)

    return SubjectDateIndex


def RowLooksLikeT1Mprage(TableRow: dict[str, str]) -> bool:
    DescriptionText = " ".join(
        [
            GetFirstAvailableValue(TableRow, ["SeriesDescription", "ImageDescription", "Description", "Protocol"]),
            GetFirstAvailableValue(TableRow, ["SeriesType", "Sequence", "Weighting"]),
        ]
    ).upper()

    return "T1" in DescriptionText or "MPRAGE" in DescriptionText or "MP-RAGE" in DescriptionText or "SPGR" in DescriptionText


def RowLooksLike3T(TableRow: dict[str, str]) -> bool:
    FieldStrength = GetFirstAvailableValue(
        TableRow,
        ["MagneticFieldStrength", "FIELD_STRENGTH", "FieldStrength", "Field Strength", "FLDSTRENG", "FLDSTRNGTH"],
    ).upper()

    return FieldStrength in {"3", "3.0", "3T", "3 T"} or "3T" in FieldStrength


def ScoreMriQcFallbackRow(TableRow: dict[str, str]) -> tuple[int, int, int]:
    T1Priority = 0 if RowLooksLikeT1Mprage(TableRow) else 1
    FieldStrengthPriority = 0 if RowLooksLike3T(TableRow) else 1
    SeriesNumberText = GetFirstAvailableValue(TableRow, ["SeriesNumber"])

    try:
        SeriesNumber = int(float(SeriesNumberText))
    except ValueError:
        SeriesNumber = 999999

    return T1Priority, FieldStrengthPriority, SeriesNumber


def GetBestMriQcSubjectDateRow(SubjectDateKey: str, MriQcSubjectDateIndex: dict[str, list[dict[str, str]]]) -> dict[str, str] | None:
    MatchingRows = MriQcSubjectDateIndex.get(SubjectDateKey, [])

    if not MatchingRows:
        return None

    return sorted(MatchingRows, key=ScoreMriQcFallbackRow)[0]


def CountSubjectDateRows(SubjectDateKey: str, SubjectDateIndex: dict[str, list[dict[str, str]]]) -> int:
    return len(SubjectDateIndex.get(SubjectDateKey, []))


def NormaliseQcStatusFromMri3Meta(Mri3MetaRow: dict[str, str] | None) -> str:
    QcErrorValue = GetFirstAvailableValue(Mri3MetaRow, ["HAS_QC_ERROR"])
    QcErrorText = NormaliseText(QcErrorValue).upper()

    if not QcErrorText:
        return ""

    if QcErrorText in {"0", "N", "NO", "FALSE"}:
        return "NoQcError"

    if QcErrorText in {"1", "Y", "YES", "TRUE"}:
        return "HasQcError"

    return QcErrorValue


def InspectNiftiFiles(DataRootDirectory: Path) -> list[dict[str, object]]:
    """Create one base manifest row per extracted NIfTI image."""
    ImagesDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Images"
    NiftiRows: list[dict[str, object]] = []

    if not ImagesDirectory.exists():
        return NiftiRows

    for ImageFilePath in sorted(ImagesDirectory.rglob("*")):
        if not ImageFilePath.is_file():
            continue

        if not IsNiftiFile(ImageFilePath):
            continue

        ImageIdKey = ExtractImageIdFromText(ImageFilePath)
        SubjectIdFromPath = ExtractSubjectIdFromText(ImageFilePath)

        NiftiRows.append(
            {
                "ImageIdKey": ImageIdKey,
                "ImageId": FormatImageId(ImageIdKey),
                "SubjectIdFromPath": SubjectIdFromPath,
                "ImageFileName": ImageFilePath.name,
                "ImageRelativePath": GetRelativePath(ImageFilePath, DataRootDirectory),
                "ImageDirectory": GetRelativePath(ImageFilePath.parent, DataRootDirectory),
                "ImageSizeMegabytes": round(GetFileSizeMegabytes(ImageFilePath), 3),
            }
        )

    return NiftiRows


def LoadAndIndexFirstTable(CsvFilePaths: list[Path]) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]], str]:
    """Load the first matching metadata table and index it by image identifier."""
    if not CsvFilePaths:
        return [], {}, ""

    CsvFilePath = CsvFilePaths[0]
    TableRows = ReadCsvRows(CsvFilePath)
    ImageIdIndex = BuildImageIdIndex(TableRows)

    return TableRows, ImageIdIndex, CsvFilePath.name


def LoadAndIndexAllTables(CsvFilePaths: list[Path]) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]], str]:
    """Load multiple metadata tables and index their combined rows by image identifier."""
    CombinedRows: list[dict[str, str]] = []
    SourceFileNames: list[str] = []

    for CsvFilePath in CsvFilePaths:
        TableRows = ReadCsvRows(CsvFilePath)
        CombinedRows.extend(TableRows)
        SourceFileNames.append(CsvFilePath.name)

    ImageIdIndex = BuildImageIdIndex(CombinedRows)

    return CombinedRows, ImageIdIndex, "; ".join(SourceFileNames)


def BuildIdaMetadataRows(DataRootDirectory: Path) -> list[dict[str, str]]:
    """Build lightweight metadata rows from extracted IDA metadata file paths and text."""
    IdaMetadataRows: list[dict[str, str]] = []

    for MetadataFilePath in FindIdaMetadataFiles(DataRootDirectory):
        RelativePath = GetRelativePath(MetadataFilePath, DataRootDirectory)
        SearchText = f"{MetadataFilePath.name}\n{MetadataFilePath.parent}\n"

        FileExtension = MetadataFilePath.suffix.lower()

        if FileExtension in {".txt", ".xml", ".json", ".csv", ".html", ".htm"}:
            try:
                SearchText += ReadTextFile(MetadataFilePath)[:20000]
            except Exception:
                pass

        ImageIdKey = ExtractImageIdFromText(SearchText)

        if not ImageIdKey:
            continue

        IdaMetadataRows.append(
            {
                "ImageId": FormatImageId(ImageIdKey),
                "ImageIdKey": ImageIdKey,
                "SubjectId": ExtractSubjectIdFromText(SearchText),
                "StudyDate": ExtractDateFromText(SearchText),
                "MetadataFileName": MetadataFilePath.name,
                "MetadataRelativePath": RelativePath,
                "MetadataDirectory": GetRelativePath(MetadataFilePath.parent, DataRootDirectory),
                "MetadataFileExtension": FileExtension,
            }
        )

    return IdaMetadataRows


def GetMetadataValue(
    PrimaryRow: dict[str, str] | None,
    SecondaryRow: dict[str, str] | None,
    ExactColumnCandidates: list[str],
    FragmentColumnCandidates: list[str] | None = None,
) -> str:
    """Return a metadata value from a primary row, then from a secondary row."""
    FragmentColumnCandidates = FragmentColumnCandidates or []

    PrimaryExactValue = GetFirstAvailableValue(PrimaryRow, ExactColumnCandidates)

    if PrimaryExactValue:
        return PrimaryExactValue

    PrimaryFragmentValue = GetFirstAvailableValueContaining(PrimaryRow, FragmentColumnCandidates)

    if PrimaryFragmentValue:
        return PrimaryFragmentValue

    SecondaryExactValue = GetFirstAvailableValue(SecondaryRow, ExactColumnCandidates)

    if SecondaryExactValue:
        return SecondaryExactValue

    return GetFirstAvailableValueContaining(SecondaryRow, FragmentColumnCandidates)


def BuildImageManifestRows(DataRootDirectory: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Join NIfTI files to IDA metadata, ADNI MRI metadata, QC, ranking, and standardised-list indicators."""
    PrintProgress("Building image manifest rows.")
    ClinicalStudyDataDirectory = DataRootDirectory / "Raw" / "Clinical" / "StudyData"

    Mri3MetaCsvFiles = FindClinicalCsvFiles(ClinicalStudyDataDirectory, "MRI3META_*.csv")
    MriQcCsvFiles = FindClinicalCsvFiles(ClinicalStudyDataDirectory, "MRIQC_*.csv")
    MriMprageRankCsvFiles = FindClinicalCsvFiles(ClinicalStudyDataDirectory, "MRIMPRANK_*.csv")
    StandardisedListCsvFiles = FindStandardisedListCsvFiles(ClinicalStudyDataDirectory)

    PrintProgress(f"Found MRI3META files: {len(Mri3MetaCsvFiles)}")
    PrintProgress(f"Found MRIQC files: {len(MriQcCsvFiles)}")
    PrintProgress(f"Found MRIMPRANK files: {len(MriMprageRankCsvFiles)}")
    PrintProgress(f"Found standardised-list files: {len(StandardisedListCsvFiles)}")
    PrintProgress("Loading and indexing MRI metadata tables.")

    Mri3MetaRows, Mri3MetaIndex, Mri3MetaSourceFiles = LoadAndIndexFirstTable(Mri3MetaCsvFiles)
    MriQcRows, MriQcIndex, MriQcSourceFiles = LoadAndIndexFirstTable(MriQcCsvFiles)
    MriMprageRankRows, MriMprageRankIndex, MriMprageRankSourceFiles = LoadAndIndexFirstTable(MriMprageRankCsvFiles)

    PrintProgress(f"MRI3META rows loaded: {len(Mri3MetaRows)}")
    PrintProgress(f"MRIQC rows loaded: {len(MriQcRows)}")
    PrintProgress(f"MRIMPRANK rows loaded: {len(MriMprageRankRows)}")
    PrintProgress("Building subject-date fallback indexes.")

    Mri3MetaSubjectDateIndex = BuildSubjectDateIndex(
        TableRows=Mri3MetaRows,
        SubjectColumns=["PTID", "ParticipantID", "SubjectId", "Subject ID"],
        DateColumns=["EXAMDATE", "StudyDate", "ScanDate", "USERDATE", "USERDATE2"],
    )
    MriQcSubjectDateIndex = BuildSubjectDateIndex(
        TableRows=MriQcRows,
        SubjectColumns=["ParticipantID", "PTID", "SubjectId", "Subject ID"],
        DateColumns=["StudyDate", "EXAMDATE", "ScanDate"],
    )
    MriMprageRankSubjectDateIndex = BuildSubjectDateIndex(
        TableRows=MriMprageRankRows,
        SubjectColumns=["PTID", "ParticipantID", "SubjectId", "Subject ID"],
        DateColumns=["EXAMDATE", "StudyDate", "ScanDate", "USERDATE", "USERDATE2"],
    )

    IdaMetadataRows = BuildIdaMetadataRows(DataRootDirectory)
    IdaMetadataIndex = BuildImageIdIndex(IdaMetadataRows)

    StandardisedImageIdSet = BuildImageIdSetFromTables(StandardisedListCsvFiles)
    PrintProgress(f"Standardised-list image IDs indexed: {len(StandardisedImageIdSet)}")
    PrintProgress("Inspecting extracted NIfTI files.")
    NiftiRows = InspectNiftiFiles(DataRootDirectory)
    PrintProgress(f"NIfTI rows found: {len(NiftiRows)}")
    ImageManifestRows: list[dict[str, object]] = []
    TotalNiftiRows = len(NiftiRows)

    for RowIndex, NiftiRow in enumerate(NiftiRows, start=1):
        ImageIdKey = str(NiftiRow["ImageIdKey"])

        IdaMetadataRow = GetFirstIndexedRow(ImageIdKey, IdaMetadataIndex)
        Mri3MetaRowByImageId = GetFirstIndexedRow(ImageIdKey, Mri3MetaIndex)
        MriQcRowByImageId = GetFirstIndexedRow(ImageIdKey, MriQcIndex)
        MriMprageRankRowByImageId = GetFirstIndexedRow(ImageIdKey, MriMprageRankIndex)

        SubjectIdFromMetadata = GetMetadataValue(
            PrimaryRow=MriQcRowByImageId,
            SecondaryRow=IdaMetadataRow,
            ExactColumnCandidates=["ParticipantID", "PTID", "Subject ID", "SubjectID", "SUBJECT", "Subject", "SubjectId"],
            FragmentColumnCandidates=["Subject", "Participant", "PTID"],
        )

        if not SubjectIdFromMetadata:
            SubjectIdFromMetadata = str(NiftiRow["SubjectIdFromPath"])

        StudyDateFromMetadata = GetMetadataValue(
            PrimaryRow=MriQcRowByImageId,
            SecondaryRow=IdaMetadataRow,
            ExactColumnCandidates=[
                "StudyDate",
                "Study Date",
                "EXAMDATE",
                "ScanDate",
                "Scan Date",
                "AcqDate",
                "AcquisitionDate",
                "SeriesDate",
                "Date",
            ],
            FragmentColumnCandidates=["Date"],
        )

        SubjectDateKey = GetSubjectDateKey(SubjectIdFromMetadata, StudyDateFromMetadata)

        Mri3MetaRowBySubjectDate = None
        MriQcRowBySubjectDate = None
        MriMprageRankRowBySubjectDate = None

        if SubjectDateKey:
            Mri3MetaRowsBySubjectDate = Mri3MetaSubjectDateIndex.get(SubjectDateKey, [])
            if Mri3MetaRowsBySubjectDate:
                Mri3MetaRowBySubjectDate = Mri3MetaRowsBySubjectDate[0]

            MriQcRowBySubjectDate = GetBestMriQcSubjectDateRow(
                SubjectDateKey=SubjectDateKey,
                MriQcSubjectDateIndex=MriQcSubjectDateIndex,
            )

            MriMprageRankRowsBySubjectDate = MriMprageRankSubjectDateIndex.get(SubjectDateKey, [])
            if MriMprageRankRowsBySubjectDate:
                MriMprageRankRowBySubjectDate = sorted(
                    MriMprageRankRowsBySubjectDate,
                    key=lambda Row: int(float(GetFirstAvailableValue(Row, ["RANK"]) or 999999)),
                )[0]

        Mri3MetaRow = Mri3MetaRowByImageId or Mri3MetaRowBySubjectDate
        MriQcRow = MriQcRowByImageId or MriQcRowBySubjectDate
        MriMprageRankRow = MriMprageRankRowByImageId or MriMprageRankRowBySubjectDate

        SubjectId = GetMetadataValue(
            PrimaryRow=Mri3MetaRow,
            SecondaryRow=IdaMetadataRow,
            ExactColumnCandidates=["PTID", "Subject ID", "SubjectID", "SUBJECT", "Subject", "SubjectId"],
            FragmentColumnCandidates=["Subject", "PTID"],
        )

        if not SubjectId:
            SubjectId = str(NiftiRow["SubjectIdFromPath"])

        StudyDate = GetMetadataValue(
            PrimaryRow=Mri3MetaRow,
            SecondaryRow=IdaMetadataRow,
            ExactColumnCandidates=[
                "StudyDate",
                "Study Date",
                "EXAMDATE",
                "ScanDate",
                "Scan Date",
                "AcqDate",
                "AcquisitionDate",
                "SeriesDate",
                "Date",
            ],
            FragmentColumnCandidates=["Date"],
        )

        ImageDescription = GetMetadataValue(
            PrimaryRow=Mri3MetaRow,
            SecondaryRow=IdaMetadataRow,
            ExactColumnCandidates=[
                "ImageDescription",
                "Image Description",
                "SeriesDescription",
                "Series Description",
                "Sequence",
                "Protocol",
                "Description",
            ],
            FragmentColumnCandidates=["Description", "Sequence", "Protocol"],
        )

        ImageManifestRows.append(
            {
                "ImageId": NiftiRow["ImageId"],
                "ImageIdKey": ImageIdKey,
                "SubjectId": SubjectId,
                "SubjectIdFromPath": NiftiRow["SubjectIdFromPath"],
                "RID": GetFirstAvailableValue(Mri3MetaRow, ["RID"]),
                "VisitCode": GetFirstAvailableValue(Mri3MetaRow, ["VISCODE", "VISCODE2", "Visit", "VisitCode"]),
                "StudyDate": StudyDate,
                "ImageDescription": ImageDescription,
                "FieldStrength": GetMetadataValue(
                    PrimaryRow=MriQcRow,
                    SecondaryRow=Mri3MetaRow,
                    ExactColumnCandidates=[
                        "MagneticFieldStrength",
                        "FIELD_STRENGTH",
                        "FieldStrength",
                        "Field Strength",
                        "MagStrength",
                        "MAGSTRENGTH",
                        "FLDSTRENG",
                        "FLDSTRNGTH",
                        "Tesla",
                    ],
                    FragmentColumnCandidates=["Field", "Tesla", "Strength"],
                ),
                "Weighting": GetMetadataValue(
                    PrimaryRow=Mri3MetaRow,
                    SecondaryRow=IdaMetadataRow,
                    ExactColumnCandidates=["Weighting", "SequenceWeighting"],
                    FragmentColumnCandidates=["Weighting"],
                ),
                "AcquisitionType": GetMetadataValue(
                    PrimaryRow=Mri3MetaRow,
                    SecondaryRow=IdaMetadataRow,
                    ExactColumnCandidates=["AcquisitionType", "Acquisition Type", "AcqType"],
                    FragmentColumnCandidates=["AcquisitionType", "AcqType"],
                ),
                "AcquisitionPlane": GetMetadataValue(
                    PrimaryRow=Mri3MetaRow,
                    SecondaryRow=IdaMetadataRow,
                    ExactColumnCandidates=["AcquisitionPlane", "Acquisition Plane", "AcqPlane", "Plane"],
                    FragmentColumnCandidates=["Plane"],
                ),
                "Manufacturer": GetMetadataValue(
                    PrimaryRow=MriQcRow,
                    SecondaryRow=IdaMetadataRow,
                    ExactColumnCandidates=["ScannerManufacturer", "Manufacturer", "Mfg", "MFG"],
                    FragmentColumnCandidates=["Manufacturer", "MFG"],
                ),
                "ScannerModel": GetMetadataValue(
                    PrimaryRow=MriQcRow,
                    SecondaryRow=IdaMetadataRow,
                    ExactColumnCandidates=["ScannerModel", "Scanner Model", "MfgModel", "Mfg Model", "Model"],
                    FragmentColumnCandidates=["Model"],
                ),
                "QcStatus": NormaliseQcStatusFromMri3Meta(Mri3MetaRow),
                "MprageRank": GetFirstAvailableValueContaining(
                    MriMprageRankRow,
                    ["Rank"],
                ),
                "InStandardised3TList": ImageIdKey in StandardisedImageIdSet,
                "IdaMetadataMatchCount": CountIndexedRows(ImageIdKey, IdaMetadataIndex),
                "Mri3MetaMatchCount": max(
                    CountIndexedRows(ImageIdKey, Mri3MetaIndex),
                    CountSubjectDateRows(SubjectDateKey, Mri3MetaSubjectDateIndex),
                ),
                "MriQcMatchCount": max(
                    CountIndexedRows(ImageIdKey, MriQcIndex),
                    CountSubjectDateRows(SubjectDateKey, MriQcSubjectDateIndex),
                ),
                "MprageRankMatchCount": max(
                    CountIndexedRows(ImageIdKey, MriMprageRankIndex),
                    CountSubjectDateRows(SubjectDateKey, MriMprageRankSubjectDateIndex),
                ),
                "ImageFileName": NiftiRow["ImageFileName"],
                "ImageRelativePath": NiftiRow["ImageRelativePath"],
                "ImageDirectory": NiftiRow["ImageDirectory"],
                "ImageSizeMegabytes": NiftiRow["ImageSizeMegabytes"],
            }
        )


        if RowIndex == 1 or RowIndex % ProgressPrintEvery == 0 or RowIndex == TotalNiftiRows:
            CurrentRow = ImageManifestRows[-1]
            PrintProgress(
                "Image row "
                f"{RowIndex}/{TotalNiftiRows}: "
                f"Image {CurrentRow['ImageId']}, "
                f"Subject {CurrentRow['SubjectId']}, "
                f"StudyDate={CurrentRow['StudyDate']}, "
                f"MRIQCMatches={CurrentRow['MriQcMatchCount']}"
            )

    PrintProgress("Summarising image manifest metadata coverage.")

    SummaryValues = {
        "NiftiFileCount": len(NiftiRows),
        "ImageManifestRowCount": len(ImageManifestRows),
        "MissingImageIdCount": sum(1 for ImageManifestRow in ImageManifestRows if not ImageManifestRow["ImageIdKey"]),
        "IdaMetadataMatchedImageCount": sum(
            1 for ImageManifestRow in ImageManifestRows if int(ImageManifestRow["IdaMetadataMatchCount"]) > 0
        ),
        "Mri3MetaMatchedImageCount": sum(
            1 for ImageManifestRow in ImageManifestRows if int(ImageManifestRow["Mri3MetaMatchCount"]) > 0
        ),
        "MriQcMatchedImageCount": sum(
            1 for ImageManifestRow in ImageManifestRows if int(ImageManifestRow["MriQcMatchCount"]) > 0
        ),
        "MprageRankMatchedImageCount": sum(
            1 for ImageManifestRow in ImageManifestRows if int(ImageManifestRow["MprageRankMatchCount"]) > 0
        ),
        "StandardisedListMatchedImageCount": sum(
            1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["InStandardised3TList"] is True
        ),
        "SubjectIdAvailableCount": sum(1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["SubjectId"]),
        "StudyDateAvailableCount": sum(1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["StudyDate"]),
        "ImageDescriptionAvailableCount": sum(
            1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["ImageDescription"]
        ),
        "FieldStrengthAvailableCount": sum(1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["FieldStrength"]),
        "ManufacturerAvailableCount": sum(1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["Manufacturer"]),
        "ScannerModelAvailableCount": sum(1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["ScannerModel"]),
        "QcStatusAvailableCount": sum(1 for ImageManifestRow in ImageManifestRows if ImageManifestRow["QcStatus"]),
        "Mri3MetaSourceFiles": Mri3MetaSourceFiles,
        "MriQcSourceFiles": MriQcSourceFiles,
        "MriMprageRankSourceFiles": MriMprageRankSourceFiles,
        "IdaMetadataFileCount": len(IdaMetadataRows),
        "StandardisedListSourceFileCount": len(StandardisedListCsvFiles),
    }

    return ImageManifestRows, SummaryValues


def BuildSummaryRows(SummaryValues: dict[str, object]) -> list[dict[str, object]]:
    """Convert summary values to CSV-friendly metric rows."""
    MetricNames = [
        "NiftiFileCount",
        "ImageManifestRowCount",
        "MissingImageIdCount",
        "IdaMetadataMatchedImageCount",
        "Mri3MetaMatchedImageCount",
        "MriQcMatchedImageCount",
        "MprageRankMatchedImageCount",
        "StandardisedListMatchedImageCount",
        "SubjectIdAvailableCount",
        "StudyDateAvailableCount",
        "ImageDescriptionAvailableCount",
        "FieldStrengthAvailableCount",
        "ManufacturerAvailableCount",
        "ScannerModelAvailableCount",
        "QcStatusAvailableCount",
        "IdaMetadataFileCount",
        "StandardisedListSourceFileCount",
        "Mri3MetaSourceFiles",
        "MriQcSourceFiles",
        "MriMprageRankSourceFiles",
    ]

    return [{"Metric": MetricName, "Value": SummaryValues.get(MetricName, "")} for MetricName in MetricNames]


def WriteMarkdownSummary(OutputFilePath: Path, SummaryRows: list[dict[str, object]]) -> None:
    """Write a brief Markdown summary for the image manifest build."""
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# Image Manifest Summary\n\n")
        OutputFile.write(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def ParseArguments() -> argparse.Namespace:
    """Parse command-line arguments for image manifest construction."""
    ArgumentParser = argparse.ArgumentParser(
        description="Build an image-level manifest for unpacked ADNI MRI files."
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
        default=Path("Data") / "Interim" / "Imaging",
        help="Directory for image manifest outputs. Default: Data/Interim/Imaging",
    )

    return ArgumentParser.parse_args()


def Main() -> None:
    StartedAt = datetime.now()
    PrintProgress("Starting image manifest build.")
    Arguments = ParseArguments()

    OutputDirectory = Arguments.output_directory
    EnsureDirectory(OutputDirectory)

    ImageManifestRows, SummaryValues = BuildImageManifestRows(DataRootDirectory=Arguments.data_root)
    SummaryRows = BuildSummaryRows(SummaryValues)

    ImageManifestFieldNames = [
        "ImageId",
        "ImageIdKey",
        "SubjectId",
        "SubjectIdFromPath",
        "RID",
        "VisitCode",
        "StudyDate",
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
    ]

    WriteCsv(
        OutputFilePath=OutputDirectory / "ImageManifest.csv",
        FieldNames=ImageManifestFieldNames,
        DataRows=ImageManifestRows,
    )

    WriteCsv(
        OutputFilePath=OutputDirectory / "ImageManifestSummary.csv",
        FieldNames=["Metric", "Value"],
        DataRows=SummaryRows,
    )

    WriteMarkdownSummary(
        OutputFilePath=OutputDirectory / "ImageManifestSummary.md",
        SummaryRows=SummaryRows,
    )

    ElapsedSeconds = round((datetime.now() - StartedAt).total_seconds(), 1)
    PrintProgress("Image manifest build complete.")
    print(f"Output directory: {OutputDirectory}")
    print(f"Image manifest rows: {len(ImageManifestRows)}")
    print(f"Elapsed seconds: {ElapsedSeconds}")


if __name__ == "__main__":
    Main()