# Age-Conditioned Joint Biometry as a Preoperative Review Flag for Interformula Discordance: A Study of 4,123 Eyes

**Short title:** Joint biometry and formula discordance  
**Article type:** Full-length Article  
**Main-text word count:** 2,988  
**Abstract word count:** 241  
**Tables/Figures:** 2/2
**Supplemental files:** 1 file containing supplemental methods, 14 supplemental tables, and 1 supplemental figure

**Authors:** Woojin Sa, MD; Jinho Jeong, MD  
**Affiliations:** Department of Ophthalmology, Jeju National University Hospital, Jeju, Republic of Korea (both authors)  
**Corresponding author:** Jinho Jeong, MD, Department of Ophthalmology, Jeju National University Hospital, 15 Aran 13-gil, Jeju-si, Jeju-do 63241, Republic of Korea. Email: dr.jinho.jeong@gmail.com  
**Meeting presentation:** None  
**Author contributions:** Conceptualization, methodology, software, formal analysis, visualization, original drafting, and supervision: J.J. Investigation, data curation, and validation: W.S. and J.J. Review and editing: W.S. and J.J. Both authors approved the final manuscript.  
**Financial support:** None  
**Conflicts of interest:** The authors declare no conflicts of interest  

## Abstract

### Purpose

To test whether age-conditioned joint ocular biometry identifies a low-burden subgroup enriched for interformula disagreement despite conventional axial length (AL) and keratometry (K).

### Setting

Jeju National University Hospital, Jeju, Republic of Korea.

### Design

Retrospective observational study.

### Methods

A patient-separated biometry-only reference model was frozen before formula outcomes. In 4,123 linked eyes, Hoffer Q, SRK/T, Haigis, and Barrett Universal II TK predictions were aligned at the same IOL model and power; postoperative refraction was unavailable. Spread was the maximum minus minimum prediction. Models adjusted for age, power, year, IOL model, and component marginal extremeness, with patient-clustered inference.

### Results

Median spread was 0.29 D; 491 eyes (11.9%) reached 0.50 D. Each 10-percentile score increase was associated with 0.0218 D greater adjusted spread (95% CI, 0.0192-0.0243). In a clinically focused post hoc subgroup of 3,365 eyes with AL 22 to <26 mm and mean K 42 to <46 D, 31.8% at or above the 90th percentile versus 4.4% below reached 0.50 D (unadjusted risk ratio, 7.29; 95% CI, 4.83-10.24). Adjusted risks were 16.6% versus 4.6% (risk ratio, 3.57; 95% CI, 1.87-6.09). The threshold flagged 2.5%, with 15.9% sensitivity and 98.2% specificity. In 646 untouched-split eyes, the adjusted effect was 0.0190 D per 10 percentile points (95% CI, 0.0126-0.0253).

### Conclusions

Age-conditioned joint biometry identified a low-burden, discordance-enriched subgroup despite conventional AL and K. It may target review but does not measure postoperative accuracy, rule out discordance, or select a formula.

**Keywords:** intraocular lens calculation; ocular geometry; predicted refraction; cataract surgery; multivariable reference model

IOL formulas can yield different predicted postoperative refractions for the same eye and power, and performance varies with biometry and implementation.1-3 Discordance is visible before surgery and can prompt review of measurements, constants, inputs, and IOL choice; accuracy is known only afterward.

Most subgroup analyses classify one variable at a time, such as AL, K, or anterior chamber depth (ACD).4 Formula-specific biometric associations suggest that relationships among measurements may matter.5 Large swept-source biometry datasets demonstrate age-related coupling among AL, ACD, lens thickness (LT), and white-to-white (WTW),6 and short-eye outcomes can vary with the joint AL-ACD configuration.7

Multivariable approaches include the 27-group AL-ACD-K LAKE classification8 and multicenter autoencoder screening.9 Neither tested an age-calibrated, outcome-naive continuous score against same-eye, same-power interformula spread. Earlier spread studies were smaller or selected after disagreement.10,11 We tested whether joint geometry identified spread beyond age, power, and marginal extremeness despite conventional AL and K.

## Methods

### Study Design, Data Sources, and Ethics

This retrospective observational study was conducted at Jeju National University Hospital and combined an institutional IOLMaster 700 biometry export with deidentified formula-screen images. Eligible clinical biometry records dated November 22, 2022 through June 15, 2026; the linked primary formula cohort dated November 23, 2022 through June 15, 2026. Reporting followed the STROBE statement.12 The Jeju National University Hospital Institutional Review Board approved the protocol on July 14, 2026 (JNUH 2026-06-028-003) and waived informed consent. Direct identifiers were retained only in a protected linkage environment. Analytic files used nonreversible patient and examination tokens.

The biometry source contained 12,615 measurement records representing 9,305 patient-eye pairs before eligibility filtering; records included repeated same-day and longitudinal measurements.

### Formula Extraction, Validation, and Linkage

A local OCR pipeline extracted eye, IOL model, formula, IOL power, and predicted refraction from 38,226 pages in 5,194 examinations, yielding 908,037 traceable rows. Independent full-pipeline reruns produced identical normalized outputs. In a separate masked, OOD-enriched 500-eye source-screen audit, all prespecified fields matched the original reports. Audit methods appear in the Supplement; source-level sensitivities varied duplicate resolution and excluded low-confidence, conflicting, or sequence-inconsistent rows.

Formula screens were linked to biometry by patient, date, and eye. The conservative primary cohort required a unique patient-date-eye record. A linked sensitivity retained repeated same-day records by selecting the biometry acquisition closest in time to the formula screen.

### Formula Panel and IOL Power Anchoring

The panel comprised Hoffer Q, SRK/T, Haigis, and Barrett Universal II TK. The reports displayed the device's TK marker for every formula block; Hoffer Q, SRK/T, and Haigis retained their standard displayed names within the TK workflow. Predictions were compared only at the same eye, IOL model, and power and were not recomputed. The clinical export recorded IOLMaster 700 software 1.90.33.4.C89415, corresponding to report footer 1.90.33.04. For ZCB00, local constants were Haigis a0 -1.302, a1 +0.210, and a2 +0.251; Hoffer Q pACD +5.80; SRK/T A-constant 119.30; and Barrett lens factor +2.09 and design factor +4.5. For the ARTIS® one-piece hydrophobic acrylic aspheric IOL (Cristalens Industrie, Lannion, France), corresponding constants were +0.088, +0.233, and +0.200; +6.09; 119.74; and +2.27/+5.0.

For the primary analysis, the selected power gave a Haigis prediction from 0.00 to -0.50 D and was closest to -0.25 D. ZCB00 was preferred. ARTIS was used only when a usable ZCB00 Haigis row was unavailable; in all 3 included ARTIS eyes, the ZCB00 Haigis block was absent while ARTIS provided the complete panel. Because Haigis anchoring can constrain Haigis-containing differences, power was reselected with the same rule using Barrett Universal II TK. The paired sensitivity included only eyes eligible under both rules.

Haigis-L or Barrett True-K TK appeared in 197 archive examination-eyes,13 none among the 5,974 eyes with all 4 routine formulas. Undocumented previous corneal refractive surgery remained possible elsewhere in the cohort. Medical records and corneal topography were specifically reviewed for the 9 short-steep eyes.

### Age-Conditioned Joint-Biometry Reference Model

The reference model (continuous-age-bilateral-v3.2.0) was frozen before the final formula analysis. The primary Extended model used AL, mean K, ACD, LT, WTW, and CCT. A separately trained Core sensitivity used AL, mean K, ACD, and LT. In the source export, R1/R2 were the flat/steep anterior keratometric radii and TR1/TR2 the flat/steep total-keratometry radii (mm), with TA1/TA2 their axes. Mean K for the reference model was calculated from R1/R2 using a keratometric index of 1.3375.

Eligibility required age 2 to 100 years and frozen ranges: AL 14 to 38 mm, mean K 30 to 65 D, ACD 0.8 to 6.0 mm, LT 2 to 8 mm, WTW 8 to 16 mm, and CCT 0.35 to 0.80 mm. These bounds matched the frozen V3.2 bundle, training constants, and serialized metadata. The latest eligible acquisition per patient-eye was retained; equal-date ties kept the first row. Identifiers were stripped and case-normalized; formula-link identifiers also lost a terminal numeric `.0` and nonalphanumerics. This yielded 8,164 Extended-eligible eyes (4,498 patients) and 8,177 Core-eligible eyes (4,501 patients).

For each measurement, the model estimated an age-specific expected value with a Huber piecewise-linear spline and divided residuals by an age-local robust scale. A reweighted minimum covariance determinant estimator provided the multivariable center and covariance.14 The square root of the robust Mahalanobis distance quantified how unusual the joint standardized geometry was. A separate patient-level calibration set converted distance to an age-local empirical percentile. Patients, not eyes, were separated across derivation, tuning, calibration, and untouched technical-test sets. Formula predictions and spread were not used in model development.

The primary categories were <90th, 90th to <97.5th, and ≥97.5th percentile. We call the score a reference-model percentile or joint biometric atypicality, not a diagnosis. Tail calibration used the untouched technical-test set. The frozen split was reconstructed for formula-cohort patients, and associations were repeated in formula eyes assigned to the untouched test split.

Post hoc design ablation compared 3 scores using the same patient split and 6 inputs: age-agnostic global, mean-only age-adjusted, and frozen full age-conditioned. Technical test examined age-percentile correlation and age-specific tail rates. Conventional-AL/K analyses compared incremental R2, 10-fold cross-validated RMSE, equal 2.5% review burden, and score-by-age interaction after flexible age adjustment.

### Outcomes and Statistical Analysis

The primary outcome was continuous spread: the maximum minus minimum predicted refraction among the 4 formulas at the anchored power. Spread ≥0.75 D was a sparse prespecified secondary outcome. The clinically focused post hoc subgroup comprised AL 22 to <26 mm and mean K 42 to <46 D; within this subgroup, spread ≥0.50 D provided a stable, interpretable contrast. These cutoffs are descriptive, not universal normal limits.

Ordinary least squares models adjusted for age, anchor power, IOL model, acquisition year, and absolute age-adjusted marginal z scores of AL, mean K, ACD, LT, WTW, and CCT. The percentile entered per 10 points; CIs used patient-cluster-robust covariance. In conventional-AL/K eyes, logistic models estimated continuous and ≥90th-threshold contrasts with the same covariates. Marginal risks were standardized over observed covariates; 95% CIs used 20,000 multivariate-normal draws from the robust coefficient covariance. Unadjusted contrasts used 2,000 patient-cluster bootstraps, operating characteristics used Wilson CIs, and patient-separated 10-fold cross-validation assessed incremental fit.

Figure 2 combined observed and adjusted mean spread, conventional-AL/K risk, and pairwise-gap models. Panel C used all 4,123 eyes and the same covariates as the primary continuous-spread model; CIs used patient-cluster-robust covariance.

Sensitivity analyses used paired Barrett TK anchoring, the expanded closest-time linkage, minimum OCR confidence ≥0.95, rank-based models, upper-quantile regression,15 alternative AL/K windows, restriction to all marginal |z| <2.5, the frozen Core score, reference-model split, acquisition year, representative-record rule, leave-one-formula-out panels, published-LAKE NNN component ranges, and recorded-sex QA. Equal-review-burden comparisons used the largest marginal |z| among the same inputs: all 6 for Extended and AL/K/ACD/LT for Core. Patient-cluster label permutation tested paired accuracy. Core, equal-burden, formula-decomposition, and biometric-domain analyses were exploratory; interaction P values used the Benjamini-Hochberg false-discovery rate. Two-sided P<.05 denoted statistical significance for primary analyses.

## Results

### Cohort Assembly

The reference-model stage began with 12,615 biometry records. After eligibility and one-record-per-eye processing, the Extended model included 8,164 eyes from 4,498 patients. The formula archive yielded 6,895 Haigis-anchor examination-eyes; 6,451 linked to biometry and 4,123 eyes from 2,292 patients entered the conservative cohort (Figure 1). The main exclusions were nonunique same-date linkage (1,011) and an incomplete 4-formula panel at the selected power (1,198).

### Primary Association and Clinical Contrast

Median age was 71.2 years, median AL was 23.75 mm, and median anchor power was 21.0 D (Table 1). ZCB00 was selected in 4,120 eyes and ARTIS in 3. Median formula spread was 0.29 D (IQR, 0.20-0.40); 491 eyes (11.9%) reached 0.50 D and 40 (1.0%) reached 0.75 D.

Each 10-percentile increase in the Extended reference percentile was associated with 0.0218 D greater adjusted spread (95% CI, 0.0192-0.0243; P<.001), with an incremental R2 of 0.053. Patient-separated 10-fold cross-validated RMSE improved from 0.106 to 0.100 D. The partial Spearman correlation was 0.366 (patient-cluster bootstrap 95% CI, 0.333-0.398); rank-based, marginal-|z|-restricted, and upper-quantile analyses remained positive (Table 2).

From deciles 1 to 10, observed mean spread increased from 0.19 to 0.45 D and the proportion reaching 0.50 D increased from 1.2% to 36.1% (Figure 2A-B), supporting a graded association.

The conventional-AL/K subgroup included 3,365 eyes; 170 (5.1%) reached 0.50 D. Spread ≥0.50 D occurred in 27 of 85 eyes (31.8%) at or above the 90th Extended percentile and in 143 of 3,280 eyes (4.4%) below it. The unadjusted risk ratio was 7.29 (95% CI, 4.83-10.24), and the risk difference was 27.4 percentage points (95% CI, 17.1-37.9). Standardized adjusted risks were 16.6% above versus 4.6% below the threshold, giving an adjusted risk ratio of 3.57 (95% CI, 1.87-6.09) and risk difference of 12.0 percentage points (95% CI, 4.4-23.7). Separately, the continuous adjusted odds ratio was 1.71 per 10 percentile points (95% CI, 1.53-1.92) (Figure 2B; Table 2).

In all 4,123 eyes, adjusted pairwise-gap slopes ranged from -0.0023 D (Hoffer Q-Haigis) to +0.0232 D (Hoffer Q-SRK/T) per 10 percentile points (Figure 2C); this did not identify formula accuracy.

The ≥90th-percentile threshold flagged 85 of 3,365 conventional-AL/K eyes (2.5%; 95% CI, 2.0%-3.1%). Sensitivity was 15.9%, specificity 98.2%, positive predictive value 31.8%, and negative predictive value 95.6%. It was therefore a low-burden, high-specificity review flag rather than a rule-out screen.

### Robustness and Scope

Source-screen agreement was complete in the audited 500 eyes (500/500; 100.0%; exact 95% CI, 99.3%-100.0%). Across 16 nearby AL/K windows, all risk-ratio point estimates exceeded 5.2. In 3,356 eyes eligible under both anchors, high-versus-lower percentile risk ratios were 6.70 with Haigis and 7.31 with Barrett TK anchoring; continuous effects were 0.0218 and 0.0205 D per 10 percentiles. Expanded closest-time and minimum-confidence ≥0.95 analyses gave effects from 0.0212 to 0.0216 D per 10 percentiles.

The formula cohort included 646 eyes from 357 patients assigned by the frozen split hash to the reference model's untouched test partition. The adjusted effect remained 0.0190 D per 10 percentile points (95% CI, 0.0126-0.0253); among 515 conventional-AL/K test-split eyes it was 0.0178 D (95% CI, 0.0107-0.0249) (Supplemental Table S12). In the independent model technical test, 101 of 1,275 Extended eyes (7.92%; cluster-bootstrap 95% CI, 6.20%-9.81%) were ≥90th and 23 (1.80%; 95% CI, 1.01%-2.76%) were ≥97.5th (Supplemental Table S10).

Full conditioning removed technical-test age dependence: age-percentile rho was 0.016 (P=.580), versus -0.346 for global and -0.104 for mean-only scores (both P<.001); age-band ≥90th rates narrowed to 5.65%-11.48% from 3.70%-28.42% and 3.99%-32.50% (Supplemental Figure S1; Supplemental Table S14). In conventional-AL/K eyes, full score-by-age interaction was nonsignificant (P=.546; ages 50-89, P=.390). Global versus full incremental R2 was .101 versus .078 and RMSE .0898 versus .0918 D; at equal burden they captured 34 versus 27 events without a significant paired difference. Tail calibration was similar by recorded sex. Sex adjustment minimally changed the conventional-AL/K effect; the continuous score-by-sex interaction was +0.0052 D per 10 percentiles (FDR P=.002) but absent for ≥0.50 D (P=.998) (Supplemental Table S14).

In 5,031 paired source-level eyes, the anchors selected the same power in 56.0%, while 0.50-D and 0.75-D classifications agreed in 98.9% and 99.7% (Supplemental Table S6). Alternate duplicate rules changed 1 upstream 0.50-D classification and no 0.75-D classifications; after strict source exclusions, 12.2% of 4,837 eyes reached 0.50 D (Supplemental Table S5).

None of the 9 short-steep eyes had documented previous corneal refractive surgery. Topography showed regular steep corneal curvature without an ectatic or clinically significant irregular pattern.

AL modified the association (FDR-adjusted interaction P<.001). The adjusted effect was 0.0230 D per 10 percentiles among 3,874 eyes with AL 22 to <26 mm but -0.0045 D (95% CI, -0.0103 to 0.0013) among 179 eyes with AL ≥26 mm. In 70 eyes with AL <22 mm, all percentiles exceeded 54.0 and the slope was imprecise, indicating exposure-range restriction. Within 1,871 eyes in published LAKE NNN component ranges, the adjusted effect persisted (+0.0252 D per 10 percentiles; 95% CI, +0.0216 to +0.0287), but the ≥90th tail had 18 eyes and no ≥0.50-D events (Supplemental Table S9). Generalization beyond conventional AL is unsupported.

Linked-cohort acquisition year was not associated with continuous spread (joint P=.389) or spread ≥0.50 D (P=.307); linear-year estimates were -0.0012 D/y (P=.484) and odds ratio 0.893/y (P=.083) (Supplemental Table S8). The eligible clinical export used one documented software build and the displayed constants above.

### Core Sensitivity

The 4-variable Core percentile was correlated with Extended (Spearman rho, 0.797) and gave stronger exploratory estimates. Within conventional AL/K, spread ≥0.50 D occurred in 34 of 96 Core-high eyes (35.4%) versus 136 of 3,269 (4.2%) below the 90th percentile (risk ratio, 8.51; 95% CI, 5.72-11.84). The adjusted effect was 0.0288 D per 10 percentiles (95% CI, 0.0260-0.0317; incremental R2, 0.135) (Supplemental Table S4).

At the same 96-eye review burden, a screen based on the largest marginal |z| among AL, K, ACD, and LT captured 22 events (positive predictive value, 22.9%) versus 34 for Core (35.4%). The paired positive-predictive-value difference was 12.5 percentage points (cluster-bootstrap 95% CI, 3.0-21.9; patient-cluster paired permutation P=.020). The analogous Extended-versus-6-variable max-|z| comparison did not reach significance (27 versus 20 events; P=.184) (Supplemental Table S11).

The association remained positive when each formula was omitted in turn: adjusted effects ranged from 0.0140 to 0.0274 D per 10 percentile points (all P<.001) (Supplemental Table S13). In particular, the effect persisted after omitting Barrett Universal II TK (0.0141 D; 95% CI, 0.0114-0.0168), indicating that the signal was not dependent on that formula alone.

## Discussion

The central result is enrichment, not widespread disagreement. Within conventional-AL/K eyes, spread ≥0.50 D was approximately 7-fold more frequent above the 90th Extended percentile before adjustment; the standardized adjusted risk ratio was 3.57. Persistence within published LAKE NNN ranges supported a relational signal, although its sparse upper tail did not show threshold enrichment.

LAKE classification and autoencoder screening interpret biometry relationally but address classification and data quality rather than age-calibrated formula-screen triage.8,9 Our outcome-naive association persisted after marginal-extremeness adjustment and in untouched-split formula eyes. Full conditioning stabilized age-specific tails, whereas global scoring enriched discordance more strongly; it improved age-relative calibration, not predictive enrichment. No approach identifies an erroneous measurement or establishes postoperative benefit.

The threshold flagged 2.5% of conventional-AL/K eyes, about 1 in 40; about 1 in 3 flagged eyes was discordant. It missed 84.1% and is not a rule-out screen.

In one representative eye, AL was 23.26 mm, mean K 45.58 D, ACD 3.05 mm, and LT 5.61 mm; no marginal |z| exceeded 2.5, yet the joint percentile was 91.8 and same-power predictions ranged from -0.20 to +0.16 D. A flag should initiate 3 steps: check scan quality and repeat suspect biometry; verify IOL model, power, constants, and formula inputs; then compare same-power predictions and document the formula rationale. The score identifies neither the abnormal step nor the correct formula; agreement is not postoperative accuracy.16

Traditional strata remain useful in short, long, steep, or flat eyes.4,7,17,18 This flag instead asks whether plausible measurements form uncommon age-conditioned geometry. Recent Barrett Universal II data show that optional inputs and axial-length implementation can affect performance, particularly in short eyes.19 Such input asymmetry may contribute to panel spread, but mechanism was not tested.

Deterministic reruns and the separate source-screen audit supported extraction fidelity; rare errors outside the audited enriched sample remain possible.

The exploratory Core result suggests that relational information may be concentrated in AL, K, ACD, and LT. Its post hoc internal equal-burden comparison supports prospective evaluation, not superiority; Extended did not significantly outperform its 6-variable marginal comparator.

All 4 local blocks carried the device's TK marker, but this panel reflects one deployed IOLMaster workflow. A 36-formula benchmark spanning contemporary methods identified multiple modern high performers.20 Leave-one-formula-out associations reduce concern about a single-formula artifact but do not establish panel transportability. External validation should include current multiformula and ray-tracing platforms.

Formula spread does not identify the most accurate formula; postoperative refraction was unavailable, and decision benefit over unstructured review was not tested. Single-center sourcing limits transportability across devices, software, constants, IOLs, and populations; selection also limits generalization beyond conventional AL.

Measurement provenance remains important. Alternate record rules changed 0.31% to 0.44% of flags, and 6 of 40 events at ≥0.75 D arose among 9 short-steep eyes. Targeted review found no previous corneal refractive surgery or ectatic or clinically significant irregular topography.

In conclusion, a frozen age-conditioned joint-biometry percentile identified a small discordance-enriched subgroup despite conventional AL and K. The post hoc clinical contrast gave unadjusted and standardized adjusted risk ratios of 7.29 and 3.57. Available before surgery, the percentile may allocate targeted review of measurements, inputs, and same-power predictions; it neither measures accuracy, rules out discordance, nor selects a formula. External and postoperative validation should test whether it improves decisions.

## Acknowledgments

None.

## Synopsis

In a post hoc conventional-AL/K subgroup, a frozen biometry-only ≥90th percentile flagged 2.5% and enriched ≥0.50 D interformula discordance 7.29-fold unadjusted and 3.57-fold adjusted.

## Value Statement

### What Was Known

- IOL formula predictions can diverge in eyes with obvious axial-length or keratometric extremes.
- Multivariable approaches can classify biometric combinations or flag potentially suspect records, but age-calibrated linkage to routine interformula spread has not been established.

### What This Paper Adds

- A biometry-only model frozen before formula outcomes linked an age-conditioned relational percentile to same-power discordance; its association persisted beyond marginal extremeness and in patients assigned to the model's untouched test split.
- In a clinically focused post hoc conventional-AL/K subgroup, 31.8% at or above versus 4.4% below the 90th percentile reached 0.50 D (unadjusted risk ratio, 7.29); adjusted risks were 16.6% versus 4.6% (risk ratio, 3.57).
- The threshold flagged approximately 1 in 40 conventional-AL/K eyes; approximately 1 in 3 flagged eyes was discordant, but 15.9% sensitivity precludes rule-out use.
- A 3-step triggered review checks scan and biometry quality, verifies IOL model/power/constants/inputs, then compares same-power predictions and documents the formula rationale.
- The score identifies relational atypicality; it neither identifies the erroneous input, selects a formula, nor substitutes for postoperative error.

## Data Availability

Deidentified derived data may be available to qualified investigators subject to institutional approval and applicable ethics and data-use restrictions. The private linkage map and source clinical images will not be publicly released.

## Code Availability

Calculator and model source code for V3.2.1 are available at https://github.com/peopleatkorea-droid/IOLmaster_conversion/releases/tag/biometry-ood-v3.2.1. The frozen release is archived at Zenodo (https://doi.org/10.5281/zenodo.21942146), and the source tag resolves to commit `7a008555348f76697e93c9ad31da3046108dc69a`. As accessed August 15, 2026, the stable calculator at https://k-era.org/tools/biometry-ood served release V3.2.1 with the `continuous-age-bilateral-v3.2.0` model, an immutable SHA-256 manifest, and synthetic educational demos only. Patient-level analytic data, linkage maps, and source images are not public.

## Disclosures Summary

Financial support: None. Conflicts of interest: The authors declare no conflicts of interest.

## Artificial Intelligence Use

During the preparation of this work, the authors used OpenAI Codex for exploratory data checking, statistical code review, language editing, figure preparation, and document formatting. The authors reviewed and verified all outputs, made all scientific and editorial decisions, and take full responsibility for the content of the publication.

## References

1. Melles RB, Holladay JT, Chang WJ. Accuracy of intraocular lens calculation formulas. *Ophthalmology*. 2018;125(2):169-178. doi:10.1016/j.ophtha.2017.08.027.
2. Darcy K, Gunn D, Tavassoli S, Sparrow J, Kane JX. Assessment of the accuracy of new and updated intraocular lens power calculation formulas in 10 930 eyes from the UK National Health Service. *J Cataract Refract Surg*. 2020;46(1):2-7. doi:10.1016/j.jcrs.2019.08.014.
3. Kim SY, Lee SH, Kim NR, Chin HS, Jung JW. Accuracy of intraocular lens power calculation formulas using a swept-source optical biometer. *PLoS One*. 2020;15(1):e0227638. doi:10.1371/journal.pone.0227638.
4. Jeong J, Song H, Lee JK, Chuck RS, Kwon JW. The effect of ocular biometric factors on the accuracy of various IOL power calculation formulas. *BMC Ophthalmol*. 2017;17(1):62. doi:10.1186/s12886-017-0454-y.
5. Oh R, Oh JY, Choi HJ, Kim MK, Yoon CH. Evaluation of prediction errors in nine intraocular lens calculation formulas using an explainable machine learning model. *BMC Ophthalmol*. 2024;24:531. doi:10.1186/s12886-024-03801-2.
6. Wendelstein JA, Reifeltshammer SA, Cooke DL, Hirnschall N, Hoffmann PC, Langenbucher A, Bolz M, Riaz KM. The 10,000 Eyes Study: analysis of keratometry, axial length, anterior chamber depth, lens thickness, and white-to-white diameter in 10,000 cataractous eyes. *Am J Ophthalmol*. 2023;245:44-60. doi:10.1016/j.ajo.2022.08.024.
7. Gao R, Zhang J, Han X, et al. Intraocular lens calculation formula selection for short eyes: based on axial length and anterior chamber depth. *BMC Ophthalmol*. 2025;25(1):21. doi:10.1186/s12886-024-03793-z.
8. Jimenez-Garcia M, Puzo M, Gimenez-Calvo G, Segura-Calvo FJ, Larrosa Poves JM, Castro-Alonso FJ; UFR-ARCCA Group Zaragoza. Segmentation of patients with cataract according to their ocular biometry: the LAKE classification. *J Cataract Refract Surg*. 2026;52(4):325-332. doi:10.1097/j.jcrs.0000000000001824.
9. Langenbucher A, Hoffmann P, Cayless A, Szentmary N, Riaz K, Gatinel D, Findl O, Priglinger S, Pantanelli S, Yeo TK, Savini G, Wendelstein J. Qualifying optical biometry data before cataract surgery using autoencoders. *Z Med Phys*. Published online January 28, 2026. doi:10.1016/j.zemedi.2026.01.004.
10. Ong K, Feng L. Prevalence of variation in predicted refraction between different intraocular lens formulae. *Asian J Ophthalmol*. 2018;16(2):60-61. doi:10.35119/asjoo.v16i2.389.
11. Chang P, Qian S, Wang Y, Li S, Yang F, Hu Y, Liu Z, Zhao YE. Accuracy of new-generation intraocular lens calculation formulas in eyes with variations in predicted refraction. *Graefes Arch Clin Exp Ophthalmol*. 2023;261(1):127-135. doi:10.1007/s00417-022-05748-w.
12. von Elm E, Altman DG, Egger M, Pocock SJ, Gotzsche PC, Vandenbroucke JP; STROBE Initiative. The Strengthening the Reporting of Observational Studies in Epidemiology (STROBE) statement. *PLoS Med*. 2007;4(10):e296. doi:10.1371/journal.pmed.0040296.
13. Abulafia A, Hill WE, Koch DD, Wang L, Barrett GD. Accuracy of the Barrett True-K formula for intraocular lens power prediction after laser in situ keratomileusis or photorefractive keratectomy for myopia. *J Cataract Refract Surg*. 2016;42(3):363-369. doi:10.1016/j.jcrs.2015.11.039.
14. Rousseeuw PJ, Van Driessen K. A fast algorithm for the minimum covariance determinant estimator. *Technometrics*. 1999;41(3):212-223. doi:10.1080/00401706.1999.10485670.
15. Koenker R, Bassett G Jr. Regression quantiles. *Econometrica*. 1978;46(1):33-50.
16. Sorkin N, Zadok R, Totah H, Savini G, Ribeiro F, Findl O, Buonsanti D, Raimundo M, Abulafia A. Analysis of the ESCRS calculator's prediction accuracy. *J Cataract Refract Surg*. 2024;50(11):1109-1116. doi:10.1097/j.jcrs.0000000000001512.
17. Sheard RM, Smith GT, Cooke DL. Improving the prediction accuracy of the SRK/T formula: the T2 formula. *J Cataract Refract Surg*. 2010;36(11):1829-1834. doi:10.1016/j.jcrs.2010.05.031.
18. Reitblat O, Levy A, Kleinmann G, Lerman TT, Assia EI. Intraocular lens power calculation for eyes with high and low average keratometry readings. *J Cataract Refract Surg*. 2017;43(9):1149-1156. doi:10.1016/j.jcrs.2017.06.036.
19. Figueiredo I, Machado I, Lobo C, Raimundo M. Spherical equivalent prediction analysis in intraocular lens power calculations using Barrett Universal II formula variations. *J Cataract Refract Surg*. 2026;52(3):231-237. doi:10.1097/j.jcrs.0000000000001804.
20. Voytsekhivskyy OV, Hoffer KJ, Cooke DL, Savini G. IOL Power Calculation Project: accuracy of 36 formulas. *Am J Ophthalmol*. 2025;277:45-56. doi:10.1016/j.ajo.2025.05.004.

## Tables

### Table 1. Primary cohort characteristics by Extended reference-model category

| Characteristic | Overall | <90th percentile | 90th to <97.5th | ≥97.5th |
|---|---:|---:|---:|---:|
| Eyes | 4,123 | 3,952 | 153 | 18 |
| Patients | 2,292 | 2,230 | 128 | 15 |
| Age, y | 71.2 [64.2, 77.6] | 71.1 [64.0, 77.6] | 72.4 [67.8, 80.0] | 75.1 [71.4, 78.0] |
| Axial length, mm | 23.75 [23.19, 24.38] | 23.74 [23.19, 24.34] | 24.65 [23.23, 25.87] | 26.37 [24.01, 27.04] |
| Mean K, D | 43.72 [42.81, 44.63] | 43.70 [42.81, 44.61] | 44.05 [42.89, 45.26] | 43.96 [43.32, 44.69] |
| ACD, mm | 3.10 [2.85, 3.35] | 3.10 [2.86, 3.35] | 3.04 [2.50, 3.40] | 3.12 [2.68, 3.37] |
| LT, mm | 4.55 [4.27, 4.83] | 4.54 [4.27, 4.82] | 4.77 [4.37, 5.10] | 4.96 [4.72, 5.19] |
| WTW, mm | 11.81 [11.55, 12.09] | 11.82 [11.56, 12.08] | 11.76 [11.36, 12.18] | 11.70 [11.36, 11.89] |
| CCT, mm | 0.540 [0.518, 0.563] | 0.539 [0.518, 0.562] | 0.549 [0.521, 0.592] | 0.555 [0.541, 0.592] |
| Anchor IOL power, D | 21.0 [19.5, 22.5] | 21.0 [19.5, 22.5] | 18.0 [14.0, 21.5] | 13.0 [10.2, 19.1] |
| Four-formula spread, D | 0.29 [0.20, 0.40] | 0.28 [0.19, 0.39] | 0.47 [0.34, 0.62] | 0.42 [0.32, 0.64] |
| Spread ≥0.50 D | 491 (11.9%) | 419 (10.6%) | 65 (42.5%) | 7 (38.9%) |
| Spread ≥0.75 D | 40 (1.0%) | 24 (0.6%) | 14 (9.2%) | 2 (11.1%) |

Values are median [interquartile range] unless stated otherwise. Patient counts across categories need not sum to the overall count because fellow eyes can occupy different categories. ACD = anterior chamber depth; CCT = central corneal thickness; K = keratometry; LT = lens thickness; WTW = white-to-white.

### Table 2. Primary clinical findings and anchor sensitivity

| Analysis | Eyes / patients | Adjusted effect per 10 percentile points, D (95% CI) | <90th: spread ≥0.50 D | ≥90th: spread ≥0.50 D | Unadjusted risk ratio (95% CI) | Adjusted marginal risk ratio (95% CI) |
|---|---:|---:|---:|---:|---:|---:|
| Full cohort, Extended | 4,123 / 2,292 | +0.0218 (+0.0192 to +0.0243) | 419/3,952 (10.6%) | 72/171 (42.1%) | 3.97 (3.14 to 4.91) | — |
| Conventional AL/K, primary Haigis anchor | 3,365 / 1,901 | +0.0216 (+0.0189 to +0.0243) | 143/3,280 (4.4%) | 27/85 (31.8%) | 7.29 (4.83 to 10.24) | 3.57 (1.87 to 6.09) |
| Conventional AL/K, paired Haigis anchor | 3,356 / 1,894 | +0.0218 (+0.0192 to +0.0245) | 143/3,274 (4.4%) | 24/82 (29.3%) | 6.70 (4.35 to 9.46) | — |
| Conventional AL/K, paired Barrett TK anchor | 3,356 / 1,894 | +0.0205 (+0.0180 to +0.0230) | 131/3,274 (4.0%) | 24/82 (29.3%) | 7.31 (4.74 to 10.35) | — |
| Conventional AL/K, Core sensitivity | 3,365 / 1,901 | +0.0288 (+0.0260 to +0.0317) | 136/3,269 (4.2%) | 34/96 (35.4%) | 8.51 (5.72 to 11.84) | — |

Unadjusted risk-ratio confidence intervals used 2,000 patient-cluster bootstrap samples. The adjusted threshold contrast used marginal standardization from a cluster-robust logistic model; adjusted risks were 4.6% below and 16.6% at or above the 90th percentile, with a risk difference of 12.0 percentage points (95% CI, 4.4-23.7). Separately, the adjusted continuous odds ratio was 1.71 per 10 percentile points (95% CI, 1.53-1.92). The primary threshold's flag rate was 2.5%, sensitivity 15.9%, specificity 98.2%, positive predictive value 31.8%, and negative predictive value 95.6%. Core was exploratory.

## Figure Legends

### Figure 1. Two-stage reference-model construction and formula-cohort assembly

Stage 1 used 12,615 biometry records representing 9,305 patient-eye pairs. Model-specific eligibility required complete inputs within the frozen ranges, including LT 2 to 8 mm and mean K 30 to 65 D, and the latest eligible acquisition per patient-eye. Patients were separated across model-development partitions, and formula outcomes were excluded. Stage 2 linked formula screens to biometry and retained 4,123 eyes with unique same-date linkage, a complete 4-formula panel at one IOL power, and an on-target Haigis anchor. The formula cohort is an outcome-independent internal evaluation, not external validation.

### Figure 2. Continuous and formula-pair relationships between joint biometry and interformula discordance

(A) In all 4,123 eyes, points show observed mean 4-formula spread with intercept-only patient-cluster-robust 95% CIs within cohort-wide percentile deciles; the line and band show covariate-standardized adjusted mean spread and its patient-cluster-robust 95% CI. (B) In 3,365 conventional-AL/K eyes, points show observed decile risks with Wilson 95% CIs; the line and band show standardized adjusted risk from the continuous logistic model with delta-method patient-cluster-robust 95% CIs. Vertical lines mark the 90th and 97.5th percentiles. The separate observed categorical contrast was 4.4% below versus 31.8% at or above the 90th percentile. (C) In all 4,123 eyes, points show adjusted change in each absolute pairwise formula gap per 10 percentile points with patient-cluster-robust 95% CIs. Panel C adjusted for age, anchor power, IOL model, acquisition year, and absolute age-adjusted marginal z scores of AL, K, ACD, LT, WTW, and CCT. Pairwise decomposition was exploratory and does not identify accuracy. Conventional AL/K = AL 22 to <26 mm and mean K 42 to <46 D.

## Supplemental Tables

Supplemental Tables S1-S3 describe outcomes, cohort assembly, and the frozen design; S5-S8 and S10-S12 report robustness or internal validation. S4, S9, S11, S13, and S14 include exploratory or post hoc analyses. Continuous spread was the primary outcome, spread ≥0.75 D was prespecified secondary, and the conventional-AL/K 0.50-D contrast was post hoc.

**Supplemental Methods: source-screen audit.** Before postoperative outcomes were entered, a resident reviewed 500 eyes: all 34 Rare and 113 Uncommon eyes plus a SHA-256-seeded random sample of 353 Typical eyes from 2,500 recent eligible eyes. OOD category and percentile were concealed and review order was randomized. Prespecified biometry fields and the formula name, IOL model, IOL power, and predicted refraction were compared directly with the original IOLMaster reports. Eye-level complete exact agreement required every audited field to match; agreement was 500/500 (100.0%; exact 95% CI, 99.3%-100.0%), with no adjudication required. This audit evaluated extraction fidelity, not postoperative accuracy.

### Supplemental Table S1. Formula-spread thresholds in the primary cohort

| Threshold, D | Eyes | Percent | Wilson 95% CI, % |
|---:|---:|---:|---:|
| 0.25 | 2,520 | 61.1 | 59.6-62.6 |
| 0.50 | 491 | 11.9 | 11.0-12.9 |
| 0.75 | 40 | 1.0 | 0.7-1.3 |
| 1.00 | 2 | 0.05 | 0.0-0.2 |

### Supplemental Table S2. Mutually exclusive reasons for exclusion from the linked primary cohort

| Reason | Eyes | Patients | Mean AL, mm | Mean Extended percentile |
|---|---:|---:|---:|---:|
| Included primary | 4,123 | 2,292 | 23.87 | 43.7 |
| Nonunique same-date linkage | 1,011 | 576 | 24.19 | 51.6 |
| Incomplete 4-formula panel | 1,198 | 865 | 24.67 | 55.9 |
| Haigis target window not met | 95 | 58 | 26.35 | 54.4 |
| Reference or marginal score unavailable | 22 | 20 | 24.14 | NA |
| Not Extended score tier | 2 | 2 | 26.96 | 23.0 |

### Supplemental Table S3. Frozen reference-model design and reconstructed eligibility

| Model | Inputs | Source records | Eligible eyes / patients | Derivation | Tuning | Calibration | Technical test | Age-local bandwidth |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Extended | AL, K, ACD, LT, WTW, CCT | 12,615 | 8,164 / 4,498 | 4,511 / 2,487 | 1,133 / 628 | 1,245 / 681 | 1,275 / 702 | 4 y |
| Core | AL, K, ACD, LT | 12,615 | 8,177 / 4,501 | 4,518 / 2,490 | 1,133 / 628 | 1,246 / 681 | 1,280 / 702 | 8 y |

Eligibility used age 2 to 100 years; AL 14 to 38 mm; mean K 30 to 65 D; ACD 0.8 to 6.0 mm; LT 2 to 8 mm; WTW 8 to 16 mm; and CCT 0.35 to 0.80 mm. The latest eligible acquisition per patient-eye was retained, with the first source row retained for equal-date ties.

### Supplemental Table S4. Exploratory frozen Core-score sensitivity

| Cohort | Core group | Eyes | Spread ≥0.50 D | Median spread, D | Adjusted effect per 10 percentiles, D | Incremental R2 |
|---|---|---:|---:|---:|---:|---:|
| Full cohort | <90th | 3,923 | 399 (10.2%) | 0.28 | +0.0283 (0.0256-0.0311) | 0.087 |
| Full cohort | ≥90th | 200 | 92 (46.0%) | 0.49 | +0.0283 (0.0256-0.0311) | 0.087 |
| Conventional AL/K | <90th | 3,269 | 136 (4.2%) | 0.25 | +0.0288 (0.0260-0.0317) | 0.135 |
| Conventional AL/K | ≥90th | 96 | 34 (35.4%) | 0.44 | +0.0288 (0.0260-0.0317) | 0.135 |

Core used AL, K, ACD, and LT. Its tier-matched equal-review-burden comparison appears in Supplemental Table S11.

### Supplemental Table S5. Upstream formula-source robustness under alternate duplicate and quality rules

| Rule | Eyes | Median spread, D | Spread ≥0.50 D | Spread ≥0.75 D |
|---|---:|---:|---:|---:|
| Highest-confidence duplicate | 5,062 | 0.29 | 631 (12.47%) | 66 (1.30%) |
| First-page duplicate | 5,062 | 0.29 | 630 (12.45%) | 66 (1.30%) |
| Last-page duplicate | 5,062 | 0.29 | 631 (12.47%) | 66 (1.30%) |
| Median duplicate prediction | 5,062 | 0.29 | 630 (12.45%) | 66 (1.30%) |
| Confidence ≥0.95 and no source conflict | 4,839 | 0.29 | 593 (12.25%) | 60 (1.24%) |
| Strict clean plus major block QC | 4,837 | 0.29 | 591 (12.22%) | 59 (1.22%) |

These are source-level formula-panel analyses before biometry linkage and do not replace a source-clean sensitivity in the final 4,123-eye cohort.

### Supplemental Table S6. Upstream paired Haigis-versus-Barrett anchor robustness

| Endpoint | Haigis events | Barrett events | Classification agreement | Patient-cluster paired P |
|---|---:|---:|---:|---:|
| Spread ≥0.50 D | 610 | 605 | 98.95% | .590 |
| Spread ≥0.75 D | 59 | 52 | 99.70% | .118 |

Among 5,031 paired source-level eyes, the same power was selected in 56.0%. Mean Barrett-minus-Haigis spread was -0.0008 D (patient-cluster bootstrap 95% CI, -0.0013 to -0.0003 D).

### Supplemental Table S7. Frozen-percentile sensitivity to representative-record selection

| Selection rule | Eyes | Different source record vs frozen | Eyes ≥90th | Flag movement vs frozen | Median percentile |
|---|---:|---:|---:|---:|---:|
| Latest eligible (frozen) | 8,164 | 0 | 631 | 0 | 46.55 |
| Earliest eligible | 8,164 | 734 | 622 | 25 (0.31%) | 46.34 |
| Lowest AL SD | 8,164 | 942 | 625 | 36 (0.44%) | 46.60 |

Among the 8,164 eligible patient-eyes, 1,715 had more than 1 eligible record. The frozen latest-eligible rule retained the first source row for equal-date ties. Percentiles were recalculated with the unchanged frozen model; the model was not retrained.

### Supplemental Table S8. Linked-cohort acquisition-year sensitivity

| Outcome | Categorical-year joint P | Linear year estimate | 95% CI | P |
|---|---:|---:|---:|---:|
| Continuous spread | .389 | -0.0012 D/y | -0.0046 to +0.0022 | .484 |
| Spread ≥0.50 D | .307 | OR 0.893/y | 0.786-1.015 | .083 |

Models used all 4,123 linked primary eyes, adjusted for the primary covariates and Extended percentile, and used patient-cluster covariance.

### Supplemental Table S9. Biometric-range sensitivities of the Extended-percentile association

**A. Axial-length heterogeneity**

| AL stratum | Eyes / patients | Adjusted effect per 10 percentiles, D | 95% CI | P | Extended percentile, median [IQR] | Spread ≥0.50 D | Spread ≥0.75 D |
|---|---:|---:|---:|---:|---:|---:|---:|
| <22 mm | 70 / 43 | +0.0255 | -0.0102 to +0.0613 | .157 | 76.3 [67.8, 83.6] | 31 (44.3%) | 7 (10.0%) |
| 22 to <26 mm | 3,874 / 2,154 | +0.0230 | +0.0205 to +0.0256 | <.001 | 40.9 [19.3, 63.9] | 409 (10.6%) | 31 (0.8%) |
| ≥26 mm | 179 / 123 | -0.0045 | -0.0103 to +0.0013 | .129 | 67.8 [34.1, 91.1] | 51 (28.5%) | 2 (1.1%) |

Effects are adjusted changes in continuous spread per 10-point increase in the Extended percentile. The AL-by-percentile interaction was significant (raw P<.001; Benjamini-Hochberg FDR-adjusted P<.001). The short-eye stratum had restricted percentile exposure; the long-eye estimate indicates that no positive association was detected, not proof of biological absence.

**B. Published LAKE NNN component-range restriction**

| Eyes / patients | Adjusted effect per 10 percentiles, D | 95% CI | P | Spearman rho (cluster-bootstrap 95% CI) | ≥90th percentile | Spread ≥0.50 D among ≥90th |
|---:|---:|---:|---:|---:|---:|---:|
| 1,871 / 1,152 | +0.0252 | +0.0216 to +0.0287 | <.001 | .314 (.265-.361) | 18 (1.0%) | 0/18 (0.0%) |

The published component ranges were 22.13≤AL<24.84 mm, 2.64≤ACD<3.43 mm, and 42.50≤mean K<45.60 D. Unadjusted through fully adjusted continuous slopes were positive (+0.0121 to +0.0264 D per 10 percentiles). A quadratic term suggested mild concavity (P=.033); the highest percentile among the 19 eyes with spread ≥0.50 D was 88.9. Because the binary model had only 19 events for 15 parameters, its adjusted odds ratio is not reported. This restriction applies published NNN component boundaries and is not a claim of independently reproducing the full 27-group framework.

### Supplemental Table S10. Untouched technical-test tail calibration

**A. Overall calibration**

| Score | Threshold | Test eyes | Flagged eyes | Observed percent | Nominal percent | Patient-cluster bootstrap 95% CI, % |
|---|---:|---:|---:|---:|---:|---:|
| Extended | ≥90th | 1,275 | 101 | 7.92 | 10.0 | 6.20-9.81 |
| Extended | ≥97.5th | 1,275 | 23 | 1.80 | 2.5 | 1.01-2.76 |
| Core | ≥90th | 1,280 | 122 | 9.53 | 10.0 | 7.66-11.54 |
| Core | ≥97.5th | 1,280 | 29 | 2.27 | 2.5 | 1.30-3.40 |

The Extended upper tail was modestly conservative in the internal untouched test set; the Core proportions were near nominal. These results assess internal calibration, not external transportability.

**B. Extended calibration by recorded sex**

| Recorded sex | Test eyes / patients | Median percentile | ≥90th, n (%) | Cluster-bootstrap 95% CI, % | ≥97.5th, n (%) | Cluster-bootstrap 95% CI, % |
|---|---:|---:|---:|---:|---:|---:|
| Female | 668 / 364 | 46.7 | 55 (8.23) | 5.78-10.85 | 16 (2.40) | 1.05-3.92 |
| Male | 607 / 338 | 50.1 | 46 (7.58) | 5.13-10.30 | 7 (1.15) | 0.17-2.30 |

Female-minus-male differences were -3.37 percentile points for the median (cluster-bootstrap 95% CI, -10.19 to +4.34), +0.66 percentage points for the ≥90th rate (95% CI, -3.07 to +4.12), and +1.24 points for the ≥97.5th rate (95% CI, -0.49 to +3.07). Recorded sex was not used to fit or calibrate the score; these are internal QA estimates, not external fairness validation.

### Supplemental Table S11. Equal-review-burden comparison with the largest marginal |z|

| Score and flag | Inputs for marginal comparator | Flagged eyes | Events | Positive predictive value | Sensitivity | Specificity |
|---|---|---:|---:|---:|---:|---:|
| Extended percentile ≥90th | AL, K, ACD, LT, WTW, CCT | 85 | 27 | 31.8% | 15.9% | 98.2% |
| Top 6-variable max-z | AL, K, ACD, LT, WTW, CCT | 85 | 20 | 23.5% | 11.8% | 98.0% |
| Core percentile ≥90th | AL, K, ACD, LT | 96 | 34 | 35.4% | 20.0% | 98.1% |
| Top 4-variable max-z | AL, K, ACD, LT | 96 | 22 | 22.9% | 12.9% | 97.7% |

Comparisons used the same conventional-AL/K cohort and matched the number of eyes flagged. For Extended, the positive-predictive-value difference was 8.2 percentage points (patient-cluster bootstrap 95% CI, -1.9 to 18.5; paired cluster-permutation P=.184). For Core, the difference was 12.5 points (95% CI, 3.0-21.9; P=.020). These comparisons were exploratory and post hoc.

### Supplemental Table S12. Formula association by frozen reference-model patient split

| Reference-model split | Eyes / patients | Adjusted effect per 10 percentiles, D | 95% CI | Conventional AL/K eyes / patients | Conventional AL/K effect, D | 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| Derivation | 2,279 / 1,269 | +0.0219 | +0.0187 to +0.0251 | 1,855 / 1,047 | +0.0222 | +0.0188 to +0.0257 |
| Tuning | 569 / 318 | +0.0224 | +0.0163 to +0.0285 | 480 / 273 | +0.0230 | +0.0169 to +0.0290 |
| Calibration | 629 / 348 | +0.0247 | +0.0175 to +0.0320 | 515 / 290 | +0.0213 | +0.0133 to +0.0294 |
| Untouched test | 646 / 357 | +0.0190 | +0.0126 to +0.0253 | 515 / 291 | +0.0178 | +0.0107 to +0.0249 |

The formula cohort was not an external cohort. The final row restricts the association analysis to patients not used to derive, tune, or calibrate the frozen reference model.

### Supplemental Table S13. Leave-one-formula-out association in conventional-AL/K eyes

| Formula panel | Adjusted effect per 10 percentiles, D | 95% CI | P | <90th events / eyes | ≥90th events / eyes |
|---|---:|---:|---:|---:|---:|
| All 4 formulas | +0.0216 | +0.0189 to +0.0243 | <.001 | 143/3,280 | 27/85 |
| Omit Hoffer Q | +0.0180 | +0.0154 to +0.0206 | <.001 | 38/3,280 | 11/85 |
| Omit SRK/T | +0.0140 | +0.0112 to +0.0169 | <.001 | 73/3,280 | 13/85 |
| Omit Haigis | +0.0274 | +0.0242 to +0.0305 | <.001 | 121/3,280 | 23/85 |
| Omit Barrett Universal II TK | +0.0141 | +0.0114 to +0.0168 | <.001 | 82/3,280 | 15/85 |

Each reduced panel used the maximum minus minimum prediction among the remaining 3 formulas at the same IOL model and power. Persistence after omitting Barrett Universal II TK argues against the association being solely attributable to mixing total-keratometry and standard-keratometry formulas.

### Supplemental Table S14. Post hoc age-conditioning design ablation

**A. Untouched technical-test calibration (1,275 eyes)**

| Score | Age-percentile Spearman rho (P) | Overall ≥90th | Age-band ≥90th range | Overall ≥97.5th |
|---|---:|---:|---:|---:|
| Age-agnostic global | -0.346 (<.001) | 10.98% | 3.70%-28.42% | 2.20% |
| Age-adjusted mean only | -0.104 (<.001) | 8.94% | 3.99%-32.50% | 2.20% |
| Full age-conditioned | 0.016 (.580) | 7.92% | 5.65%-11.48% | 1.80% |

**B. Conventional-AL/K formula-discordance analyses (3,365 eyes; 170 events)**

| Score | Incremental R2 | 10-fold CV RMSE, D | Events among top 85 | PPV | Sensitivity | Score-by-age P |
|---|---:|---:|---:|---:|---:|---:|
| Age-agnostic global | .101 | .0898 | 34 | 40.0% | 20.0% | .170 |
| Age-adjusted mean only | .061 | .0933 | 27 | 31.8% | 15.9% | .077 |
| Full age-conditioned | .078 | .0918 | 27 | 31.8% | 15.9% | .546 |

All 3 scores used the same patient split and biometric inputs. Formula models used flexible nonlinear age adjustment. At the equal 2.5% review burden, full-minus-global differences were -8.1 percentage points for PPV (patient-cluster bootstrap 95% CI, -17.6 to +1.2) and -4.0 points for sensitivity (95% CI, -8.6 to +0.6). The full-score-by-age interaction remained nonsignificant when restricted to ages 50-89 years (P=.390). These post hoc comparisons show an age-calibration–enrichment trade-off, not predictive superiority of age conditioning.

**C. Recorded-sex sensitivity of the Extended association**

| Formula population | Complete-case eyes / patients | No-sex effect per 10 percentiles, D | Sex-adjusted effect, D | Male / female slopes, D | Continuous score×female effect, D (95% CI) | Raw / FDR P | ≥0.50-D interaction OR ratio (FDR P) |
|---|---:|---:|---:|---:|---:|---:|---:|
| All formula eyes | 4,121 / 2,291 | +0.0217 | +0.0217 | +0.0196 / +0.0235 | +0.0040 (+0.0012 to +0.0068) | .005 / .011 | 1.11 (.106) |
| Conventional AL/K | 3,363 / 1,900 | +0.0215 | +0.0214 | +0.0185 / +0.0238 | +0.0052 (+0.0023 to +0.0082) | <.001 / .002 | 1.00 (.998) |

Sex adjustment minimally changed the score effect. The continuous interaction was small and both sex-specific slopes remained positive; no interaction was detected for spread ≥0.50 D. Two eyes recorded as Other were excluded from sex-specific models; no formula-cohort eyes had unresolved sex after protected linkage. These analyses were post hoc and do not justify sex-specific recalibration.

### Supplemental Figure S1. Age-specific tail calibration in the untouched technical-test set

Panel A shows the proportion at or above the 90th percentile; Panel B shows the proportion at or above the 97.5th percentile. Lines are descriptive Gaussian-kernel-smoothed rates across age. Points show estimates in prespecified age bands (2-9, 10-19, 20-39, 40-59, 60-74, 75-89, and ≥90 years), with patient-cluster bootstrap 95% CIs; horizontal dash-dot lines mark nominal rates. Wide intervals at age extremes reflect sparse data. Calibration was internal and does not establish external transportability.
