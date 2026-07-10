#!/usr/bin/env python3
"""Train age-stratified Core and Extended biometry OOD models."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

try:
    from modeling.train_ood_model import (
        finite_float,
        huber_quadratic_regression,
        huber_robust_covariance,
        mahalanobis_distance,
        parse_date,
        quantile,
        read_xlsx_rows,
        sha256_file,
    )
except ModuleNotFoundError:
    from train_ood_model import (
        finite_float,
        huber_quadratic_regression,
        huber_robust_covariance,
        mahalanobis_distance,
        parse_date,
        quantile,
        read_xlsx_rows,
        sha256_file,
    )


KERATOMETRIC_CONSTANT = 337.5
BUNDLE_VERSION = "age-stratified-v2.0.0"
TIERS = {
    "Core": ["AL", "Mean_K", "ACD", "LT"],
    "Extended": ["AL", "Mean_K", "ACD", "LT", "WTW", "CCT"],
}
COMMON_RANGES = {
    "Mean_K": (30.0, 65.0),
    "ACD": (0.8, 6.0),
    "LT": (2.0, 8.0),
    "WTW": (8.0, 16.0),
    "CCT": (0.35, 0.8),
}
STRATA = [
    {
        "key": "pediatric",
        "label": "Pediatric",
        "display_age_range": "2-17 years",
        "age_min": 2.0,
        "age_max_exclusive": 18.0,
        "al_range": (14.0, 38.0),
        "age_adjusted": ["AL", "Mean_K", "ACD", "LT", "WTW", "CCT"],
        "cohort_status": "Provisional pediatric biometry reference; indication not verified by EMR.",
    },
    {
        "key": "young_adult",
        "label": "Young adult",
        "display_age_range": "18-39 years",
        "age_min": 18.0,
        "age_max_exclusive": 40.0,
        "al_range": (14.0, 38.0),
        "age_adjusted": ["ACD", "LT"],
        "cohort_status": "Provisional young-adult biometry reference; referral enrichment is possible.",
    },
    {
        "key": "adult",
        "label": "Adult cataract-age",
        "display_age_range": "40-100 years",
        "age_min": 40.0,
        "age_max_exclusive": 101.0,
        "al_range": (18.0, 38.0),
        "age_adjusted": ["ACD", "LT"],
        "cohort_status": "Primary adult institutional biometry reference.",
    },
]


def input_ranges_for(stratum):
    return {"AL": stratum["al_range"], **COMMON_RANGES}


def prepare_reference_rows(source_path, stratum, required_inputs):
    counts = {
        "source_rows": 0,
        "age_eligible_rows": 0,
        "excluded_test_or_demo": 0,
        "excluded_missing_or_invalid": 0,
        "excluded_input_range": 0,
        "superseded_repeat_exam": 0,
    }
    latest = {}
    anonymous_index = 0
    ranges = input_ranges_for(stratum)

    for row in read_xlsx_rows(source_path):
        counts["source_rows"] += 1
        patient_id = str(row.get("Pat_ID") or "").strip()
        if patient_id.lower() in {"test", "demo", "sample"}:
            counts["excluded_test_or_demo"] += 1
            continue
        acquisition = parse_date(row.get("Acquisition_Date"))
        dob = parse_date(row.get("DOB"))
        if acquisition is None or dob is None or acquisition < dob:
            counts["excluded_missing_or_invalid"] += 1
            continue
        age = (acquisition - dob).days / 365.2425
        if not stratum["age_min"] <= age < stratum["age_max_exclusive"]:
            continue
        counts["age_eligible_rows"] += 1

        al = finite_float(row.get("AL"))
        r1 = finite_float(row.get("R1"))
        r2 = finite_float(row.get("R2"))
        values = {
            "AL": al,
            "ACD": finite_float(row.get("ACD")),
            "LT": finite_float(row.get("LT")),
            "WTW": finite_float(row.get("W2W")),
            "CCT": finite_float(row.get("CCT")),
        }
        if r1 is None or r2 is None or r1 <= 0 or r2 <= 0:
            values["Mean_K"] = None
        else:
            values["Mean_K"] = ((KERATOMETRIC_CONSTANT / r1) + (KERATOMETRIC_CONSTANT / r2)) / 2.0
        if any(values[name] is None for name in required_inputs):
            counts["excluded_missing_or_invalid"] += 1
            continue
        if any(not ranges[name][0] <= values[name] <= ranges[name][1] for name in required_inputs):
            counts["excluded_input_range"] += 1
            continue

        eye_side = str(row.get("Eye_Side") or "").strip().upper()
        if patient_id:
            key = (patient_id, eye_side)
        else:
            anonymous_index += 1
            key = (f"ANONYMOUS-{anonymous_index}", eye_side)
        record = {"age": age, "acquisition": acquisition, **values}
        if key in latest:
            counts["superseded_repeat_exam"] += 1
        if key not in latest or acquisition > latest[key]["acquisition"]:
            latest[key] = record
    counts["reference_patient_ids"] = len({key[0] for key in latest})
    return list(latest.values()), counts


def transformed_feature_label(name, age_adjusted):
    display = {"Mean_K": "Mean K", "WTW": "WTW", "CCT": "CCT"}.get(name, name)
    return f"{display} vs age" if name in age_adjusted else display


def train_model(source_path, stratum, tier):
    inputs = TIERS[tier]
    reference, counts = prepare_reference_rows(source_path, stratum, inputs)
    minimum = 100 if tier == "Core" else 150
    if len(reference) < minimum:
        raise ValueError(f"{stratum['key']} {tier} cohort is too small: {len(reference)}")

    ages = [row["age"] for row in reference]
    age_center = statistics.median(ages)
    age_scale = 10.0
    adjusted = [name for name in inputs if name in stratum["age_adjusted"]]
    age_adjustment = {}
    for name in adjusted:
        coefficients = huber_quadratic_regression(
            ages,
            [row[name] for row in reference],
            age_center=age_center,
            age_scale=age_scale,
        )
        age_adjustment[name] = {"coefficients": coefficients}

    features = []
    for row in reference:
        t = (row["age"] - age_center) / age_scale
        vector = []
        for name in inputs:
            value = row[name]
            if name in age_adjustment:
                coefficients = age_adjustment[name]["coefficients"]
                expected = coefficients[0] + coefficients[1] * t + coefficients[2] * t * t
                value -= expected
            vector.append(value)
        features.append(vector)

    location, covariance, precision = huber_robust_covariance(features)
    distances = sorted(mahalanobis_distance(row, location, precision) for row in features)
    standard_deviations = [math.sqrt(covariance[i][i]) for i in range(len(covariance))]
    model_version = f"{stratum['key']}-{tier.lower()}-v2.0.0"
    ranges = input_ranges_for(stratum)
    return {
        "schema_version": 2,
        "model_name": f"Biometry OOD {stratum['label']} {tier}",
        "model_key": f"{stratum['key']}_{tier.lower()}",
        "model_version": model_version,
        "stratum_key": stratum["key"],
        "stratum_label": stratum["label"],
        "display_age_range": stratum["display_age_range"],
        "age_min_inclusive": stratum["age_min"],
        "age_max_exclusive": stratum["age_max_exclusive"],
        "cohort_status": stratum["cohort_status"],
        "tier": tier,
        "inputs": inputs,
        "input_ranges": {name: list(ranges[name]) for name in inputs},
        "age_adjustment": {
            "method": "Huber quadratic regression",
            "age_center_years": age_center,
            "age_scale_years": age_scale,
            "features": age_adjustment,
        },
        "feature_labels": [transformed_feature_label(name, adjusted) for name in inputs],
        "covariance_method": "Multivariate Huber M-estimator; tuning distance 3.338",
        "robust_location": location,
        "robust_covariance": covariance,
        "precision_matrix": precision,
        "feature_standard_deviations": standard_deviations,
        "reference_distances": distances,
        "reference_rows": len(reference),
        "reference_patients": counts["reference_patient_ids"],
        "training_filter_counts": counts,
        "score_thresholds_percentile": {"score_0_upper": 90.0, "score_1_upper": 97.5},
        "distance_thresholds": {"p90": quantile(distances, 0.90), "p97_5": quantile(distances, 0.975)},
    }


def train_bundle(source_path, output_path, report_path):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    models = []
    for stratum in STRATA:
        for tier in ("Core", "Extended"):
            models.append(train_model(source_path, stratum, tier))
    bundle = {
        "schema_version": 2,
        "bundle_version": BUNDLE_VERSION,
        "trained_at_utc": now,
        "intended_use": "Research-use age-stratified anatomical OOD screening; not a refractive prediction model.",
        "selection_rule": "Select age stratum; use Extended when both WTW and CCT are valid, otherwise Core.",
        "source": {
            "filename": Path(source_path).name,
            "sha256": sha256_file(source_path),
            "worksheet": "Corrected_All_Eyes",
        },
        "models": models,
    }
    report = {
        "bundle_version": BUNDLE_VERSION,
        "trained_at_utc": now,
        "source": bundle["source"],
        "models": [
            {
                "model_key": model["model_key"],
                "model_version": model["model_version"],
                "age_range": model["display_age_range"],
                "tier": model["tier"],
                "inputs": model["inputs"],
                "reference_rows": model["reference_rows"],
                "reference_patients": model["reference_patients"],
                "cohort_status": model["cohort_status"],
                "filter_counts": model["training_filter_counts"],
                "distance_thresholds": model["distance_thresholds"],
            }
            for model in models
        ],
        "limitations": [
            "Pediatric and young-adult surgical indication is not available in the source workbook.",
            "Both eyes may contribute; reference-eye counts are not independent patient counts.",
            "Core and Extended percentiles are separately calibrated and should not be numerically pooled.",
            "External and postoperative outcome validation are required before clinical decision-support use.",
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_xlsx", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/biometry_ood_age_stratified_v2.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/biometry_ood_age_stratified_v2_validation.json"),
    )
    args = parser.parse_args()
    bundle = train_bundle(args.source_xlsx, args.output, args.report)
    print(f"Trained {bundle['bundle_version']} with {len(bundle['models'])} models")
    for model in bundle["models"]:
        print(f"  {model['model_key']}: {model['reference_rows']} eyes")


if __name__ == "__main__":
    main()
