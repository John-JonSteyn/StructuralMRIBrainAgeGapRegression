# Feature Extraction

This directory contains scripts for MRI feature extraction from the selected ADNI baseline cohort.

The feature-extraction workflow starts from:

```text
Data/Interim/Cohort/SelectedBaselineCohort.csv
```

and produces derived MRI feature outputs under:

```text
Data/Processed/
```

---

## FastSurfer

This study uses **FastSurfer v2.4.2** through Docker.

The feature-extraction scripts use these Docker images:

```text
deepmi/fastsurfer:cpu-v2.4.2
deepmi/fastsurfer:cuda-v2.4.2
```

The CPU image is used if Docker GPU access is unavailable. The CUDA image is used if Docker can access an NVIDIA GPU.

FastSurfer requires a local FreeSurfer licence file for the full surface-processing pipeline.

Request the licence from the [official FreeSurfer registration page](https://surfer.nmr.mgh.harvard.edu/registration.html). The licence should be emailed to you shortly afterwards.

Save the licence file as:

```text
LocalOnly/FreeSurfer/license.txt
```

---

## Required starting point

Before running the feature-extraction scripts, the data-preparation workflow must have produced:

```text
Data/Interim/Cohort/SelectedBaselineCohort.csv
```

This file defines the selected baseline scan for each participant.

The current selected cohort contains:

```text
Selected participants: 695
Diagnostic groups: CN, MCI, AD
```

---

## Script sequence

Run these scripts from the repository root.

### 1. Pull the FastSurfer Docker images

```powershell
python Source\FeatureExtraction\PullFastSurferImage.py
```

This script checks that Docker is available, pulls the FastSurfer CPU and CUDA Docker images, and lists the local FastSurfer images.

Expected images:

```text
deepmi/fastsurfer:cpu-v2.4.2
deepmi/fastsurfer:cuda-v2.4.2
```

---

### 2. Prepare the FastSurfer input manifest

```powershell
python Source\FeatureExtraction\PrepareFastSurferInputs.py
```

This script reads:

```text
Data/Interim/Cohort/SelectedBaselineCohort.csv
```

and writes:

```text
Data/Processed/FeatureExtraction/FastSurferInputManifest.csv
Data/Processed/FeatureExtraction/FastSurferInputManifestSummary.csv
Data/Processed/FeatureExtraction/FastSurferInputManifestSummary.md
```

The manifest contains one row per selected scan and includes:

```text
RID
SubjectId
ImageId
ImageIdKey
Diagnosis3Class
Age
Sex
Education
ImageRelativePath
ContainerT1Path
FastSurferSubjectId
FastSurferOutputDirectory
ContainerFastSurferOutputDirectory
ExpectedStatsDirectory
ProcessingStatus
```

The script checks that the FreeSurfer licence exists at:

```text
LocalOnly/FreeSurfer/license.txt
```

A successful run should report:

```text
FastSurfer input manifest build complete.
Manifest rows: 695
License found: True
```

---

### 3. Run one FastSurfer test scan

```powershell
python Source\FeatureExtraction\RunFastSurferTestScan.py
```

This script reads:

```text
Data/Processed/FeatureExtraction/FastSurferInputManifest.csv
```

It selects one pending scan, checks Docker GPU availability, and runs FastSurfer on that scan only.

If Docker can access an NVIDIA GPU, the script uses:

```text
deepmi/fastsurfer:cuda-v2.4.2
```

If Docker GPU access is unavailable, the script uses:

```text
deepmi/fastsurfer:cpu-v2.4.2
```

The test scan output is written under:

```text
Data/Processed/FastSurfer/
```

The test summary is written to:

```text
Data/Processed/FeatureExtraction/FastSurferTestScanSummary.csv
Data/Processed/FeatureExtraction/FastSurferTestScanSummary.md
```

Each completed subject has an output directory such as:

```text
Data/Processed/FastSurfer/RID_1046_I118908/
```

The key output folder for later feature extraction is:

```text
Data/Processed/FastSurfer/RID_1046_I118908/stats/
```

Expected stats files include outputs such as:

```text
aseg.stats
aseg+DKT.stats
brainvol.stats
lh.aparc.DKTatlas.mapped.stats
rh.aparc.DKTatlas.mapped.stats
wmparc.DKTatlas.mapped.stats
```

Runtime will vary by machine, GPU availability, CPU speed, disk speed, and scan characteristics.
