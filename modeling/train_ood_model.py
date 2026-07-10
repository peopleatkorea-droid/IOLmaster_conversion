#!/usr/bin/env python3
"""Train the prototype age-adjusted biometry OOD model from the source XLSX.

The script intentionally uses only the Python standard library. Patient-level
records never enter the exported model; only aggregate coefficients, matrices,
and the empirical reference-distance distribution are stored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path


XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
KERATOMETRIC_CONSTANT = 337.5
AGE_CENTER = 70.0
AGE_SCALE = 10.0
AGE_RANGE = (40.0, 100.0)
INPUT_RANGES = {
    "AL": (18.0, 38.0),
    "Mean_K": (30.0, 60.0),
    "ACD": (0.8, 6.0),
    "LT": (2.0, 8.0),
}


def column_index(reference):
    value = 0
    for character in reference:
        if not character.isalpha():
            break
        value = value * 26 + ord(character.upper()) - 64
    return value - 1


def read_xlsx_rows(path, sheet_xml="xl/worksheets/sheet1.xml"):
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(text.text or "" for text in item.iter(XML_NS + "t"))
                for item in root.findall(XML_NS + "si")
            ]

        with archive.open(sheet_xml) as worksheet:
            headers = None
            for _, element in ET.iterparse(worksheet, events=("end",)):
                if element.tag != XML_NS + "row":
                    continue
                values = {}
                for cell in element.findall(XML_NS + "c"):
                    index = column_index(cell.attrib.get("r", ""))
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find(XML_NS + "v")
                    value = None if value_node is None else value_node.text
                    if cell_type == "s" and value is not None:
                        value = shared[int(value)]
                    elif cell_type == "inlineStr":
                        value = "".join(text.text or "" for text in cell.iter(XML_NS + "t"))
                    values[index] = value

                if headers is None:
                    max_index = max(values) if values else -1
                    headers = [values.get(i) for i in range(max_index + 1)]
                else:
                    yield {headers[i]: values.get(i) for i in range(len(headers))}
                element.clear()


def parse_date(value):
    text = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def finite_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def prepare_reference_rows(rows):
    counts = {
        "source_rows": 0,
        "excluded_test_or_demo": 0,
        "excluded_missing_or_invalid": 0,
        "excluded_age": 0,
        "excluded_input_range": 0,
        "superseded_repeat_exam": 0,
    }
    latest = {}
    anonymous_index = 0
    for row in rows:
        counts["source_rows"] += 1
        patient_id = str(row.get("Pat_ID") or "").strip()
        if patient_id.lower() in {"test", "demo", "sample"}:
            counts["excluded_test_or_demo"] += 1
            continue

        acquisition = parse_date(row.get("Acquisition_Date"))
        dob = parse_date(row.get("DOB"))
        al = finite_float(row.get("AL"))
        r1 = finite_float(row.get("R1"))
        r2 = finite_float(row.get("R2"))
        acd = finite_float(row.get("ACD"))
        lt = finite_float(row.get("LT"))
        if None in (acquisition, dob, al, r1, r2, acd, lt) or r1 <= 0 or r2 <= 0:
            counts["excluded_missing_or_invalid"] += 1
            continue

        age = (acquisition - dob).days / 365.2425
        if not AGE_RANGE[0] <= age <= AGE_RANGE[1]:
            counts["excluded_age"] += 1
            continue
        mean_k = ((KERATOMETRIC_CONSTANT / r1) + (KERATOMETRIC_CONSTANT / r2)) / 2.0
        values = {"AL": al, "Mean_K": mean_k, "ACD": acd, "LT": lt}
        if any(not INPUT_RANGES[name][0] <= value <= INPUT_RANGES[name][1] for name, value in values.items()):
            counts["excluded_input_range"] += 1
            continue

        eye_side = str(row.get("Eye_Side") or "").strip().upper()
        if patient_id:
            key = (patient_id, eye_side)
        else:
            anonymous_index += 1
            key = (f"ANONYMOUS-{anonymous_index}", eye_side)
        record = {
            "age": age,
            "AL": al,
            "Mean_K": mean_k,
            "ACD": acd,
            "LT": lt,
            "acquisition": acquisition,
        }
        if key in latest:
            counts["superseded_repeat_exam"] += 1
        if key not in latest or acquisition > latest[key]["acquisition"]:
            latest[key] = record
    return list(latest.values()), counts


def median_absolute_deviation(values):
    center = statistics.median(values)
    mad = statistics.median(abs(value - center) for value in values)
    return max(1e-12, 1.4826 * mad)


def solve_linear(matrix, vector):
    size = len(vector)
    augmented = [list(matrix[i]) + [vector[i]] for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("Singular matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                augmented[row][index] - factor * augmented[column][index]
                for index in range(size + 1)
            ]
    return [augmented[i][-1] for i in range(size)]


def inverse_matrix(matrix):
    size = len(matrix)
    columns = []
    for index in range(size):
        unit = [1.0 if i == index else 0.0 for i in range(size)]
        columns.append(solve_linear(matrix, unit))
    return [[columns[column][row] for column in range(size)] for row in range(size)]


def weighted_least_squares(design, outcome, weights):
    width = len(design[0])
    normal = [[0.0] * width for _ in range(width)]
    target = [0.0] * width
    for row, value, weight in zip(design, outcome, weights):
        for i in range(width):
            target[i] += weight * row[i] * value
            for j in range(width):
                normal[i][j] += weight * row[i] * row[j]
    return solve_linear(normal, target)


def huber_quadratic_regression(
    ages,
    values,
    iterations=50,
    tuning=1.345,
    age_center=AGE_CENTER,
    age_scale=AGE_SCALE,
):
    design = []
    for age in ages:
        t = (age - age_center) / age_scale
        design.append([1.0, t, t * t])
    weights = [1.0] * len(values)
    coefficients = weighted_least_squares(design, values, weights)
    for _ in range(iterations):
        residuals = [
            value - sum(coefficients[j] * row[j] for j in range(3))
            for row, value in zip(design, values)
        ]
        scale = median_absolute_deviation(residuals)
        new_weights = [min(1.0, tuning * scale / max(abs(residual), 1e-12)) for residual in residuals]
        updated = weighted_least_squares(design, values, new_weights)
        if max(abs(updated[i] - coefficients[i]) for i in range(3)) < 1e-10:
            coefficients = updated
            break
        coefficients, weights = updated, new_weights
    return coefficients


def covariance_matrix(rows, weights, location):
    dimensions = len(location)
    covariance = [[0.0] * dimensions for _ in range(dimensions)]
    weight_sum = sum(weights)
    for row, weight in zip(rows, weights):
        delta = [row[i] - location[i] for i in range(dimensions)]
        for i in range(dimensions):
            for j in range(dimensions):
                covariance[i][j] += weight * delta[i] * delta[j]
    denominator = max(1.0, weight_sum - 1.0)
    covariance = [[value / denominator for value in matrix_row] for matrix_row in covariance]
    ridge = max(covariance[i][i] for i in range(dimensions)) * 1e-9
    for i in range(dimensions):
        covariance[i][i] += ridge
    return covariance


def mahalanobis_distance(row, location, precision):
    delta = [row[i] - location[i] for i in range(len(row))]
    projected = [sum(precision[i][j] * delta[j] for j in range(len(row))) for i in range(len(row))]
    return math.sqrt(max(0.0, sum(delta[i] * projected[i] for i in range(len(row)))))


def huber_robust_covariance(rows, iterations=100, tuning=3.338):
    dimensions = len(rows[0])
    location = [statistics.median(row[i] for row in rows) for i in range(dimensions)]
    scales = [median_absolute_deviation([row[i] for row in rows]) for i in range(dimensions)]
    covariance = [[0.0] * dimensions for _ in range(dimensions)]
    for i in range(dimensions):
        covariance[i][i] = scales[i] ** 2

    for _ in range(iterations):
        precision = inverse_matrix(covariance)
        distances = [mahalanobis_distance(row, location, precision) for row in rows]
        weights = [min(1.0, tuning / max(distance, 1e-12)) for distance in distances]
        weight_sum = sum(weights)
        updated_location = [
            sum(weight * row[i] for row, weight in zip(rows, weights)) / weight_sum
            for i in range(dimensions)
        ]
        updated_covariance = covariance_matrix(rows, weights, updated_location)
        location_change = max(abs(updated_location[i] - location[i]) for i in range(dimensions))
        covariance_change = max(
            abs(updated_covariance[i][j] - covariance[i][j])
            for i in range(dimensions)
            for j in range(dimensions)
        )
        location, covariance = updated_location, updated_covariance
        if location_change < 1e-10 and covariance_change < 1e-10:
            break
    return location, covariance, inverse_matrix(covariance)


def quantile(sorted_values, probability):
    if not sorted_values:
        raise ValueError("Cannot calculate a quantile from an empty list")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train(source_path, model_path, report_path, model_version="core-v1.0.0"):
    reference, counts = prepare_reference_rows(read_xlsx_rows(source_path))
    if len(reference) < 1000:
        raise ValueError(f"Reference cohort is unexpectedly small: {len(reference)}")

    ages = [row["age"] for row in reference]
    acd_coefficients = huber_quadratic_regression(ages, [row["ACD"] for row in reference])
    lt_coefficients = huber_quadratic_regression(ages, [row["LT"] for row in reference])

    features = []
    for row in reference:
        t = (row["age"] - AGE_CENTER) / AGE_SCALE
        expected_acd = acd_coefficients[0] + acd_coefficients[1] * t + acd_coefficients[2] * t * t
        expected_lt = lt_coefficients[0] + lt_coefficients[1] * t + lt_coefficients[2] * t * t
        features.append(
            [row["AL"], row["Mean_K"], row["ACD"] - expected_acd, row["LT"] - expected_lt]
        )

    location, covariance, precision = huber_robust_covariance(features)
    distances = sorted(mahalanobis_distance(row, location, precision) for row in features)
    standard_deviations = [math.sqrt(covariance[i][i]) for i in range(len(covariance))]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "schema_version": 1,
        "model_name": "Biometry OOD Core",
        "model_version": model_version,
        "trained_at_utc": now,
        "intended_use": "Research-use anatomical out-of-distribution screening; not a refractive prediction model.",
        "source": {
            "filename": Path(source_path).name,
            "sha256": sha256_file(source_path),
            "worksheet": "Corrected_All_Eyes",
            "source_rows": counts["source_rows"],
            "reference_rows": len(reference),
        },
        "training_filter_counts": counts,
        "keratometric_constant": KERATOMETRIC_CONSTANT,
        "validated_age_range_years": list(AGE_RANGE),
        "input_ranges": {name: list(bounds) for name, bounds in INPUT_RANGES.items()},
        "age_adjustment": {
            "method": "Huber quadratic regression",
            "age_center_years": AGE_CENTER,
            "age_scale_years": AGE_SCALE,
            "ACD": {"coefficients": acd_coefficients},
            "LT": {"coefficients": lt_coefficients},
        },
        "features": ["AL", "Mean_K", "Age_Adjusted_ACD", "Age_Adjusted_LT"],
        "covariance_method": "Multivariate Huber M-estimator; tuning distance 3.338",
        "robust_location": location,
        "robust_covariance": covariance,
        "precision_matrix": precision,
        "feature_standard_deviations": standard_deviations,
        "reference_distances": distances,
        "score_thresholds_percentile": {"score_0_upper": 90.0, "score_1_upper": 97.5},
        "distance_thresholds": {"p90": quantile(distances, 0.90), "p97_5": quantile(distances, 0.975)},
    }

    report = {
        "model_version": payload["model_version"],
        "trained_at_utc": now,
        "source": payload["source"],
        "filter_counts": counts,
        "reference_age_quantiles": {
            name: quantile(sorted(ages), probability)
            for name, probability in (("p01", 0.01), ("p50", 0.50), ("p99", 0.99))
        },
        "age_adjustment": payload["age_adjustment"],
        "feature_location": dict(zip(payload["features"], location)),
        "feature_standard_deviation": dict(zip(payload["features"], standard_deviations)),
        "distance_thresholds": payload["distance_thresholds"],
        "limitations": [
            "Single-center retrospective reference distribution.",
            "Post-refractive and other special-eye history is not available in the source and is handled only by robust weighting.",
            "OOD percentile measures anatomical rarity, not postoperative prediction error.",
            "External and outcome validation are required before clinical decision support use.",
        ],
    }

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(model_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_xlsx", type=Path)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/biometry_ood_core_v1.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/biometry_ood_core_v1_validation.json"),
    )
    parser.add_argument("--version", default="core-v1.0.0")
    args = parser.parse_args()
    payload = train(args.source_xlsx, args.model, args.report, args.version)
    print(
        f"Trained {payload['model_version']} with {payload['source']['reference_rows']} reference eyes; "
        f"model saved to {args.model}"
    )


if __name__ == "__main__":
    main()
