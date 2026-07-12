# Changelog

## 2026-07-12

### Added

- Added the V3.2 secondary Age+AL-conditioned geometry score to the Python runtime, Excel export, and browser calculator.
- Added joint age-and-AL empirical calibration, untouched-test validation by age and AL band, and an explanatory report.
- Added regression tests that keep all V3.1 Overall OOD geometry and calibration inputs unchanged.
- Added a reproducible marginal-adjustment analysis for the postoperative pilot, including patient-cluster inference, leave-one-patient-out discrimination, machine-readable results, and a clinician-facing summary.
- Added a Korean guide to continuous age adjustment, robust splines, local MAD scaling, the transition from age strata, and the rationale for the age anchors.
- Added patient-cluster bootstrap confidence intervals for the V3.2 conditional-score category proportions.

### Changed

- Switched active desktop, web, Windows-build, and static-deployment artifacts to `continuous-age-bilateral-v3.2.0`.
- Displayed the new metric as a clearly separated research score; AL selects the conditional reference but is excluded from its distance.
- Added AL-conditioned percentile, status, reference context, dominant residuals, local effective N, calibration ceiling, warnings, and Core-sensitivity fields to the desktop XLSX output.
- Preserved the V3.1 Overall age adjustment, robust geometry, and calibration values exactly instead of refitting them under a newer scikit-learn version.
- Updated the web result view with a dedicated `Geometry given age + AL` card and conditional calibration details while retaining Overall OOD as the primary result.
- Updated the Windows build, static-site allowlist, and R2 publisher to package the V3.2 model artifact.
- Made the JavaScript regression suite compatible with the repository's ES module configuration.

### Research findings

- In 85 routine pilot eyes, formula spread increased from 0.84 D in Typical eyes to 1.31 D in Rare eyes (`rho=0.393`, `p=0.0002`).
- The OOD association with formula spread remained after adjustment for absolute AL and K deviations and after adjustment for all six marginal deviations; the combined six-variable model added `Delta R2=0.044` (`p=0.038`).
- Leave-one-patient-out discrimination for formula spread at least 1 D improved from AUC 0.737 to 0.809 in the primary marginal model.
- OOD did not show a consistent association with postoperative prediction error, so the defensible use remains formula-disagreement screening rather than refractive-error prediction.

### Validation

- Selected an 8-year age bandwidth and 1.0 standardized-AL bandwidth for both Core and Extended conditional calibration using the held-out tuning set.
- On the untouched test set, conditional-percentile uniformity KS was 0.043 for Core and 0.032 for Extended; Rare proportions were 1.33% and 1.49%, respectively.
- Patient-cluster bootstrap 95% intervals for the conditional Rare proportion were 0.7-2.1% for Core and 0.8-2.3% for Extended.
- Confirmed that V3.2 reproduces all V3.1 Overall demo distances, percentiles, and categories while adding the conditional result in parallel.
- Passed the 15-test Python suite, JavaScript core regression suite, and exact seven-file static deployment build.

## 2026-07-11

### Added

- Added versioned Cloudflare R2 publishing for the allowlisted static Explorer bundle, including SHA-256 manifests, immutable release paths, remote verification, explicit stable promotion, and rollback by version.
- Added a GitHub Actions workflow for manual publish/promote and automatic promotion from `biometry-ood-v*` tags.
- Added the continuous-age bilateral V3.1 OOD training pipeline with patient-level derivation, tuning, calibration, and untouched-test splits.
- Added Core and Extended V3.1 model artifacts, cluster-aware validation reports, and the one-eye V3 sensitivity model for reproducibility.
- Added Huber spline age adjustment, age-local MAD scaling, robust Minimum Covariance Determinant geometry, and age-weighted empirical percentile calibration.
- Added marginal feature profiles, local calibration effective sample size, and Core-only sensitivity results when the Extended model is selected.
- Added randomized clinical demo examples covering adult, pediatric, young-adult, Typical, Uncommon, and Rare anatomy combinations.
- Added modeling dependencies and scripts for bilateral training, continuous-age sensitivity analysis, and age-biometry trend figures.
- Added an allowlist-only static deployment builder that publishes the web calculator and active model without source data, reports, or project code.
- Added persistent browser-only processing and research/education-use notices to the calculator.
- Added a restrictive Content Security Policy that limits the static calculator to same-origin scripts, styles, images, and model loading while disabling form submission.

### Changed

- Added collision protection that permits idempotent publication of matching content but rejects an attempt to overwrite an existing version with different hashes.
- Made `stable.json` and the no-cache gateway HTML the only mutable objects, with the gateway pointer written last after remote manifest verification.
- Added a K-ERA-relative base path to the promoted entry so all versioned scripts, styles, and model requests remain on `/tools/biometry-ood`.
- Switched the desktop parser, web calculator, and Windows build from the age-stratified V2 bundle to `continuous-age-bilateral-v3.1.0`.
- Included both eligible eyes while keeping fellow eyes in the same patient-level data split to prevent leakage.
- Replaced age-stratum switching with one continuous model across ages 2–100 years.
- Updated the web result view with a tail-expanded percentile scale, emphasized indicator, larger percentile display, age-adjusted feature profile, and clearer clinical wording.
- Renamed the explanatory output to `Largest marginal deviations for age` and clarified that it is not a causal decomposition of Mahalanobis distance.
- Documented the complete OOD model logic, cohort construction, calibration method, limitations, and pilot postoperative formula conventions in `README.md`.
- Updated the executable output columns and number formats for the new calibration, marginal-deviation, and Core-sensitivity fields.
- Replaced over-precise rarity point estimates such as `1 in 23` with rounded ranges such as `~1 in 20–30`.
- Corrected the calibration reference wording to `age-weighted calibration eyes`; patient clustering applies to effective-sample interpretation and validation confidence intervals rather than the empirical percentile unit.
- Added explicit Core fallback warnings when WTW or CCT is missing, invalid, or outside the Extended-model range.
- Added age-local effective-N and attainable-percentile-ceiling warnings for sparsely calibrated ages.
- Added selected model version, tier-specific untouched-test cohort, and applicability limits directly to the result view.

### Validation

- Published and promoted the initial `v3.1.0` bundle to `releases.k-era.org`, then verified the stable metadata, entry HTML, immutable assets, active model, cache controls, and K-ERA proxy paths.
- Added credential-free R2 dry-run coverage and verified the publisher with the PowerShell parser, the full 14-test Python suite, and the JavaScript core regression suite.
- V3.1 Core used 8,177 eyes from 4,501 patients; Extended used 8,164 eyes from 4,498 patients.
- The untouched bilateral test set contained 1,280 Core eyes and 1,275 Extended eyes, with patient-cluster bootstrap confidence intervals reported for category proportions.
- Added Python and JavaScript regression tests for continuous age behavior, age-local percentile calibration, Core/Extended selection, demo cases, and tail-expanded scale mapping.
- Made the Node regression test resolve model artifacts relative to `__dirname`, so it runs independently of the current working directory.
- Added static deployment regression tests that verify the exact seven-file allowlist and reject contaminated output directories.
- Added regression coverage for invalid optional-input fallback and sparse age-local calibration warnings.
- Verified the R2 release and promotion workflow with a credential-free dry run covering all tests, the allowlisted build, manifest generation, immutable object paths, and stable-pointer writes.
- Kept postoperative outcome interpretation explicitly exploratory; the OOD percentile does not directly predict refractive error or select an IOL formula.

### Repository

- Excluded local lecture slides, manuscript figures, and other generated presentation outputs from version control.
- Added a tracked pre-commit guard for clinical Excel/CSV/PDF sources and presentation/manuscript PPT, Word, and PNG artifacts.
- Extended repository protection to ignore and pre-commit block local R2 credential files matching `.env*.local`.

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
