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


BUNDLE_VERSION = "continuous-age-bilateral-v3.2.0"
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20260711
AL_CONDITIONAL_AGE_BANDWIDTH_CANDIDATES = [4.0, 6.0, 8.0, 10.0, 12.0]
AL_CONDITIONAL_AL_BANDWIDTH_CANDIDATES = [0.5, 0.75, 1.0, 1.5, 2.0]
AL_VALIDATION_BANDS = [
    ("14-21.99", 14.0, 22.0),
    ("22-24.49", 22.0, 24.5),
    ("24.5-25.99", 24.5, 26.0),
    ("26-38", 26.0, 38.000001),
]


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


def derive_al_conditional_geometry(inputs, location, covariance):
    if not inputs or inputs[0] != "AL":
        raise ValueError("AL-conditioned geometry requires AL as the first model input")
    conditioner_variance = float(covariance[0, 0])
    if conditioner_variance <= 0:
        raise ValueError("AL-conditioned geometry requires positive AL variance")
    target_cross_covariance = np.asarray(covariance[1:, 0], dtype=float)
    regression = target_cross_covariance / conditioner_variance
    conditional_covariance = (
        np.asarray(covariance[1:, 1:], dtype=float)
        - np.outer(target_cross_covariance, target_cross_covariance) / conditioner_variance
    )
    conditional_covariance, raw_eigenvalues, regularized_eigenvalues, eigenvalue_floor = (
        v3.regularize_covariance(conditional_covariance)
    )
    return {
        "conditioner": "AL",
        "conditioner_index": 0,
        "conditioner_location": float(location[0]),
        "target_inputs": inputs[1:],
        "target_location": np.asarray(location[1:], dtype=float),
        "regression_coefficients": regression,
        "conditional_covariance": conditional_covariance,
        "conditional_precision": np.linalg.inv(conditional_covariance),
        "conditional_standard_deviations": np.sqrt(np.diag(conditional_covariance)),
        "raw_eigenvalues": raw_eigenvalues,
        "regularized_eigenvalues": regularized_eigenvalues,
        "eigenvalue_floor": eigenvalue_floor,
    }


def al_conditional_residual(vector, geometry):
    vector = np.asarray(vector, dtype=float)
    al_delta = vector[0] - geometry["conditioner_location"]
    expected_targets = (
        np.asarray(geometry["target_location"], dtype=float)
        + np.asarray(geometry["regression_coefficients"], dtype=float) * al_delta
    )
    return vector[1:] - expected_targets


def al_conditional_distance(vector, geometry):
    residual = al_conditional_residual(vector, geometry)
    projected = np.asarray(geometry["conditional_precision"], dtype=float) @ residual
    return math.sqrt(max(0.0, float(residual @ projected)))


def al_conditional_percentile(calibration_pairs, age, al_standardized, distance, age_bandwidth, al_bandwidth):
    total_weight = 0.0
    below_weight = 0.0
    cluster_weights = defaultdict(float)
    for pair_index, pair in enumerate(calibration_pairs):
        calibration_age, calibration_al, calibration_distance = pair[:3]
        cluster_id = pair[3] if len(pair) > 3 else pair_index
        age_delta = (calibration_age - age) / age_bandwidth
        al_delta = (calibration_al - al_standardized) / al_bandwidth
        weight = math.exp(-0.5 * (age_delta * age_delta + al_delta * al_delta))
        total_weight += weight
        cluster_weights[cluster_id] += weight
        if calibration_distance < distance:
            below_weight += weight
    denominator = total_weight + 1.0
    effective_denominator = sum(weight * weight for weight in cluster_weights.values())
    effective_n = (
        total_weight * total_weight / effective_denominator
        if effective_denominator > 0
        else 0.0
    )
    return {
        "percentile": 100.0 * below_weight / denominator,
        "tail_probability": (1.0 + total_weight - below_weight) / denominator,
        "effective_n": effective_n,
        "max_percentile": 100.0 * total_weight / denominator,
    }


def al_band_metrics(percentiles, records):
    result = {}
    for label, lower, upper in AL_VALIDATION_BANDS:
        subset = [
            percentile
            for percentile, record in zip(percentiles, records)
            if lower <= record["AL"] < upper
        ]
        if subset:
            result[label] = {
                "n": len(subset),
                "ks_distance_from_uniform": v3.ks_distance(subset),
                "category_proportions": {
                    "typical": sum(value < 90.0 for value in subset) / len(subset),
                    "uncommon": sum(90.0 <= value < 97.5 for value in subset) / len(subset),
                    "rare": sum(value >= 97.5 for value in subset) / len(subset),
                },
            }
    return result


def age_band_metrics(percentiles, records):
    result = {}
    for label, lower, upper in v3.AGE_BANDS:
        subset = [
            percentile
            for percentile, record in zip(percentiles, records)
            if lower <= record["age"] < upper
        ]
        if subset:
            result[label] = {
                "n": len(subset),
                "ks_distance_from_uniform": v3.ks_distance(subset),
                "category_proportions": {
                    "typical": sum(value < 90.0 for value in subset) / len(subset),
                    "uncommon": sum(90.0 <= value < 97.5 for value in subset)
                    / len(subset),
                    "rare": sum(value >= 97.5 for value in subset) / len(subset),
                },
            }
    return result


def select_al_conditional_bandwidth(calibration_pairs, tuning_records, tuning_vectors, tuning_distances):
    candidates = []
    for age_bandwidth in AL_CONDITIONAL_AGE_BANDWIDTH_CANDIDATES:
        for al_bandwidth in AL_CONDITIONAL_AL_BANDWIDTH_CANDIDATES:
            calibrations = [
                al_conditional_percentile(
                    calibration_pairs,
                    record["age"],
                    vector[0],
                    distance,
                    age_bandwidth,
                    al_bandwidth,
                )
                for record, vector, distance in zip(
                    tuning_records, tuning_vectors, tuning_distances
                )
            ]
            percentiles = [item["percentile"] for item in calibrations]
            overall_ks = v3.ks_distance(percentiles)
            age_ks = []
            for _, lower, upper in v3.AGE_BANDS:
                subset = [
                    percentile
                    for percentile, record in zip(percentiles, tuning_records)
                    if lower <= record["age"] < upper
                ]
                if len(subset) >= 10:
                    age_ks.append(v3.ks_distance(subset))
            al_metrics = al_band_metrics(percentiles, tuning_records)
            al_ks = [
                item["ks_distance_from_uniform"]
                for item in al_metrics.values()
                if item["n"] >= 10
            ]
            effective_values = sorted(item["effective_n"] for item in calibrations)
            p10_effective_n = quantile(effective_values, 0.10)
            precision_penalty = max(0.0, 50.0 - p10_effective_n) / 200.0
            objective = (
                overall_ks
                + (statistics.mean(age_ks) if age_ks else 0.0)
                + (statistics.mean(al_ks) if al_ks else 0.0)
                + precision_penalty
            )
            candidates.append(
                {
                    "age_bandwidth_years": age_bandwidth,
                    "al_bandwidth_standardized": al_bandwidth,
                    "objective": objective,
                    "overall_ks": overall_ks,
                    "mean_age_band_ks": statistics.mean(age_ks) if age_ks else None,
                    "mean_al_band_ks": statistics.mean(al_ks) if al_ks else None,
                    "p10_effective_n": p10_effective_n,
                    "median_effective_n": statistics.median(effective_values),
                }
            )
    selected = min(
        candidates,
        key=lambda item: (
            item["objective"],
            item["age_bandwidth_years"],
            item["al_bandwidth_standardized"],
        ),
    )
    return selected, candidates


def al_conditional_test_metrics(payload, records):
    geometry = payload["al_conditional_geometry"]
    vectors = [
        v3.transform_record(record, payload["inputs"], payload["age_adjustment"], payload["feature_scalers"])[1]
        for record in records
    ]
    distances = [al_conditional_distance(vector, geometry) for vector in vectors]
    calibrations = [
        al_conditional_percentile(
            geometry["calibration_age_al_distance"],
            record["age"],
            vector[0],
            distance,
            geometry["age_bandwidth_years"],
            geometry["al_bandwidth_standardized"],
        )
        for record, vector, distance in zip(records, vectors, distances)
    ]
    percentiles = [item["percentile"] for item in calibrations]
    ordered = sorted(percentiles)
    return {
        "overall": {
            "n": len(records),
            "percentile_median": statistics.median(percentiles),
            "percentile_p90": quantile(ordered, 0.90),
            "percentile_p97_5": quantile(ordered, 0.975),
            "category_proportions": {
                "typical": sum(value < 90.0 for value in percentiles) / len(percentiles),
                "uncommon": sum(90.0 <= value < 97.5 for value in percentiles) / len(percentiles),
                "rare": sum(value >= 97.5 for value in percentiles) / len(percentiles),
            },
            "ks_distance_from_uniform": v3.ks_distance(percentiles),
            "effective_n_median": statistics.median(item["effective_n"] for item in calibrations),
            "effective_n_p10": quantile(sorted(item["effective_n"] for item in calibrations), 0.10),
        },
        "by_age": age_band_metrics(percentiles, records),
        "by_al": al_band_metrics(percentiles, records),
    }


def al_conditional_cluster_bootstrap_intervals(payload, records):
    geometry = payload["al_conditional_geometry"]
    grouped = defaultdict(list)
    for record in records:
        vector = v3.transform_record(
            record,
            payload["inputs"],
            payload["age_adjustment"],
            payload["feature_scalers"],
        )[1]
        distance = al_conditional_distance(vector, geometry)
        percentile = al_conditional_percentile(
            geometry["calibration_age_al_distance"],
            record["age"],
            vector[0],
            distance,
            geometry["age_bandwidth_years"],
            geometry["al_bandwidth_standardized"],
        )["percentile"]
        grouped[record["patient_id"]].append(v3.category(percentile))
    patients = sorted(grouped)
    rng = random.Random(BOOTSTRAP_SEED + 1)
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


def train_model(source_path, tier, base_payload=None, base_report=None):
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

    if base_payload is not None:
        if base_payload["inputs"] != inputs:
            raise ValueError(f"{tier} base model inputs do not match the requested tier")
        age_adjustment = base_payload["age_adjustment"]
        feature_scalers = base_payload.get("feature_scalers")
        covariance = np.asarray(base_payload["robust_covariance"], dtype=float)
        precision = np.asarray(base_payload["precision_matrix"], dtype=float)
        location = np.asarray(base_payload["robust_location"], dtype=float)
        raw_eigenvalues = np.linalg.eigvalsh(covariance)
        regularized_eigenvalues = raw_eigenvalues
        eigenvalue_floor = 0.0
        estimator = None
    else:
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
    al_conditional_geometry = derive_al_conditional_geometry(inputs, location, covariance)

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
    if base_payload is not None:
        calibration_age_distance = base_payload["calibration_age_distance"]
        calibration_distances = base_payload["calibration_distances"]
    else:
        calibration_age_distance = [
            [
                record["age"],
                v3.distance_from_vector(vector, location, precision),
                cluster_map[record["patient_id"]],
            ]
            for record, vector in zip(splits["calibration"], calibration_vectors)
        ]
        calibration_distances = sorted(pair[1] for pair in calibration_age_distance)

    tuning_vectors = []
    tuning_distances = []
    for record in splits["tuning"]:
        _, tuning_vector = v3.transform_record(
            record, inputs, age_adjustment, feature_scalers
        )
        tuning_vectors.append(tuning_vector)
        tuning_distances.append(v3.distance_from_vector(tuning_vector, location, precision))
    if base_payload is not None:
        selected_bandwidth = {
            "bandwidth_years": base_payload["age_calibration_bandwidth_years"]
        }
        bandwidth_candidates = []
    else:
        selected_bandwidth, bandwidth_candidates = v3.select_age_bandwidth(
            calibration_age_distance,
            splits["tuning"],
            tuning_distances,
        )
    age_calibration_bandwidth = selected_bandwidth["bandwidth_years"]
    al_conditional_calibration = [
        [
            record["age"],
            vector[0],
            al_conditional_distance(vector, al_conditional_geometry),
            cluster_map[record["patient_id"]],
        ]
        for record, vector in zip(splits["calibration"], calibration_vectors)
    ]
    tuning_al_conditional_distances = [
        al_conditional_distance(vector, al_conditional_geometry)
        for vector in tuning_vectors
    ]
    selected_al_conditional_bandwidth, al_conditional_bandwidth_candidates = (
        select_al_conditional_bandwidth(
            al_conditional_calibration,
            splits["tuning"],
            tuning_vectors,
            tuning_al_conditional_distances,
        )
    )
    al_conditional_geometry_payload = {
        "method": (
            "Conditional robust Gaussian geometry using the covariance Schur complement; "
            "AL is conditioned on after continuous age standardization and is excluded from "
            "the conditional distance"
        ),
        "conditioner": al_conditional_geometry["conditioner"],
        "conditioner_index": al_conditional_geometry["conditioner_index"],
        "conditioner_location": al_conditional_geometry["conditioner_location"],
        "target_inputs": al_conditional_geometry["target_inputs"],
        "target_labels": [
            "Mean K" if name == "Mean_K" else name
            for name in al_conditional_geometry["target_inputs"]
        ],
        "target_location": al_conditional_geometry["target_location"].tolist(),
        "regression_coefficients": al_conditional_geometry[
            "regression_coefficients"
        ].tolist(),
        "conditional_covariance": al_conditional_geometry[
            "conditional_covariance"
        ].tolist(),
        "conditional_precision": al_conditional_geometry[
            "conditional_precision"
        ].tolist(),
        "conditional_standard_deviations": al_conditional_geometry[
            "conditional_standard_deviations"
        ].tolist(),
        "calibration_age_al_distance": al_conditional_calibration,
        "age_bandwidth_years": selected_al_conditional_bandwidth[
            "age_bandwidth_years"
        ],
        "al_bandwidth_standardized": selected_al_conditional_bandwidth[
            "al_bandwidth_standardized"
        ],
        "reference_unit": "age-and-AL-weighted calibration eyes",
        "calibration_method": (
            "Patient-held-out bilateral age-and-AL-local empirical calibration; joint Gaussian "
            f"kernel bandwidths {selected_al_conditional_bandwidth['age_bandwidth_years']:g} years "
            f"and {selected_al_conditional_bandwidth['al_bandwidth_standardized']:g} standardized AL; "
            "add-one upper-tail smoothing; cluster-aware effective N"
        ),
    }
    marginal_reference_values = (
        base_payload["marginal_reference_values"]
        if base_payload is not None
        else {
            name: sorted(vector[index] for vector in calibration_vectors)
            for index, name in enumerate(inputs)
        }
    )

    counts = split_counts(splits)
    payload = {
        "schema_version": 5,
        "model_name": f"Biometry OOD bilateral continuous age-adjusted {tier}",
        "model_key": f"bilateral_{tier.lower()}",
        "model_version": f"bilateral-{tier.lower()}-v3.2.0",
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
        "al_conditional_geometry": al_conditional_geometry_payload,
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
        "covariance": (
            base_report["covariance"]
            if base_report is not None
            else {
                "method": payload["covariance_method"],
                "raw_support_fraction": float(np.mean(estimator.raw_support_)),
                "reweighted_support_fraction": float(np.mean(estimator.support_)),
                "raw_minimum_eigenvalue": float(np.min(raw_eigenvalues)),
                "regularized_minimum_eigenvalue": float(np.min(regularized_eigenvalues)),
                "maximum_eigenvalue": float(np.max(regularized_eigenvalues)),
                "eigenvalue_floor": eigenvalue_floor,
                "condition_number_2": float(np.linalg.cond(covariance)),
            }
        ),
        "calibration": {
            "method": payload["calibration_method"],
            "distance_thresholds": payload["distance_thresholds"],
            "bandwidth_selection": (
                base_report["calibration"]["bandwidth_selection"]
                if base_report is not None
                else {
                    "selected": selected_bandwidth,
                    "candidates": bandwidth_candidates,
                }
            ),
        },
        "al_conditional_geometry": {
            "method": al_conditional_geometry_payload["method"],
            "conditioner": "continuous-age-standardized AL",
            "target_inputs": al_conditional_geometry_payload["target_inputs"],
            "raw_minimum_eigenvalue": float(
                np.min(al_conditional_geometry["raw_eigenvalues"])
            ),
            "regularized_minimum_eigenvalue": float(
                np.min(al_conditional_geometry["regularized_eigenvalues"])
            ),
            "maximum_eigenvalue": float(
                np.max(al_conditional_geometry["regularized_eigenvalues"])
            ),
            "eigenvalue_floor": al_conditional_geometry["eigenvalue_floor"],
            "condition_number_2": float(
                np.linalg.cond(al_conditional_geometry["conditional_covariance"])
            ),
            "calibration_method": al_conditional_geometry_payload[
                "calibration_method"
            ],
            "bandwidth_selection": {
                "selected": selected_al_conditional_bandwidth,
                "candidates": al_conditional_bandwidth_candidates,
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
    report["al_conditional_geometry"]["independent_test_eye_level"] = (
        al_conditional_test_metrics(payload, splits["test"])
    )
    report["al_conditional_geometry"][
        "independent_test_cluster_bootstrap_95_ci"
    ] = al_conditional_cluster_bootstrap_intervals(payload, splits["test"])
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


def train_bundle(
    source_path,
    output_path,
    report_path,
    one_eye_bundle_path,
    base_bundle_path=None,
    base_report_path=None,
):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    base_models = {}
    base_reports = {}
    if base_bundle_path is not None:
        base_bundle = json.loads(Path(base_bundle_path).read_text(encoding="utf-8"))
        base_models = {model["tier"]: model for model in base_bundle["models"]}
    if base_report_path is not None:
        base_report = json.loads(Path(base_report_path).read_text(encoding="utf-8"))
        base_reports = {
            model["model_key"].removeprefix("bilateral_").title(): model
            for model in base_report["models"]
        }
    core_payload, core_report, core_internal = train_model(
        source_path, "Core", base_models.get("Core"), base_reports.get("Core")
    )
    ext_payload, ext_report, ext_internal = train_model(
        source_path, "Extended", base_models.get("Extended"), base_reports.get("Extended")
    )
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
        "schema_version": 5,
        "bundle_version": BUNDLE_VERSION,
        "trained_at_utc": now,
        "intended_use": (
            "Research-use bilateral, continuously age-adjusted anatomical rarity screening, "
            "including a secondary AL-conditioned geometry discordance score; not a refractive "
            "prediction model."
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
            "The AL-conditioned score uses a linear conditional covariance approximation after robust age standardization; nonlinear AL relationships and sparse AL extremes require external validation.",
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
        default=Path("models/biometry_ood_bilateral_v32.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/biometry_ood_bilateral_v32_validation.json"),
    )
    parser.add_argument(
        "--one-eye-model",
        type=Path,
        default=Path("models/biometry_ood_continuous_v3.json"),
    )
    parser.add_argument(
        "--base-model",
        type=Path,
        default=Path("models/biometry_ood_bilateral_v31.json"),
        help="Immutable V3.1 Overall model to preserve while adding the V3.2 score",
    )
    parser.add_argument(
        "--base-report",
        type=Path,
        default=Path("reports/biometry_ood_bilateral_v31_validation.json"),
    )
    args = parser.parse_args()
    bundle, report = train_bundle(
        args.source_xlsx,
        args.output,
        args.report,
        args.one_eye_model,
        args.base_model,
        args.base_report,
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
