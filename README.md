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

## Research Focus

Brain-age modelling provides a way to convert high-dimensional structural MRI information into an interpretable ageing-related marker. In this study, brain-age prediction is used as an intermediate modelling step to derive brain-age gap, which is then analysed in relation to cognitive and diagnostic outcomes.

The central research question is:

> Is MRI-derived brain-age gap associated with cognitive decline and Alzheimer’s disease diagnosis after accounting for chronological age and basic participant-level variables?

---

## Data

This study is designed for use with data from the Alzheimer’s Disease Neuroimaging Initiative (ADNI).

ADNI provides longitudinal neuroimaging, clinical, cognitive, genetic, and biomarker data for Alzheimer’s disease research. Access is managed through the official ADNI data access process and is subject to the applicable data-use agreements.

---

## Reproducibility Principles

The study prioritises:

* Clear separation between raw data, derived outputs, source code, and reports.
* Documented preprocessing and modelling decisions.
* Deterministic train-test splitting where applicable.
* Explicit recording of model inputs, covariates, and evaluation metrics.
* Version-controlled analysis code.
* Transparent reporting of statistical models, assumptions, and evaluation criteria.
## Purpose

This study investigates whether structural MRI-derived brain-age gap is associated with cognitive decline and Alzheimer’s disease diagnosis.

The aim is to establish a reproducible analysis workflow that connects neuroimaging-derived ageing estimates with cognitive and diagnostic outcomes in a transparent, statistically interpretable way.