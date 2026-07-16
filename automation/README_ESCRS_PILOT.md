# ESCRS formula-spread pilot automation

This research helper prepares a fully anonymized biometry queue and, only after
one-time UI verification, operates the public ESCRS calculator slowly in a
visible browser.

It does not call or inspect private endpoints. It does not send patient names,
medical-record numbers, dates of birth, acquisition dates, or the source eye.
Every eye receives a local HMAC identifier such as `ESCRS-12AB34CD56EF`.

## Prespecified research convention

- IOL: J&J TECNIS 1-Piece ZCB00
- Target refraction: `-0.25 D`
- Primary anchor: Barrett Universal II
- Eligible anchor: Barrett predicted refraction between `-0.50 D` and `0.00 D`
- Tie-break: closest to `-0.25 D`, then the slightly more myopic prediction
- Formula spread: maximum minus minimum predicted refraction at the exact same
  Barrett-anchored ZCB00 power
- Minimum formula count for a spread: 3
- ZCB00 supported power range: `+5.0 D` to `+34.0 D`

The result is a standardized preoperative formula-disagreement endpoint. It is
not postoperative prediction error. Postoperative PE still requires the actual
implanted IOL model/power and postoperative manifest refraction.

## Install

Use a dedicated virtual environment.

```powershell
py -3.11 -m venv .venv-escrs
.\.venv-escrs\Scripts\python.exe -m pip install -r requirements-escrs-automation.txt
```

The default browser channel is the installed Microsoft Edge, so downloading a
separate automated browser is not required.

## 1. Prepare a 10-eye queue

```powershell
.\.venv-escrs\Scripts\python.exe -m automation.escrs_formula_pilot prepare `
  --input Extreme_ALK_only_postop_collection_1319eyes_simplified.xlsx `
  --limit 10
```

Gender is joined locally from `IOLMaster700_corrected_3.xlsx` using patient ID,
acquisition date, and eye. Those linkage fields never enter the generated queue.
If the same eye has multiple measurements, the lowest valid `AL_SD` is selected.
When the workbook contains multiple cohorts, the technical pilot balances the
cohorts first and then samples across the AL range within each cohort.

Generated files are written below `analysis_outputs/escrs/`, and the private HMAC
key is written below `.escrs_private/`. Both locations are ignored by Git.

## 2. Inspect the public UI without entering data

```powershell
.\.venv-escrs\Scripts\python.exe -m automation.escrs_formula_pilot inspect-ui `
  --profile automation/escrs_ui_profile.example.json `
  --keep-open
```

This saves a visible-control manifest and screenshot without entering biometry.
Copy the example profile to `automation/escrs_ui_profile.json`, update selectors
from the manifest, verify result parsing against one manual test calculation,
and only then change `"verified"` to `true`.

## 3. Run the visible 10-eye pilot

```powershell
.\.venv-escrs\Scripts\python.exe -m automation.escrs_formula_pilot run `
  --profile automation/escrs_ui_profile.json `
  --limit 10 `
  --allow-unverified-history `
  --confirm-live I_UNDERSTAND_ESCRS_UI_AUTOMATION
```

`--allow-unverified-history` is intentionally explicit. The biometry export does
not establish prior LASIK/PRK/RK status; such eyes must later be identified and
excluded from the routine-formula cohort.

## Enforced traffic safeguards

- one visible browser and one case at a time
- randomized 45–75 second minimum interval
- 100 cases per local calendar day
- 10-minute pause after every 25 cases
- immediate stop on HTTP 403/429, CAPTCHA, access-denied, or unusual-traffic text
- checkpoint and screenshot/text snapshot after every completed case
- no proxy rotation, CAPTCHA bypass, multi-session execution, or hidden API use
- partial/unexpected formula output stops the run by default

The first live run should remain limited to 10 eyes and be compared with a
manual ESCRS calculation before any larger batch is authorized.

## 4. Export the checkpoint

An anonymized CSV can be generated without touching the source workbook.

```powershell
.\.venv-escrs\Scripts\python.exe -m automation.escrs_formula_pilot export
```

To also write the results into a new local workbook copy:

```powershell
.\.venv-escrs\Scripts\python.exe -m automation.escrs_formula_pilot export `
  --source-workbook Extreme_biometry_postop_collection_1805extreme_600controls_simplified.xlsx `
  --sheet Study_Cases `
  --output-workbook analysis_outputs\escrs\Study_Cases_with_ESCRS_results.xlsx
```

The command refuses to overwrite the source workbook.
