# Visualisation

`GenerateBrainAgeFigures.py` writes exactly four PNG files:

* `table1_demographic_characteristics.png`;
* `figure1_predicted_vs_actual_age.png`;
* `figure2_gap_distribution_by_diagnosis.png`; and
* `figure3_calibration_curves.png`.

The PNGs contain only the table or plot. Figure captions and descriptive paragraphs are not embedded in the images. PDF output is disabled.

Run from the repository root:

```powershell
python Source\Visualisation\GenerateBrainAgeFigures.py
```