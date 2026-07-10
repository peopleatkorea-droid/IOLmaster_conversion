#!/usr/bin/env python3
"""Runtime calculator for the age-adjusted biometry OOD model."""

from __future__ import annotations

import bisect
import json
import math
import sys
from datetime import datetime
from pathlib import Path


MODEL_RELATIVE_PATH = Path("models") / "biometry_ood_age_stratified_v2.json"


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


class BiometryOODModel:
    def __init__(self, payload):
        self.payload = payload
        self.version = payload["model_version"]
        self.inputs = payload["inputs"]
        self.feature_labels = payload["feature_labels"]
        self.location = payload["robust_location"]
        self.precision = payload["precision_matrix"]
        self.standard_deviations = payload["feature_standard_deviations"]
        self.reference_distances = payload["reference_distances"]
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
        return coefficients[0] + coefficients[1] * t + coefficients[2] * t * t

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
        for name in self.inputs:
            expected = self.expected_by_age(name, age)
            transformed[name] = numeric[name] - expected if expected is not None else numeric[name]
        adjusted_acd = transformed["ACD"]
        adjusted_lt = transformed["LT"]
        vector = [transformed[name] for name in self.inputs]
        delta = [vector[i] - self.location[i] for i in range(len(vector))]
        projected = _dot_matrix_vector(self.precision, delta)
        distance_squared = max(0.0, sum(delta[i] * projected[i] for i in range(len(delta))))
        distance = math.sqrt(distance_squared)
        percentile = 100.0 * bisect.bisect_right(self.reference_distances, distance) / len(
            self.reference_distances
        )
        score_0_upper = self.score_thresholds["score_0_upper"]
        score_1_upper = self.score_thresholds["score_1_upper"]
        if percentile < score_0_upper:
            score, status = 0, "Routine-range anatomy"
        elif percentile < score_1_upper:
            score, status = 1, "Uncommon anatomy"
        else:
            score, status = 2, "Out-of-distribution anatomy"

        z_scores = [
            delta[i] / self.standard_deviations[i] if self.standard_deviations[i] > 0 else 0.0
            for i in range(len(delta))
        ]
        ranked = sorted(range(len(z_scores)), key=lambda i: abs(z_scores[i]), reverse=True)[:2]
        dominant = "; ".join(f"{self.feature_labels[i]} {z_scores[i]:+.1f} SD" for i in ranked)

        return {
            "Age_at_Biometry": round(age, 3),
            "Mean_K": round(numeric["Mean_K"], 6),
            "Age_Adjusted_ACD": round(adjusted_acd, 6),
            "Age_Adjusted_LT": round(adjusted_lt, 6),
            "OOD_Distance": round(distance, 6),
            "OOD_Percentile": round(percentile, 3),
            "Anatomy_Score": score,
            "OOD_Status": status,
            "OOD_Dominant_Deviation": dominant,
            "OOD_Age_Stratum": self.stratum_label,
            "OOD_Model_Tier": self.tier,
            "OOD_Model_Version": self.version,
        }

    def not_calculated(self, reason, age=None, mean_k=None):
        return {
            "Age_at_Biometry": round(age, 3) if age is not None else None,
            "Mean_K": round(mean_k, 6) if mean_k is not None else None,
            "Age_Adjusted_ACD": None,
            "Age_Adjusted_LT": None,
            "OOD_Distance": None,
            "OOD_Percentile": None,
            "Anatomy_Score": None,
            "OOD_Status": "Not calculated",
            "OOD_Dominant_Deviation": reason,
            "OOD_Age_Stratum": self.stratum_label,
            "OOD_Model_Tier": self.tier,
            "OOD_Model_Version": self.version,
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
        return model.score_values(numeric_age, values)

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
            "Anatomy_Score": None,
            "OOD_Status": "Not calculated",
            "OOD_Dominant_Deviation": reason,
            "OOD_Age_Stratum": None,
            "OOD_Model_Tier": None,
            "OOD_Model_Version": self.version,
        }


def load_default_model():
    return BiometryOODSelector.from_json(resource_path(MODEL_RELATIVE_PATH))
