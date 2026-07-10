#!/usr/bin/env python3
"""Train continuously age-adjusted, patient-split biometry OOD models."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import numpy as np
    import sklearn
    from sklearn.covariance import MinCovDet
except ModuleNotFoundError as exc:
    raise SystemExit(
        "V3 training dependencies are missing. Install requirements-modeling.txt first."
    ) from exc

try:
    from modeling.train_ood_model import (
        finite_float,
        parse_date,
        quantile,
        read_xlsx_rows,
        sha256_file,
    )
except ModuleNotFoundError:
    from train_ood_model import finite_float, parse_date, quantile, read_xlsx_rows, sha256_file


BUNDLE_VERSION = "continuous-age-calibrated-v3.0.0"
KERATOMETRIC_CONSTANT = 337.5
AGE_MIN = 2.0
AGE_MAX_EXCLUSIVE = 101.0
AGE_CENTER = 50.0
AGE_SCALE = 10.0
AGE_KNOTS = [5.0, 10.0, 15.0, 18.0, 30.0, 40.0, 55.0, 70.0, 85.0]
SCALE_ANCHORS = [2.0, 5.0, 8.0, 11.0, 14.0, 17.0, 20.0, 25.0, 30.0, 35.0,
                 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
SCALE_NEIGHBORS = 250
SPLIT_SEED = "biometry-ood-v3-final-split-20260710"
EYE_SELECTION_SEED = "biometry-ood-v3-eye-20260710"
SPLIT_RATIOS = {"derivation": 0.55, "tuning": 0.15, "calibration": 0.15, "test": 0.15}
MCD_SUPPORT_FRACTION = 0.75
MCD_RANDOM_STATE = 20260710
AGE_CALIBRATION_BANDWIDTH_CANDIDATES = [4.0, 6.0, 8.0, 10.0, 12.0]

TIERS = {
    "Core": ["AL", "Mean_K", "ACD", "LT"],
    "Extended": ["AL", "Mean_K", "ACD", "LT", "WTW", "CCT"],
}

INPUT_RANGES = {
    "AL": (14.0, 38.0),
    "Mean_K": (30.0, 65.0),
    "ACD": (0.8, 6.0),
    "LT": (2.0, 8.0),
    "WTW": (8.0, 16.0),
    "CCT": (0.35, 0.8),
}

AGE_BANDS = [
    ("2-17", 2.0, 18.0),
    ("18-39", 18.0, 40.0),
    ("40-59", 40.0, 60.0),
    ("60-79", 60.0, 80.0),
    ("80-100", 80.0, 101.0),
]


def stable_fraction(seed, patient_id):
    digest = hashlib.sha256(f"{seed}|{patient_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def split_for_patient(patient_id):
    value = stable_fraction(SPLIT_SEED, patient_id)
    if value < SPLIT_RATIOS["derivation"]:
        return "derivation"
    if value < SPLIT_RATIOS["derivation"] + SPLIT_RATIOS["tuning"]:
        return "tuning"
    if value < SPLIT_RATIOS["derivation"] + SPLIT_RATIOS["tuning"] + SPLIT_RATIOS["calibration"]:
        return "calibration"
    return "test"


def age_basis(age):
    t = (age - AGE_CENTER) / AGE_SCALE
    basis = [1.0, t]
    basis.extend(max(0.0, t - ((knot - AGE_CENTER) / AGE_SCALE)) for knot in AGE_KNOTS)
    return basis


def robust_scale(values):
    center = statistics.median(values)
    mad = statistics.median(abs(value - center) for value in values)
    return max(1e-12, 1.4826 * mad)


def fit_huber_spline(ages, values, tuning=1.345, max_iterations=100):
    design = np.asarray([age_basis(age) for age in ages], dtype=float)
    outcome = np.asarray(values, dtype=float)
    weights = np.ones(len(values), dtype=float)
    coefficients = np.linalg.lstsq(design, outcome, rcond=None)[0]
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        residuals = outcome - design @ coefficients
        scale = robust_scale(residuals.tolist())
        updated_weights = np.minimum(1.0, tuning * scale / np.maximum(np.abs(residuals), 1e-12))
        weighted_design = design * np.sqrt(updated_weights)[:, None]
        weighted_outcome = outcome * np.sqrt(updated_weights)
        updated = np.linalg.lstsq(weighted_design, weighted_outcome, rcond=None)[0]
        if np.max(np.abs(updated - coefficients)) < 1e-10:
            coefficients = updated
            break
        coefficients = updated
        weights = updated_weights
    residuals = outcome - design @ coefficients
    return coefficients, robust_scale(residuals.tolist()), iterations


def expected_by_age(age_adjustment, name, age):
    coefficients = age_adjustment["features"][name]["coefficients"]
    return float(np.dot(np.asarray(age_basis(age)), np.asarray(coefficients)))


def interpolate(age, anchors, values):
    if age <= anchors[0]:
        return values[0]
    if age >= anchors[-1]:
        return values[-1]
    upper = bisect.bisect_right(anchors, age)
    lower = upper - 1
    fraction = (age - anchors[lower]) / (anchors[upper] - anchors[lower])
    return values[lower] + fraction * (values[upper] - values[lower])


def scale_by_age(age_adjustment, name, age):
    feature = age_adjustment["features"][name]
    return interpolate(age, feature["scale_anchors_years"], feature["scale_values"])


def values_from_row(row):
    r1 = finite_float(row.get("R1"))
    r2 = finite_float(row.get("R2"))
    mean_k = None
    if r1 is not None and r2 is not None and r1 > 0 and r2 > 0:
        mean_k = ((KERATOMETRIC_CONSTANT / r1) + (KERATOMETRIC_CONSTANT / r2)) / 2.0
    return {
        "AL": finite_float(row.get("AL")),
        "Mean_K": mean_k,
        "ACD": finite_float(row.get("ACD")),
        "LT": finite_float(row.get("LT")),
        "WTW": finite_float(row.get("W2W")),
        "CCT": finite_float(row.get("CCT")),
    }


def prepare_patient_records(source_path, required_inputs):
    counts = {
        "source_rows": 0,
        "excluded_test_or_demo": 0,
        "excluded_missing_or_invalid_date": 0,
        "excluded_age": 0,
        "excluded_missing_input": 0,
        "excluded_input_range": 0,
        "superseded_repeat_exam": 0,
        "additional_eye_not_selected": 0,
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
        if not AGE_MIN <= age < AGE_MAX_EXCLUSIVE:
            counts["excluded_age"] += 1
            continue
        values = values_from_row(row)
        if any(values[name] is None for name in required_inputs):
            counts["excluded_missing_input"] += 1
            continue
        if any(not INPUT_RANGES[name][0] <= values[name] <= INPUT_RANGES[name][1] for name in required_inputs):
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

    records_by_patient = defaultdict(list)
    for record in latest_by_eye.values():
        records_by_patient[record["patient_id"]].append(record)

    selected = []
    for patient_id, records in records_by_patient.items():
        records.sort(
            key=lambda record: stable_fraction(
                EYE_SELECTION_SEED,
                f"{patient_id}|{record['eye_side']}",
            )
        )
        selected.append(records[0])
        counts["additional_eye_not_selected"] += len(records) - 1

    for record in selected:
        record["split"] = split_for_patient(record["patient_id"])
    counts["eligible_patients"] = len(selected)
    counts["eligible_eyes_after_selection"] = len(selected)
    return selected, counts


def records_by_split(records):
    result = {"derivation": [], "tuning": [], "calibration": [], "test": []}
    for record in records:
        result[record["split"]].append(record)
    return result


def age_band_counts(records):
    return {
        label: sum(lower <= record["age"] < upper for record in records)
        for label, lower, upper in AGE_BANDS
    }


def fit_age_adjustment(derivation, inputs):
    ages = [record["age"] for record in derivation]
    features = {}
    for name in inputs:
        coefficients, residual_scale, iterations = fit_huber_spline(
            ages,
            [record[name] for record in derivation],
        )
        residuals = [
            record[name] - float(np.dot(np.asarray(age_basis(record["age"])), coefficients))
            for record in derivation
        ]
        scale_values = []
        neighbor_count = min(SCALE_NEIGHBORS, len(derivation))
        for anchor in SCALE_ANCHORS:
            nearest = sorted(
                range(len(derivation)),
                key=lambda index: abs(ages[index] - anchor),
            )[:neighbor_count]
            scale_values.append(robust_scale([residuals[index] for index in nearest]))
        features[name] = {
            "coefficients": coefficients.tolist(),
            "residual_scale": residual_scale,
            "scale_method": f"Linear interpolation of MAD scales from {neighbor_count} nearest-age derivation patients",
            "scale_anchors_years": SCALE_ANCHORS,
            "scale_values": scale_values,
            "iterations": iterations,
        }
    return {
        "method": "Huber piecewise-linear spline",
        "basis": "linear hinge spline",
        "huber_tuning": 1.345,
        "age_center_years": AGE_CENTER,
        "age_scale_years": AGE_SCALE,
        "knots_years": AGE_KNOTS,
        "dispersion_method": "Continuous nearest-age MAD scale interpolation",
        "features": features,
    }


def transform_record(record, inputs, age_adjustment, feature_scalers=None, age_override=None):
    age = record["age"] if age_override is None else age_override
    raw_residuals = []
    standardized = []
    for index, name in enumerate(inputs):
        residual = record[name] - expected_by_age(age_adjustment, name, age)
        raw_residuals.append(residual)
        if age_adjustment.get("dispersion_method"):
            scale = scale_by_age(age_adjustment, name, age)
        else:
            scale = feature_scalers[index]
        standardized.append(residual / scale)
    return raw_residuals, standardized


def regularize_covariance(covariance):
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    largest = float(np.max(eigenvalues))
    floor = max(1e-10, largest * 1e-8)
    regularized_values = np.maximum(eigenvalues, floor)
    regularized = eigenvectors @ np.diag(regularized_values) @ eigenvectors.T
    return regularized, eigenvalues, regularized_values, floor


def distance_from_vector(vector, location, precision):
    delta = np.asarray(vector, dtype=float) - np.asarray(location, dtype=float)
    return math.sqrt(max(0.0, float(delta @ np.asarray(precision) @ delta)))


def conformal_percentile(sorted_distances, distance):
    rank_below = bisect.bisect_left(sorted_distances, distance)
    return 100.0 * rank_below / (len(sorted_distances) + 1.0)


def age_local_percentile(age_distance_pairs, age, distance, bandwidth):
    total_weight = 0.0
    below_weight = 0.0
    squared_weight = 0.0
    cluster_weights = defaultdict(float)
    has_clusters = False
    for pair_index, pair in enumerate(age_distance_pairs):
        calibration_age, calibration_distance = pair[0], pair[1]
        cluster_id = pair[2] if len(pair) > 2 else pair_index
        has_clusters = has_clusters or len(pair) > 2
        weight = math.exp(
            -0.5 * ((calibration_age - age) / bandwidth) ** 2
        )
        total_weight += weight
        squared_weight += weight * weight
        cluster_weights[cluster_id] += weight
        if calibration_distance < distance:
            below_weight += weight
    percentile = 100.0 * below_weight / (total_weight + 1.0)
    denominator = (
        sum(weight * weight for weight in cluster_weights.values())
        if has_clusters
        else squared_weight
    )
    effective_n = total_weight * total_weight / denominator if denominator else 0.0
    return percentile, effective_n


def category(percentile):
    if percentile < 90.0:
        return 0
    if percentile < 97.5:
        return 1
    return 2


def score_record(payload, record, age_override=None):
    score_age = record["age"] if age_override is None else age_override
    _, vector = transform_record(
        record,
        payload["inputs"],
        payload["age_adjustment"],
        payload["feature_scalers"],
        age_override=age_override,
    )
    distance = distance_from_vector(vector, payload["robust_location"], payload["precision_matrix"])
    if payload.get("calibration_age_distance"):
        percentile, _ = age_local_percentile(
            payload["calibration_age_distance"],
            score_age,
            distance,
            payload["age_calibration_bandwidth_years"],
        )
    else:
        percentile = conformal_percentile(payload["calibration_distances"], distance)
    return distance, percentile


def uniformity_metrics(payload, records):
    percentiles = [score_record(payload, record)[1] for record in records]
    ordered = sorted(value / 100.0 for value in percentiles)
    n = len(ordered)
    ks = max(
        max(abs(value - ((index + 1) / n)), abs(value - (index / n)))
        for index, value in enumerate(ordered)
    )
    categories = [category(value) for value in percentiles]
    return {
        "n": n,
        "percentile_median": statistics.median(percentiles),
        "percentile_p90": quantile(sorted(percentiles), 0.90),
        "percentile_p97_5": quantile(sorted(percentiles), 0.975),
        "category_proportions": {
            "typical": categories.count(0) / n,
            "uncommon": categories.count(1) / n,
            "rare": categories.count(2) / n,
        },
        "ks_distance_from_uniform": ks,
    }


def validation_by_age(payload, records):
    result = {}
    for label, lower, upper in AGE_BANDS:
        subset = [record for record in records if lower <= record["age"] < upper]
        result[label] = uniformity_metrics(payload, subset) if len(subset) >= 10 else {"n": len(subset)}
    return result


def boundary_continuity(payload, records):
    result = {}
    for boundary in (18.0, 40.0):
        subset = [record for record in records if abs(record["age"] - boundary) <= 3.0]
        differences = []
        for record in subset:
            before = score_record(payload, record, age_override=boundary - 0.01)[1]
            after = score_record(payload, record, age_override=boundary + 0.01)[1]
            differences.append(abs(before - after))
        result[str(int(boundary))] = {
            "n": len(differences),
            "median_absolute_percentile_change": statistics.median(differences) if differences else None,
            "p90_absolute_percentile_change": quantile(sorted(differences), 0.90) if differences else None,
            "maximum_absolute_percentile_change": max(differences) if differences else None,
        }
    return result


def ks_distance(percentiles):
    ordered = sorted(value / 100.0 for value in percentiles)
    n = len(ordered)
    return max(
        max(abs(value - ((index + 1) / n)), abs(value - (index / n)))
        for index, value in enumerate(ordered)
    )


def select_age_bandwidth(calibration_pairs, tuning_records, tuning_distances):
    candidates = []
    for bandwidth in AGE_CALIBRATION_BANDWIDTH_CANDIDATES:
        percentiles = [
            age_local_percentile(calibration_pairs, record["age"], distance, bandwidth)[0]
            for record, distance in zip(tuning_records, tuning_distances)
        ]
        overall_ks = ks_distance(percentiles)
        band_ks = {}
        for label, lower, upper in AGE_BANDS:
            subset = [
                percentile
                for record, percentile in zip(tuning_records, percentiles)
                if lower <= record["age"] < upper
            ]
            if len(subset) >= 10:
                band_ks[label] = ks_distance(subset)
        mean_band_ks = statistics.mean(band_ks.values())
        objective = overall_ks + mean_band_ks
        candidates.append(
            {
                "bandwidth_years": bandwidth,
                "objective": objective,
                "overall_ks": overall_ks,
                "mean_age_band_ks": mean_band_ks,
                "age_band_ks": band_ks,
            }
        )
    selected = min(candidates, key=lambda item: (item["objective"], item["bandwidth_years"]))
    return selected, candidates


def train_model(source_path, tier):
    inputs = TIERS[tier]
    records, filter_counts = prepare_patient_records(source_path, inputs)
    splits = records_by_split(records)
    for split_name, minimum in (
        ("derivation", 500),
        ("tuning", 120),
        ("calibration", 120),
        ("test", 120),
    ):
        if len(splits[split_name]) < minimum:
            raise ValueError(f"{tier} {split_name} set is too small: {len(splits[split_name])}")

    age_adjustment = fit_age_adjustment(splits["derivation"], inputs)
    feature_scalers = [scale_by_age(age_adjustment, name, AGE_CENTER) for name in inputs]
    derivation_vectors = np.asarray(
        [
            transform_record(record, inputs, age_adjustment, feature_scalers)[1]
            for record in splits["derivation"]
        ],
        dtype=float,
    )
    estimator = MinCovDet(
        support_fraction=MCD_SUPPORT_FRACTION,
        random_state=MCD_RANDOM_STATE,
        assume_centered=False,
        store_precision=False,
    ).fit(derivation_vectors)
    covariance, raw_eigenvalues, regularized_eigenvalues, eigenvalue_floor = regularize_covariance(
        estimator.covariance_
    )
    precision = np.linalg.inv(covariance)
    location = estimator.location_

    calibration_vectors = [
        transform_record(record, inputs, age_adjustment, feature_scalers)[1]
        for record in splits["calibration"]
    ]
    calibration_age_distance = [
        [record["age"], distance_from_vector(vector, location, precision)]
        for record, vector in zip(splits["calibration"], calibration_vectors)
    ]
    calibration_distances = sorted(pair[1] for pair in calibration_age_distance)
    tuning_distances = []
    for record in splits["tuning"]:
        _, tuning_vector = transform_record(
            record, inputs, age_adjustment, feature_scalers
        )
        tuning_distances.append(distance_from_vector(tuning_vector, location, precision))
    selected_bandwidth, bandwidth_candidates = select_age_bandwidth(
        calibration_age_distance,
        splits["tuning"],
        tuning_distances,
    )
    age_calibration_bandwidth = selected_bandwidth["bandwidth_years"]
    marginal_reference_values = {
        name: sorted(vector[index] for vector in calibration_vectors)
        for index, name in enumerate(inputs)
    }

    payload = {
        "schema_version": 3,
        "model_name": f"Biometry OOD continuous age-adjusted {tier}",
        "model_key": f"continuous_{tier.lower()}",
        "model_version": f"continuous-{tier.lower()}-v3.0.0",
        "stratum_key": "continuous_age",
        "stratum_label": "Continuous age-adjusted",
        "display_age_range": "2-100 years",
        "age_min_inclusive": AGE_MIN,
        "age_max_exclusive": AGE_MAX_EXCLUSIVE,
        "cohort_status": (
            "Single-center continuously age-adjusted institutional reference; "
            "clinical indication is not verified by EMR."
        ),
        "tier": tier,
        "inputs": inputs,
        "input_ranges": {name: list(INPUT_RANGES[name]) for name in inputs},
        "age_adjustment": age_adjustment,
        "feature_labels": [f"{('Mean K' if name == 'Mean_K' else name)} vs age" for name in inputs],
        "feature_scalers": feature_scalers,
        "covariance_method": (
            "Reweighted Minimum Covariance Determinant; support_fraction 0.75; "
            "eigenvalue floor 1e-8 of maximum eigenvalue"
        ),
        "robust_location": location.tolist(),
        "robust_covariance": covariance.tolist(),
        "precision_matrix": precision.tolist(),
        "feature_standard_deviations": np.sqrt(np.diag(covariance)).tolist(),
        "calibration_method": (
            "Patient-held-out age-local empirical calibration; one deterministic eye per patient; "
            f"Gaussian age kernel bandwidth {age_calibration_bandwidth:g} years selected in a separate tuning set; "
            "add-one upper-tail smoothing"
        ),
        "calibration_distances": calibration_distances,
        "calibration_age_distance": calibration_age_distance,
        "age_calibration_bandwidth_years": age_calibration_bandwidth,
        "marginal_reference_values": marginal_reference_values,
        "reference_rows": len(splits["calibration"]),
        "reference_patients": len(splits["calibration"]),
        "derivation_rows": len(splits["derivation"]),
        "derivation_patients": len(splits["derivation"]),
        "tuning_rows": len(splits["tuning"]),
        "tuning_patients": len(splits["tuning"]),
        "test_rows": len(splits["test"]),
        "test_patients": len(splits["test"]),
        "training_filter_counts": filter_counts,
        "split_counts": {name: len(rows) for name, rows in splits.items()},
        "split_age_band_counts": {name: age_band_counts(rows) for name, rows in splits.items()},
        "score_thresholds_percentile": {"score_0_upper": 90.0, "score_1_upper": 97.5},
        "threshold_interpretation": "Prespecified descriptive categories, not clinical decision thresholds.",
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
        "split_counts": payload["split_counts"],
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
        "independent_test": uniformity_metrics(payload, splits["test"]),
        "independent_test_by_age": validation_by_age(payload, splits["test"]),
        "boundary_continuity": boundary_continuity(payload, splits["test"]),
    }
    internal = {"records": records, "splits": splits}
    return payload, report, internal


def rank_values(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0 + 1.0
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def correlation(a, b):
    a_mean = statistics.mean(a)
    b_mean = statistics.mean(b)
    numerator = sum((x - a_mean) * (y - b_mean) for x, y in zip(a, b))
    denominator = math.sqrt(
        sum((x - a_mean) ** 2 for x in a) * sum((y - b_mean) ** 2 for y in b)
    )
    return numerator / denominator if denominator else 0.0


def linearly_weighted_kappa(a, b):
    size = 3
    table = [[0] * size for _ in range(size)]
    for left, right in zip(a, b):
        table[left][right] += 1
    total = len(a)
    row_totals = [sum(row) for row in table]
    column_totals = [sum(table[i][j] for i in range(size)) for j in range(size)]
    weight = lambda i, j: 1.0 - abs(i - j) / (size - 1)
    observed = sum(weight(i, j) * table[i][j] for i in range(size) for j in range(size)) / total
    expected = sum(
        weight(i, j) * row_totals[i] * column_totals[j]
        for i in range(size)
        for j in range(size)
    ) / (total * total)
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def core_extended_agreement(core_payload, core_internal, ext_payload, ext_internal):
    core_test = {
        (record["patient_id"], record["eye_side"]): record
        for record in core_internal["splits"]["test"]
    }
    ext_test = {
        (record["patient_id"], record["eye_side"]): record
        for record in ext_internal["splits"]["test"]
    }
    keys = sorted(set(core_test) & set(ext_test))
    core_percentiles = [score_record(core_payload, core_test[key])[1] for key in keys]
    ext_percentiles = [score_record(ext_payload, ext_test[key])[1] for key in keys]
    core_categories = [category(value) for value in core_percentiles]
    ext_categories = [category(value) for value in ext_percentiles]
    return {
        "n_same_patient_and_eye": len(keys),
        "pearson_correlation": correlation(core_percentiles, ext_percentiles),
        "spearman_correlation": correlation(rank_values(core_percentiles), rank_values(ext_percentiles)),
        "category_agreement": sum(a == b for a, b in zip(core_categories, ext_categories)) / len(keys),
        "linearly_weighted_kappa": linearly_weighted_kappa(core_categories, ext_categories),
        "rare_classification_changed": sum(
            (a == 2) != (b == 2) for a, b in zip(core_categories, ext_categories)
        ) / len(keys),
        "median_absolute_percentile_difference": statistics.median(
            abs(a - b) for a, b in zip(core_percentiles, ext_percentiles)
        ),
        "maximum_absolute_percentile_difference": max(
            abs(a - b) for a, b in zip(core_percentiles, ext_percentiles)
        ),
    }


def train_bundle(source_path, output_path, report_path):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    core_payload, core_report, core_internal = train_model(source_path, "Core")
    ext_payload, ext_report, ext_internal = train_model(source_path, "Extended")
    agreement = core_extended_agreement(
        core_payload,
        core_internal,
        ext_payload,
        ext_internal,
    )
    source = {
        "filename": Path(source_path).name,
        "sha256": sha256_file(source_path),
        "worksheet": "Corrected_All_Eyes",
    }
    bundle = {
        "schema_version": 3,
        "bundle_version": BUNDLE_VERSION,
        "trained_at_utc": now,
        "intended_use": (
            "Research-use continuously age-adjusted anatomical rarity screening; "
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
        "patient_level_design": {
            "split_seed": SPLIT_SEED,
            "eye_selection_seed": EYE_SELECTION_SEED,
            "split_ratios": SPLIT_RATIOS,
            "one_eye_per_patient": True,
            "exam_selection": "Latest valid examination per patient-eye before deterministic eye selection.",
        },
        "models": [core_report, ext_report],
        "core_extended_independent_test_agreement": agreement,
        "limitations": [
            "Single-center retrospective institutional reference distribution.",
            "Clinical indication, phakic status, prior refractive surgery, and device quality warnings are not verified by EMR.",
            "Age adjustment removes cross-sectional institutional age trends and must not be interpreted as longitudinal biological change.",
            "The calibration set is internally independent but external-center and other-biometer validation remain required.",
            "OOD percentile measures anatomical rarity, not postoperative prediction error or measurement failure.",
            "The 90th and 97.5th percentile categories are prespecified descriptive labels, not clinical decision thresholds.",
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
        default=Path("models/biometry_ood_continuous_v3.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/biometry_ood_continuous_v3_validation.json"),
    )
    args = parser.parse_args()
    bundle, report = train_bundle(args.source_xlsx, args.output, args.report)
    print(f"Trained {bundle['bundle_version']} with {len(bundle['models'])} models")
    for model in bundle["models"]:
        print(
            f"  {model['model_key']}: derivation={model['derivation_patients']}, "
            f"tuning={model['tuning_patients']}, calibration={model['reference_patients']}, "
            f"test={model['test_patients']}"
        )
    agreement = report["core_extended_independent_test_agreement"]
    print(
        f"  Core/Extended test category agreement: "
        f"{100 * agreement['category_agreement']:.1f}%"
    )


if __name__ == "__main__":
    main()
