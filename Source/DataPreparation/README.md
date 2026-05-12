# Data Preparation

This directory contains scripts that convert locally unpacked ADNI raw data into interim tables used for cohort construction.

The outputs are derived from restricted ADNI data and must not be committed to version control.

---

## Run the interim-data workflow

From the repository root, run:

```powershell
python Source\DataPreparation\PrepareInterimData.py
```

This runs the data-preparation stages in order:

1. `InspectRawData.py`
2. `BuildImageManifest.py`
3. `BuildClinicalVisits.py`
4. `LinkImagesToClinicalVisits.py`
5. `SelectBaselineCohort.py`

The expected outputs are:

```text
Data/Interim/
  Inspection/
  Imaging/
    ImageManifest.csv
  Clinical/
    ClinicalVisits.csv
  Linkage/
    ImageClinicalLinkage.csv
  Cohort/
    SelectedBaselineCohort.csv
```

---

## Script sequence

### `InspectRawData.py`

Inspects the unpacked raw-data layout.

Input:

```text
Data/Raw/
```

Output:

```text
Data/Interim/Inspection/
```

### `BuildImageManifest.py`

Builds one row per extracted NIfTI image.

Inputs:

```text
Data/Raw/Imaging/Baseline3T1MPRAGE/Images/
Data/Raw/Imaging/Baseline3T1MPRAGE/Manifest/
Data/Raw/Clinical/StudyData/
```

Output:

```text
Data/Interim/Imaging/ImageManifest.csv
```

### `BuildClinicalVisits.py`

Builds one row per ADNI clinical visit.

Input:

```text
Data/Raw/Clinical/StudyData/
```

Output:

```text
Data/Interim/Clinical/ClinicalVisits.csv
```

### `LinkImagesToClinicalVisits.py`

Links MRI images to the nearest same-subject clinical visit within ±90 days.

Inputs:

```text
Data/Interim/Imaging/ImageManifest.csv
Data/Interim/Clinical/ClinicalVisits.csv
```

Output:

```text
Data/Interim/Linkage/ImageClinicalLinkage.csv
```

### `SelectBaselineCohort.py`

Selects one linked baseline MRI row per participant.

Input:

```text
Data/Interim/Linkage/ImageClinicalLinkage.csv
```

Output:

```text
Data/Interim/Cohort/SelectedBaselineCohort.csv
```

Selection rule:

```text
Keep linked image-clinical rows with RID, age, diagnosis, and a baseline-like visit.
For participants with multiple eligible rows, select the highest-ranked row using standardised-list status, image-clinical date proximity, cognitive-score availability, MPRAGE rank, and image ID as tie-breakers.
```