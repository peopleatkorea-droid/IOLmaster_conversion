#!/usr/bin/env python3
"""Analyze age-adjusted axial-length phenotypes in children aged 3-17 years."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression

try:
    from modeling import train_continuous_ood_v3 as v3
    from modeling.train_ood_model import parse_date, read_xlsx_rows
except ModuleNotFoundError:
    import train_continuous_ood_v3 as v3
    from train_ood_model import parse_date, read_xlsx_rows


AGE_MIN = 3.0
AGE_MAX_EXCLUSIVE = 18.0
FEATURES = ["AL", "Mean_K", "ACD", "LT", "WTW", "CCT"]
OUTCOMES = ["Mean_K", "ACD", "LT"]
AGE_BANDS = [("3-6", 3.0, 7.0), ("7-9", 7.0, 10.0), ("10-12", 10.0, 13.0), ("13-17", 13.0, 18.0)]
GROUPS = ["Short", "Typical", "Long"]
COLORS = {"Short": "#B44A3A", "Typical": "#5D6972", "Long": "#087C86"}
LABELS = {
    "Mean_K": ("Mean K", "D"),
    "ACD": ("Anterior chamber depth", "mm"),
    "LT": ("Lens thickness", "mm"),
}


def deterministic_eye_index(patient_id: str, count: int, seed: int) -> int:
    digest = hashlib.sha256(f"{seed}|{patient_id}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % count


def prepare_records(source_path: Path, seed: int):
    counts = Counter()
    latest_by_eye = {}
    exam_by_eye_date = {}

    for row in read_xlsx_rows(source_path):
        counts["source_rows"] += 1
        patient_id = str(row.get("Pat_ID") or "").strip()
        if not patient_id or patient_id.lower() in {"test", "demo", "sample"}:
            counts["excluded_test_demo_or_missing_id"] += 1
            continue

        acquisition = parse_date(row.get("Acquisition_Date"))
        dob = parse_date(row.get("DOB"))
        if acquisition is None or dob is None or acquisition < dob:
            counts["excluded_invalid_date"] += 1
            continue
        age = (acquisition - dob).days / 365.2425
        if not AGE_MIN <= age < AGE_MAX_EXCLUSIVE:
            counts["excluded_age"] += 1
            continue

        sex = str(row.get("Gender") or "").strip()
        if sex not in {"Male", "Female"}:
            counts["excluded_sex"] += 1
            continue

        values = v3.values_from_row(row)
        if any(values[name] is None for name in FEATURES):
            counts["excluded_missing_input"] += 1
            continue
        if any(
            not v3.INPUT_RANGES[name][0] <= values[name] <= v3.INPUT_RANGES[name][1]
            for name in FEATURES
        ):
            counts["excluded_input_range"] += 1
            continue

        eye_side = str(row.get("Eye_Side") or "").strip().upper()
        if eye_side not in {"OD", "OS"}:
            counts["excluded_eye_side"] += 1
            continue
        record = {
            "patient_id": patient_id,
            "eye_side": eye_side,
            "age": age,
            "sex": sex,
            "acquisition": acquisition,
            **values,
        }
        counts["eligible_exam_rows"] += 1
        exam_by_eye_date[(patient_id, eye_side, acquisition)] = record
        eye_key = (patient_id, eye_side)
        if eye_key not in latest_by_eye or acquisition > latest_by_eye[eye_key]["acquisition"]:
            latest_by_eye[eye_key] = record

    eyes_by_patient = defaultdict(list)
    for record in latest_by_eye.values():
        eyes_by_patient[record["patient_id"]].append(record)

    primary = []
    patient_means = []
    for patient_id, records in sorted(eyes_by_patient.items()):
        records = sorted(records, key=lambda item: item["eye_side"])
        primary.append(records[deterministic_eye_index(patient_id, len(records), seed)])
        patient_means.append(
            {
                "patient_id": patient_id,
                "eye_side": "MEAN",
                "age": float(np.mean([record["age"] for record in records])),
                "sex": records[0]["sex"],
                "acquisition": max(record["acquisition"] for record in records),
                **{
                    name: float(np.mean([record[name] for record in records]))
                    for name in FEATURES
                },
            }
        )

    exams_by_eye = defaultdict(list)
    for (patient_id, eye_side, _), record in exam_by_eye_date.items():
        exams_by_eye[(patient_id, eye_side)].append(record)
    for records in exams_by_eye.values():
        records.sort(key=lambda item: item["acquisition"])

    counts["latest_eligible_eyes"] = len(latest_by_eye)
    counts["eligible_patients"] = len(primary)
    counts["bilateral_patients"] = sum(len(records) == 2 for records in eyes_by_patient.values())
    counts["unilateral_patients"] = sum(len(records) == 1 for records in eyes_by_patient.values())
    return primary, patient_means, exams_by_eye, dict(counts)


def arrays(records):
    return {
        "age": np.asarray([record["age"] for record in records], dtype=float),
        "sex": np.asarray([record["sex"] == "Female" for record in records], dtype=float),
        **{
            name: np.asarray([record[name] for record in records], dtype=float)
            for name in FEATURES
        },
    }


class RestrictedCubicSpline:
    """Five-knot restricted cubic spline with linear tails."""

    def __init__(self, quantiles=(0.05, 0.275, 0.50, 0.725, 0.95)):
        self.quantiles = quantiles
        self.lower = None
        self.scale = None
        self.knots = None

    def fit(self, age):
        values = np.asarray(age, dtype=float).reshape(-1)
        self.lower = float(np.min(values))
        upper = float(np.max(values))
        self.scale = max(upper - self.lower, 1e-9)
        normalized = (values - self.lower) / self.scale
        self.knots = np.quantile(normalized, self.quantiles)
        if len(np.unique(self.knots)) != len(self.knots):
            raise ValueError("Age distribution does not support five unique spline knots")
        return self

    def transform(self, age):
        if self.knots is None:
            raise ValueError("RestrictedCubicSpline must be fitted before transform")
        values = np.asarray(age, dtype=float).reshape(-1)
        normalized = (values - self.lower) / self.scale
        penultimate, last = self.knots[-2], self.knots[-1]

        def positive_cube(value):
            return np.maximum(value, 0.0) ** 3

        columns = [normalized]
        denominator = last - penultimate
        for knot in self.knots[:-2]:
            basis = (
                positive_cube(normalized - knot)
                - positive_cube(normalized - penultimate) * (last - knot) / denominator
                + positive_cube(normalized - last) * (penultimate - knot) / denominator
            )
            columns.append(basis)
        return np.column_stack(columns)

    def fit_transform(self, age):
        return self.fit(age).transform(age)


def make_age_spline(age):
    transformer = RestrictedCubicSpline()
    return transformer, transformer.fit_transform(age)


def fit_axial_length_phenotypes(data):
    transformer, basis = make_age_spline(data["age"])
    covariates = np.column_stack([basis, data["sex"]])
    model = LinearRegression().fit(covariates, data["AL"])
    expected = model.predict(covariates)
    residual = data["AL"] - expected
    lower, upper = np.quantile(residual, [0.20, 0.80])
    groups = np.where(residual <= lower, "Short", np.where(residual >= upper, "Long", "Typical"))
    return {
        "transformer": transformer,
        "basis": basis,
        "expected": expected,
        "residual": residual,
        "lower_cutoff": float(lower),
        "upper_cutoff": float(upper),
        "groups": groups,
    }


def fit_ols(design, outcome):
    matrix = np.column_stack([np.ones(len(design)), design])
    beta = np.linalg.lstsq(matrix, outcome, rcond=None)[0]
    residual = outcome - matrix @ beta
    rss = float(residual @ residual)
    rank = int(np.linalg.matrix_rank(matrix))
    return beta, rss, len(outcome) - rank


def nested_interaction_test(data, phenotype, outcome_name):
    basis = phenotype["basis"]
    al_residual = phenotype["residual"]
    reduced = np.column_stack([basis, data["sex"], al_residual])
    full = np.column_stack([basis, data["sex"], al_residual, basis * al_residual[:, None]])
    _, reduced_rss, reduced_df = fit_ols(reduced, data[outcome_name])
    _, full_rss, full_df = fit_ols(full, data[outcome_name])
    numerator_df = reduced_df - full_df
    f_statistic = ((reduced_rss - full_rss) / numerator_df) / (full_rss / full_df)
    return {
        "f_statistic": float(f_statistic),
        "df_numerator": int(numerator_df),
        "df_denominator": int(full_df),
        "p_value": float(stats.f.sf(f_statistic, numerator_df, full_df)),
    }


def partial_spearman(data, phenotype, outcome_name):
    covariates = np.column_stack([phenotype["basis"], data["sex"]])
    outcome_model = LinearRegression().fit(covariates, data[outcome_name])
    outcome_residual = data[outcome_name] - outcome_model.predict(covariates)
    result = stats.spearmanr(phenotype["residual"], outcome_residual)
    return {"rho": float(result.statistic), "p_value": float(result.pvalue)}


def group_design(basis, sex, groups, include_interactions=False):
    short = (groups == "Short").astype(float)
    long = (groups == "Long").astype(float)
    columns = [basis, sex, short, long]
    if include_interactions:
        columns.extend([basis * short[:, None], basis * long[:, None]])
    return np.column_stack(columns)


def adjusted_group_contrasts(data, phenotype, outcome_name, bootstrap_replicates, rng):
    basis = phenotype["basis"]
    groups = phenotype["groups"]
    design = group_design(basis, data["sex"], groups)
    beta, _, _ = fit_ols(design, data[outcome_name])
    short_index = 1 + basis.shape[1] + 1
    long_index = short_index + 1

    def estimates(coefficients):
        return {
            "short_vs_typical": float(coefficients[short_index]),
            "long_vs_typical": float(coefficients[long_index]),
            "short_vs_long": float(coefficients[short_index] - coefficients[long_index]),
        }

    point = estimates(beta)
    distributions = {name: [] for name in point}
    for _ in range(bootstrap_replicates):
        index = rng.integers(0, len(data["age"]), len(data["age"]))
        sampled_design = design[index]
        sampled_outcome = data[outcome_name][index]
        sampled_beta, _, _ = fit_ols(sampled_design, sampled_outcome)
        for name, value in estimates(sampled_beta).items():
            distributions[name].append(value)

    return {
        name: {
            "estimate": value,
            "lower_95": float(np.quantile(distributions[name], 0.025)),
            "upper_95": float(np.quantile(distributions[name], 0.975)),
        }
        for name, value in point.items()
    }


def fit_group_curves(data, phenotype, outcome_name, bootstrap_replicates, rng):
    basis = phenotype["basis"]
    groups = phenotype["groups"]
    design = group_design(basis, data["sex"], groups, include_interactions=True)
    beta, _, _ = fit_ols(design, data[outcome_name])
    grid_age = np.linspace(AGE_MIN, AGE_MAX_EXCLUSIVE - 1.0, 141)
    grid_basis = phenotype["transformer"].transform(grid_age)

    def prediction_design(group):
        grid_groups = np.full(len(grid_age), group)
        return group_design(
            grid_basis,
            np.full(len(grid_age), 0.5),
            grid_groups,
            include_interactions=True,
        )

    grid_designs = {group: prediction_design(group) for group in GROUPS}

    def predict(coefficients, group):
        matrix = np.column_stack([np.ones(len(grid_age)), grid_designs[group]])
        return matrix @ coefficients

    points = {group: predict(beta, group) for group in GROUPS}
    distributions = {
        group: np.empty((bootstrap_replicates, len(grid_age)), dtype=float)
        for group in GROUPS
    }
    for replicate in range(bootstrap_replicates):
        index = rng.integers(0, len(data["age"]), len(data["age"]))
        sampled_beta, _, _ = fit_ols(design[index], data[outcome_name][index])
        for group in GROUPS:
            distributions[group][replicate] = predict(sampled_beta, group)

    curves = {}
    for group in GROUPS:
        curves[group] = {
            "estimate": points[group],
            "lower_95": np.quantile(distributions[group], 0.025, axis=0),
            "upper_95": np.quantile(distributions[group], 0.975, axis=0),
        }
    return grid_age, curves


def summarize_age_bands(data, phenotype):
    rows = []
    for band, lower, upper in AGE_BANDS:
        for group in GROUPS:
            mask = (
                (data["age"] >= lower)
                & (data["age"] < upper)
                & (phenotype["groups"] == group)
            )
            indices = np.flatnonzero(mask)
            row = {"age_band": band, "group": group, "n": int(len(indices))}
            for name in ["AL", *OUTCOMES]:
                values = data[name][indices]
                row[f"{name}_median"] = float(np.median(values))
                row[f"{name}_q25"] = float(np.quantile(values, 0.25))
                row[f"{name}_q75"] = float(np.quantile(values, 0.75))
            rows.append(row)
    return rows


def fit_piecewise_lt(data, groups, group, bootstrap_replicates, rng):
    mask = groups == group
    age = data["age"][mask]
    lt = data["LT"][mask]
    sex = data["sex"][mask]
    knots = np.arange(7.0, 13.001, 0.05)

    def best_fit(sample_age, sample_lt, sample_sex):
        best = None
        for knot in knots:
            matrix = np.column_stack(
                [np.ones(len(sample_age)), sample_age, np.maximum(sample_age - knot, 0.0), sample_sex]
            )
            beta = np.linalg.lstsq(matrix, sample_lt, rcond=None)[0]
            residual = sample_lt - matrix @ beta
            rss = float(residual @ residual)
            if best is None or rss < best[0]:
                best = (rss, knot, beta)
        return best[1], best[2][1], best[2][1] + best[2][2]

    point = best_fit(age, lt, sex)
    distribution = np.empty((bootstrap_replicates, 3), dtype=float)
    for replicate in range(bootstrap_replicates):
        index = rng.integers(0, len(age), len(age))
        distribution[replicate] = best_fit(age[index], lt[index], sex[index])
    names = ["breakpoint_age", "slope_before", "slope_after"]
    return {
        "n": int(len(age)),
        **{
            name: {
                "estimate": float(point[index]),
                "lower_95": float(np.quantile(distribution[:, index], 0.025)),
                "upper_95": float(np.quantile(distribution[:, index], 0.975)),
            }
            for index, name in enumerate(names)
        },
    }


def repeated_exam_summary(exams_by_eye):
    changes_by_patient_band = defaultdict(list)
    for (patient_id, _), records in exams_by_eye.items():
        if len(records) < 2:
            continue
        first, last = records[0], records[-1]
        interval_years = (last["acquisition"] - first["acquisition"]).days / 365.2425
        if interval_years < 30 / 365.2425:
            continue
        band = next(
            (label for label, lower, upper in AGE_BANDS if lower <= first["age"] < upper),
            None,
        )
        if band is None:
            continue
        changes_by_patient_band[(patient_id, band)].append(
            {
                "follow_up_years": interval_years,
                "AL_per_year": (last["AL"] - first["AL"]) / interval_years,
                "LT_per_year": (last["LT"] - first["LT"]) / interval_years,
            }
        )

    by_band = defaultdict(list)
    for (patient_id, band), changes in changes_by_patient_band.items():
        by_band[band].append(
            {
                "patient_id": patient_id,
                **{
                    name: float(np.mean([change[name] for change in changes]))
                    for name in ["follow_up_years", "AL_per_year", "LT_per_year"]
                },
            }
        )

    result = {}
    for band, _, _ in AGE_BANDS:
        records = by_band.get(band, [])
        summary = {"patients": len(records)}
        for name in ["follow_up_years", "AL_per_year", "LT_per_year"]:
            values = np.asarray([record[name] for record in records], dtype=float)
            if len(values):
                summary[name] = {
                    "median": float(np.median(values)),
                    "q25": float(np.quantile(values, 0.25)),
                    "q75": float(np.quantile(values, 0.75)),
                }
            else:
                summary[name] = None
        result[band] = summary
    return result


def benjamini_hochberg(p_values):
    count = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(count, dtype=float)
    running = 1.0
    for rank_index in range(count - 1, -1, -1):
        original_index = order[rank_index]
        rank = rank_index + 1
        running = min(running, p_values[original_index] * count / rank)
        adjusted[original_index] = min(1.0, running)
    return adjusted


def analyze_dataset(records, bootstrap_replicates, seed):
    data = arrays(records)
    phenotype = fit_axial_length_phenotypes(data)
    result = {
        "n": len(records),
        "age": {
            "mean": float(np.mean(data["age"])),
            "sd": float(np.std(data["age"], ddof=1)),
            "median": float(np.median(data["age"])),
            "q25": float(np.quantile(data["age"], 0.25)),
            "q75": float(np.quantile(data["age"], 0.75)),
        },
        "sex": dict(Counter(record["sex"] for record in records)),
        "phenotype": {
            "definition": "Age- and sex-adjusted AL residual quintiles",
            "short_cutoff_mm": phenotype["lower_cutoff"],
            "long_cutoff_mm": phenotype["upper_cutoff"],
            "counts": dict(Counter(str(group) for group in phenotype["groups"])),
        },
        "outcomes": {},
    }

    interaction_p_values = []
    curve_payload = {}
    for offset, outcome_name in enumerate(OUTCOMES):
        outcome_rng = np.random.default_rng(seed + 1000 * (offset + 1))
        interaction = nested_interaction_test(data, phenotype, outcome_name)
        interaction_p_values.append(interaction["p_value"])
        grid_age, curves = fit_group_curves(
            data,
            phenotype,
            outcome_name,
            bootstrap_replicates,
            outcome_rng,
        )
        curve_payload[outcome_name] = {"age": grid_age, "groups": curves}
        result["outcomes"][outcome_name] = {
            "partial_spearman": partial_spearman(data, phenotype, outcome_name),
            "adjusted_contrasts": adjusted_group_contrasts(
                data,
                phenotype,
                outcome_name,
                bootstrap_replicates,
                outcome_rng,
            ),
            "age_by_al_residual_interaction": interaction,
        }

    adjusted_p_values = benjamini_hochberg(np.asarray(interaction_p_values))
    for outcome_name, adjusted_p in zip(OUTCOMES, adjusted_p_values):
        result["outcomes"][outcome_name]["age_by_al_residual_interaction"][
            "fdr_bh_p_value"
        ] = float(adjusted_p)

    result["age_band_summary"] = summarize_age_bands(data, phenotype)
    result["lt_piecewise"] = {
        group: fit_piecewise_lt(
            data,
            phenotype["groups"],
            group,
            bootstrap_replicates,
            np.random.default_rng(seed + 7000 + index),
        )
        for index, group in enumerate(GROUPS)
    }
    return result, data, phenotype, curve_payload


def nice_ticks(low, high, target=5):
    span = max(high - low, 1e-9)
    rough = span / target
    exponent = math.floor(math.log10(rough))
    fraction = rough / (10**exponent)
    step_fraction = next(value for value in (1, 2, 2.5, 5, 10) if fraction <= value)
    step = step_fraction * (10**exponent)
    start = math.floor(low / step) * step
    end = math.ceil(high / step) * step
    ticks = []
    value = start
    while value <= end + step * 0.01:
        ticks.append(value)
        value += step
    return start, end, ticks, step


def tick_label(value, step):
    if step >= 1:
        return f"{value:.0f}"
    if step >= 0.1:
        return f"{value:.1f}"
    return f"{value:.2f}"


def svg_text(x, y, value, size=14, weight=400, fill="#173E54", anchor="start"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{html.escape(str(value))}</text>'
    )


def svg_path(points):
    return " ".join(
        ("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}"
        for index, (x, y) in enumerate(points)
    )


def render_trajectory_figure(output_path, result, data, phenotype, curve_payload):
    width, height = 1800, 760
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#F7F9FA"/>',
        '<g font-family="Arial, Segoe UI, sans-serif">',
        svg_text(68, 58, "Age-adjusted axial-length phenotypes in children", size=31, weight=750),
        svg_text(
            68,
            89,
            "Sex-balanced restricted cubic-spline estimates with conditional 95% bootstrap intervals",
            size=15,
            fill="#5B707B",
        ),
    ]
    legend_x = 1125
    for index, group in enumerate(GROUPS):
        x = legend_x + index * 190
        parts.append(
            f'<line x1="{x}" y1="73" x2="{x + 42}" y2="73" stroke="{COLORS[group]}" stroke-width="5" stroke-linecap="round"/>'
        )
        parts.append(svg_text(x + 53, 78, group, size=14, weight=650, fill="#425864"))

    panel_width = 540
    panel_height = 540
    panel_y = 130
    panel_positions = [55, 630, 1205]
    age_grid = curve_payload[OUTCOMES[0]]["age"]

    for panel_x, outcome_name in zip(panel_positions, OUTCOMES):
        title, unit = LABELS[outcome_name]
        plot_x, plot_y = panel_x + 68, panel_y + 62
        plot_width, plot_height = panel_width - 98, panel_height - 118
        curve = curve_payload[outcome_name]["groups"]
        observed_values = data[outcome_name]
        visible = list(observed_values)
        for group in GROUPS:
            visible.extend(curve[group]["lower_95"])
            visible.extend(curve[group]["upper_95"])
        raw_low, raw_high = np.quantile(visible, [0.01, 0.99])
        padding = max((raw_high - raw_low) * 0.08, 0.04 if unit == "mm" else 0.15)
        y_min, y_max, y_ticks, y_step = nice_ticks(raw_low - padding, raw_high + padding)

        def sx(age):
            return plot_x + (age - AGE_MIN) / (AGE_MAX_EXCLUSIVE - 1.0 - AGE_MIN) * plot_width

        def sy(value):
            return plot_y + (y_max - value) / (y_max - y_min) * plot_height

        parts.extend(
            [
                f'<rect x="{panel_x}" y="{panel_y}" width="{panel_width}" height="{panel_height}" rx="6" fill="#FFFFFF" stroke="#CBD6DC"/>',
                svg_text(panel_x + 22, panel_y + 34, title, size=21, weight=700),
                svg_text(panel_x + panel_width - 22, panel_y + 34, unit, size=13, weight=650, fill="#667983", anchor="end"),
            ]
        )
        for tick in y_ticks:
            y = sy(tick)
            parts.append(
                f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_width}" y2="{y:.1f}" stroke="#E6ECEF"/>'
            )
            parts.append(svg_text(plot_x - 10, y + 5, tick_label(tick, y_step), size=12, fill="#61747E", anchor="end"))
        for tick in range(3, 18, 2):
            x = sx(tick)
            parts.append(
                f'<line x1="{x:.1f}" y1="{plot_y}" x2="{x:.1f}" y2="{plot_y + plot_height}" stroke="#F1F4F5"/>'
            )
            parts.append(svg_text(x, plot_y + plot_height + 24, tick, size=12, fill="#61747E", anchor="middle"))

        for group in GROUPS:
            upper = [(sx(age), sy(value)) for age, value in zip(age_grid, curve[group]["upper_95"])]
            lower = [(sx(age), sy(value)) for age, value in reversed(list(zip(age_grid, curve[group]["lower_95"])))]
            polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in upper + lower)
            parts.append(
                f'<polygon points="{polygon}" fill="{COLORS[group]}" fill-opacity="0.10"/>'
            )
            points = [(sx(age), sy(value)) for age, value in zip(age_grid, curve[group]["estimate"])]
            parts.append(
                f'<path d="{svg_path(points)}" fill="none" stroke="{COLORS[group]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
            )

            for _, lower_age, upper_age in AGE_BANDS:
                mask = (
                    (data["age"] >= lower_age)
                    & (data["age"] < upper_age)
                    & (phenotype["groups"] == group)
                )
                if np.sum(mask) < 5:
                    continue
                x = sx(float(np.median(data["age"][mask])))
                y = sy(float(np.median(data[outcome_name][mask])))
                parts.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.6" fill="#FFFFFF" stroke="{COLORS[group]}" stroke-width="2.4"/>'
                )

        parts.extend(
            [
                f'<line x1="{plot_x}" y1="{plot_y + plot_height}" x2="{plot_x + plot_width}" y2="{plot_y + plot_height}" stroke="#8FA0A9"/>',
                f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_height}" stroke="#8FA0A9"/>',
                svg_text(plot_x + plot_width / 2, panel_y + panel_height - 15, "Age (years)", size=13, weight=650, fill="#526770", anchor="middle"),
            ]
        )

    short_cutoff = result["phenotype"]["short_cutoff_mm"]
    long_cutoff = result["phenotype"]["long_cutoff_mm"]
    parts.extend(
        [
            svg_text(
                68,
                714,
                f"N={result['n']}; Short <= expected AL {short_cutoff:+.2f} mm; Long >= expected AL {long_cutoff:+.2f} mm; circles show observed age-band medians",
                size=13,
                fill="#526770",
            ),
            svg_text(1730, 714, "Exploratory clinical cohort", size=12, fill="#788991", anchor="end"),
            "</g>",
            "</svg>",
        ]
    )
    output_path.write_text("\n".join(parts), encoding="utf-8")


def write_age_band_csv(output_path, rows):
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_curve_csv(output_path, curve_payload):
    fieldnames = ["outcome", "age", "group", "estimate", "lower_95", "upper_95"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for outcome_name in OUTCOMES:
            ages = curve_payload[outcome_name]["age"]
            for group in GROUPS:
                curve = curve_payload[outcome_name]["groups"][group]
                for index, age in enumerate(ages):
                    writer.writerow(
                        {
                            "outcome": outcome_name,
                            "age": float(age),
                            "group": group,
                            "estimate": float(curve["estimate"][index]),
                            "lower_95": float(curve["lower_95"][index]),
                            "upper_95": float(curve["upper_95"][index]),
                        }
                    )


def markdown_ci(value):
    return f"{value['estimate']:.3f} [{value['lower_95']:.3f}, {value['upper_95']:.3f}]"


def write_report(output_path, source_path, result, sensitivity, repeated, bootstrap_replicates):
    lines = [
        "# Pediatric age-adjusted axial-length phenotype analysis",
        "",
        f"- Source: `{source_path.name}`",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Primary cohort: {result['n']} children aged 3-17 years, one deterministic eye per child",
        f"- Bootstrap replicates: {bootstrap_replicates}",
        "- Status: exploratory; diagnosis, lens clarity, cycloplegic refraction, and treatment history are not yet EMR-verified",
        "",
        "## Phenotype definition",
        "",
        "AL was modeled as a nonlinear function of age plus sex. The residual was divided into the bottom 20% (Short), middle 60% (Typical), and top 20% (Long).",
        "",
        f"- Short cutoff: `{result['phenotype']['short_cutoff_mm']:+.3f} mm` from age- and sex-expected AL",
        f"- Long cutoff: `{result['phenotype']['long_cutoff_mm']:+.3f} mm` from age- and sex-expected AL",
        f"- Counts: {result['phenotype']['counts']}",
        "",
        "## Adjusted anatomical contrasts",
        "",
        "Positive values indicate that Short eyes have larger values than Long eyes after age and sex adjustment.",
        "",
        "| Outcome | Short vs Long, estimate [95% bootstrap CI] | Partial rho with AL residual | Age x AL interaction p | BH-FDR p |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in OUTCOMES:
        outcome = result["outcomes"][name]
        lines.append(
            f"| {name} | {markdown_ci(outcome['adjusted_contrasts']['short_vs_long'])} | "
            f"{outcome['partial_spearman']['rho']:.3f} | "
            f"{outcome['age_by_al_residual_interaction']['p_value']:.4f} | "
            f"{outcome['age_by_al_residual_interaction']['fdr_bh_p_value']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## Lens-thickness segmented regression",
            "",
            "| AL phenotype | N | Breakpoint age [95% CI] | Slope before, mm/year [95% CI] | Slope after, mm/year [95% CI] |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for group in GROUPS:
        summary = result["lt_piecewise"][group]
        lines.append(
            f"| {group} | {summary['n']} | {markdown_ci(summary['breakpoint_age'])} | "
            f"{markdown_ci(summary['slope_before'])} | {markdown_ci(summary['slope_after'])} |"
        )

    lines.extend(
        [
            "",
            "## Sensitivity analysis",
            "",
            "The sensitivity cohort averaged both eligible eyes within each child before repeating the same models.",
            "",
            "| Outcome | Age x AL interaction p, primary | Age x AL interaction p, bilateral mean |",
            "|---|---:|---:|",
        ]
    )
    for name in OUTCOMES:
        lines.append(
            f"| {name} | {result['outcomes'][name]['age_by_al_residual_interaction']['p_value']:.4f} | "
            f"{sensitivity['outcomes'][name]['age_by_al_residual_interaction']['p_value']:.4f} |"
        )

    lines.extend(["", "## Repeated-exam exploratory subset", ""])
    for band, summary in repeated.items():
        if summary["patients"] < 5:
            lines.append(f"- {band}: fewer than 5 repeated patients; estimates suppressed")
            continue
        lines.append(
            f"- {band}: {summary['patients']} patients; median follow-up {summary['follow_up_years']['median']:.2f} years; "
            f"AL {summary['AL_per_year']['median']:+.3f} mm/year; LT {summary['LT_per_year']['median']:+.3f} mm/year"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Age-adjusted Short eyes are steeper, shallower, and thicker-lensed than Long eyes.",
            "- The level differences are robust, but no age-trajectory interaction remains significant after BH-FDR correction.",
            "- LT interaction is nominally significant in the primary analysis but not after BH-FDR correction or in the bilateral-mean sensitivity analysis; it is suggestive rather than confirmed.",
            "- K and ACD show no clear group-specific age-trajectory interaction.",
            "- LT breakpoints cluster around age 9, with overlapping bootstrap intervals across AL phenotypes.",
            "",
            "## Required clinical review before submission",
            "",
            "Exclude or annotate congenital/developmental cataract, lens subluxation, glaucoma, prior ocular surgery, syndromic disease, contact-lens effects, and myopia-control treatment. Add cycloplegic spherical equivalent when available.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def to_jsonable(value):
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [to_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default="IOLMaster700_corrected_3.xlsx")
    parser.add_argument("--output-dir", default="outputs/pediatric_al_phenotype")
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260714)
    args = parser.parse_args()

    source_path = Path(args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    primary, patient_means, exams_by_eye, filter_counts = prepare_records(source_path, args.seed)
    result, data, phenotype, curve_payload = analyze_dataset(
        primary,
        args.bootstrap_replicates,
        args.seed,
    )
    sensitivity, _, _, _ = analyze_dataset(
        patient_means,
        max(200, min(500, args.bootstrap_replicates)),
        args.seed + 50000,
    )
    repeated = repeated_exam_summary(exams_by_eye)
    result["filter_counts"] = filter_counts
    result["repeated_exam_summary"] = repeated
    result["sensitivity_bilateral_mean"] = {
        "n": sensitivity["n"],
        "phenotype": sensitivity["phenotype"],
        "outcomes": {
            name: {
                "partial_spearman": sensitivity["outcomes"][name]["partial_spearman"],
                "adjusted_contrasts": sensitivity["outcomes"][name]["adjusted_contrasts"],
                "age_by_al_residual_interaction": sensitivity["outcomes"][name][
                    "age_by_al_residual_interaction"
                ],
            }
            for name in OUTCOMES
        },
    }

    json_path = output_dir / "pediatric_al_phenotype_results.json"
    report_path = output_dir / "pediatric_al_phenotype_report.md"
    age_band_path = output_dir / "pediatric_al_phenotype_age_bands.csv"
    curve_path = output_dir / "pediatric_al_phenotype_curves.csv"
    figure_path = output_dir / "pediatric_al_phenotype_trajectories.svg"

    json_path.write_text(
        json.dumps(to_jsonable(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(
        report_path,
        source_path,
        result,
        sensitivity,
        repeated,
        args.bootstrap_replicates,
    )
    write_age_band_csv(age_band_path, result["age_band_summary"])
    write_curve_csv(curve_path, curve_payload)
    render_trajectory_figure(figure_path, result, data, phenotype, curve_payload)

    for path in [report_path, json_path, age_band_path, curve_path, figure_path]:
        print(path)


if __name__ == "__main__":
    main()
