"""Build a regional FastSurfer feature table for analysis."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


FastSurferInputManifestPath = Path("Data") / "Processed" / "FeatureExtraction" / "FastSurferInputManifest.csv"
FastSurferOutputRootDirectory = Path("Data") / "Processed" / "FastSurfer"

OutputDirectory = Path("Data") / "Processed" / "Analysis"
FastSurferRegionalFeaturesPath = OutputDirectory / "FastSurferRegionalFeatures.csv"
FastSurferRegionalFeaturesSummaryPath = OutputDirectory / "FastSurferRegionalFeaturesSummary.csv"
FastSurferRegionalFeaturesMarkdownSummaryPath = OutputDirectory / "FastSurferRegionalFeaturesSummary.md"
FastSurferFeatureDictionaryPath = OutputDirectory / "FastSurferFeatureDictionary.csv"
FastSurferRegionalFeatureExclusionsPath = OutputDirectory / "FastSurferRegionalFeatureExclusions.csv"

ProgressPrintEvery = 10

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


def GetMetadataValue(ManifestRow: dict[str, str], Headers: list[str], OutputFieldName: str) -> str:
    CandidateFields = MetadataFieldCandidates.get(OutputFieldName, [OutputFieldName])
    SourceFieldName = GetFirstExistingField(Headers, CandidateFields)

    if not SourceFieldName:
        return ""

    return NormaliseText(ManifestRow.get(SourceFieldName, ""))


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


def ParseFloat(NumberText: str) -> float | None:
    NumberText = NormaliseText(NumberText)

    if not NumberText:
        return None

    try:
        return float(NumberText)
    except ValueError:
        return None


def IsNumericValue(TextValue: str) -> bool:
    return ParseFloat(TextValue) is not None


def FormatNumericValue(TextValue: str) -> str:
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

    ValueIndex = -2 if len(MeasureParts) >= 2 else -1
    UnitIndex = -1

    MeasureValue = MeasureParts[ValueIndex]
    Unit = MeasureParts[UnitIndex] if len(MeasureParts) >= 2 else ""

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


def BuildMetadataRow(ManifestRow: dict[str, str], Headers: list[str], FastSurferStatus: str) -> dict[str, object]:
    MetadataRow: dict[str, object] = {}

    for OutputMetadataField in OutputMetadataFields:
        if OutputMetadataField == "FastSurferStatus":
            MetadataRow[OutputMetadataField] = FastSurferStatus
        else:
            MetadataRow[OutputMetadataField] = GetMetadataValue(ManifestRow, Headers, OutputMetadataField)

    return MetadataRow


def BuildRegionalFeatureRows(
    ManifestRows: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    Headers = GetHeaders(ManifestRows)
    RegionalFeatureRows: list[dict[str, object]] = []
    ExclusionRows: list[dict[str, object]] = []
    FeatureDictionaryRowsByName: dict[str, dict[str, object]] = {}

    TotalRows = len(ManifestRows)
    PrintProgress(f"Checking {TotalRows} FastSurfer manifest rows.")

    for RowIndex, ManifestRow in enumerate(ManifestRows, start=1):
        FastSurferSubjectId = GetMetadataValue(ManifestRow, Headers, "FastSurferSubjectId")
        RID = GetMetadataValue(ManifestRow, Headers, "RID")
        SubjectId = GetMetadataValue(ManifestRow, Headers, "SubjectId")
        ImageId = GetMetadataValue(ManifestRow, Headers, "ImageId")
        Diagnosis3Class = GetMetadataValue(ManifestRow, Headers, "Diagnosis3Class")

        FastSurferStatus = GetFastSurferStatus(FastSurferSubjectId)
        MissingRequiredStatsFiles = GetMissingRequiredStatsFiles(FastSurferSubjectId)

        ShouldPrintThisRow = RowIndex == 1 or RowIndex % ProgressPrintEvery == 0 or RowIndex == TotalRows

        if ShouldPrintThisRow:
            PrintProgress(
                f"Row {RowIndex}/{TotalRows}: RID {RID}, Image {ImageId}, "
                f"{Diagnosis3Class}, FastSurferStatus={FastSurferStatus}"
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
            Headers=Headers,
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


def BuildSummaryRows(
    ManifestRows: list[dict[str, str]],
    RegionalFeatureRows: list[dict[str, object]],
    FeatureDictionaryRows: list[dict[str, object]],
    ExclusionRows: list[dict[str, object]],
    FeatureFieldNames: list[str],
) -> list[dict[str, object]]:
    IncludedDiagnosisCounts = CountByField(RegionalFeatureRows, "Diagnosis3Class")
    ExcludedDiagnosisCounts = CountByField(ExclusionRows, "Diagnosis3Class")
    ManifestDiagnosisCounts = CountByField(ManifestRows, "Diagnosis3Class")

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
        {"Metric": "FeatureTablePath", "Value": str(FastSurferRegionalFeaturesPath)},
        {"Metric": "FeatureDictionaryPath", "Value": str(FastSurferFeatureDictionaryPath)},
        {"Metric": "ExclusionsPath", "Value": str(FastSurferRegionalFeatureExclusionsPath)},
    ]

    return SummaryRows


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

    RegionalFeatureRows, FeatureDictionaryRows, ExclusionRows = BuildRegionalFeatureRows(ManifestRows)

    PrintProgress("Collecting feature column names.")
    FeatureFieldNames = GetAllFeatureFieldNames(RegionalFeatureRows)
    OutputFieldNames = OutputMetadataFields + FeatureFieldNames

    PrintProgress(f"FastSurfer feature columns: {len(FeatureFieldNames)}")
    PrintProgress(f"Total output columns: {len(OutputFieldNames)}")

    PrintProgress("Completing missing fields for rectangular CSV output.")
    CompletedRegionalFeatureRows = CompleteMissingFields(RegionalFeatureRows, OutputFieldNames)

    PrintProgress("Building summary rows.")
    SummaryRows = BuildSummaryRows(
        ManifestRows=ManifestRows,
        RegionalFeatureRows=RegionalFeatureRows,
        FeatureDictionaryRows=FeatureDictionaryRows,
        ExclusionRows=ExclusionRows,
        FeatureFieldNames=FeatureFieldNames,
    )

    PrintProgress(f"Writing feature table: {FastSurferRegionalFeaturesPath}")
    WriteCsv(
        FastSurferRegionalFeaturesPath,
        OutputFieldNames,
        CompletedRegionalFeatureRows,
    )

    PrintProgress(f"Writing feature dictionary: {FastSurferFeatureDictionaryPath}")
    WriteCsv(
        FastSurferFeatureDictionaryPath,
        FeatureDictionaryFields,
        FeatureDictionaryRows,
    )

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

    PrintProgress(f"Writing summary: {FastSurferRegionalFeaturesSummaryPath}")
    WriteCsv(
        FastSurferRegionalFeaturesSummaryPath,
        ["Metric", "Value"],
        SummaryRows,
    )

    PrintProgress(f"Writing Markdown summary: {FastSurferRegionalFeaturesMarkdownSummaryPath}")
    WriteMarkdownSummary(SummaryRows)

    PrintSummary(SummaryRows)

    PrintRows(
        "Processing exclusions",
        ExclusionRows,
        ["RowNumber", "RID", "SubjectId", "ImageId", "Diagnosis3Class", "FastSurferStatus", "ExclusionReason"],
    )

    print()
    print("FastSurfer regional feature extraction complete.")
    print(f"Feature table: {FastSurferRegionalFeaturesPath}")
    print(f"Summary: {FastSurferRegionalFeaturesSummaryPath}")
    print(f"Feature dictionary: {FastSurferFeatureDictionaryPath}")
    print(f"Exclusions: {FastSurferRegionalFeatureExclusionsPath}")


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