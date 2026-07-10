#!/usr/bin/env python3
"""Runtime calculator for the age-adjusted biometry OOD model."""

from __future__ import annotations

import bisect
import json
import math
import sys
from datetime import datetime
from pathlib import Path


MODEL_RELATIVE_PATH = Path("models") / "biometry_ood_bilateral_v31.json"


def resource_path(relative_path: Path) -> Path:
    """Return a resource path that works in source and PyInstaller builds."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def parse_iso_date(value):
    text = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def age_at_measurement(dob, acquisition_date):
    birth = parse_iso_date(dob)
    measured = parse_iso_date(acquisition_date)
    if birth is None or measured is None or measured < birth:
        return None
    return (measured - birth).days / 365.2425


def mean_k_from_radii(r1, r2):
    try:
        radius_1 = float(r1)
        radius_2 = float(r2)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(radius_1) and math.isfinite(radius_2)):
        return None
    if radius_1 <= 0 or radius_2 <= 0:
        return None
    return ((337.5 / radius_1) + (337.5 / radius_2)) / 2.0


def _dot_matrix_vector(matrix, vector):
    return [sum(row[j] * vector[j] for j in range(len(vector))) for row in matrix]


def _interpolate(value, anchors, values):
    if value <= anchors[0]:
        return values[0]
    if value >= anchors[-1]:
        return values[-1]
    upper = bisect.bisect_right(anchors, value)
    lower = upper - 1
    fraction = (value - anchors[lower]) / (anchors[upper] - anchors[lower])
    return values[lower] + fraction * (values[upper] - values[lower])


def _quantile(sorted_values, probability):
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def approximate_frequency_range(tail_probability):
    frequency = max(1.0, 1.0 / max(tail_probability, 1e-12))
    if frequency < 10:
        step = 1
    elif frequency < 50:
        step = 5
    elif frequency < 100:
        step = 10
    elif frequency < 250:
        step = 25
    elif frequency < 500:
        step = 50
    else:
        step = 100
    lower = max(1, round((frequency * 0.8) / step) * step)
    upper = max(lower, round((frequency * 1.25) / step) * step)
    if upper == lower:
        upper += step
    return int(lower), int(upper)


def calibration_warning(effective_n, max_percentile):
    warnings = []
    if max_percentile < 97.5:
        warnings.append(
            f"Age-local calibration can reach at most {max_percentile:.1f} percentile at this age, "
            "so the Rare threshold is not attainable."
        )
    if effective_n < 50:
        warnings.append(
            f"Age-local calibration effective N is {effective_n:.0f}; percentile precision is limited."
        )
    return " ".join(warnings) or None


def reference_context(
    percentile,
    reference_count,
    tail_probability=None,
    age_local=False,
    reference_unit=None,
):
    if percentile < 90.0:
        population = (
            reference_unit
            or ("age-weighted calibration eyes" if age_local else "reference eyes")
        )
        return f"Within the central 90% of {population}"
    if tail_probability is None:
        minimum_tail_probability = 1.0 / max(1, reference_count)
        tail_probability = max(1.0 - percentile / 100.0, minimum_tail_probability)
    lower, upper = approximate_frequency_range(tail_probability)
    population = (
        reference_unit
        or ("age-weighted calibration eyes" if age_local else "reference eyes")
    )
    return f"About 1 in {lower}-{upper} {population} is this unusual or more"


class BiometryOODModel:
    def __init__(self, payload):
        self.payload = payload
        self.version = payload["model_version"]
        self.inputs = payload["inputs"]
        self.feature_labels = payload["feature_labels"]
        self.location = payload["robust_location"]
        self.precision = payload["precision_matrix"]
        self.standard_deviations = payload["feature_standard_deviations"]
        self.reference_distances = payload.get(
            "calibration_distances", payload.get("reference_distances", [])
        )
        self.calibration_age_distance = payload.get("calibration_age_distance", [])
        self.age_calibration_bandwidth = payload.get("age_calibration_bandwidth_years")
        self.calibration_method = payload.get("calibration_method", "In-sample empirical percentile")
        self.reference_unit = payload.get("reference_unit")
        self.feature_scalers = payload.get("feature_scalers")
        self.marginal_reference_values = payload.get("marginal_reference_values", {})
        self.score_thresholds = payload["score_thresholds_percentile"]
        self.age_adjustment = payload["age_adjustment"]
        self.input_ranges = payload["input_ranges"]
        self.age_min = payload["age_min_inclusive"]
        self.age_max_exclusive = payload["age_max_exclusive"]
        self.stratum_label = payload["stratum_label"]
        self.tier = payload["tier"]

    @classmethod
    def from_json(cls, path):
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def expected_by_age(self, name, age):
        adjustment = self.age_adjustment
        feature = adjustment["features"].get(name)
        if feature is None:
            return None
        t = (age - adjustment["age_center_years"]) / adjustment["age_scale_years"]
        coefficients = feature["coefficients"]
        if adjustment.get("basis") == "linear hinge spline":
            result = coefficients[0] + coefficients[1] * t
            for coefficient, knot in zip(coefficients[2:], adjustment["knots_years"]):
                scaled_knot = (knot - adjustment["age_center_years"]) / adjustment["age_scale_years"]
                result += coefficient * max(0.0, t - scaled_knot)
            return result
        return coefficients[0] + coefficients[1] * t + coefficients[2] * t * t

    def scale_by_age(self, name, age, index):
        feature = self.age_adjustment["features"].get(name, {})
        if feature.get("scale_anchors_years"):
            return _interpolate(age, feature["scale_anchors_years"], feature["scale_values"])
        if self.feature_scalers:
            return self.feature_scalers[index]
        return 1.0

    def calibrated_percentile(self, age, distance):
        if self.calibration_age_distance and self.age_calibration_bandwidth:
            total_weight = 0.0
            below_weight = 0.0
            squared_weight = 0.0
            cluster_weights = {}
            has_clusters = False
            for pair_index, pair in enumerate(self.calibration_age_distance):
                calibration_age, calibration_distance = pair[0], pair[1]
                cluster_id = pair[2] if len(pair) > 2 else pair_index
                has_clusters = has_clusters or len(pair) > 2
                weight = math.exp(
                    -0.5 * ((calibration_age - age) / self.age_calibration_bandwidth) ** 2
                )
                total_weight += weight
                squared_weight += weight * weight
                cluster_weights[cluster_id] = cluster_weights.get(cluster_id, 0.0) + weight
                if calibration_distance < distance:
                    below_weight += weight
            denominator = total_weight + 1.0
            percentile = 100.0 * below_weight / denominator
            tail_probability = (1.0 + total_weight - below_weight) / denominator
            effective_denominator = (
                sum(weight * weight for weight in cluster_weights.values())
                if has_clusters
                else squared_weight
            )
            effective_n = (
                total_weight * total_weight / effective_denominator
                if effective_denominator > 0
                else 0.0
            )
            max_percentile = 100.0 * total_weight / denominator
            return percentile, tail_probability, effective_n, max_percentile
        percentile = 100.0 * bisect.bisect_right(
            self.reference_distances, distance
        ) / len(self.reference_distances)
        tail_probability = max(
            1.0 - percentile / 100.0,
            1.0 / max(1, len(self.reference_distances)),
        )
        return percentile, tail_probability, float(len(self.reference_distances)), 100.0

    def _validate_range(self, name, value):
        lower, upper = self.input_ranges[name]
        return lower <= value <= upper

    def score_values(self, age, values):
        if not self.age_min <= age < self.age_max_exclusive:
            return self.not_calculated(
                f"Age outside selected model range ({self.age_min}-{self.age_max_exclusive})",
                age=age,
                mean_k=values.get("Mean_K"),
            )
        numeric = {}
        for name in self.inputs:
            try:
                numeric[name] = float(values.get(name))
            except (TypeError, ValueError):
                return self.not_calculated(
                    f"{name} is missing or non-numeric", age=age, mean_k=values.get("Mean_K")
                )
            if not math.isfinite(numeric[name]):
                return self.not_calculated(
                    f"{name} is missing or non-finite", age=age, mean_k=values.get("Mean_K")
                )
        for name, value in numeric.items():
            if not self._validate_range(name, value):
                lower, upper = self.input_ranges[name]
                return self.not_calculated(
                    f"{name} outside model input range ({lower}-{upper})",
                    age=age,
                    mean_k=values.get("Mean_K"),
                )

        transformed = {}
        vector = []
        for index, name in enumerate(self.inputs):
            expected = self.expected_by_age(name, age)
            transformed[name] = numeric[name] - expected if expected is not None else numeric[name]
            vector.append(transformed[name] / self.scale_by_age(name, age, index))
        adjusted_acd = transformed["ACD"]
        adjusted_lt = transformed["LT"]
        delta = [vector[i] - self.location[i] for i in range(len(vector))]
        projected = _dot_matrix_vector(self.precision, delta)
        distance_squared = max(0.0, sum(delta[i] * projected[i] for i in range(len(delta))))
        distance = math.sqrt(distance_squared)
        percentile, tail_probability, effective_n, max_percentile = self.calibrated_percentile(
            age, distance
        )
        score_0_upper = self.score_thresholds["score_0_upper"]
        score_1_upper = self.score_thresholds["score_1_upper"]
        if percentile < score_0_upper:
            status = "Typical anatomy"
        elif percentile < score_1_upper:
            status = "Uncommon anatomy"
        else:
            status = "Rare anatomy"

        z_scores = [
            delta[i] / self.standard_deviations[i] if self.standard_deviations[i] > 0 else 0.0
            for i in range(len(delta))
        ]
        ranked = sorted(range(len(z_scores)), key=lambda i: abs(z_scores[i]), reverse=True)[:2]
        dominant = "; ".join(
            f"{self.feature_labels[i].removesuffix(' vs age')} {z_scores[i]:+.1f} SD"
            for i in ranked
        )

        units = {"AL": "mm", "Mean_K": "D", "ACD": "mm", "LT": "mm", "WTW": "mm", "CCT": "mm"}
        profile = []
        for index, name in enumerate(self.inputs):
            reference_values = self.marginal_reference_values.get(name)
            if not reference_values:
                continue
            marginal_percentile = 100.0 * bisect.bisect_left(
                reference_values, vector[index]
            ) / (len(reference_values) + 1.0)
            profile.append(
                {
                    "name": name,
                    "label": "Mean K" if name == "Mean_K" else name,
                    "unit": units[name],
                    "observed": numeric[name],
                    "residual": transformed[name],
                    "standardized_value": vector[index],
                    "marginal_percentile": marginal_percentile,
                    "q2_5": _quantile(reference_values, 0.025),
                    "q25": _quantile(reference_values, 0.25),
                    "q50": _quantile(reference_values, 0.50),
                    "q75": _quantile(reference_values, 0.75),
                    "q97_5": _quantile(reference_values, 0.975),
                }
            )

        return {
            "Age_at_Biometry": round(age, 3),
            "Mean_K": round(numeric["Mean_K"], 6),
            "Age_Adjusted_ACD": round(adjusted_acd, 6),
            "Age_Adjusted_LT": round(adjusted_lt, 6),
            "OOD_Distance": round(distance, 6),
            "OOD_Percentile": round(percentile, 3),
            "OOD_Status": status,
            "OOD_Reference_Context": reference_context(
                percentile,
                len(self.reference_distances),
                tail_probability=tail_probability,
                age_local=bool(self.calibration_age_distance),
                reference_unit=self.reference_unit,
            ),
            "OOD_Dominant_Deviation": dominant,
            "OOD_Largest_Marginal_Deviations": dominant,
            "OOD_Local_Calibration_Effective_N": round(effective_n, 1),
            "OOD_Local_Calibration_Max_Percentile": round(max_percentile, 3),
            "OOD_Calibration_Warning": calibration_warning(effective_n, max_percentile),
            "OOD_Age_Stratum": self.stratum_label,
            "OOD_Model_Tier": self.tier,
            "OOD_Model_Version": self.version,
            "OOD_Feature_Profile": profile,
            "OOD_Calibration_Method": self.calibration_method,
        }

    def not_calculated(self, reason, age=None, mean_k=None):
        return {
            "Age_at_Biometry": round(age, 3) if age is not None else None,
            "Mean_K": round(mean_k, 6) if mean_k is not None else None,
            "Age_Adjusted_ACD": None,
            "Age_Adjusted_LT": None,
            "OOD_Distance": None,
            "OOD_Percentile": None,
            "OOD_Status": "Not calculated",
            "OOD_Reference_Context": None,
            "OOD_Dominant_Deviation": reason,
            "OOD_Largest_Marginal_Deviations": reason,
            "OOD_Local_Calibration_Effective_N": None,
            "OOD_Local_Calibration_Max_Percentile": None,
            "OOD_Calibration_Warning": None,
            "OOD_Age_Stratum": self.stratum_label,
            "OOD_Model_Tier": self.tier,
            "OOD_Model_Version": self.version,
            "OOD_Feature_Profile": [],
            "OOD_Calibration_Method": self.calibration_method,
        }


class BiometryOODSelector:
    def __init__(self, bundle):
        self.payload = bundle
        self.version = bundle["bundle_version"]
        self.models = [BiometryOODModel(payload) for payload in bundle["models"]]

    @classmethod
    def from_json(cls, path):
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def models_for_age(self, age):
        return [model for model in self.models if model.age_min <= age < model.age_max_exclusive]

    def select_model(self, age, wtw=None, cct=None):
        candidates = self.models_for_age(age)
        if not candidates:
            return None
        extended = next(model for model in candidates if model.tier == "Extended")
        try:
            optional = {"WTW": float(wtw), "CCT": float(cct)}
            extended_valid = all(
                math.isfinite(optional[name]) and extended._validate_range(name, optional[name])
                for name in optional
            )
        except (TypeError, ValueError):
            extended_valid = False
        if extended_valid:
            return extended
        return next(model for model in candidates if model.tier == "Core")

    def model_selection_warning(self, age, wtw=None, cct=None):
        candidates = self.models_for_age(age)
        if not candidates:
            return None
        extended = next(model for model in candidates if model.tier == "Extended")
        optional = {"WTW": wtw, "CCT": cct}
        provided = {
            name: value is not None and str(value).strip() != ""
            for name, value in optional.items()
        }
        if not any(provided.values()):
            return None

        issues = []
        ignored = []
        for name, value in optional.items():
            if not provided[name]:
                issues.append(f"{name} is missing")
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                issues.append(f"{name} is non-numeric")
                continue
            lower, upper = extended.input_ranges[name]
            if not math.isfinite(numeric) or not lower <= numeric <= upper:
                issues.append(f"{name} is outside {lower:g}-{upper:g}")
            else:
                ignored.append(name)
        if not issues:
            return None
        ignored_text = f" Valid {' and '.join(ignored)} input was ignored." if ignored else ""
        return f"Extended model not used: {'; '.join(issues)}.{ignored_text} Core model calculated."

    def score_values(self, age, al, mean_k, acd, lt, wtw=None, cct=None):
        try:
            numeric_age = float(age)
        except (TypeError, ValueError):
            return self.not_calculated("Age is missing or non-numeric", mean_k=mean_k)
        if not math.isfinite(numeric_age):
            return self.not_calculated("Age is missing or non-finite", mean_k=mean_k)
        model = self.select_model(numeric_age, wtw, cct)
        if model is None:
            return self.not_calculated(
                "Age outside available model range (2-100 years)", age=numeric_age, mean_k=mean_k
            )
        values = {
            "AL": al,
            "Mean_K": mean_k,
            "ACD": acd,
            "LT": lt,
            "WTW": wtw,
            "CCT": cct,
        }
        result = model.score_values(numeric_age, values)
        result["OOD_Model_Selection_Warning"] = self.model_selection_warning(
            numeric_age, wtw, cct
        )
        result["OOD_Core_Sensitivity_Percentile"] = None
        result["OOD_Core_Sensitivity_Status"] = None
        if model.tier == "Extended" and result["OOD_Status"] != "Not calculated":
            core = next(candidate for candidate in self.models_for_age(numeric_age) if candidate.tier == "Core")
            core_result = core.score_values(numeric_age, values)
            result["OOD_Core_Sensitivity_Percentile"] = core_result["OOD_Percentile"]
            result["OOD_Core_Sensitivity_Status"] = core_result["OOD_Status"]
        return result

    def score_row(self, row):
        age = age_at_measurement(row.get("DOB"), row.get("Acquisition_Date"))
        mean_k = mean_k_from_radii(row.get("R1"), row.get("R2"))
        if age is None:
            return self.not_calculated("DOB or acquisition date is missing/invalid", mean_k=mean_k)
        if mean_k is None:
            return self.not_calculated("R1 or R2 is missing/invalid", age=age)
        return self.score_values(
            age,
            row.get("AL"),
            mean_k,
            row.get("ACD"),
            row.get("LT"),
            row.get("W2W"),
            row.get("CCT"),
        )

    def not_calculated(self, reason, age=None, mean_k=None):
        return {
            "Age_at_Biometry": round(age, 3) if age is not None else None,
            "Mean_K": round(mean_k, 6) if mean_k is not None else None,
            "Age_Adjusted_ACD": None,
            "Age_Adjusted_LT": None,
            "OOD_Distance": None,
            "OOD_Percentile": None,
            "OOD_Status": "Not calculated",
            "OOD_Reference_Context": None,
            "OOD_Dominant_Deviation": reason,
            "OOD_Largest_Marginal_Deviations": reason,
            "OOD_Local_Calibration_Effective_N": None,
            "OOD_Local_Calibration_Max_Percentile": None,
            "OOD_Calibration_Warning": None,
            "OOD_Age_Stratum": None,
            "OOD_Model_Tier": None,
            "OOD_Model_Version": self.version,
            "OOD_Core_Sensitivity_Percentile": None,
            "OOD_Core_Sensitivity_Status": None,
            "OOD_Model_Selection_Warning": None,
            "OOD_Feature_Profile": [],
            "OOD_Calibration_Method": None,
        }


def load_default_model():
    return BiometryOODSelector.from_json(resource_path(MODEL_RELATIVE_PATH))
