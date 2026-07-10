# Changelog

## 2026-07-11

### Added

- Added the continuous-age bilateral V3.1 OOD training pipeline with patient-level derivation, tuning, calibration, and untouched-test splits.
- Added Core and Extended V3.1 model artifacts, cluster-aware validation reports, and the one-eye V3 sensitivity model for reproducibility.
- Added Huber spline age adjustment, age-local MAD scaling, robust Minimum Covariance Determinant geometry, and age-weighted empirical percentile calibration.
- Added marginal feature profiles, local calibration effective sample size, and Core-only sensitivity results when the Extended model is selected.
- Added randomized clinical demo examples covering adult, pediatric, young-adult, Typical, Uncommon, and Rare anatomy combinations.
- Added modeling dependencies and scripts for bilateral training, continuous-age sensitivity analysis, and age-biometry trend figures.

### Changed

- Switched the desktop parser, web calculator, and Windows build from the age-stratified V2 bundle to `continuous-age-bilateral-v3.1.0`.
- Included both eligible eyes while keeping fellow eyes in the same patient-level data split to prevent leakage.
- Replaced age-stratum switching with one continuous model across ages 2–100 years.
- Updated the web result view with a tail-expanded percentile scale, emphasized indicator, larger percentile display, age-adjusted feature profile, and clearer clinical wording.
- Renamed the explanatory output to `Largest marginal deviations for age` and clarified that it is not a causal decomposition of Mahalanobis distance.
- Documented the complete OOD model logic, cohort construction, calibration method, limitations, and pilot postoperative formula conventions in `README.md`.
- Updated the executable output columns and number formats for the new calibration, marginal-deviation, and Core-sensitivity fields.

### Validation

- V3.1 Core used 8,177 eyes from 4,501 patients; Extended used 8,164 eyes from 4,498 patients.
- The untouched bilateral test set contained 1,280 Core eyes and 1,275 Extended eyes, with patient-cluster bootstrap confidence intervals reported for category proportions.
- Added Python and JavaScript regression tests for continuous age behavior, age-local percentile calibration, Core/Extended selection, demo cases, and tail-expanded scale mapping.
- Kept postoperative outcome interpretation explicitly exploratory; the OOD percentile does not directly predict refractive error or select an IOL formula.

### Repository

- Excluded local lecture slides, manuscript figures, and other generated presentation outputs from version control.

## 2026-07-10

### Added

- Added age-stratified Core and Extended V2 OOD models.
- Added clinician-facing percentile, rarity context, and dominant-deviation summaries.

### Changed

- Replaced the numeric anatomy score with percentile-based Typical, Uncommon, and Rare meaning.
- Simplified the desktop and web result views for clinical interpretation.

## 2026-06-15

### Added

- Added the GitHub project documentation and Windows build workflow.

### Fixed

- Fixed IOLMaster CSV parsing and preserved leading zeros in patient identifiers.
