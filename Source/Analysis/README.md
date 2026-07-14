# Analysis Dataset Construction

`BuildFastSurferModellingDataset.py` converts the integrated FastSurfer regional feature table into the one-row-per-participant modelling input used by `Source/Modelling/`.

Run from the repository root:

```powershell
python Source\Analysis\BuildFastSurferModellingDataset.py
```

Input:

```text
Data/Processed/Analysis/FastSurferRegionalFeatures.csv
```

Outputs:

```text
Data/Processed/Analysis/FastSurferModellingDataset.csv
Data/Processed/Analysis/FastSurferModellingDatasetSummary.csv
Data/Processed/Analysis/FastSurferModellingDatasetSummary.md
```

The script maps `Diagnosis3Class` to `Diagnosis`, maps `ADAS13` to `ADAS`, retains the required demographic and cognitive fields, and includes every column beginning with `FastSurfer_`.

The modelling scripts apply their own reconstruction-QC gate and exclude QC measurements from the anatomical predictor matrix.
