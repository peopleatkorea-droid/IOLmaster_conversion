#!/usr/bin/env python3
"""Train bilateral, patient-split, continuously age-adjusted biometry OOD models."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn
from sklearn.covariance import MinCovDet

try:
    from modeling import train_continuous_ood_v3 as v3
    from modeling.train_ood_model import finite_float, parse_date, quantile, read_xlsx_rows, sha256_file
except ModuleNotFoundError:
    import train_continuous_ood_v3 as v3
    from train_ood_model import finite_float, parse_date, quantile, read_xlsx_rows, sha256_file


BUNDLE_VERSION = "continuous-age-bilateral-v3.1.0"
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20260711


def prepare_bilateral_records(source_path, required_inputs):
    counts = {
        "source_rows": 0,
        "excluded_test_or_demo": 0,
        "excluded_missing_or_invalid_date": 0,
        "excluded_age": 0,
        "excluded_missing_input": 0,
        "excluded_input_range": 0,
        "superseded_repeat_exam": 0,
    }
    latest_by_eye = {}
    anonymous_index = 0

    for row in read_xlsx_rows(source_path):
        counts["source_rows"] += 1
        patient_id = str(row.get("Pat_ID") or "").strip()
        if patient_id.lower() in {"test", "demo", "sample"}:
            counts["excluded_test_or_demo"] += 1
            continue
        acquisition = parse_date(row.get("Acquisition_Date"))
        dob = parse_date(row.get("DOB"))
        if acquisition is None or dob is None or acquisition < dob:
            counts["excluded_missing_or_invalid_date"] += 1
            continue
        age = (acquisition - dob).days / 365.2425
        if not v3.AGE_MIN <= age < v3.AGE_MAX_EXCLUSIVE:
            counts["excluded_age"] += 1
            continue
        values = v3.values_from_row(row)
        if any(values[name] is None for name in required_inputs):
            counts["excluded_missing_input"] += 1
            continue
        if any(
            not v3.INPUT_RANGES[name][0] <= values[name] <= v3.INPUT_RANGES[name][1]
            for name in required_inputs
        ):
            counts["excluded_input_range"] += 1
            continue

        eye_side = str(row.get("Eye_Side") or "").strip().upper() or "UNKNOWN"
        if not patient_id:
            anonymous_index += 1
            patient_id = f"ANONYMOUS-{anonymous_index}"
        key = (patient_id, eye_side)
        record = {
            "patient_id": patient_id,
            "eye_side": eye_side,
            "age": age,
            "acquisition": acquisition,
            **values,
        }
        if key in latest_by_eye:
            counts["superseded_repeat_exam"] += 1
        if key not in latest_by_eye or acquisition > latest_by_eye[key]["acquisition"]:
            latest_by_eye[key] = record

    records = list(latest_by_eye.values())
    for record in records:
        record["split"] = v3.split_for_patient(record["patient_id"])
    patient_eye_counts = defaultdict(int)
    for record in records:
        patient_eye_counts[record["patient_id"]] += 1
    counts["eligible_eyes"] = len(records)
    counts["eligible_patients"] = len(patient_eye_counts)
    counts["bilateral_patients"] = sum(count >= 2 for count in patient_eye_counts.values())
    counts["unilateral_patients"] = sum(count == 1 for count in patient_eye_counts.values())
    return records, counts


def unique_patients(records):
    return len({record["patient_id"] for record in records})


def split_counts(records_by_split):
    return {
        split: {"eyes": len(records), "patients": unique_patients(records)}
        for split, records in records_by_split.items()
    }


def split_age_counts(records_by_split):
    result = {}
    for split, records in records_by_split.items():
        result[split] = {}
        for label, lower, upper in v3.AGE_BANDS:
            subset = [record for record in records if lower <= record["age"] < upper]
            result[split][label] = {
                "eyes": len(subset),
                "patients": unique_patients(subset),
            }
    return result


def cluster_bootstrap_category_intervals(payload, records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["patient_id"]].append(v3.category(v3.score_record(payload, record)[1]))
    patients = sorted(grouped)
    rng = random.Random(BOOTSTRAP_SEED)
    proportions = {0: [], 1: [], 2: []}
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = [patients[rng.randrange(len(patients))] for _ in patients]
        categories = [category for patient in sampled for category in grouped[patient]]
        for category in proportions:
            proportions[category].append(categories.count(category) / len(categories))
    labels = {0: "typical", 1: "uncommon", 2: "rare"}
    return {
        labels[category]: {
            "lower_95": quantile(sorted(values), 0.025),
            "upper_95": quantile(sorted(values), 0.975),
        }
        for category, values in proportions.items()
    }


def paired_eye_summary(records, inputs):
    grouped = defaultdict(dict)
    for record in records:
        grouped[record["patient_id"]][record["eye_side"]] = record
    pairs = [eyes for eyes in grouped.values() if "OD" in eyes and "OS" in eyes]
    result = {"paired_patients": len(pairs), "features": {}}
    for name in inputs:
        right = [eyes["OD"][name] for eyes in pairs]
        left = [eyes["OS"][name] for eyes in pairs]
        differences = sorted(abs(a - b) for a, b in zip(right, left))
        result["features"][name] = {
            "pearson_correlation": v3.correlation(right, left),
            "median_absolute_difference": statistics.median(differences),
            "p95_absolute_difference": quantile(differences, 0.95),
        }
    return result


def train_model(source_path, tier):
    inputs = v3.TIERS[tier]
    records, filter_counts = prepare_bilateral_records(source_path, inputs)
    splits = v3.records_by_split(records)
    for split_name, minimum_patients in (
        ("derivation", 500),
        ("tuning", 120),
        ("calibration", 120),
        ("test", 120),
    ):
        if unique_patients(splits[split_name]) < minimum_patients:
            raise ValueError(
                f"{tier} {split_name} patient set is too small: "
                f"{unique_patients(splits[split_name])}"
            )

    age_adjustment = v3.fit_age_adjustment(splits["derivation"], inputs)
    feature_scalers = [
        v3.scale_by_age(age_adjustment, name, v3.AGE_CENTER) for name in inputs
    ]
    derivation_vectors = np.asarray(
        [
            v3.transform_record(record, inputs, age_adjustment, feature_scalers)[1]
            for record in splits["derivation"]
        ],
        dtype=float,
    )
    estimator = MinCovDet(
        support_fraction=v3.MCD_SUPPORT_FRACTION,
        random_state=v3.MCD_RANDOM_STATE,
        assume_centered=False,
        store_precision=False,
    ).fit(derivation_vectors)
    covariance, raw_eigenvalues, regularized_eigenvalues, eigenvalue_floor = (
        v3.regularize_covariance(estimator.covariance_)
    )
    precision = np.linalg.inv(covariance)
    location = estimator.location_

    calibration_vectors = [
        v3.transform_record(record, inputs, age_adjustment, feature_scalers)[1]
        for record in splits["calibration"]
    ]
    cluster_map = {
        patient_id: index
        for index, patient_id in enumerate(
            sorted({record["patient_id"] for record in splits["calibration"]})
        )
    }
    calibration_age_distance = [
        [
            record["age"],
            v3.distance_from_vector(vector, location, precision),
            cluster_map[record["patient_id"]],
        ]
        for record, vector in zip(splits["calibration"], calibration_vectors)
    ]
    calibration_distances = sorted(pair[1] for pair in calibration_age_distance)

    tuning_distances = []
    for record in splits["tuning"]:
        _, tuning_vector = v3.transform_record(
            record, inputs, age_adjustment, feature_scalers
        )
        tuning_distances.append(v3.distance_from_vector(tuning_vector, location, precision))
    selected_bandwidth, bandwidth_candidates = v3.select_age_bandwidth(
        calibration_age_distance,
        splits["tuning"],
        tuning_distances,
    )
    age_calibration_bandwidth = selected_bandwidth["bandwidth_years"]
    marginal_reference_values = {
        name: sorted(vector[index] for vector in calibration_vectors)
        for index, name in enumerate(inputs)
    }

    counts = split_counts(splits)
    payload = {
        "schema_version": 4,
        "model_name": f"Biometry OOD bilateral continuous age-adjusted {tier}",
        "model_key": f"bilateral_{tier.lower()}",
        "model_version": f"bilateral-{tier.lower()}-v3.1.0",
        "stratum_key": "continuous_age_bilateral",
        "stratum_label": "Continuous age-adjusted bilateral",
        "display_age_range": "2-100 years",
        "age_min_inclusive": v3.AGE_MIN,
        "age_max_exclusive": v3.AGE_MAX_EXCLUSIVE,
        "cohort_status": (
            "Single-center bilateral institutional eye reference with patient-level splits; "
            "clinical indication is not verified by EMR."
        ),
        "reference_unit": "age-weighted calibration eyes",
        "tier": tier,
        "inputs": inputs,
        "input_ranges": {name: list(v3.INPUT_RANGES[name]) for name in inputs},
        "age_adjustment": age_adjustment,
        "feature_labels": [
            f"{('Mean K' if name == 'Mean_K' else name)} vs age" for name in inputs
        ],
        "feature_scalers": feature_scalers,
        "covariance_method": (
            "Eye-level reweighted Minimum Covariance Determinant after patient-level split; "
            "support_fraction 0.75; eigenvalue floor 1e-8 of maximum eigenvalue"
        ),
        "robust_location": location.tolist(),
        "robust_covariance": covariance.tolist(),
        "precision_matrix": precision.tolist(),
        "feature_standard_deviations": np.sqrt(np.diag(covariance)).tolist(),
        "calibration_method": (
            "Patient-held-out bilateral age-local empirical calibration; "
            f"Gaussian age kernel bandwidth {age_calibration_bandwidth:g} years selected in a separate tuning set; "
            "add-one upper-tail smoothing; cluster-aware effective N"
        ),
        "calibration_distances": calibration_distances,
        "calibration_age_distance": calibration_age_distance,
        "age_calibration_bandwidth_years": age_calibration_bandwidth,
        "marginal_reference_values": marginal_reference_values,
        "reference_rows": counts["calibration"]["eyes"],
        "reference_patients": counts["calibration"]["patients"],
        "derivation_rows": counts["derivation"]["eyes"],
        "derivation_patients": counts["derivation"]["patients"],
        "tuning_rows": counts["tuning"]["eyes"],
        "tuning_patients": counts["tuning"]["patients"],
        "test_rows": counts["test"]["eyes"],
        "test_patients": counts["test"]["patients"],
        "training_filter_counts": filter_counts,
        "split_counts": counts,
        "split_age_band_counts": split_age_counts(splits),
        "score_thresholds_percentile": {"score_0_upper": 90.0, "score_1_upper": 97.5},
        "threshold_interpretation": (
            "Prespecified descriptive categories, not clinical decision thresholds."
        ),
        "distance_thresholds": {
            "p90": quantile(calibration_distances, 0.90),
            "p97_5": quantile(calibration_distances, 0.975),
        },
    }
    report = {
        "model_key": payload["model_key"],
        "model_version": payload["model_version"],
        "inputs": inputs,
        "filter_counts": filter_counts,
        "split_counts": counts,
        "split_age_band_counts": payload["split_age_band_counts"],
        "age_adjustment": age_adjustment,
        "covariance": {
            "method": payload["covariance_method"],
            "raw_support_fraction": float(np.mean(estimator.raw_support_)),
            "reweighted_support_fraction": float(np.mean(estimator.support_)),
            "raw_minimum_eigenvalue": float(np.min(raw_eigenvalues)),
            "regularized_minimum_eigenvalue": float(np.min(regularized_eigenvalues)),
            "maximum_eigenvalue": float(np.max(regularized_eigenvalues)),
            "eigenvalue_floor": eigenvalue_floor,
            "condition_number_2": float(np.linalg.cond(covariance)),
        },
        "calibration": {
            "method": payload["calibration_method"],
            "distance_thresholds": payload["distance_thresholds"],
            "bandwidth_selection": {
                "selected": selected_bandwidth,
                "candidates": bandwidth_candidates,
            },
        },
        "independent_test_eye_level": v3.uniformity_metrics(payload, splits["test"]),
        "independent_test_by_age_eye_level": v3.validation_by_age(payload, splits["test"]),
        "independent_test_cluster_bootstrap_95_ci": cluster_bootstrap_category_intervals(
            payload, splits["test"]
        ),
        "boundary_continuity": v3.boundary_continuity(payload, splits["test"]),
        "paired_eye_summary_in_test": paired_eye_summary(splits["test"], inputs),
    }
    return payload, report, {"records": records, "splits": splits}


def model_agreement(left_payload, right_payload, records):
    left = [v3.score_record(left_payload, record)[1] for record in records]
    right = [v3.score_record(right_payload, record)[1] for record in records]
    left_categories = [v3.category(value) for value in left]
    right_categories = [v3.category(value) for value in right]
    return {
        "n_eyes": len(records),
        "n_patients": unique_patients(records),
        "pearson_correlation": v3.correlation(left, right),
        "spearman_correlation": v3.correlation(v3.rank_values(left), v3.rank_values(right)),
        "category_agreement": sum(a == b for a, b in zip(left_categories, right_categories)) / len(records),
        "linearly_weighted_kappa": v3.linearly_weighted_kappa(left_categories, right_categories),
        "rare_classification_changed": sum(
            (a == 2) != (b == 2) for a, b in zip(left_categories, right_categories)
        ) / len(records),
        "median_absolute_percentile_difference": statistics.median(
            abs(a - b) for a, b in zip(left, right)
        ),
        "maximum_absolute_percentile_difference": max(abs(a - b) for a, b in zip(left, right)),
    }


def one_eye_sensitivity(one_eye_bundle_path, bilateral_payloads, source_path):
    one_eye_bundle = json.loads(Path(one_eye_bundle_path).read_text(encoding="utf-8"))
    one_eye_models = {model["tier"]: model for model in one_eye_bundle["models"]}
    result = {}
    for tier, bilateral_payload in bilateral_payloads.items():
        one_eye_records, _ = v3.prepare_patient_records(source_path, v3.TIERS[tier])
        test_records = [record for record in one_eye_records if record["split"] == "test"]
        result[tier] = model_agreement(
            one_eye_models[tier], bilateral_payload, test_records
        )
    return result


def train_bundle(source_path, output_path, report_path, one_eye_bundle_path):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    core_payload, core_report, core_internal = train_model(source_path, "Core")
    ext_payload, ext_report, ext_internal = train_model(source_path, "Extended")
    bilateral_agreement = v3.core_extended_agreement(
        core_payload, core_internal, ext_payload, ext_internal
    )
    sensitivity = one_eye_sensitivity(
        one_eye_bundle_path,
        {"Core": core_payload, "Extended": ext_payload},
        source_path,
    )
    source = {
        "filename": Path(source_path).name,
        "sha256": sha256_file(source_path),
        "worksheet": "Corrected_All_Eyes",
    }
    bundle = {
        "schema_version": 4,
        "bundle_version": BUNDLE_VERSION,
        "trained_at_utc": now,
        "intended_use": (
            "Research-use bilateral, continuously age-adjusted anatomical rarity screening; "
            "not a refractive prediction model."
        ),
        "selection_rule": "Use Extended when both WTW and CCT are valid; otherwise use Core.",
        "source": source,
        "models": [core_payload, ext_payload],
    }
    report = {
        "bundle_version": BUNDLE_VERSION,
        "trained_at_utc": now,
        "source": source,
        "software": {"numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "bilateral_patient_level_design": {
            "split_seed": v3.SPLIT_SEED,
            "split_ratios": v3.SPLIT_RATIOS,
            "both_eligible_eyes_included": True,
            "same_patient_eyes_always_share_split": True,
            "estimand": "Eye-level institutional anatomical rarity.",
            "inference": "Patient-cluster bootstrap for test category confidence intervals.",
        },
        "models": [core_report, ext_report],
        "core_extended_independent_test_agreement": bilateral_agreement,
        "one_eye_v3_sensitivity_on_deterministically_selected_test_eyes": sensitivity,
        "limitations": [
            "Single-center retrospective institutional reference distribution.",
            "Inter-eye dependence is handled by patient-level splits and cluster-bootstrap validation; covariance geometry remains eye-level.",
            "Clinical indication, phakic status, prior refractive surgery, and device quality warnings are not verified by EMR.",
            "Age adjustment removes cross-sectional institutional age trends and must not be interpreted as longitudinal biological change.",
            "External-center and other-biometer validation remain required.",
            "OOD percentile measures anatomical rarity, not postoperative prediction error or measurement failure.",
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_xlsx", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/biometry_ood_bilateral_v31.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/biometry_ood_bilateral_v31_validation.json"),
    )
    parser.add_argument(
        "--one-eye-model",
        type=Path,
        default=Path("models/biometry_ood_continuous_v3.json"),
    )
    args = parser.parse_args()
    bundle, report = train_bundle(
        args.source_xlsx, args.output, args.report, args.one_eye_model
    )
    print(f"Trained {bundle['bundle_version']} with {len(bundle['models'])} models")
    for model in bundle["models"]:
        print(
            f"  {model['model_key']}: derivation={model['derivation_rows']} eyes/"
            f"{model['derivation_patients']} patients, calibration={model['reference_rows']} eyes/"
            f"{model['reference_patients']} patients, test={model['test_rows']} eyes/"
            f"{model['test_patients']} patients"
        )
    agreement = report["core_extended_independent_test_agreement"]
    print(f"  Core/Extended test category agreement: {100 * agreement['category_agreement']:.1f}%")


if __name__ == "__main__":
    main()
