#!/usr/bin/env python3
"""Analyze familial, lifestyle, and physical-growth factors in the 2012-2014 cohort.

Baseline questionnaire variables are evaluated as predictors of subsequent annual
axial elongation. Changes measured over the same interval are evaluated separately
as concurrent associations and are not described as prospective predictors.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np
from scipy import stats
from sklearn.model_selection import RepeatedKFold

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from modeling.analyze_pediatric_longitudinal_growth import (
        DEFAULT_FOLLOW_SOURCE,
        DEFAULT_SOURCE,
        EYES,
        add_intercept,
        eligible_records,
        fit_age_spline,
        fit_ols,
        load_records,
        matrix,
        nested_comparison,
        solve_ols,
        strip_private_fit_fields,
        winsorize,
    )
    from modeling.train_ood_model import read_xlsx_rows
except ModuleNotFoundError:
    from analyze_pediatric_longitudinal_growth import (
        DEFAULT_FOLLOW_SOURCE,
        DEFAULT_SOURCE,
        EYES,
        add_intercept,
        eligible_records,
        fit_age_spline,
        fit_ols,
        load_records,
        matrix,
        nested_comparison,
        solve_ols,
        strip_private_fit_fields,
        winsorize,
    )
    from train_ood_model import read_xlsx_rows


ACTIVITY_CODE_LABELS = {
    1: "<=1 hour/day",
    2: ">1 to 2 hours/day",
    3: ">2 to 3 hours/day",
    4: ">3 to 4 hours/day",
    5: ">4 hours/day",
}
BASELINE_ACTIVITY_COLUMNS = {
    "study_category": "studyhour",
    "tv_category": "TVhour",
    "computer_category": "Comhour",
    "smartphone_category": "Smarthour",
    "outdoor_category": "Outdoorhour",
}
FOLLOW_ACTIVITY_COLUMNS = {
    "study_category": "StudyH",
    "tv_category": "TVH",
    "computer_category": "ComH",
    "smartphone_category": "SmarH",
    "outdoor_category": "OutdoorH",
}
BASELINE_MODEL_ORDER = [
    "demographics",
    "al",
    "biometry",
    "family",
    "lifestyle",
    "full",
    "full_school",
    "full_lifestyle_categorical",
]
STATE_MODEL_ORDER = [
    "demographics",
    "family",
    "lifestyle",
    "full",
    "full_school",
]
CONCURRENT_MODEL_ORDER = [
    "baseline_full",
    "change_lifestyle",
    "change_body",
    "change_all",
    "change_all_school",
]
SURVEY_PREDICTOR_NAMES = [
    "parent_surgery_myopia_count",
    *BASELINE_ACTIVITY_COLUMNS,
    "height_per_10cm",
    "bmi_per_5",
]
CHANGE_PREDICTOR_NAMES = [
    *(f"{name}_change_per_year" for name in BASELINE_ACTIVITY_COLUMNS),
    "height_growth_cm_per_year",
    "bmi_change_per_year",
]
DISPLAY_LABELS = {
    "parent_surgery_myopia_count": "Parent(s) with myopia-related refractive surgery, per parent",
    "study_category": "Study/homework, per category",
    "tv_category": "Television, per category",
    "computer_category": "Computer use, per category",
    "smartphone_category": "Smartphone use, per category",
    "outdoor_category": "Outdoor activity, per category",
    "height_per_10cm": "Height, per 10 cm",
    "bmi_per_5": "BMI, per 5 kg/m2",
    "study_category_change_per_year": "Study/homework category change per year",
    "tv_category_change_per_year": "Television category change per year",
    "computer_category_change_per_year": "Computer category change per year",
    "smartphone_category_change_per_year": "Smartphone category change per year",
    "outdoor_category_change_per_year": "Outdoor category change per year",
    "height_growth_cm_per_year": "Height growth, per cm/year",
    "bmi_change_per_year": "BMI change, per unit/year",
}


def as_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def require_number(row, column, patient_id):
    value = as_number(row.get(column))
    if value is None:
        raise ValueError(f"Missing {column} for patient {patient_id}")
    return value


def parent_yes(value, patient_id, column):
    code = int(require_number({column: value}, column, patient_id))
    if code not in (1, 2):
        raise ValueError(f"Unexpected {column} code {code} for patient {patient_id}")
    return 1.0 if code == 1 else 0.0


def activity_code(row, column, patient_id):
    code = int(require_number(row, column, patient_id))
    if code not in ACTIVITY_CODE_LABELS:
        raise ValueError(f"Unexpected {column} code {code} for patient {patient_id}")
    return float(code)


def cohen_kappa(first, second):
    first = list(first)
    second = list(second)
    categories = sorted(set(first) | set(second))
    observed = sum(a == b for a, b in zip(first, second)) / len(first)
    first_counts = Counter(first)
    second_counts = Counter(second)
    expected = sum(
        first_counts[value] * second_counts[value] for value in categories
    ) / (len(first) ** 2)
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def bh_adjust(p_values):
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for reverse_rank, index in enumerate(order[::-1], start=1):
        rank = len(values) - reverse_rank + 1
        candidate = values[index] * len(values) / rank
        running = min(running, candidate)
        adjusted[index] = min(running, 1.0)
    return adjusted


def attach_survey(records, source_path):
    rows = {
        str(row.get("ID") or "").strip(): row
        for row in read_xlsx_rows(source_path)
        if str(row.get("ID") or "").strip()
    }
    augmented = []
    for source_record in records:
        record = dict(source_record)
        patient_id = record["patient_id"]
        row = rows.get(patient_id)
        if row is None:
            raise ValueError(f"Survey row not found for patient {patient_id}")

        father = parent_yes(row.get("paternalM"), patient_id, "paternalM")
        mother = parent_yes(row.get("martnalM"), patient_id, "martnalM")
        father_follow = parent_yes(row.get("parMyo"), patient_id, "parMyo")
        mother_follow = parent_yes(row.get("matMyo"), patient_id, "matMyo")
        record.update(
            {
                "father_surgery_myopia": father,
                "mother_surgery_myopia": mother,
                "parent_surgery_myopia_count": father + mother,
                "father_surgery_myopia_follow": father_follow,
                "mother_surgery_myopia_follow": mother_follow,
            }
        )

        for name, baseline_column in BASELINE_ACTIVITY_COLUMNS.items():
            follow_column = FOLLOW_ACTIVITY_COLUMNS[name]
            baseline = activity_code(row, baseline_column, patient_id)
            follow = activity_code(row, follow_column, patient_id)
            record[name] = baseline
            record[f"{name}_follow"] = follow
            record[f"{name}_change"] = follow - baseline
            record[f"{name}_change_per_year"] = (follow - baseline) / record["interval"]

        height = require_number(row, "Height", patient_id)
        height_follow = require_number(row, "Height14", patient_id)
        weight = require_number(row, "Weight", patient_id)
        weight_follow = require_number(row, "Weight14", patient_id)
        bmi = require_number(row, "BMI_12", patient_id)
        bmi_follow = require_number(row, "BMI14", patient_id)
        if not (100 <= height <= 190 and 100 <= height_follow <= 200):
            raise ValueError(f"Implausible height for patient {patient_id}")
        if not (10 <= weight <= 120 and 10 <= weight_follow <= 150):
            raise ValueError(f"Implausible weight for patient {patient_id}")
        if not (10 <= bmi <= 40 and 10 <= bmi_follow <= 45):
            raise ValueError(f"Implausible BMI for patient {patient_id}")
        record.update(
            {
                "height_cm": height,
                "height_follow_cm": height_follow,
                "height_per_10cm": height / 10.0,
                "weight_kg": weight,
                "weight_follow_kg": weight_follow,
                "bmi": bmi,
                "bmi_follow": bmi_follow,
                "bmi_per_5": bmi / 5.0,
                "height_growth_cm_per_year": (height_follow - height) / record["interval"],
                "weight_growth_kg_per_year": (weight_follow - weight) / record["interval"],
                "bmi_change_per_year": (bmi_follow - bmi) / record["interval"],
            }
        )
        augmented.append(record)
    return augmented


def survey_reliability(records):
    result = {}
    for baseline, follow in (
        ("father_surgery_myopia", "father_surgery_myopia_follow"),
        ("mother_surgery_myopia", "mother_surgery_myopia_follow"),
        *((name, f"{name}_follow") for name in BASELINE_ACTIVITY_COLUMNS),
    ):
        first = matrix(records, baseline)
        second = matrix(records, follow)
        result[baseline] = {
            "agreement": float(np.mean(first == second)),
            "cohen_kappa": float(cohen_kappa(first, second)),
            "spearman_rho": float(stats.spearmanr(first, second).statistic),
        }
    return result


def school_names(records):
    return sorted({record["school"] for record in records if record["school"]})


def common_design(train_records, test_records):
    train_age = matrix(train_records, "age")
    test_age = matrix(test_records, "age")
    spline = fit_age_spline(train_age)
    train_basis = spline.transform(train_age)
    test_basis = spline.transform(test_age)
    names = [f"age_rcs_{index + 1}" for index in range(train_basis.shape[1])]
    train = np.column_stack(
        [train_basis, matrix(train_records, "female"), matrix(train_records, "interval")]
    )
    test = np.column_stack(
        [test_basis, matrix(test_records, "female"), matrix(test_records, "interval")]
    )
    return train, test, [*names, "female", "interval_years"]


def append_features(train_x, test_x, names, train_records, test_records, features):
    if not features:
        return train_x, test_x, list(names)
    train_values = np.column_stack([matrix(train_records, key) for key in features])
    test_values = np.column_stack([matrix(test_records, key) for key in features])
    return (
        np.column_stack([train_x, train_values]),
        np.column_stack([test_x, test_values]),
        [*names, *features],
    )


def append_school_dummies(train_x, test_x, names, train_records, test_records, schools):
    if len(schools) < 2:
        return train_x, test_x, list(names)
    levels = schools[1:]
    train_values = np.column_stack(
        [[float(record["school"] == level) for record in train_records] for level in levels]
    )
    test_values = np.column_stack(
        [[float(record["school"] == level) for record in test_records] for level in levels]
    )
    return (
        np.column_stack([train_x, train_values]),
        np.column_stack([test_x, test_values]),
        [*names, *(f"school_{level}" for level in levels)],
    )


def append_activity_dummies(train_x, test_x, names, train_records, test_records):
    train_columns = []
    test_columns = []
    dummy_names = []
    for feature in BASELINE_ACTIVITY_COLUMNS:
        for level in (2, 3, 4, 5):
            train_columns.append(
                [float(record[feature] == level) for record in train_records]
            )
            test_columns.append(
                [float(record[feature] == level) for record in test_records]
            )
            dummy_names.append(f"{feature}_{level}")
    return (
        np.column_stack([train_x, np.column_stack(train_columns)]),
        np.column_stack([test_x, np.column_stack(test_columns)]),
        [*names, *dummy_names],
    )


def baseline_design(train_records, test_records, model_name, schools):
    train_x, test_x, names = common_design(train_records, test_records)
    blocks = {
        "demographics": [],
        "al": ["AL_baseline"],
        "biometry": ["AL_baseline", "K_baseline", "ACD_baseline"],
        "family": [
            "AL_baseline",
            "K_baseline",
            "ACD_baseline",
            "parent_surgery_myopia_count",
        ],
        "lifestyle": [
            "AL_baseline",
            "K_baseline",
            "ACD_baseline",
            "parent_surgery_myopia_count",
            *BASELINE_ACTIVITY_COLUMNS,
        ],
        "full": [
            "AL_baseline",
            "K_baseline",
            "ACD_baseline",
            *SURVEY_PREDICTOR_NAMES,
        ],
        "full_school": [
            "AL_baseline",
            "K_baseline",
            "ACD_baseline",
            *SURVEY_PREDICTOR_NAMES,
        ],
        "full_lifestyle_categorical": [
            "AL_baseline",
            "K_baseline",
            "ACD_baseline",
            "parent_surgery_myopia_count",
            "height_per_10cm",
            "bmi_per_5",
        ],
    }
    train_x, test_x, names = append_features(
        train_x, test_x, names, train_records, test_records, blocks[model_name]
    )
    if model_name == "full_school":
        train_x, test_x, names = append_school_dummies(
            train_x, test_x, names, train_records, test_records, schools
        )
    if model_name == "full_lifestyle_categorical":
        train_x, test_x, names = append_activity_dummies(
            train_x, test_x, names, train_records, test_records
        )
    return train_x, test_x, names


def concurrent_design(train_records, test_records, model_name, schools):
    train_x, test_x, names = baseline_design(
        train_records, test_records, "full", schools
    )
    lifestyle_changes = [
        f"{name}_change_per_year" for name in BASELINE_ACTIVITY_COLUMNS
    ]
    body_changes = ["height_growth_cm_per_year", "bmi_change_per_year"]
    additions = {
        "baseline_full": [],
        "change_lifestyle": lifestyle_changes,
        "change_body": body_changes,
        "change_all": [*lifestyle_changes, *body_changes],
        "change_all_school": [*lifestyle_changes, *body_changes],
    }
    train_x, test_x, names = append_features(
        train_x, test_x, names, train_records, test_records, additions[model_name]
    )
    if model_name == "change_all_school":
        train_x, test_x, names = append_school_dummies(
            train_x, test_x, names, train_records, test_records, schools
        )
    return train_x, test_x, names


def state_design(train_records, test_records, model_name, schools):
    train_age = matrix(train_records, "age")
    test_age = matrix(test_records, "age")
    spline = fit_age_spline(train_age)
    train_basis = spline.transform(train_age)
    test_basis = spline.transform(test_age)
    names = [f"age_rcs_{index + 1}" for index in range(train_basis.shape[1])]
    train_x = np.column_stack([train_basis, matrix(train_records, "female")])
    test_x = np.column_stack([test_basis, matrix(test_records, "female")])
    names.append("female")
    blocks = {
        "demographics": [],
        "family": ["parent_surgery_myopia_count"],
        "lifestyle": ["parent_surgery_myopia_count", *BASELINE_ACTIVITY_COLUMNS],
        "full": [*SURVEY_PREDICTOR_NAMES],
        "full_school": [*SURVEY_PREDICTOR_NAMES],
    }
    train_x, test_x, names = append_features(
        train_x, test_x, names, train_records, test_records, blocks[model_name]
    )
    if model_name == "full_school":
        train_x, test_x, names = append_school_dummies(
            train_x, test_x, names, train_records, test_records, schools
        )
    return train_x, test_x, names


def build_models(records, model_order, design_function, outcome):
    schools = school_names(records)
    fits = {}
    for name in model_order:
        design, _, feature_names = design_function(records, records, name, schools)
        fits[name] = fit_ols(design, outcome, feature_names)
    return fits


def model_comparisons(fits, pairs):
    return {
        label: nested_comparison(fits[reduced], fits[full])
        for label, reduced, full in pairs
    }


def repeated_cross_validation(
    records,
    outcome,
    model_order,
    design_function,
    repeats,
    folds,
    seed,
):
    outcome = np.asarray(outcome, dtype=float)
    schools = school_names(records)
    storage = {name: [] for name in model_order}
    paired_previous = {name: [] for name in model_order[1:]}
    paired_first = {name: [] for name in model_order[1:]}
    indices = np.arange(len(records))
    for repeat in range(repeats):
        predictions = {name: np.full(len(records), np.nan) for name in model_order}
        splitter = RepeatedKFold(
            n_splits=folds,
            n_repeats=1,
            random_state=seed + repeat,
        )
        for train_index, test_index in splitter.split(indices):
            train_records = [records[index] for index in train_index]
            test_records = [records[index] for index in test_index]
            for name in model_order:
                train_x, test_x, _ = design_function(
                    train_records, test_records, name, schools
                )
                beta, _ = solve_ols(train_x, outcome[train_index])
                predictions[name][test_index] = add_intercept(test_x) @ beta

        centered = outcome - np.mean(outcome)
        sst = float(centered @ centered)
        repeat_rmse = {}
        for name in model_order:
            residual = outcome - predictions[name]
            sse = float(residual @ residual)
            repeat_rmse[name] = math.sqrt(float(np.mean(residual**2)))
            storage[name].append(
                {
                    "rmse": repeat_rmse[name],
                    "r2": 1.0 - sse / sst if sst > 0 else 0.0,
                }
            )
        for index, name in enumerate(model_order[1:], start=1):
            previous = model_order[index - 1]
            paired_previous[name].append(repeat_rmse[name] - repeat_rmse[previous])
            paired_first[name].append(repeat_rmse[name] - repeat_rmse[model_order[0]])

    summary = {}
    for name, values in storage.items():
        summary[name] = {}
        for metric in ("rmse", "r2"):
            observed = np.asarray([value[metric] for value in values], dtype=float)
            summary[name][metric] = {
                "mean": float(np.mean(observed)),
                "sd_across_repeats": float(np.std(observed, ddof=1)),
                "lower_95_repeats": float(np.quantile(observed, 0.025)),
                "upper_95_repeats": float(np.quantile(observed, 0.975)),
            }
    def summarize_paired(storage):
        return {
            name: {
                "mean_rmse_difference": float(np.mean(values)),
                "lower_95_repeats": float(np.quantile(values, 0.025)),
                "upper_95_repeats": float(np.quantile(values, 0.975)),
                "fraction_improved": float(np.mean(np.asarray(values) < 0)),
            }
            for name, values in storage.items()
        }

    return {
        "repeats": repeats,
        "folds": folds,
        "models": summary,
        "rmse_differences_vs_previous": summarize_paired(paired_previous),
        "rmse_differences_vs_first_model": summarize_paired(paired_first),
    }


def add_fdr_to_coefficients(fit, names):
    coefficients = fit["coefficients"]
    present = [name for name in names if name in coefficients]
    adjusted = bh_adjust([coefficients[name]["p_value"] for name in present])
    return {
        name: {**coefficients[name], "fdr_p": float(fdr)}
        for name, fdr in zip(present, adjusted)
    }


def sex_specific_parent_fit(records, outcome):
    schools = school_names(records)
    design, _, names = baseline_design(records, records, "full", schools)
    count_index = names.index("parent_surgery_myopia_count")
    design = np.delete(design, count_index, axis=1)
    names.pop(count_index)
    design, _, names = append_features(
        design,
        design,
        names,
        records,
        records,
        ["father_surgery_myopia", "mother_surgery_myopia"],
    )
    return fit_ols(design, outcome, names)


def parent_state_dose_response(records):
    age = matrix(records, "age")
    age_basis = fit_age_spline(age).transform(age)
    parent_count = matrix(records, "parent_surgery_myopia_count")
    design = np.column_stack(
        [
            age_basis,
            matrix(records, "female"),
            parent_count == 1,
            parent_count == 2,
            *(matrix(records, name) for name in BASELINE_ACTIVITY_COLUMNS),
            matrix(records, "height_per_10cm"),
            matrix(records, "bmi_per_5"),
        ]
    )
    names = [
        *(f"age_rcs_{index + 1}" for index in range(age_basis.shape[1])),
        "female",
        "one_parent",
        "two_parents",
        *BASELINE_ACTIVITY_COLUMNS,
        "height_per_10cm",
        "bmi_per_5",
    ]
    fit = fit_ols(design, matrix(records, "AL_baseline"), names)
    groups = {}
    for count in (0, 1, 2):
        values = matrix(
            [record for record in records if record["parent_surgery_myopia_count"] == count],
            "AL_baseline",
        )
        groups[str(count)] = {
            "n": len(values),
            "raw_mean_AL": float(np.mean(values)),
            "raw_sd_AL": float(np.std(values, ddof=1)),
        }
    return {
        "groups": groups,
        "one_parent_vs_none": fit["coefficients"]["one_parent"],
        "two_parents_vs_none": fit["coefficients"]["two_parents"],
    }


def sensitivity_models(analysis_sets):
    output = {}
    baseline_keys = [
        "baseline_AL",
        "female",
        "parent_surgery_myopia_count",
        "study_category",
        "outdoor_category",
        "height_per_10cm",
        "bmi_per_5",
    ]
    change_keys = [
        "study_category_change_per_year",
        "outdoor_category_change_per_year",
        "height_growth_cm_per_year",
        "bmi_change_per_year",
    ]
    for label, (records, outcome) in analysis_sets.items():
        schools = school_names(records)
        baseline_x, _, baseline_names = baseline_design(
            records, records, "full", schools
        )
        change_x, _, change_names = concurrent_design(
            records, records, "change_all", schools
        )
        baseline_fit = fit_ols(baseline_x, outcome, baseline_names)
        change_fit = fit_ols(change_x, outcome, change_names)
        state_x, _, state_names = state_design(
            records, records, "full", schools
        )
        state_fit = fit_ols(state_x, matrix(records, "AL_baseline"), state_names)
        output[label] = {
            "n": len(records),
            "baseline": {
                key: baseline_fit["coefficients"].get(key) for key in baseline_keys
            },
            "concurrent": {
                key: change_fit["coefficients"].get(key) for key in change_keys
            },
            "state": {
                key: state_fit["coefficients"].get(key)
                for key in ("female", "parent_surgery_myopia_count", "study_category")
            },
            "baseline_adjusted_r2": baseline_fit["adjusted_r2"],
            "concurrent_adjusted_r2": change_fit["adjusted_r2"],
            "state_adjusted_r2": state_fit["adjusted_r2"],
        }
    return output


def legacy_correlations(records):
    total_change = matrix(records, "AL_rate") * matrix(records, "interval")
    annual_change = matrix(records, "AL_rate")
    output = {}
    for name in (
        "study_category",
        "study_category_follow",
        "study_category_change",
        "outdoor_category",
        "outdoor_category_follow",
        "parent_surgery_myopia_count",
    ):
        values = matrix(records, name)
        output[name] = {}
        for outcome_name, outcome in (
            ("two_year_AL_change", total_change),
            ("annual_AL_change", annual_change),
        ):
            pearson = stats.pearsonr(values, outcome)
            spearman = stats.spearmanr(values, outcome)
            output[name][outcome_name] = {
                "pearson_r": float(pearson.statistic),
                "pearson_p": float(pearson.pvalue),
                "spearman_rho": float(spearman.statistic),
                "spearman_p": float(spearman.pvalue),
            }
    return output


def write_model_csv(path, fits, cv):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "n",
                "adjusted_r2",
                "in_sample_rmse",
                "cv_rmse",
                "cv_r2",
                "cv_rmse_lower_repeat_percentile",
                "cv_rmse_upper_repeat_percentile",
            ]
        )
        for name, fit in fits.items():
            metrics = cv["models"][name]
            writer.writerow(
                [
                    name,
                    fit["n"],
                    fit["adjusted_r2"],
                    fit["rmse_in_sample"],
                    metrics["rmse"]["mean"],
                    metrics["r2"]["mean"],
                    metrics["rmse"]["lower_95_repeats"],
                    metrics["rmse"]["upper_95_repeats"],
                ]
            )


def write_coefficient_csv(path, coefficient_groups):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "analysis",
                "predictor",
                "label",
                "estimate",
                "lower_95",
                "upper_95",
                "unit",
                "p_value",
                "fdr_p",
            ]
        )
        for analysis, coefficients in coefficient_groups.items():
            for name, value in coefficients.items():
                writer.writerow(
                    [
                        analysis,
                        name,
                        DISPLAY_LABELS.get(name, name),
                        value["estimate"],
                        value["lower_95"],
                        value["upper_95"],
                        "mm" if analysis == "baseline_AL_state" else "mm/year",
                        value["p_value"],
                        value.get("fdr_p", ""),
                    ]
                )


def plot_cv_performance(path_base, state_cv, baseline_cv, concurrent_cv):
    colors = ["#607D8B", "#087F8C", "#2A6FBB", "#7C6AAB", "#C56A3D", "#A33A32"]
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for axis, cv, order, title in (
        (
            axes[0],
            state_cv,
            STATE_MODEL_ORDER[:4],
            "Attained AL state",
        ),
        (
            axes[1],
            baseline_cv,
            BASELINE_MODEL_ORDER[:6],
            "Prospective baseline models",
        ),
        (
            axes[2],
            concurrent_cv,
            CONCURRENT_MODEL_ORDER[:4],
            "Concurrent change models",
        ),
    ):
        values = [cv["models"][name]["r2"]["mean"] for name in order]
        labels = [name.replace("demographics", "demo").replace("change_", "+change ") for name in order]
        bars = axis.bar(range(len(order)), values, color=colors[: len(order)], width=0.72)
        axis.axhline(0, color="#384B55", linewidth=0.8)
        axis.set_xticks(range(len(order)), labels, rotation=28, ha="right")
        axis.set_ylabel("Repeated-CV R2")
        axis.set_title(title, fontsize=12, weight="bold")
        axis.grid(axis="y", color="#D9E1E5", linewidth=0.7)
        axis.set_axisbelow(True)
        upper = max(values) if values else 0.0
        axis.set_ylim(min(0.0, min(values) * 1.2), upper * 1.28 + 0.002)
        for bar, value in zip(bars, values):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.004 if value >= 0 else value - 0.004,
                f"{value:.3f}",
                ha="center",
                va="bottom" if value >= 0 else "top",
                fontsize=9,
            )
    figure.suptitle(
        "State and velocity: incremental information from survey data",
        fontsize=15,
        weight="bold",
        y=0.99,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    for extension in ("png", "svg"):
        figure.savefig(path_base.with_suffix(f".{extension}"), dpi=300, bbox_inches="tight")
    plt.close(figure)


def plot_forest(path_base, coefficient_groups):
    figure, axes = plt.subplots(len(coefficient_groups), 1, figsize=(11.5, 16))
    for axis, (title, details) in zip(axes, coefficient_groups.items()):
        coefficients = details["coefficients"]
        names = list(coefficients)
        estimates = np.asarray([coefficients[name]["estimate"] for name in names])
        lower = np.asarray([coefficients[name]["lower_95"] for name in names])
        upper = np.asarray([coefficients[name]["upper_95"] for name in names])
        positions = np.arange(len(names))[::-1]
        colors = [
            "#B13A32" if coefficients[name].get("fdr_p", 1.0) < 0.05 else "#087F8C"
            for name in names
        ]
        axis.axvline(0, color="#384B55", linewidth=1)
        for y, estimate, lo, hi, color in zip(positions, estimates, lower, upper, colors):
            axis.errorbar(
                estimate,
                y,
                xerr=[[estimate - lo], [hi - estimate]],
                fmt="o",
                color=color,
                ecolor=color,
                capsize=3,
                markersize=5,
            )
        axis.set_yticks(positions, [DISPLAY_LABELS.get(name, name) for name in names])
        axis.set_xlabel(details["x_label"])
        axis.set_title(title, fontsize=12, weight="bold")
        axis.grid(axis="x", color="#D9E1E5", linewidth=0.7)
        axis.set_axisbelow(True)
    figure.suptitle(
        "Familial, lifestyle, and physical-growth associations",
        fontsize=15,
        weight="bold",
        y=1.01,
    )
    figure.tight_layout(rect=(0.30, 0, 1, 0.97), h_pad=3.0)
    for extension in ("png", "svg"):
        figure.savefig(path_base.with_suffix(f".{extension}"), dpi=300, bbox_inches="tight")
    plt.close(figure)


def coefficient_text(value, digits=4):
    return (
        f"{value['estimate']:+.{digits}f} "
        f"[{value['lower_95']:+.{digits}f}, {value['upper_95']:+.{digits}f}]"
    )


def write_report(path, source_path, result):
    state_fits = result["state_models"]["fits"]
    state_cv = result["state_models"]["cross_validation"]["models"]
    state_comparisons = result["state_models"]["comparisons"]
    state_coefficients = result["state_models"]["survey_coefficients_fdr"]
    baseline_fits = result["baseline_models"]["fits"]
    baseline_cv = result["baseline_models"]["cross_validation"]["models"]
    baseline_comparisons = result["baseline_models"]["comparisons"]
    concurrent_fits = result["concurrent_models"]["fits"]
    concurrent_cv = result["concurrent_models"]["cross_validation"]["models"]
    concurrent_comparisons = result["concurrent_models"]["comparisons"]
    baseline_coefficients = result["baseline_models"]["survey_coefficients_fdr"]
    change_coefficients = result["concurrent_models"]["change_coefficients_fdr"]

    lines = [
        "# Pediatric familial, lifestyle, and physical-growth analysis",
        "",
        f"- Source: `{source_path.name}`",
        f"- Primary cohort: {result['cohort']['primary_n']} children",
        "- Outcome: patient-level mean of bilateral annual AL change (mm/year)",
        "- Questionnaire code labels were recovered from the original SPSS metadata; source-record adjudication remains pending",
        "- Parental history means myopia-related refractive surgery, not all parental myopia",
        "- Activity categories are ordinal: <=1, <=2, <=3, <=4, and >=5 hours/day",
        "",
        "## Main answer",
        "",
        "The clearest positive result is state-velocity separation: the familial proxy is strongly related to attained baseline AL but not to subsequent AL velocity.",
        "",
        f"- Familial proxy and baseline AL: {coefficient_text(state_coefficients['parent_surgery_myopia_count'], 3)} mm per parent; "
        f"P={state_coefficients['parent_surgery_myopia_count']['p_value']:.4g}, FDR P={state_coefficients['parent_surgery_myopia_count']['fdr_p']:.4g}",
        f"- Familial proxy and subsequent AL velocity: {coefficient_text(baseline_coefficients['parent_surgery_myopia_count'])} mm/year per parent; "
        f"P={baseline_coefficients['parent_surgery_myopia_count']['p_value']:.4g}",
        f"- Female sex and baseline AL: {coefficient_text(state_fits['full']['coefficients']['female'], 3)} mm; female sex and subsequent velocity: "
        f"{coefficient_text(baseline_fits['full']['coefficients']['female'])} mm/year",
        "",
    ]
    added_blocks = [
        ("Family history", "add_family_after_biometry", "family"),
        ("Baseline lifestyle", "add_lifestyle_after_family", "lifestyle"),
        ("Baseline body size", "add_body_after_lifestyle", "full"),
    ]
    for label, comparison_name, model_name in added_blocks:
        comparison = baseline_comparisons[comparison_name]
        lines.append(
            f"- {label}: partial R2 {comparison['partial_r2']:.4f}, "
            f"P={comparison['p_value']:.4g}; CV R2 {baseline_cv[model_name]['r2']['mean']:.4f}, "
            f"CV RMSE {baseline_cv[model_name]['rmse']['mean']:.4f} mm/year"
        )
    lines.extend(
        [
            "",
            "Baseline questionnaire data should be interpreted as prospective predictors. "
            "Questionnaire and physical changes measured over the same 2-year interval are concurrent associations only.",
            "",
            "## Attained baseline AL state",
            "",
            "| Model | Adjusted R2 | CV R2 | CV RMSE, mm |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in STATE_MODEL_ORDER:
        fit = state_fits[name]
        cv = state_cv[name]
        lines.append(
            f"| {name} | {fit['adjusted_r2']:.4f} | {cv['r2']['mean']:.4f} | {cv['rmse']['mean']:.4f} |"
        )
    lines.extend(
        [
            "",
            "### Survey and body-size associations with baseline AL",
            "",
            "| Predictor | Estimate [95% CI], mm | P | FDR P |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, value in state_coefficients.items():
        lines.append(
            f"| {DISPLAY_LABELS.get(name, name)} | {coefficient_text(value, 3)} | "
            f"{value['p_value']:.4g} | {value['fdr_p']:.4g} |"
        )
    dose = result["state_models"]["parent_dose_response"]
    lines.extend(
        [
            "",
            "### Familial-proxy dose response",
            "",
            "| Parents with myopia-related refractive surgery | N | Raw mean AL, mm | Adjusted difference vs none, mm |",
            "|---:|---:|---:|---:|",
            f"| 0 | {dose['groups']['0']['n']} | {dose['groups']['0']['raw_mean_AL']:.3f} | Reference |",
            f"| 1 | {dose['groups']['1']['n']} | {dose['groups']['1']['raw_mean_AL']:.3f} | {coefficient_text(dose['one_parent_vs_none'], 3)} |",
            f"| 2 | {dose['groups']['2']['n']} | {dose['groups']['2']['raw_mean_AL']:.3f} | {coefficient_text(dose['two_parents_vs_none'], 3)} |",
        ]
    )
    lines.extend(
        [
            "",
            "## Baseline prediction models",
            "",
            "| Model | Adjusted R2 | CV R2 | CV RMSE |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in BASELINE_MODEL_ORDER:
        fit = baseline_fits[name]
        cv = baseline_cv[name]
        lines.append(
            f"| {name} | {fit['adjusted_r2']:.4f} | {cv['r2']['mean']:.4f} | {cv['rmse']['mean']:.4f} |"
        )
    lines.extend(
        [
            "",
            "### Baseline survey and body-size coefficients",
            "",
            "| Predictor | Estimate [95% CI], mm/year | P | FDR P |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, value in baseline_coefficients.items():
        lines.append(
            f"| {DISPLAY_LABELS.get(name, name)} | {coefficient_text(value)} | "
            f"{value['p_value']:.4g} | {value['fdr_p']:.4g} |"
        )
    lines.extend(
        [
            "",
            "## Concurrent changes over the same interval",
            "",
            "| Model | Adjusted R2 | CV R2 | CV RMSE |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in CONCURRENT_MODEL_ORDER:
        fit = concurrent_fits[name]
        cv = concurrent_cv[name]
        lines.append(
            f"| {name} | {fit['adjusted_r2']:.4f} | {cv['r2']['mean']:.4f} | {cv['rmse']['mean']:.4f} |"
        )
    lines.extend(
        [
            "",
            "### Concurrent-change coefficients",
            "",
            "| Predictor | Estimate [95% CI], mm/year | P | FDR P |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, value in change_coefficients.items():
        lines.append(
            f"| {DISPLAY_LABELS.get(name, name)} | {coefficient_text(value)} | "
            f"{value['p_value']:.4g} | {value['fdr_p']:.4g} |"
        )
    lines.extend(
        [
            "",
            "## Block tests",
            "",
            "| Block | Partial R2 | P |",
            "|---|---:|---:|",
        ]
    )
    for name, comparison in {**baseline_comparisons, **concurrent_comparisons}.items():
        lines.append(
            f"| {name} | {comparison['partial_r2']:.4f} | {comparison['p_value']:.4g} |"
        )
    for name, comparison in state_comparisons.items():
        lines.append(
            f"| state_{name} | {comparison['partial_r2']:.4f} | {comparison['p_value']:.4g} |"
        )
    lines.extend(
        [
            "",
            "## Legacy correlation reproduction",
            "",
            "The earlier simple correlation used questionnaire information measured at the 2-year visit. That variable overlaps the outcome interval and is not a baseline predictor.",
            "",
            "| Analysis set | Predictor | Pearson r with 2-year AL change | P |",
            "|---|---|---:|---:|",
        ]
    )
    for set_name, correlations in result["legacy_correlations"].items():
        for name in ("study_category", "study_category_follow", "study_category_change"):
            value = correlations[name]["two_year_AL_change"]
            lines.append(
                f"| {set_name} | {name} | {value['pearson_r']:.3f} | {value['pearson_p']:.4g} |"
            )
    lines.extend(
        [
            "",
            "## Questionnaire reliability",
            "",
            "| Baseline variable | Exact agreement | Cohen kappa | Spearman rho |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, value in result["questionnaire_reliability"].items():
        lines.append(
            f"| {name} | {value['agreement']:.3f} | {value['cohen_kappa']:.3f} | {value['spearman_rho']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- The parental variable is a low-sensitivity familial proxy because it requires prior refractive surgery.",
            "- A one-category activity coefficient assumes an ordinal linear trend; the categorical sensitivity model tests this assumption.",
            "- Lifestyle changes and body growth occurred during the AL-growth interval and cannot establish temporal causality.",
            "- Questionnaire measurement reliability is limited, especially for lifestyle categories.",
            "- Cross-validated performance, not nominal P values alone, determines practical predictive value.",
            "- Cycloplegic refraction was unavailable, so residual confounding by baseline refractive status remains important.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_cohort(records):
    return {
        "n": len(records),
        "age_mean": float(np.mean(matrix(records, "age"))),
        "female_n": int(np.sum(matrix(records, "female"))),
        "followup_years_median": float(np.median(matrix(records, "interval"))),
        "annual_al_growth_mean": float(np.mean(matrix(records, "AL_rate"))),
        "annual_al_growth_sd": float(np.std(matrix(records, "AL_rate"), ddof=1)),
        "parent_count_distribution": {
            str(int(value)): int(count)
            for value, count in sorted(Counter(matrix(records, "parent_surgery_myopia_count")).items())
        },
        "school_counts": dict(Counter(record["school"] for record in records)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default=DEFAULT_SOURCE)
    parser.add_argument("--follow-source", default=DEFAULT_FOLLOW_SOURCE)
    parser.add_argument("--output-dir", default="outputs/pediatric_survey_growth")
    parser.add_argument("--cv-repeats", type=int, default=100)
    parser.add_argument("--cv-folds", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    source_path = Path(args.source)
    follow_path = Path(args.follow_source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_records, loader_exclusions = load_records(source_path, follow_path)
    records = attach_survey(raw_records, source_path)
    eligible = eligible_records(records)
    name_matched = [record for record in eligible if record["name_match"]]
    physiologic = [
        record for record in name_matched if record["physiologic_al_model"]
    ]
    primary = [
        record
        for record in physiologic
        if all(-1.00 <= record[f"AL_rate_{eye}"] <= 1.50 for eye in EYES)
        and record["AL_rate_discordance"] <= 1.00
    ]
    hard_qc = [record for record in name_matched if record["hard_al_qc"]]
    winsorized, winsor_limits = winsorize(matrix(physiologic, "AL_rate"))
    outcome = matrix(primary, "AL_rate")

    baseline_fits = build_models(
        primary, BASELINE_MODEL_ORDER, baseline_design, outcome
    )
    baseline_comparisons = model_comparisons(
        baseline_fits,
        [
            ("add_AL_after_demographics", "demographics", "al"),
            ("add_K_ACD_after_AL", "al", "biometry"),
            ("add_family_after_biometry", "biometry", "family"),
            ("add_lifestyle_after_family", "family", "lifestyle"),
            ("add_body_after_lifestyle", "lifestyle", "full"),
            ("add_school_fixed_effects", "full", "full_school"),
        ],
    )
    baseline_cv = repeated_cross_validation(
        primary,
        outcome,
        BASELINE_MODEL_ORDER,
        baseline_design,
        args.cv_repeats,
        args.cv_folds,
        args.seed,
    )

    state_outcome = matrix(primary, "AL_baseline")
    state_fits = build_models(primary, STATE_MODEL_ORDER, state_design, state_outcome)
    state_comparisons = model_comparisons(
        state_fits,
        [
            ("add_family_after_demographics", "demographics", "family"),
            ("add_lifestyle_after_family", "family", "lifestyle"),
            ("add_body_after_lifestyle", "lifestyle", "full"),
            ("add_school_fixed_effects", "full", "full_school"),
        ],
    )
    state_cv = repeated_cross_validation(
        primary,
        state_outcome,
        STATE_MODEL_ORDER,
        state_design,
        args.cv_repeats,
        args.cv_folds,
        args.seed + 20000,
    )
    state_coefficients = add_fdr_to_coefficients(
        state_fits["full"], SURVEY_PREDICTOR_NAMES
    )

    concurrent_fits = build_models(
        primary, CONCURRENT_MODEL_ORDER, concurrent_design, outcome
    )
    concurrent_comparisons = {
        "add_lifestyle_changes": nested_comparison(
            concurrent_fits["baseline_full"], concurrent_fits["change_lifestyle"]
        ),
        "add_body_changes": nested_comparison(
            concurrent_fits["baseline_full"], concurrent_fits["change_body"]
        ),
        "add_all_changes": nested_comparison(
            concurrent_fits["baseline_full"], concurrent_fits["change_all"]
        ),
        "add_school_fixed_effects_to_changes": nested_comparison(
            concurrent_fits["change_all"], concurrent_fits["change_all_school"]
        ),
    }
    concurrent_cv = repeated_cross_validation(
        primary,
        outcome,
        CONCURRENT_MODEL_ORDER,
        concurrent_design,
        args.cv_repeats,
        args.cv_folds,
        args.seed + 10000,
    )

    baseline_coefficients = add_fdr_to_coefficients(
        baseline_fits["full"], SURVEY_PREDICTOR_NAMES
    )
    change_coefficients = add_fdr_to_coefficients(
        concurrent_fits["change_all"], CHANGE_PREDICTOR_NAMES
    )
    parental_separate = sex_specific_parent_fit(primary, outcome)

    sensitivity = sensitivity_models(
        {
            "exact_name_matched": (name_matched, matrix(name_matched, "AL_rate")),
            "primary_obvious_outliers_removed": (primary, outcome),
            "physiologic_winsorized_1_99": (physiologic, winsorized),
            "hard_al_qc": (hard_qc, matrix(hard_qc, "AL_rate")),
        }
    )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_path),
        "follow_source": str(follow_path),
        "analysis_notes": {
            "parental_history_definition": "Parent had myopia-related refractive surgery; code 1=yes, 2=no",
            "activity_codes": ACTIVITY_CODE_LABELS,
            "baseline_prediction": "Only baseline questionnaire and body-size values are used",
            "concurrent_changes": "2012-2014 changes overlap the AL-growth interval and are not prospective predictors",
            "outcome": "Patient-level mean of bilateral annual AL change, mm/year",
            "winsorization": winsor_limits,
        },
        "loader_exclusions": loader_exclusions,
        "cohort": {
            "source_n": len(records),
            "name_matched_n": len(name_matched),
            "physiologic_n": len(physiologic),
            "primary_n": len(primary),
            "hard_qc_n": len(hard_qc),
            "primary_summary": summarize_cohort(primary),
        },
        "questionnaire_reliability": survey_reliability(primary),
        "state_models": {
            "fits": state_fits,
            "comparisons": state_comparisons,
            "cross_validation": state_cv,
            "survey_coefficients_fdr": state_coefficients,
            "parent_dose_response": parent_state_dose_response(primary),
        },
        "baseline_models": {
            "fits": baseline_fits,
            "comparisons": baseline_comparisons,
            "cross_validation": baseline_cv,
            "survey_coefficients_fdr": baseline_coefficients,
            "parental_separate_sensitivity": parental_separate,
        },
        "concurrent_models": {
            "fits": concurrent_fits,
            "comparisons": concurrent_comparisons,
            "cross_validation": concurrent_cv,
            "change_coefficients_fdr": change_coefficients,
        },
        "sensitivity": sensitivity,
        "legacy_correlations": {
            "all_linked_425": legacy_correlations(records),
            "primary_403": legacy_correlations(primary),
        },
    }
    clean_result = strip_private_fit_fields(result)

    json_path = output_dir / "pediatric_survey_growth_results.json"
    json_path.write_text(
        json.dumps(clean_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_model_csv(
        output_dir / "baseline_AL_state_model_performance.csv",
        state_fits,
        state_cv,
    )
    write_model_csv(
        output_dir / "baseline_prediction_model_performance.csv",
        baseline_fits,
        baseline_cv,
    )
    write_model_csv(
        output_dir / "concurrent_change_model_performance.csv",
        concurrent_fits,
        concurrent_cv,
    )
    write_coefficient_csv(
        output_dir / "survey_growth_coefficients.csv",
        {
            "baseline_AL_state": state_coefficients,
            "baseline_prediction": baseline_coefficients,
            "concurrent_change": change_coefficients,
        },
    )
    write_report(
        output_dir / "pediatric_survey_growth_report.md",
        source_path,
        clean_result,
    )
    plot_cv_performance(
        output_dir / "survey_growth_cv_performance",
        state_cv,
        baseline_cv,
        concurrent_cv,
    )
    plot_forest(
        output_dir / "survey_growth_coefficients",
        {
            "Attained baseline AL": {
                "coefficients": state_coefficients,
                "x_label": "Difference in baseline AL (mm)",
            },
            "Baseline predictors": {
                "coefficients": baseline_coefficients,
                "x_label": "Difference in annual AL growth (mm/year)",
            },
            "Concurrent changes": {
                "coefficients": change_coefficients,
                "x_label": "Difference in annual AL growth (mm/year)",
            },
        },
    )

    print(f"Primary cohort: {len(primary)} children")
    print(
        "Baseline full CV R2/RMSE: "
        f"{baseline_cv['models']['full']['r2']['mean']:.4f}/"
        f"{baseline_cv['models']['full']['rmse']['mean']:.4f}"
    )
    print(
        "Concurrent change-all CV R2/RMSE: "
        f"{concurrent_cv['models']['change_all']['r2']['mean']:.4f}/"
        f"{concurrent_cv['models']['change_all']['rmse']['mean']:.4f}"
    )
    print(f"Wrote outputs to {output_dir}")


if __name__ == "__main__":
    main()
