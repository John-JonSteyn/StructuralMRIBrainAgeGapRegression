# Data

This directory documents how to obtain and organise the restricted ADNI data required for the structural MRI brain-age study:

**Structural MRI Brain-Age Gap Regression for Cognitive Decline and Alzheimer’s Disease Analysis Using ADNI**

ADNI data are not included in this repository. Access requires approval through the LONI Image & Data Archive and compliance with the applicable ADNI data-use agreements.

The repository contains documentation and source code for reproducing the analysis workflow. Restricted ADNI files must be downloaded and stored locally by each approved user.

---

## Expected local layout

After downloading and unpacking the data, the local data directory must have this structure:

```text
Data/
  README.md
  Raw/
    Clinical/
      StudyData/
    Imaging/
      Baseline3T1MPRAGE/
        Manifest/
        Archives/
        Images/
```

The clinical and imaging data are stored separately because ADNI distributes tabular study data and MRI image files through different IDA workflows. The unpacking utility creates this structure automatically.

---

## Step 1: Obtain ADNI access

1. Register for a LONI Image & Data Archive / IDA account.
2. Apply for access to ADNI.
3. Wait for ADNI approval.
4. Log in to IDA.
5. Select the ADNI study.

ADNI data are restricted. Reproducibility for this study means that an approved ADNI user can recreate the same local data layout; it does not mean that restricted ADNI data are redistributed through this repository.

---

## Step 2: Download the clinical and metadata bundle

In IDA, open the ADNI study-data download area:

```text
ADNI -> Study Files / Study Data
```

Select these files:

```text
ADAS
ADNIMERGE2
ADNI 3T MRI Standardized Lists
CDR
DATADIC
DXSUM
FAQ
MMSE
MRI3META
MRIMPRANK
MRIQC
NEUROBAT
PTDEMOG
REGISTRY
ROSTER
```

Download the selected files as a single archive. IDA downloads this archive as:

```text
download.zip
```

Place `download.zip` directly in:

```text
Data/
```

These tables provide the clinical outcomes, diagnostic labels, participant covariates, visit information, MRI acquisition metadata, scan-ranking information, and MRI quality-control information needed to link ADNI T1 MRI scans to participant-level variables.

---

## Clinical and metadata file roles

| File pattern                         | Role in the study                                                                                                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ADAS_*.csv`                         | Alzheimer’s Disease Assessment Scale cognitive data. Used for cognitive outcome analyses.                                                                     |
| `ADNIMERGE2.tar.gz`                  | Merged ADNI clinical package. Used as the main longitudinal table for age, visit, diagnosis, cognition, and covariate linkage where available.                |
| `ADNI_3T_MRI_Standardized_Lists.zip` | ADNI standardised 3T MRI image lists. Used to support scan selection and verify that selected MRI images correspond to recommended ADNI structural MRI scans. |
| `CDR_*.csv`                          | Clinical Dementia Rating data. Used for dementia severity and CDR-SB analyses.                                                                                |
| `DATADIC_*.csv`                      | ADNI data dictionary. Used to interpret variable names, table fields, coding, and visit variables.                                                            |
| `DXSUM_*.csv`                        | Diagnostic summary table. Used to assign and verify diagnostic labels by visit.                                                                               |
| `FAQ_*.csv`                          | Functional Activities Questionnaire data. Used as a functional outcome or secondary clinical measure.                                                         |
| `MMSE_*.csv`                         | Mini-Mental State Examination data. Used as a global cognitive outcome.                                                                                       |
| `MRI3META_*.csv`                     | 3T MRI metadata. Used to link image identifiers to scan dates, acquisition metadata, image descriptions, and MRI protocol information.                        |
| `MRIMPRANK_*.csv`                    | MPRAGE ranking table. Used to choose among repeated MPRAGE scans for the same participant or visit.                                                           |
| `MRIQC_*.csv`                        | MRI quality-control table. Used to identify usable scans and exclude scans failing ADNI MRI QC criteria.                                                      |
| `NEUROBAT_*.csv`                     | Neuropsychological battery data. Used for additional cognitive measures beyond MMSE, ADAS, CDR, and FAQ.                                                      |
| `PTDEMOG_*.csv`                      | Participant demographics. Used for sex, education, and demographic covariates.                                                                                |
| `REGISTRY_*.csv`                     | Subject registry and visit participation table. Used for visit linkage and participant tracking.                                                              |
| `ROSTER_*.csv`                       | Subject roster. Used for subject identifiers and cohort-level linkage.                                                                                        |

ADNI appends download or version dates to some filenames. The exact date suffix is not part of the cohort definition.

---

## Step 3: Create the MRI image search

In IDA, open:

```text
ADNI -> Search -> Advanced Image Search
```

Use these search settings.

### Search sections

Select:

```text
Project/Phase
Subject
Study/Visit
Image
Imaging Protocol
```

These sections expose the fields needed to define the imaging cohort: ADNI phase, participant diagnostic group, baseline or screening visit, MRI sequence, and MRI acquisition parameters.

### Image type

Select:

```text
Pre-processed
```

Pre-processed ADNI images have already undergone ADNI-standard image corrections. This keeps the acquisition focused on structural brain-age modelling rather than raw-image correction and reduces avoidable heterogeneity in the first-pass imaging set.

### Project and phases

Select:

```text
Project:
  ADNI

Phases:
  ADNI 1
  ADNI GO
  ADNI 2
  ADNI 3
```

These phases provide the main ADNI structural MRI data used for this first-pass study. Restricting the acquisition to these phases keeps the image cohort aligned with the selected metadata, MRI QC files, and clinical tables.

### Research groups

Select:

```text
CN
MCI
EMCI
LMCI
AD
```

The study compares cognitively normal participants, mild cognitive impairment, and Alzheimer’s disease. EMCI and LMCI are ADNI mild-cognitive-impairment subtypes and are retained for later harmonisation into the broader MCI category.

### Visits

Select:

```text
ADNI Screening
ADNI Baseline
ADNIGO Screening MRI
ADNI2 Screening MRI-New Pt
ADNI2 Baseline-New Pt
ADNI2 Initial Visit-Cont Pt
ADNI3 Initial Visit-Cont Pt
```

Set visit logic to:

```text
OR
```

The first-pass analysis uses one baseline or initial structural MRI per participant. ADNI phases encode baseline-like visits differently, so these visit labels are combined with `OR` to capture the corresponding entry-point MRI scans across phases.

### Image criteria

Set:

```text
Image description:
  *MPRAGE*

Modality:
  MRI

Image logic:
  AND
```

MPRAGE is the primary 3D T1-weighted anatomical sequence used for structural MRI analysis in ADNI. The wildcard captures common ADNI series descriptions containing `MPRAGE`. The `AND` logic ensures that returned records satisfy both the image-description criterion and the MRI modality criterion.

### Imaging protocol criteria

Set:

```text
Field strength:
  3 tesla

Weighting:
  T1

Acquisition type:
  3D

Acquisition plane:
  SAGITTAL
```

3T is used to keep field strength consistent across the first-pass imaging cohort. T1-weighted structural MRI is the required anatomical contrast for brain-age modelling. A 3D acquisition provides a whole-brain anatomical volume suitable for registration, segmentation, and structural feature extraction. Sagittal MPRAGE is the standard orientation used by many ADNI 3D T1 acquisitions.

### Result columns

Select these fields for display in the search results:

```text
Subject ID
Age
Sex
Research Group
Study Date
Image Description
Image ID
Modality
Field Strength
Weighting
Acquisition Type
Acquisition Plane
Manufacturer
Mfg Model
```

These fields are needed to audit the image search, check cohort composition, identify repeated scans, link image files to participant and visit metadata, and document scanner/acquisition heterogeneity.

Export the search-results CSV and name it:

```text
IDA_SearchResults_MPRAGE_Preprocessed_3T_T1.csv
```

Place the exported CSV directly in:

```text
Data/
```

The search-results CSV records the exact images returned by IDA before download.

---

## Step 4: Add the MRI images to an IDA collection

Select all matching images returned by the search and add them to an IDA collection.

Name the collection:

```text
ADNI_Baseline_3T_T1_MPRAGE_Preprocessed
```

If IDA truncates the collection name, use:

```text
ADNI_Baseline_3T_T1_MPRAG
```

The collection corresponds to:

```text
Baseline/screening 3T T1-weighted preprocessed MPRAGE MRI
ADNI 1, ADNI GO, ADNI 2, ADNI 3
CN, MCI, EMCI, LMCI, AD
```

IDA downloads image files through collections. The collection name records the key acquisition choices: ADNI source, baseline/screening timing, 3T field strength, T1 contrast, MPRAGE sequence, and preprocessed image type.

---

## Step 5: Export collection metadata

Before downloading image archives, export the collection metadata from IDA.

Download the IDA metadata archive. In this acquisition, the metadata archive is named:

```text
ADNI_Baseline_3T_T1_MPRAG_IDA_Metadata.zip
```

Place the metadata zip directly in:

```text
Data/
```

The metadata files provide the audit trail linking downloaded image files to IDA image identifiers, subject identifiers, scan descriptions, and acquisition metadata.

### Manifest file roles

| File                                              | Role in the study                                                                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `IDA_SearchResults_MPRAGE_Preprocessed_3T_T1.csv` | Records the image search results returned by IDA for the specified MPRAGE query.                                               |
| `IDA_CollectionManifest.csv`                      | Records the images added to the IDA collection and supports local auditing of the downloaded image set.                        |
| `IDA_Metadata.csv`                                | Records IDA download metadata for the image files and supports file-level linkage after download.                              |
| `ADNI_Baseline_3T_T1_MPRAG_IDA_Metadata.zip`      | IDA metadata archive downloaded with the image collection. The unpacking utility extracts it into the imaging manifest folder. |

---

## Step 6: Download the MRI image archives

Use IDA Advanced Download for the image collection.

Set the download grouping to:

```text
10 zip files
```

Large ADNI image collections are more reliable to download as split archives than as one very large zip file. Each part can be extracted and deleted after successful extraction, reducing peak disk usage.

The image archives must be named:

```text
ADNI_Baseline_3T_T1_MPRAG.zip
ADNI_Baseline_3T_T1_MPRAG1.zip
ADNI_Baseline_3T_T1_MPRAG2.zip
ADNI_Baseline_3T_T1_MPRAG3.zip
ADNI_Baseline_3T_T1_MPRAG4.zip
ADNI_Baseline_3T_T1_MPRAG5.zip
ADNI_Baseline_3T_T1_MPRAG6.zip
ADNI_Baseline_3T_T1_MPRAG7.zip
ADNI_Baseline_3T_T1_MPRAG8.zip
ADNI_Baseline_3T_T1_MPRAG9.zip
```

Place all image archive zips directly in:

```text
Data/
```

At this point, the `Data/` directory must contain:

```text
Data/
  README.md
  download.zip
  IDA_SearchResults_MPRAGE_Preprocessed_3T_T1.csv
  ADNI_Baseline_3T_T1_MPRAG.zip
  ADNI_Baseline_3T_T1_MPRAG1.zip
  ADNI_Baseline_3T_T1_MPRAG2.zip
  ADNI_Baseline_3T_T1_MPRAG3.zip
  ADNI_Baseline_3T_T1_MPRAG4.zip
  ADNI_Baseline_3T_T1_MPRAG5.zip
  ADNI_Baseline_3T_T1_MPRAG6.zip
  ADNI_Baseline_3T_T1_MPRAG7.zip
  ADNI_Baseline_3T_T1_MPRAG8.zip
  ADNI_Baseline_3T_T1_MPRAG9.zip
  ADNI_Baseline_3T_T1_MPRAG_IDA_Metadata.zip
```

---

## Step 7: Unpack the downloaded archives

Run the unpacking utility from the repository root:

```powershell
python Source\Utilities\UnpackRawData.py
```

The utility creates the raw-data folders, moves each archive into the correct location, extracts it, and deletes each zip after successful extraction.

To retain the downloaded zip archives after extraction, run:

```powershell
python Source\Utilities\UnpackRawData.py --keep-archives
```

After successful unpacking, the expected layout is:

```text
Data/
  README.md
  Raw/
    Clinical/
      StudyData/
        ADAS_*.csv
        ADNIMERGE2.tar.gz
        ADNI_3T_MRI_Standardized_Lists.zip
        ADNI_3T_MRI_Standardized_Lists/
        CDR_*.csv
        DATADIC_*.csv
        DXSUM_*.csv
        FAQ_*.csv
        MMSE_*.csv
        MRI3META_*.csv
        MRIMPRANK_*.csv
        MRIQC_*.csv
        NEUROBAT_*.csv
        PTDEMOG_*.csv
        REGISTRY_*.csv
        ROSTER_*.csv
    Imaging/
      Baseline3T1MPRAGE/
        Manifest/
          ADNI_Baseline_3T_T1_MPRAG_IDA_Metadata/
          ...
        Archives/
        Images/
          ...
```

With the default command, `Archives/` is empty because the script deletes each zip after successful extraction. The extracted image files are stored under:

```text
Data/Raw/Imaging/Baseline3T1MPRAGE/Images/
```

A successful run for this acquisition produced:

```text
Clinical files: 587
Manifest files: 3948
Remaining archive files: 0
Extracted image files: 1974
Extracted NIfTI files: 1974
```

Exact counts may differ if ADNI updates the downloadable tables or if the image search is repeated at a different time.

---

## Data governance

ADNI data are restricted and must not be committed to this repository.

The following paths are excluded from version control:

```text
Data/Raw/*
```

The repository documents how to obtain and organise the data, while the restricted ADNI files remain local to approved users.