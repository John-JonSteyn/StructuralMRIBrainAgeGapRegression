"""Build and inspect a regional FastSurfer feature table for analysis."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


FastSurferInputManifestPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferInputManifest.csv"
FastSurferOutputRootDirectory = Path("Data") / "Processed" / "FastSurfer"
SelectedBaselineCohortPath = Path("Data") / "Interim" / "Cohort" / "SelectedBaselineCohort.csv"

OutputDirectory = Path("Data") / "Processed" / "Analysis"
FastSurferRegionalFeaturesPath = OutputDirectory / "FastSurferRegionalFeatures.csv"
FastSurferRegionalFeaturesSummaryPath = OutputDirectory / "FastSurferRegionalFeaturesSummary.csv"
FastSurferRegionalFeaturesMarkdownSummaryPath = OutputDirectory / "FastSurferRegionalFeaturesSummary.md"
FastSurferFeatureDictionaryPath = OutputDirectory / "FastSurferFeatureDictionary.csv"
FastSurferRegionalFeatureExclusionsPath = OutputDirectory / "FastSurferRegionalFeatureExclusions.csv"
FastSurferRegionalFeatureMetadataCoveragePath = OutputDirectory / "FastSurferRegionalFeatureMetadataCoverage.csv"
FastSurferRegionalFeatureMissingnessPath = OutputDirectory / "FastSurferRegionalFeatureMissingness.csv"
FastSurferRegionalFeatureProblemColumnsPath = OutputDirectory / "FastSurferRegionalFeatureProblemColumns.csv"
FastSurferRegionalFeatureDictionaryAuditPath = OutputDirectory / "FastSurferRegionalFeatureDictionaryAudit.csv"

ProgressPrintEvery = 10
HighMissingnessThresholdPercent = 5.0

RequiredStatsFileNames = [
    "aseg.stats",
    "brainvol.stats",
    "lh.aparc.DKTatlas.mapped.stats",
    "rh.aparc.DKTatlas.mapped.stats",
    "wmparc.DKTatlas.mapped.stats",
]

StatsFileSettings = {
    "aseg.stats": {
        "FeaturePrefix": "FastSurfer_Aseg",
        "FeatureGroup": "SubcorticalSegmentation",
        "Hemisphere": "",
    },
    "brainvol.stats": {
        "FeaturePrefix": "FastSurfer_BrainVol",
        "FeatureGroup": "BrainVolumeSummary",
        "Hemisphere": "",
    },
    "lh.aparc.DKTatlas.mapped.stats": {
        "FeaturePrefix": "FastSurfer_LhDkt",
        "FeatureGroup": "LeftCorticalDktAtlas",
        "Hemisphere": "Left",
    },
    "rh.aparc.DKTatlas.mapped.stats": {
        "FeaturePrefix": "FastSurfer_RhDkt",
        "FeatureGroup": "RightCorticalDktAtlas",
        "Hemisphere": "Right",
    },
    "wmparc.DKTatlas.mapped.stats": {
        "FeaturePrefix": "FastSurfer_WmparcDkt",
        "FeatureGroup": "WhiteMatterParcellationDktAtlas",
        "Hemisphere": "",
    },
}

MetadataFieldCandidates = {
    "RID": ["RID"],
    "SubjectId": ["SubjectId", "Subject ID"],
    "ImageId": ["ImageId", "Image ID"],
    "Diagnosis3Class": ["Diagnosis3Class"],
    "Age": ["Age"],
    "Sex": ["Sex"],
    "Education": ["Education", "PTEDUCAT"],
    "MMSE": ["MMSE", "MMSCORE", "MMSEScore"],
    "ADAS13": ["ADAS13", "ADAS13Score"],
    "CDRSB": ["CDRSB", "CDRSumOfBoxes"],
    "FAQ": ["FAQ", "FAQScore"],
    "ImageStudyDate": ["ImageStudyDate", "StudyDate", "MRIStudyDate"],
    "ClinicalExamDate": ["ClinicalExamDate", "ExamDate", "VisitDate", "EXAMDATE"],
    "QcStatus": ["QcStatus", "MRIQCStatus", "MriQcStatus"],
    "Manufacturer": ["Manufacturer", "MriManufacturer"],
    "ScannerModel": ["ScannerModel", "MfgModel", "Mfg Model", "ManufacturerModel", "MriScannerModel"],
    "FieldStrength": ["FieldStrength", "Field Strength"],
    "FastSurferSubjectId": ["FastSurferSubjectId"],
}

OutputMetadataFields = [
    "RID",
    "SubjectId",
    "ImageId",
    "Diagnosis3Class",
    "Age",
    "Sex",
    "Education",
    "MMSE",
    "ADAS13",
    "CDRSB",
    "FAQ",
    "ImageStudyDate",
    "ClinicalExamDate",
    "QcStatus",
    "Manufacturer",
    "ScannerModel",
    "FieldStrength",
    "FastSurferSubjectId",
    "FastSurferStatus",
]

CoreMetadataFields = [
    "RID",
    "SubjectId",
    "ImageId",
    "Diagnosis3Class",
    "Age",
    "Sex",
    "Education",
    "ImageStudyDate",
    "ClinicalExamDate",
    "FastSurferSubjectId",
    "FastSurferStatus",
]

ScannerAndQcFields = [
    "QcStatus",
    "Manufacturer",
    "ScannerModel",
    "FieldStrength",
]

CognitiveFields = [
    "MMSE",
    "ADAS13",
    "CDRSB",
    "FAQ",
]

DateFields = [
    "ImageStudyDate",
    "ClinicalExamDate",
]

IdentifierColumnNames = {
    "index",
    "segid",
    "structname",
    "labelid",
    "labelname",
}

FeatureDictionaryFields = [
    "FeatureName",
    "SourceFileName",
    "FeatureGroup",
    "FeatureType",
    "Hemisphere",
    "StructureName",
    "MetricName",
    "Unit",
    "Description",
]


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def PrintProgress(Message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {Message}", flush=True)


def NormaliseText(TextValue: object) -> str:
    return str(TextValue).strip() if TextValue is not None else ""


def NormaliseHeader(Header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Header.lower())


def CleanFeatureToken(TextValue: object) -> str:
    TextValue = NormaliseText(TextValue)
    TextValue = re.sub(r"[^A-Za-z0-9]+", "_", TextValue)
    TextValue = re.sub(r"_+", "_", TextValue).strip("_")

    if not TextValue:
        return "Missing"

    if TextValue[0].isdigit():
        TextValue = f"X{TextValue}"

    return TextValue


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


def WriteMarkdownSummary(SummaryRows: list[dict[str, object]]) -> None:
    EnsureDirectory(FastSurferRegionalFeaturesMarkdownSummaryPath.parent)

    with FastSurferRegionalFeaturesMarkdownSummaryPath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# FastSurfer Regional Features Summary\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def ValidateInputs() -> None:
    if not FastSurferInputManifestPath.exists():
        raise FileNotFoundError(f"FastSurfer input manifest not found: {FastSurferInputManifestPath}")

    if not SelectedBaselineCohortPath.exists():
        raise FileNotFoundError(f"Selected baseline cohort file not found: {SelectedBaselineCohortPath}")

    if not FastSurferOutputRootDirectory.exists():
        raise FileNotFoundError(f"FastSurfer output directory not found: {FastSurferOutputRootDirectory}")


def GetHeaders(DataRows: list[dict[str, str]]) -> list[str]:
    if not DataRows:
        return []

    return list(DataRows[0].keys())


def GetFirstExistingField(Headers: list[str], CandidateFields: list[str]) -> str:
    HeaderLookup = {NormaliseHeader(Header): Header for Header in Headers}

    for CandidateField in CandidateFields:
        MatchingHeader = HeaderLookup.get(NormaliseHeader(CandidateField))

        if MatchingHeader:
            return MatchingHeader

    return ""


def GetMetadataValue(DataRow: dict[str, str], Headers: list[str], OutputFieldName: str) -> str:
    CandidateFields = MetadataFieldCandidates.get(OutputFieldName, [OutputFieldName])
    SourceFieldName = GetFirstExistingField(Headers, CandidateFields)

    if not SourceFieldName:
        return ""

    return NormaliseText(DataRow.get(SourceFieldName, ""))


def BuildRowsByImageId(DataRows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    RowsByImageId: dict[str, dict[str, str]] = {}
    Headers = GetHeaders(DataRows)

    for DataRow in DataRows:
        ImageId = GetMetadataValue(DataRow, Headers, "ImageId")

        if not ImageId:
            continue

        if ImageId not in RowsByImageId:
            RowsByImageId[ImageId] = DataRow

    return RowsByImageId


def GetMergedMetadataValue(
    CohortRow: dict[str, str],
    CohortHeaders: list[str],
    ManifestRow: dict[str, str],
    ManifestHeaders: list[str],
    OutputFieldName: str,
) -> str:
    CohortValue = GetMetadataValue(CohortRow, CohortHeaders, OutputFieldName)

    if CohortValue:
        return CohortValue

    return GetMetadataValue(ManifestRow, ManifestHeaders, OutputFieldName)


def GetSubjectOutputDirectory(FastSurferSubjectId: str) -> Path:
    return FastSurferOutputRootDirectory / FastSurferSubjectId


def GetStatsDirectory(FastSurferSubjectId: str) -> Path:
    return GetSubjectOutputDirectory(FastSurferSubjectId) / "stats"


def GetStatsFilePath(FastSurferSubjectId: str, StatsFileName: str) -> Path:
    return GetStatsDirectory(FastSurferSubjectId) / StatsFileName


def GetMissingRequiredStatsFiles(FastSurferSubjectId: str) -> list[str]:
    MissingStatsFileNames: list[str] = []

    for RequiredStatsFileName in RequiredStatsFileNames:
        RequiredStatsFilePath = GetStatsFilePath(FastSurferSubjectId, RequiredStatsFileName)

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


def ParseFloat(NumberText: object) -> float | None:
    NumberText = NormaliseText(NumberText)

    if not NumberText:
        return None

    try:
        return float(NumberText)
    except ValueError:
        return None


def IsPresent(TextValue: object) -> bool:
    return bool(NormaliseText(TextValue))


def IsNumericValue(TextValue: object) -> bool:
    return ParseFloat(TextValue) is not None


def FormatNumericValue(TextValue: object) -> str:
    NumericValue = ParseFloat(TextValue)

    if NumericValue is None:
        return ""

    return f"{NumericValue:.10g}"


def InferUnitFromMetricName(MetricName: str) -> str:
    MetricNameLower = MetricName.lower()

    if "mm3" in MetricNameLower:
        return "mm3"

    if "mm^3" in MetricNameLower:
        return "mm3"

    if MetricNameLower in {"surfarea", "surfacearea"}:
        return "mm2"

    if "area" in MetricNameLower and "curv" not in MetricNameLower:
        return "mm2"

    if MetricNameLower in {"thickavg", "thickstd", "thickness"}:
        return "mm"

    if MetricNameLower in {"numvert"}:
        return "vertices"

    if MetricNameLower in {"nvoxels", "nvtxs"}:
        return "voxels"

    return ""


def GetStatsFileSetting(StatsFileName: str, SettingName: str) -> str:
    return NormaliseText(StatsFileSettings.get(StatsFileName, {}).get(SettingName, ""))


def AddFeatureDictionaryRow(
    FeatureDictionaryRowsByName: dict[str, dict[str, object]],
    FeatureName: str,
    SourceFileName: str,
    FeatureType: str,
    StructureName: str,
    MetricName: str,
    Unit: str,
    Description: str,
) -> None:
    if FeatureName in FeatureDictionaryRowsByName:
        return

    FeatureDictionaryRowsByName[FeatureName] = {
        "FeatureName": FeatureName,
        "SourceFileName": SourceFileName,
        "FeatureGroup": GetStatsFileSetting(SourceFileName, "FeatureGroup"),
        "FeatureType": FeatureType,
        "Hemisphere": GetStatsFileSetting(SourceFileName, "Hemisphere"),
        "StructureName": StructureName,
        "MetricName": MetricName,
        "Unit": Unit,
        "Description": Description,
    }


def ParseMeasureLine(
    Line: str,
    StatsFileName: str,
    FeatureValues: dict[str, str],
    FeatureDictionaryRowsByName: dict[str, dict[str, object]],
) -> None:
    MeasureText = Line.replace("# Measure", "", 1).strip()

    if MeasureText.startswith(","):
        MeasureText = MeasureText[1:].strip()

    MeasureParts = [MeasurePart.strip() for MeasurePart in MeasureText.split(",")]

    if len(MeasureParts) < 2:
        return

    MeasureValue = MeasureParts[-2]
    Unit = MeasureParts[-1]

    if not IsNumericValue(MeasureValue):
        return

    if len(MeasureParts) >= 4:
        MeasureName = MeasureParts[1] or MeasureParts[0]
        Description = MeasureParts[2]
    else:
        MeasureName = MeasureParts[0]
        Description = ""

    FeaturePrefix = GetStatsFileSetting(StatsFileName, "FeaturePrefix")
    FeatureName = f"{FeaturePrefix}_Measure_{CleanFeatureToken(MeasureName)}"

    FeatureValues[FeatureName] = FormatNumericValue(MeasureValue)

    AddFeatureDictionaryRow(
        FeatureDictionaryRowsByName=FeatureDictionaryRowsByName,
        FeatureName=FeatureName,
        SourceFileName=StatsFileName,
        FeatureType="Measure",
        StructureName="",
        MetricName=MeasureName,
        Unit=Unit,
        Description=Description,
    )


def GetStructureName(TableRow: dict[str, str]) -> str:
    StructureFieldCandidates = [
        "StructName",
        "StructureName",
        "LabelName",
        "Name",
    ]

    for StructureFieldName in StructureFieldCandidates:
        StructureName = NormaliseText(TableRow.get(StructureFieldName, ""))

        if StructureName:
            return StructureName

    SegId = NormaliseText(TableRow.get("SegId", ""))

    if SegId:
        return f"SegId_{SegId}"

    return ""


def ParseStatsTableRow(
    TableRow: dict[str, str],
    StatsFileName: str,
    FeatureValues: dict[str, str],
    FeatureDictionaryRowsByName: dict[str, dict[str, object]],
) -> None:
    StructureName = GetStructureName(TableRow)

    if not StructureName:
        return

    FeaturePrefix = GetStatsFileSetting(StatsFileName, "FeaturePrefix")

    for MetricName, MetricValue in TableRow.items():
        if MetricName.lower() in IdentifierColumnNames:
            continue

        if not IsNumericValue(MetricValue):
            continue

        FeatureName = f"{FeaturePrefix}_{CleanFeatureToken(StructureName)}_{CleanFeatureToken(MetricName)}"
        Unit = InferUnitFromMetricName(MetricName)

        FeatureValues[FeatureName] = FormatNumericValue(MetricValue)

        AddFeatureDictionaryRow(
            FeatureDictionaryRowsByName=FeatureDictionaryRowsByName,
            FeatureName=FeatureName,
            SourceFileName=StatsFileName,
            FeatureType="RegionalTable",
            StructureName=StructureName,
            MetricName=MetricName,
            Unit=Unit,
            Description=f"{MetricName} for {StructureName}",
        )


def ParseStatsFile(
    StatsFilePath: Path,
    StatsFileName: str,
    FeatureDictionaryRowsByName: dict[str, dict[str, object]],
) -> dict[str, str]:
    FeatureValues: dict[str, str] = {}
    ColumnHeaders: list[str] = []

    with StatsFilePath.open("r", encoding="utf-8", errors="replace") as StatsFile:
        for RawLine in StatsFile:
            Line = RawLine.strip()

            if not Line:
                continue

            if Line.startswith("# Measure"):
                ParseMeasureLine(
                    Line=Line,
                    StatsFileName=StatsFileName,
                    FeatureValues=FeatureValues,
                    FeatureDictionaryRowsByName=FeatureDictionaryRowsByName,
                )
                continue

            if Line.startswith("# ColHeaders"):
                ColumnHeaders = Line.replace("# ColHeaders", "", 1).strip().split()
                continue

            if Line.startswith("#"):
                continue

            if not ColumnHeaders:
                continue

            RowValues = Line.split()

            if len(RowValues) < len(ColumnHeaders):
                continue

            if len(RowValues) > len(ColumnHeaders):
                RowValues = RowValues[: len(ColumnHeaders)]

            TableRow = dict(zip(ColumnHeaders, RowValues))

            ParseStatsTableRow(
                TableRow=TableRow,
                StatsFileName=StatsFileName,
                FeatureValues=FeatureValues,
                FeatureDictionaryRowsByName=FeatureDictionaryRowsByName,
            )

    return FeatureValues


def BuildMetadataRow(
    ManifestRow: dict[str, str],
    ManifestHeaders: list[str],
    CohortRow: dict[str, str],
    CohortHeaders: list[str],
    FastSurferStatus: str,
) -> dict[str, object]:
    MetadataRow: dict[str, object] = {}

    for OutputMetadataField in OutputMetadataFields:
        if OutputMetadataField == "FastSurferStatus":
            MetadataRow[OutputMetadataField] = FastSurferStatus
        elif OutputMetadataField == "FastSurferSubjectId":
            MetadataRow[OutputMetadataField] = GetMetadataValue(ManifestRow, ManifestHeaders, OutputMetadataField)
        else:
            MetadataRow[OutputMetadataField] = GetMergedMetadataValue(
                CohortRow=CohortRow,
                CohortHeaders=CohortHeaders,
                ManifestRow=ManifestRow,
                ManifestHeaders=ManifestHeaders,
                OutputFieldName=OutputMetadataField,
            )

    return MetadataRow


def BuildRegionalFeatureRows(
    ManifestRows: list[dict[str, str]],
    CohortRows: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    ManifestHeaders = GetHeaders(ManifestRows)
    CohortHeaders = GetHeaders(CohortRows)
    CohortRowsByImageId = BuildRowsByImageId(CohortRows)

    RegionalFeatureRows: list[dict[str, object]] = []
    ExclusionRows: list[dict[str, object]] = []
    FeatureDictionaryRowsByName: dict[str, dict[str, object]] = {}

    TotalRows = len(ManifestRows)
    PrintProgress(f"Checking {TotalRows} FastSurfer manifest rows.")
    PrintProgress(f"Selected baseline cohort rows available for metadata join: {len(CohortRowsByImageId)}")

    for RowIndex, ManifestRow in enumerate(ManifestRows, start=1):
        FastSurferSubjectId = GetMetadataValue(ManifestRow, ManifestHeaders, "FastSurferSubjectId")
        ImageId = GetMetadataValue(ManifestRow, ManifestHeaders, "ImageId")
        CohortRow = CohortRowsByImageId.get(ImageId, {})

        RID = GetMergedMetadataValue(CohortRow, CohortHeaders, ManifestRow, ManifestHeaders, "RID")
        SubjectId = GetMergedMetadataValue(CohortRow, CohortHeaders, ManifestRow, ManifestHeaders, "SubjectId")
        Diagnosis3Class = GetMergedMetadataValue(CohortRow, CohortHeaders, ManifestRow, ManifestHeaders, "Diagnosis3Class")

        FastSurferStatus = GetFastSurferStatus(FastSurferSubjectId)
        MissingRequiredStatsFiles = GetMissingRequiredStatsFiles(FastSurferSubjectId)

        ShouldPrintThisRow = RowIndex == 1 or RowIndex % ProgressPrintEvery == 0 or RowIndex == TotalRows

        if ShouldPrintThisRow:
            CohortJoinStatus = "MatchedCohort" if CohortRow else "MissingCohort"
            PrintProgress(
                f"Row {RowIndex}/{TotalRows}: RID {RID}, Image {ImageId}, "
                f"{Diagnosis3Class}, FastSurferStatus={FastSurferStatus}, {CohortJoinStatus}"
            )

        if FastSurferStatus != "Complete":
            PrintProgress(
                f"Excluding row {RowIndex}/{TotalRows}: RID {RID}, Image {ImageId}; "
                f"missing {len(MissingRequiredStatsFiles)} required stats files."
            )

            ExclusionRows.append(
                {
                    "RowNumber": RowIndex,
                    "RID": RID,
                    "SubjectId": SubjectId,
                    "ImageId": ImageId,
                    "Diagnosis3Class": Diagnosis3Class,
                    "FastSurferSubjectId": FastSurferSubjectId,
                    "FastSurferStatus": FastSurferStatus,
                    "MissingRequiredStatsFiles": "; ".join(MissingRequiredStatsFiles),
                    "ExclusionReason": "Incomplete FastSurfer required stats",
                }
            )
            continue

        RegionalFeatureRow = BuildMetadataRow(
            ManifestRow=ManifestRow,
            ManifestHeaders=ManifestHeaders,
            CohortRow=CohortRow,
            CohortHeaders=CohortHeaders,
            FastSurferStatus=FastSurferStatus,
        )

        for StatsFileName in RequiredStatsFileNames:
            StatsFilePath = GetStatsFilePath(FastSurferSubjectId, StatsFileName)

            if ShouldPrintThisRow:
                PrintProgress(f"Parsing {StatsFileName} for RID {RID}.")

            FeatureValues = ParseStatsFile(
                StatsFilePath=StatsFilePath,
                StatsFileName=StatsFileName,
                FeatureDictionaryRowsByName=FeatureDictionaryRowsByName,
            )
            RegionalFeatureRow.update(FeatureValues)

        RegionalFeatureRows.append(RegionalFeatureRow)

    PrintProgress(f"Finished parsing complete FastSurfer subjects: {len(RegionalFeatureRows)} included.")
    PrintProgress(f"Excluded incomplete FastSurfer subjects: {len(ExclusionRows)}.")

    FeatureDictionaryRows = [
        FeatureDictionaryRowsByName[FeatureName]
        for FeatureName in sorted(FeatureDictionaryRowsByName)
    ]

    PrintProgress(f"Feature dictionary rows built: {len(FeatureDictionaryRows)}.")

    return RegionalFeatureRows, FeatureDictionaryRows, ExclusionRows

def CountByField(DataRows: list[dict[str, object]], FieldName: str) -> dict[str, int]:
    ValueCounter: Counter[str] = Counter()

    for DataRow in DataRows:
        FieldValue = NormaliseText(DataRow.get(FieldName, "")) or "Missing"
        ValueCounter[FieldValue] += 1

    return dict(sorted(ValueCounter.items()))


def BuildCountRows(CountName: str, ValueCounts: dict[str, int]) -> list[dict[str, object]]:
    CountRows: list[dict[str, object]] = []

    for Value, Count in ValueCounts.items():
        CountRows.append(
            {
                "CountName": CountName,
                "Value": Value,
                "Count": Count,
            }
        )

    return CountRows


def GetAllFeatureFieldNames(RegionalFeatureRows: list[dict[str, object]]) -> list[str]:
    FeatureFieldNames = set()

    for RegionalFeatureRow in RegionalFeatureRows:
        for FieldName in RegionalFeatureRow.keys():
            if FieldName not in OutputMetadataFields:
                FeatureFieldNames.add(FieldName)

    return sorted(FeatureFieldNames)


def CompleteMissingFields(DataRows: list[dict[str, object]], FieldNames: list[str]) -> list[dict[str, object]]:
    CompletedRows: list[dict[str, object]] = []

    for DataRow in DataRows:
        CompletedRow = {}

        for FieldName in FieldNames:
            CompletedRow[FieldName] = DataRow.get(FieldName, "")

        CompletedRows.append(CompletedRow)

    return CompletedRows


def BuildMetadataCoverageRows(RegionalFeatureRows: list[dict[str, object]]) -> list[dict[str, object]]:
    CoverageRows: list[dict[str, object]] = []
    TotalRows = len(RegionalFeatureRows)

    for MetadataField in OutputMetadataFields:
        RowsWithValue = sum(1 for RegionalFeatureRow in RegionalFeatureRows if IsPresent(RegionalFeatureRow.get(MetadataField, "")))
        RowsMissingValue = TotalRows - RowsWithValue
        CoveragePercent = round((RowsWithValue / TotalRows) * 100, 2) if TotalRows else 0

        CoverageRows.append(
            {
                "FieldName": MetadataField,
                "RowsWithValue": RowsWithValue,
                "RowsMissingValue": RowsMissingValue,
                "CoveragePercent": CoveragePercent,
            }
        )

    return CoverageRows


def BuildFeatureMissingnessRows(
    RegionalFeatureRows: list[dict[str, object]],
    FeatureFieldNames: list[str],
) -> list[dict[str, object]]:
    MissingnessRows: list[dict[str, object]] = []
    TotalRows = len(RegionalFeatureRows)

    for FeatureFieldName in FeatureFieldNames:
        NumericValues: list[float] = []
        MissingRows = 0
        NonNumericRows = 0

        for RegionalFeatureRow in RegionalFeatureRows:
            RawValue = RegionalFeatureRow.get(FeatureFieldName, "")

            if not IsPresent(RawValue):
                MissingRows += 1
                continue

            NumericValue = ParseFloat(RawValue)

            if NumericValue is None:
                NonNumericRows += 1
            else:
                NumericValues.append(NumericValue)

        RowsWithValue = TotalRows - MissingRows
        MissingPercent = round((MissingRows / TotalRows) * 100, 4) if TotalRows else 0
        UniqueNumericValueCount = len(set(NumericValues))

        MissingnessRows.append(
            {
                "FeatureName": FeatureFieldName,
                "RowsWithValue": RowsWithValue,
                "RowsMissingValue": MissingRows,
                "MissingPercent": MissingPercent,
                "NonNumericRows": NonNumericRows,
                "UniqueNumericValueCount": UniqueNumericValueCount,
                "MinimumValue": min(NumericValues) if NumericValues else "",
                "MaximumValue": max(NumericValues) if NumericValues else "",
                "IsAllMissing": MissingRows == TotalRows,
                "IsHighMissingness": MissingPercent > HighMissingnessThresholdPercent,
                "IsNonNumeric": NonNumericRows > 0,
                "IsZeroVariance": UniqueNumericValueCount == 1 and MissingRows == 0 and NonNumericRows == 0,
            }
        )

    return MissingnessRows


def BuildDictionaryAuditRows(
    FeatureFieldNames: list[str],
    FeatureDictionaryRows: list[dict[str, object]],
) -> list[dict[str, object]]:
    TableFeatureNames = set(FeatureFieldNames)
    DictionaryFeatureNames = set(
        NormaliseText(FeatureDictionaryRow.get("FeatureName", ""))
        for FeatureDictionaryRow in FeatureDictionaryRows
        if IsPresent(FeatureDictionaryRow.get("FeatureName", ""))
    )

    AuditRows: list[dict[str, object]] = []

    for FeatureName in sorted(TableFeatureNames - DictionaryFeatureNames):
        AuditRows.append(
            {
                "FeatureName": FeatureName,
                "AuditIssue": "FeatureInTableButNotDictionary",
            }
        )

    for FeatureName in sorted(DictionaryFeatureNames - TableFeatureNames):
        AuditRows.append(
            {
                "FeatureName": FeatureName,
                "AuditIssue": "FeatureInDictionaryButNotTable",
            }
        )

    return AuditRows


def BuildDuplicateRows(RegionalFeatureRows: list[dict[str, object]], FieldName: str) -> list[dict[str, object]]:
    FieldValueCounts = Counter(NormaliseText(RegionalFeatureRow.get(FieldName, "")) for RegionalFeatureRow in RegionalFeatureRows)
    DuplicateRows: list[dict[str, object]] = []

    for RowIndex, RegionalFeatureRow in enumerate(RegionalFeatureRows, start=1):
        FieldValue = NormaliseText(RegionalFeatureRow.get(FieldName, ""))

        if FieldValue and FieldValueCounts[FieldValue] > 1:
            DuplicateRows.append(
                {
                    "RowNumber": RowIndex,
                    "DuplicateField": FieldName,
                    "DuplicateValue": FieldValue,
                    "RID": RegionalFeatureRow.get("RID", ""),
                    "SubjectId": RegionalFeatureRow.get("SubjectId", ""),
                    "ImageId": RegionalFeatureRow.get("ImageId", ""),
                    "Diagnosis3Class": RegionalFeatureRow.get("Diagnosis3Class", ""),
                }
            )

    return DuplicateRows


def GetCoverageByField(MetadataCoverageRows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {NormaliseText(MetadataCoverageRow["FieldName"]): MetadataCoverageRow for MetadataCoverageRow in MetadataCoverageRows}


def BuildProblemColumnRows(
    MetadataCoverageRows: list[dict[str, object]],
    FeatureMissingnessRows: list[dict[str, object]],
) -> list[dict[str, object]]:
    ProblemRows: list[dict[str, object]] = []
    MetadataCoverageByField = GetCoverageByField(MetadataCoverageRows)

    for CoreMetadataField in CoreMetadataFields:
        CoverageRow = MetadataCoverageByField.get(CoreMetadataField, {})
        RowsWithValue = int(CoverageRow.get("RowsWithValue", 0))

        if RowsWithValue == 0:
            ProblemRows.append(
                {
                    "ColumnName": CoreMetadataField,
                    "ColumnType": "Metadata",
                    "ProblemType": "MissingCoreMetadata",
                    "Details": "Core metadata field is fully empty.",
                }
            )

    for ScannerAndQcField in ScannerAndQcFields:
        CoverageRow = MetadataCoverageByField.get(ScannerAndQcField, {})
        RowsWithValue = int(CoverageRow.get("RowsWithValue", 0))

        if RowsWithValue == 0:
            ProblemRows.append(
                {
                    "ColumnName": ScannerAndQcField,
                    "ColumnType": "Metadata",
                    "ProblemType": "MissingScannerOrQcMetadata",
                    "Details": "Scanner/QC field is fully empty. Do not claim this covariate or QC status is available.",
                }
            )

    for FeatureMissingnessRow in FeatureMissingnessRows:
        FeatureName = NormaliseText(FeatureMissingnessRow["FeatureName"])

        if bool(FeatureMissingnessRow["IsAllMissing"]):
            ProblemRows.append(
                {
                    "ColumnName": FeatureName,
                    "ColumnType": "FastSurferFeature",
                    "ProblemType": "AllMissingFeature",
                    "Details": "Feature column is fully empty.",
                }
            )

        if bool(FeatureMissingnessRow["IsHighMissingness"]):
            ProblemRows.append(
                {
                    "ColumnName": FeatureName,
                    "ColumnType": "FastSurferFeature",
                    "ProblemType": "HighMissingnessFeature",
                    "Details": f"Missingness exceeds {HighMissingnessThresholdPercent}%.",
                }
            )

        if bool(FeatureMissingnessRow["IsNonNumeric"]):
            ProblemRows.append(
                {
                    "ColumnName": FeatureName,
                    "ColumnType": "FastSurferFeature",
                    "ProblemType": "NonNumericFeatureValue",
                    "Details": "Feature column contains non-numeric values.",
                }
            )

    return ProblemRows


def BuildSummaryRows(
    ManifestRows: list[dict[str, str]],
    RegionalFeatureRows: list[dict[str, object]],
    FeatureDictionaryRows: list[dict[str, object]],
    ExclusionRows: list[dict[str, object]],
    FeatureFieldNames: list[str],
    MetadataCoverageRows: list[dict[str, object]],
    FeatureMissingnessRows: list[dict[str, object]],
    ProblemRows: list[dict[str, object]],
    DictionaryAuditRows: list[dict[str, object]],
    DuplicateRidRows: list[dict[str, object]],
    DuplicateImageRows: list[dict[str, object]],
) -> list[dict[str, object]]:
    IncludedDiagnosisCounts = CountByField(RegionalFeatureRows, "Diagnosis3Class")
    ExcludedDiagnosisCounts = CountByField(ExclusionRows, "Diagnosis3Class")
    ManifestDiagnosisCounts = CountByField(ManifestRows, "Diagnosis3Class")
    FastSurferStatusCounts = CountByField(RegionalFeatureRows, "FastSurferStatus")

    MetadataCoverageByField = GetCoverageByField(MetadataCoverageRows)

    AllMissingFeatureCount = sum(1 for Row in FeatureMissingnessRows if bool(Row["IsAllMissing"]))
    HighMissingnessFeatureCount = sum(1 for Row in FeatureMissingnessRows if bool(Row["IsHighMissingness"]))
    NonNumericFeatureCount = sum(1 for Row in FeatureMissingnessRows if bool(Row["IsNonNumeric"]))
    ZeroVarianceFeatureCount = sum(1 for Row in FeatureMissingnessRows if bool(Row["IsZeroVariance"]))

    CoreMetadataReady = all(
        int(MetadataCoverageByField.get(CoreMetadataField, {}).get("RowsWithValue", 0)) == len(RegionalFeatureRows)
        for CoreMetadataField in CoreMetadataFields
    )

    ScannerAndQcMetadataReady = all(
        int(MetadataCoverageByField.get(FieldName, {}).get("RowsWithValue", 0)) > 0
        for FieldName in ScannerAndQcFields
    )

    CoreFeatureTableReadyForModelling = (
        len(RegionalFeatureRows) > 0
        and len(DuplicateRidRows) == 0
        and len(DuplicateImageRows) == 0
        and CoreMetadataReady
        and AllMissingFeatureCount == 0
        and HighMissingnessFeatureCount == 0
        and NonNumericFeatureCount == 0
        and len(DictionaryAuditRows) == 0
    )

    SummaryRows = [
        {"Metric": "GeneratedAt", "Value": datetime.now().isoformat(timespec="seconds")},
        {"Metric": "InputManifestRows", "Value": len(ManifestRows)},
        {"Metric": "OutputRegionalFeatureRows", "Value": len(RegionalFeatureRows)},
        {"Metric": "ExcludedRows", "Value": len(ExclusionRows)},
        {"Metric": "MetadataColumns", "Value": len(OutputMetadataFields)},
        {"Metric": "FastSurferFeatureColumns", "Value": len(FeatureFieldNames)},
        {"Metric": "TotalOutputColumns", "Value": len(OutputMetadataFields) + len(FeatureFieldNames)},
        {"Metric": "FeatureDictionaryRows", "Value": len(FeatureDictionaryRows)},
        {"Metric": "RequiredStatsFiles", "Value": "; ".join(RequiredStatsFileNames)},
        {"Metric": "ManifestDiagnosisCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in ManifestDiagnosisCounts.items())},
        {"Metric": "IncludedDiagnosisCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in IncludedDiagnosisCounts.items())},
        {"Metric": "ExcludedDiagnosisCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in ExcludedDiagnosisCounts.items())},
        {"Metric": "FastSurferStatusCounts", "Value": "; ".join(f"{Key}: {Value}" for Key, Value in FastSurferStatusCounts.items())},
        {"Metric": "UniqueRidCount", "Value": len(set(NormaliseText(Row.get("RID", "")) for Row in RegionalFeatureRows if IsPresent(Row.get("RID", ""))))},
        {"Metric": "DuplicateRidRows", "Value": len(DuplicateRidRows)},
        {"Metric": "DuplicateImageRows", "Value": len(DuplicateImageRows)},
        {"Metric": "AllMissingFeatureColumns", "Value": AllMissingFeatureCount},
        {"Metric": "HighMissingnessFeatureColumns", "Value": HighMissingnessFeatureCount},
        {"Metric": "NonNumericFeatureColumns", "Value": NonNumericFeatureCount},
        {"Metric": "ZeroVarianceFeatureColumns", "Value": ZeroVarianceFeatureCount},
        {"Metric": "DictionaryAuditIssueRows", "Value": len(DictionaryAuditRows)},
        {"Metric": "ProblemColumnRows", "Value": len(ProblemRows)},
        {"Metric": "CoreMetadataReady", "Value": CoreMetadataReady},
        {"Metric": "CoreFeatureTableReadyForModelling", "Value": CoreFeatureTableReadyForModelling},
        {"Metric": "ScannerAndQcMetadataReady", "Value": ScannerAndQcMetadataReady},
        {"Metric": "FeatureTablePath", "Value": str(FastSurferRegionalFeaturesPath)},
        {"Metric": "FeatureDictionaryPath", "Value": str(FastSurferFeatureDictionaryPath)},
        {"Metric": "ExclusionsPath", "Value": str(FastSurferRegionalFeatureExclusionsPath)},
    ]

    for FieldName in DateFields + CognitiveFields + ScannerAndQcFields:
        SummaryRows.append(
            {
                "Metric": f"RowsWith{FieldName}",
                "Value": MetadataCoverageByField.get(FieldName, {}).get("RowsWithValue", 0),
            }
        )

    return SummaryRows


def PrintSection(SectionTitle: str) -> None:
    print()
    print("=" * 80)
    print(SectionTitle)
    print("=" * 80)


def PrintSummary(SummaryRows: list[dict[str, object]]) -> None:
    PrintSection("FastSurfer Regional Features Summary")

    for SummaryRow in SummaryRows:
        print(f"{SummaryRow['Metric']}: {SummaryRow['Value']}")


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


def Main() -> None:
    PrintProgress("Starting FastSurfer regional feature table build.")
    EnsureDirectory(OutputDirectory)

    PrintProgress("Validating required inputs.")
    ValidateInputs()

    PrintProgress(f"Reading manifest: {FastSurferInputManifestPath}")
    ManifestRows = ReadCsvRows(FastSurferInputManifestPath)
    PrintProgress(f"Manifest rows loaded: {len(ManifestRows)}")

    PrintProgress(f"Reading selected baseline cohort metadata: {SelectedBaselineCohortPath}")
    CohortRows = ReadCsvRows(SelectedBaselineCohortPath)
    PrintProgress(f"Selected baseline cohort rows loaded: {len(CohortRows)}")

    RegionalFeatureRows, FeatureDictionaryRows, ExclusionRows = BuildRegionalFeatureRows(
        ManifestRows=ManifestRows,
        CohortRows=CohortRows,
    )

    PrintProgress("Collecting feature column names.")
    FeatureFieldNames = GetAllFeatureFieldNames(RegionalFeatureRows)
    OutputFieldNames = OutputMetadataFields + FeatureFieldNames

    PrintProgress(f"FastSurfer feature columns: {len(FeatureFieldNames)}")
    PrintProgress(f"Total output columns: {len(OutputFieldNames)}")

    PrintProgress("Completing missing fields for rectangular CSV output.")
    CompletedRegionalFeatureRows = CompleteMissingFields(RegionalFeatureRows, OutputFieldNames)

    PrintProgress("Auditing metadata coverage.")
    MetadataCoverageRows = BuildMetadataCoverageRows(RegionalFeatureRows)

    PrintProgress("Auditing feature missingness.")
    FeatureMissingnessRows = BuildFeatureMissingnessRows(RegionalFeatureRows, FeatureFieldNames)

    PrintProgress("Auditing feature dictionary.")
    DictionaryAuditRows = BuildDictionaryAuditRows(FeatureFieldNames, FeatureDictionaryRows)

    PrintProgress("Checking duplicate participant and image identifiers.")
    DuplicateRidRows = BuildDuplicateRows(RegionalFeatureRows, "RID")
    DuplicateImageRows = BuildDuplicateRows(RegionalFeatureRows, "ImageId")

    PrintProgress("Building problem-column report.")
    ProblemRows = BuildProblemColumnRows(MetadataCoverageRows, FeatureMissingnessRows)

    PrintProgress("Building summary rows.")
    SummaryRows = BuildSummaryRows(
        ManifestRows=ManifestRows,
        RegionalFeatureRows=RegionalFeatureRows,
        FeatureDictionaryRows=FeatureDictionaryRows,
        ExclusionRows=ExclusionRows,
        FeatureFieldNames=FeatureFieldNames,
        MetadataCoverageRows=MetadataCoverageRows,
        FeatureMissingnessRows=FeatureMissingnessRows,
        ProblemRows=ProblemRows,
        DictionaryAuditRows=DictionaryAuditRows,
        DuplicateRidRows=DuplicateRidRows,
        DuplicateImageRows=DuplicateImageRows,
    )

    PrintProgress(f"Writing feature table: {FastSurferRegionalFeaturesPath}")
    WriteCsv(FastSurferRegionalFeaturesPath, OutputFieldNames, CompletedRegionalFeatureRows)

    PrintProgress(f"Writing feature dictionary: {FastSurferFeatureDictionaryPath}")
    WriteCsv(FastSurferFeatureDictionaryPath, FeatureDictionaryFields, FeatureDictionaryRows)

    PrintProgress(f"Writing exclusions: {FastSurferRegionalFeatureExclusionsPath}")
    WriteCsv(
        FastSurferRegionalFeatureExclusionsPath,
        [
            "RowNumber",
            "RID",
            "SubjectId",
            "ImageId",
            "Diagnosis3Class",
            "FastSurferSubjectId",
            "FastSurferStatus",
            "MissingRequiredStatsFiles",
            "ExclusionReason",
        ],
        ExclusionRows,
    )

    PrintProgress(f"Writing metadata coverage: {FastSurferRegionalFeatureMetadataCoveragePath}")
    WriteCsv(
        FastSurferRegionalFeatureMetadataCoveragePath,
        ["FieldName", "RowsWithValue", "RowsMissingValue", "CoveragePercent"],
        MetadataCoverageRows,
    )

    PrintProgress(f"Writing feature missingness: {FastSurferRegionalFeatureMissingnessPath}")
    WriteCsv(
        FastSurferRegionalFeatureMissingnessPath,
        [
            "FeatureName",
            "RowsWithValue",
            "RowsMissingValue",
            "MissingPercent",
            "NonNumericRows",
            "UniqueNumericValueCount",
            "MinimumValue",
            "MaximumValue",
            "IsAllMissing",
            "IsHighMissingness",
            "IsNonNumeric",
            "IsZeroVariance",
        ],
        FeatureMissingnessRows,
    )

    PrintProgress(f"Writing problem columns: {FastSurferRegionalFeatureProblemColumnsPath}")
    WriteCsv(
        FastSurferRegionalFeatureProblemColumnsPath,
        ["ColumnName", "ColumnType", "ProblemType", "Details"],
        ProblemRows,
    )

    PrintProgress(f"Writing feature dictionary audit: {FastSurferRegionalFeatureDictionaryAuditPath}")
    WriteCsv(
        FastSurferRegionalFeatureDictionaryAuditPath,
        ["FeatureName", "AuditIssue"],
        DictionaryAuditRows,
    )

    PrintProgress(f"Writing summary: {FastSurferRegionalFeaturesSummaryPath}")
    WriteCsv(FastSurferRegionalFeaturesSummaryPath, ["Metric", "Value"], SummaryRows)

    PrintProgress(f"Writing Markdown summary: {FastSurferRegionalFeaturesMarkdownSummaryPath}")
    WriteMarkdownSummary(SummaryRows)

    PrintSummary(SummaryRows)

    PrintRows(
        "Metadata coverage",
        MetadataCoverageRows,
        ["FieldName", "RowsWithValue", "RowsMissingValue", "CoveragePercent"],
    )

    PrintRows(
        "Problem columns",
        ProblemRows,
        ["ColumnName", "ColumnType", "ProblemType", "Details"],
    )

    PrintRows(
        "Processing exclusions",
        ExclusionRows,
        ["RowNumber", "RID", "SubjectId", "ImageId", "Diagnosis3Class", "FastSurferStatus", "ExclusionReason"],
    )

    print()
    print("FastSurfer regional feature table build complete.")
    print(f"Feature table: {FastSurferRegionalFeaturesPath}")
    print(f"Summary: {FastSurferRegionalFeaturesSummaryPath}")
    print(f"Feature dictionary: {FastSurferFeatureDictionaryPath}")
    print(f"Exclusions: {FastSurferRegionalFeatureExclusionsPath}")
    print(f"Metadata coverage: {FastSurferRegionalFeatureMetadataCoveragePath}")
    print(f"Feature missingness: {FastSurferRegionalFeatureMissingnessPath}")
    print(f"Problem columns: {FastSurferRegionalFeatureProblemColumnsPath}")
    print(f"Feature dictionary audit: {FastSurferRegionalFeatureDictionaryAuditPath}")


if __name__ == "__main__":
    try:
        Main()
    except KeyboardInterrupt:
        print()
        print("Stopped by user before completion.")
        sys.exit(130)
    except Exception as Error:
        print(str(Error))
        sys.exit(1)