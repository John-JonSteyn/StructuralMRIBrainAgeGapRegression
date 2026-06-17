"""Build the one-row-per-patient FastSurfer modelling dataset."""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path


InputFeatureTablePath = Path("Data") / "Processed" / "Analysis" / "FastSurferRegionalFeatures.csv"
OutputDirectory = Path("Data") / "Processed" / "Analysis"
OutputModellingDatasetPath = OutputDirectory / "FastSurferModellingDataset.csv"
OutputSummaryPath = OutputDirectory / "FastSurferModellingDatasetSummary.csv"
OutputMarkdownSummaryPath = OutputDirectory / "FastSurferModellingDatasetSummary.md"

RequiredInputMetadataFields = [
    "RID",
    "Age",
    "Sex",
    "Education",
    "Diagnosis3Class",
    "MMSE",
    "ADAS13",
    "CDRSB",
    "FAQ",
]

OutputMetadataFields = [
    "RID",
    "Age",
    "Sex",
    "Education",
    "Diagnosis",
    "MMSE",
    "ADAS",
    "CDRSB",
    "FAQ",
]

FastSurferFeaturePrefix = "FastSurfer_"


def PrintProgress(Message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {Message}", flush=True)


def NormaliseText(TextValue: object) -> str:
    return str(TextValue).strip() if TextValue is not None else ""


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def ReadCsvRows(CsvFilePath: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with CsvFilePath.open("r", newline="", encoding="utf-8-sig") as CsvFile:
            CsvReader = csv.DictReader(CsvFile)
            return list(CsvReader.fieldnames or []), [dict(Row) for Row in CsvReader]

    except UnicodeDecodeError:
        with CsvFilePath.open("r", newline="", encoding="latin-1") as CsvFile:
            CsvReader = csv.DictReader(CsvFile)
            return list(CsvReader.fieldnames or []), [dict(Row) for Row in CsvReader]


def WriteCsv(OutputFilePath: Path, FieldNames: list[str], DataRows: list[dict[str, object]]) -> None:
    EnsureDirectory(OutputFilePath.parent)

    with OutputFilePath.open("w", newline="", encoding="utf-8") as OutputFile:
        CsvWriter = csv.DictWriter(OutputFile, fieldnames=FieldNames, extrasaction="ignore")
        CsvWriter.writeheader()

        for DataRow in DataRows:
            CsvWriter.writerow(DataRow)


def ValidateInputs(InputHeaders: list[str]) -> None:
    MissingFields = [
        FieldName
        for FieldName in RequiredInputMetadataFields
        if FieldName not in InputHeaders
    ]

    if MissingFields:
        raise RuntimeError(
            "Input feature table is missing required fields: "
            + ", ".join(MissingFields)
        )


def GetFastSurferFeatureFields(InputHeaders: list[str]) -> list[str]:
    return [
        FieldName
        for FieldName in InputHeaders
        if FieldName.startswith(FastSurferFeaturePrefix)
    ]


def BuildModellingRows(
    InputRows: list[dict[str, str]],
    FastSurferFeatureFields: list[str],
) -> list[dict[str, object]]:
    ModellingRows: list[dict[str, object]] = []

    for InputRow in InputRows:
        ModellingRow: dict[str, object] = {
            "RID": InputRow.get("RID", ""),
            "Age": InputRow.get("Age", ""),
            "Sex": InputRow.get("Sex", ""),
            "Education": InputRow.get("Education", ""),
            "Diagnosis": InputRow.get("Diagnosis3Class", ""),
            "MMSE": InputRow.get("MMSE", ""),
            "ADAS": InputRow.get("ADAS13", ""),
            "CDRSB": InputRow.get("CDRSB", ""),
            "FAQ": InputRow.get("FAQ", ""),
        }

        for FeatureField in FastSurferFeatureFields:
            ModellingRow[FeatureField] = InputRow.get(FeatureField, "")

        ModellingRows.append(ModellingRow)

    return ModellingRows


def CountRowsWithValue(DataRows: list[dict[str, object]], FieldName: str) -> int:
    return sum(1 for Row in DataRows if NormaliseText(Row.get(FieldName, "")))


def CountRowsByValue(DataRows: list[dict[str, object]], FieldName: str) -> dict[str, int]:
    ValueCounts: dict[str, int] = {}

    for Row in DataRows:
        FieldValue = NormaliseText(Row.get(FieldName, "")) or "Missing"
        ValueCounts[FieldValue] = ValueCounts.get(FieldValue, 0) + 1

    return dict(sorted(ValueCounts.items()))


def FormatValueCounts(ValueCounts: dict[str, int]) -> str:
    return "; ".join(f"{Value}: {Count}" for Value, Count in ValueCounts.items())


def BuildSummaryRows(
    ModellingRows: list[dict[str, object]],
    FastSurferFeatureFields: list[str],
) -> list[dict[str, object]]:
    SummaryRows = [
        {"Metric": "GeneratedAt", "Value": datetime.now().isoformat(timespec="seconds")},
        {"Metric": "InputFeatureTablePath", "Value": str(InputFeatureTablePath)},
        {"Metric": "OutputModellingDatasetPath", "Value": str(OutputModellingDatasetPath)},
        {"Metric": "Rows", "Value": len(ModellingRows)},
        {"Metric": "MetadataColumns", "Value": len(OutputMetadataFields)},
        {"Metric": "FastSurferFeatureColumns", "Value": len(FastSurferFeatureFields)},
        {"Metric": "TotalColumns", "Value": len(OutputMetadataFields) + len(FastSurferFeatureFields)},
        {"Metric": "DiagnosisCounts", "Value": FormatValueCounts(CountRowsByValue(ModellingRows, "Diagnosis"))},
    ]

    for FieldName in OutputMetadataFields:
        SummaryRows.append(
            {
                "Metric": f"RowsWith{FieldName}",
                "Value": CountRowsWithValue(ModellingRows, FieldName),
            }
        )

    return SummaryRows


def WriteMarkdownSummary(SummaryRows: list[dict[str, object]]) -> None:
    EnsureDirectory(OutputMarkdownSummaryPath.parent)

    with OutputMarkdownSummaryPath.open("w", encoding="utf-8") as OutputFile:
        OutputFile.write("# FastSurfer Modelling Dataset Summary\n\n")
        OutputFile.write("| Metric | Value |\n")
        OutputFile.write("|---|---:|\n")

        for SummaryRow in SummaryRows:
            OutputFile.write(f"| {SummaryRow['Metric']} | {SummaryRow['Value']} |\n")


def Main() -> None:
    PrintProgress("Starting FastSurfer modelling dataset build.")

    if not InputFeatureTablePath.exists():
        raise FileNotFoundError(f"Input feature table not found: {InputFeatureTablePath}")

    PrintProgress(f"Reading feature table: {InputFeatureTablePath}")
    InputHeaders, InputRows = ReadCsvRows(InputFeatureTablePath)
    PrintProgress(f"Input rows loaded: {len(InputRows)}")

    ValidateInputs(InputHeaders)

    FastSurferFeatureFields = GetFastSurferFeatureFields(InputHeaders)
    PrintProgress(f"FastSurfer feature columns found: {len(FastSurferFeatureFields)}")

    OutputFieldNames = OutputMetadataFields + FastSurferFeatureFields

    PrintProgress("Building modelling rows.")
    ModellingRows = BuildModellingRows(
        InputRows=InputRows,
        FastSurferFeatureFields=FastSurferFeatureFields,
    )

    SummaryRows = BuildSummaryRows(
        ModellingRows=ModellingRows,
        FastSurferFeatureFields=FastSurferFeatureFields,
    )

    PrintProgress(f"Writing modelling dataset: {OutputModellingDatasetPath}")
    WriteCsv(OutputModellingDatasetPath, OutputFieldNames, ModellingRows)

    PrintProgress(f"Writing summary: {OutputSummaryPath}")
    WriteCsv(OutputSummaryPath, ["Metric", "Value"], SummaryRows)

    PrintProgress(f"Writing Markdown summary: {OutputMarkdownSummaryPath}")
    WriteMarkdownSummary(SummaryRows)

    print()
    print("FastSurfer modelling dataset build complete.")
    print(f"Rows: {len(ModellingRows)}")
    print(f"FastSurfer feature columns: {len(FastSurferFeatureFields)}")
    print(f"Output: {OutputModellingDatasetPath}")


if __name__ == "__main__":
    try:
        Main()
    except Exception as Error:
        print()
        print("FastSurfer modelling dataset build failed.")
        print(str(Error))
        sys.exit(1)
