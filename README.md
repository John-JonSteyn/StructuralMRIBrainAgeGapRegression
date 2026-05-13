# Structural MRI Brain-Age Gap Regression

*A structural-MRI study estimating brain-age gap and analysing its association with cognitive decline and Alzheimer’s disease using ADNI data.*

## Overview

This study investigates whether structural MRI can be used to derive an interpretable brain-age gap marker associated with cognitive decline and Alzheimer’s disease. The analysis uses T1-weighted MRI scans from the Alzheimer’s Disease Neuroimaging Initiative (ADNI), linked with participant-level demographic, diagnostic, and cognitive variables.

Brain-age gap is defined as the difference between MRI-predicted brain age and chronological age. A positive brain-age gap indicates that a participant’s brain appears older than expected for their chronological age, while a negative brain-age gap indicates that it appears younger.

The repository contains the reproducible research workflow used to prepare data, estimate brain age, compute brain-age gap, and analyse its relationship with cognitive and diagnostic outcomes.

---

## Objectives

* Develop a reproducible workflow for handling ADNI structural MRI files and associated metadata.
* Train regression models to predict chronological age from structural MRI-derived features.
* Compute brain-age gap for held-out participants.
* Test whether brain-age gap is associated with cognitive performance.
* Evaluate whether brain-age gap differs across diagnostic groups, including cognitively normal participants, mild cognitive impairment, and Alzheimer’s disease.
* Assess whether brain-age gap provides interpretable information beyond chronological age and basic participant-level variables.

---

## Research Focus

Brain-age modelling provides a way to convert high-dimensional structural MRI information into an interpretable ageing-related marker. In this study, brain-age prediction is used as an intermediate modelling step to derive brain-age gap, which is then analysed in relation to cognitive and diagnostic outcomes.

The central research question is:

> Is MRI-derived brain-age gap associated with cognitive decline and Alzheimer’s disease diagnosis after accounting for chronological age and basic participant-level variables?

---

## Data

This study uses data from the Alzheimer’s Disease Neuroimaging Initiative (ADNI). ADNI data are not included in this repository. Access requires approval through the LONI Image & Data Archive and compliance with the applicable ADNI data-use agreements.

The data-acquisition procedure, selected ADNI tables, MRI search filters, collection names, and local folder layout are documented in [`Data/README.md`](Data/README.md).

After downloading the required ADNI archives, place them directly in `Data/` and run:

```powershell
python Source\Utilities\UnpackRawData.py
```

The first-pass dataset is designed around baseline or screening 3T T1-weighted structural MRI from ADNI 1, ADNI GO, ADNI 2, and ADNI 3, linked to diagnosis, demographics, cognitive assessments, MRI metadata, and MRI quality-control tables.

The raw and derived ADNI data directories are excluded from version control.

---

## Software Requirements

The data-preparation scripts require **Python 3.10** or later.

MRI feature extraction requires **Docker**. FastSurfer is run through the official Docker image rather than installed directly into this repository.

*On Windows, Docker Desktop should be installed with the WSL2 backend enabled. On Linux and macOS, use a working Docker installation suitable for the host system.*

FastSurfer also requires a local FreeSurfer licence file for the full surface-processing pipeline. The licence file should be stored locally and should not be committed to version control.

---

## Methodology

1. **Data preparation**
   Identifying, organising, and documenting the required ADNI imaging and tabular metadata files.

2. **MRI processing**
   Processing T1-weighted MRI scans to obtain structural neuroimaging features suitable for statistical modelling and machine-learning analysis.

3. **Feature integration**
   Linking MRI-derived features with chronological age, diagnosis, cognitive scores, and relevant participant-level covariates.

4. **Brain-age modelling**
   Training regression models to predict chronological age from MRI-derived structural features.

5. **Brain-age gap estimation**
   Calculating the difference between predicted brain age and chronological age for held-out participants.

6. **Statistical analysis**
   Analysing associations between brain-age gap, cognitive performance, and Alzheimer’s disease diagnostic status.

7. **Reporting**
   Summarising the modelling results, statistical findings, limitations, and reproducibility considerations.

---

## Reproducibility Principles

The study prioritises:

* Clear separation between raw data, derived outputs, source code, and reports.
* Documented preprocessing and modelling decisions.
* Deterministic train-test splitting where applicable.
* Explicit recording of model inputs, covariates, and evaluation metrics.
* Version-controlled analysis code.
* Transparent reporting of statistical models, assumptions, and evaluation criteria.

---

## Purpose

This study investigates whether structural MRI-derived brain-age gap is associated with cognitive decline and Alzheimer’s disease diagnosis.

The aim is to establish a reproducible analysis workflow that connects neuroimaging-derived ageing estimates with cognitive and diagnostic outcomes in a transparent, statistically interpretable way.