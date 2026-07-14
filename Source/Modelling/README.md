# Brain-Age Modelling

This directory contains the complete structural MRI brain-age analysis. The workflow validates the modelling dataset, applies reconstruction quality control, estimates scalar and regional brain age, evaluates diagnostic and cognitive utility, and tests sensitivity to the quality-control threshold.

## Primary analysis

Run from the repository root:

```powershell
python Source\Modelling\RunBrainAgeModelling.py
```

The command executes:

1. the fixed `Ridge(alpha=1.0)` exploratory analysis;
2. raw, linear, and non-linear age-bias corrections;
3. fixed-alpha scalar and regional representations;
4. the primary CN-trained RidgeCV scalar and 171-region brain-age models;
5. out-of-fold diagnostic and cognition models; and
6. paired bootstrap comparisons between representations.

The primary setting uses 9,999 bootstrap resamples. A shorter integration check can use `--bootstrap-resamples 200`.

## Reconstruction-QC sensitivity

```powershell
python Source\Modelling\RunQcSensitivityAnalysis.py
```

The sensitivity script independently re-fits the primary model with no reconstruction-QC exclusion, the 97.5th-percentile threshold, the 95th-percentile threshold, and median plus three scaled MADs.

## Visual outputs

```powershell
python Source\Visualisation\GenerateBrainAgeFigures.py
```

This writes exactly four PNG files to `Outputs/Figures/BrainAge/`. It does not create PDF files.

## Output contract

Exploratory outputs:

| File | Contents |
|---|---|
| `FixedAlphaModelResults.csv` | Fixed-alpha MAE, R², and prediction ranges |
| `FixedAlphaPredictions.csv` | RID-aligned fixed-alpha predictions |
| `BiasCorrectionResults.csv` | Raw, linear, and non-linear gap summaries |
| `BiasCorrectedGaps.csv` | Subject-level bias-correction variants |
| `RepresentationSummary.csv` | Scalar, regional, and raw representation dimensions |
| `FixedAlphaRegionalGaps.csv` | RID-aligned fixed-alpha regional-gap matrix |

Primary outputs:

| File | Contents |
|---|---|
| `BrainAgeSubjectResults.csv` | Predicted age, scalar gap, and mean regional gap |
| `RegionalBrainAgeGaps.csv` | RidgeCV 171-region gap matrix |
| `RegionalGapSummary.csv` | Per-region mean gaps and ranking |
| `BrainAgeModelSummary.csv` | Cohort, QC, feature, MAE, R², alpha, and bootstrap settings |
| `CohortSummary.csv` | Diagnosis-group demographics |
| `QCSummary.csv` | Diagnosis-stratified QC exclusions |
| `DiagnosisModelResults.csv` | AUC, Brier score, incremental AUC, and intervals |
| `DiagnosisOutOfFoldPredictions.csv` | Out-of-fold probabilities used for metrics and calibration |
| `CognitionModelResults.csv` | Out-of-fold R², incremental R², and intervals |
| `CognitionOutOfFoldPredictions.csv` | Out-of-fold cognition predictions |
| `HeadToHeadModelResults.csv` | Paired representation comparisons |
| `QcSensitivityResults.csv` | Threshold-specific diagnosis and cognition results |
| `QcSensitivityHeadToHead.csv` | Threshold-specific paired diagnosis comparisons |

All result CSVs are written to `Data/Processed/Analysis/BrainAgeResults/`. Floating-point values use 17-significant-digit serialisation to preserve reproducible round trips.