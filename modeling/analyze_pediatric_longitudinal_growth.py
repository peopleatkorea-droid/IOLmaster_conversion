#!/usr/bin/env python3
"""Compare pediatric axial-growth models in the 2012-2014 cohort.

The analysis reproduces the main KJO model and then compares raw baseline AL,
an age/sex-adjusted AL residual, anterior geometry, and nonlinear AL effects.
All analyses are patient-level and use the mean of both eyes unless explicitly
reported as an eye-specific sensitivity analysis.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.linear_model import HuberRegressor
from sklearn.model_selection import RepeatedKFold

try:
    from modeling.analyze_pediatric_al_phenotypes import RestrictedCubicSpline
    from modeling.train_ood_model import read_xlsx_rows
except ModuleNotFoundError:
    from analyze_pediatric_al_phenotypes import RestrictedCubicSpline
    from train_ood_model import read_xlsx_rows


DEFAULT_SOURCE = (
    "C:\\Users\\USER\\OneDrive\\논문 작성중\\axial myopia progression\\"
    "2012 2014 병합 match 된것만 남기기 평균치 차이 추가 2024.xlsx"
)
DEFAULT_FOLLOW_SOURCE = (
    "C:\\Users\\USER\\OneDrive\\논문 작성중\\axial myopia progression\\"
    "2014 코호트 조사결과 편집 명단업데이트 150410.xlsx"
)
EYES = ("OD", "OS")
PHYSICAL_RANGES = {
    "AL": (18.0, 32.0),
    "ACD": (2.0, 5.0),
    "K": (35.0, 50.0),
}
MODEL_ORDER = [
    "kjo_exact",
    "age_sex_interval",
    "raw_al",
    "al_residual",
    "raw_al_k",
    "raw_al_k_acd",
    "al_spline_k_acd",
    "al_hinge24_k_acd",
]


def as_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean_pair(first, second):
    return (first + second) / 2.0


def in_range(value, bounds):
    return bounds[0] <= value <= bounds[1]


def parse_calendar_date(year, month, day):
    values = [as_float(item) for item in (year, month, day)]
    if any(item is None for item in values):
        return None
    try:
        return date(*(int(item) for item in values))
    except ValueError:
        return None


def parse_year_month_midpoint(year, month):
    values = [as_float(item) for item in (year, month)]
    if any(item is None for item in values):
        return None
    try:
        return date(int(values[0]), int(values[1]), 15)
    except ValueError:
        return None


def normalized_name(value):
    return "".join(str(value or "").split())


def choose_baseline_age(row, follow_row, baseline_exam, follow_exam):
    stored_age_months = as_float(row.get("age_m"))
    stored_age = stored_age_months / 12.0 if stored_age_months is not None else None
    baseline_grade = as_float(row.get("v7"))
    expected_age = baseline_grade + 6.5 if baseline_grade is not None else None
    baseline_dob = parse_calendar_date(row.get("v10"), row.get("v11"), row.get("v12"))
    follow_dob = parse_calendar_date(
        follow_row.get("birthyear"),
        follow_row.get("birthmonth"),
        follow_row.get("birthday"),
    )

    candidates = []
    for source, dob in (("baseline_dob", baseline_dob), ("followup_dob", follow_dob)):
        if dob is None or baseline_exam is None or dob >= baseline_exam:
            continue
        age = (baseline_exam - dob).days / 365.2425
        score = abs(age - expected_age) if expected_age is not None else 0.0
        candidates.append((score, source, age))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1] != "baseline_dob"))
        _, source, age = candidates[0]
    elif stored_age is not None:
        source, age = "stored_age_months", stored_age
    else:
        return None, "missing", baseline_dob, follow_dob

    if stored_age is not None and expected_age is not None:
        stored_score = abs(stored_age - expected_age)
        chosen_score = abs(age - expected_age)
        if stored_score < 1.25 or stored_score <= chosen_score:
            source, age = "stored_age_months", stored_age
    return age, source, baseline_dob, follow_dob


def load_records(source_path: Path, follow_source_path: Path):
    records = []
    excluded = Counter()
    follow_by_baseline_id = {}
    for row in read_xlsx_rows(follow_source_path):
        baseline_id = str(row.get("ID2012") or "").strip()
        if not baseline_id:
            continue
        if baseline_id in follow_by_baseline_id:
            excluded["duplicate_followup_id"] += 1
            continue
        follow_by_baseline_id[baseline_id] = row

    for row in read_xlsx_rows(source_path):
        patient_id = str(row.get("ID") or "").strip()
        sex_code = str(row.get("v4") or "").strip()
        if not patient_id or sex_code not in {"1", "2"}:
            excluded["missing_id_or_sex"] += 1
            continue
        follow_row = follow_by_baseline_id.get(patient_id)
        if follow_row is None:
            excluded["missing_followup_link"] += 1
            continue

        baseline_exam = parse_calendar_date(row.get("v1"), row.get("v2"), row.get("v3"))
        follow_exam = parse_calendar_date(
            follow_row.get("examyear"), follow_row.get("eaxmmonth"), follow_row.get("v5")
        )
        follow_day_imputed = False
        if follow_exam is None:
            follow_exam = parse_year_month_midpoint(
                follow_row.get("examyear"), follow_row.get("eaxmmonth")
            )
            follow_day_imputed = follow_exam is not None
        if baseline_exam is None or follow_exam is None or follow_exam <= baseline_exam:
            excluded["invalid_exam_dates"] += 1
            continue

        age, age_source, baseline_dob, follow_dob = choose_baseline_age(
            row, follow_row, baseline_exam, follow_exam
        )
        if age is None:
            excluded["missing_age"] += 1
            continue

        values = {}
        missing = False
        for eye in EYES:
            baseline_suffix = f".{eye}"
            follow_suffix = f"_{eye}"
            for name, baseline_column, follow_column in (
                ("AL", f"AL{baseline_suffix}", f"AL{follow_suffix}"),
                ("ACD", f"ACD{baseline_suffix}", f"ACD{follow_suffix}"),
                ("K", f"MeanK{baseline_suffix}", f"MeanK{follow_suffix}"),
            ):
                baseline_value = as_float(row.get(baseline_column))
                follow_value = as_float(row.get(follow_column))
                if baseline_value is None or follow_value is None:
                    missing = True
                    break
                values[f"{name}_{eye}_baseline"] = baseline_value
                values[f"{name}_{eye}_follow"] = follow_value
            if missing:
                break
        if missing:
            excluded["missing_biometry"] += 1
            continue

        interval_years = (follow_exam - baseline_exam).days / 365.2425
        name_match = (
            bool(normalized_name(row.get("v5")))
            and normalized_name(row.get("v5")) == normalized_name(follow_row.get("v7"))
        )
        dob_status = (
            "exact_match"
            if baseline_dob is not None and baseline_dob == follow_dob
            else "conflict"
            if baseline_dob is not None and follow_dob is not None
            else "missing_or_invalid"
        )
        record = {
            "patient_id": patient_id,
            "school": str(row.get("v6") or "").strip(),
            "age": age,
            "follow_age": age + interval_years,
            "interval": interval_years,
            "female": 1.0 if sex_code == "2" else 0.0,
            "name_match": name_match,
            "dob_status": dob_status,
            "age_source": age_source,
            "follow_day_imputed": follow_day_imputed,
            **values,
        }

        for name in ("AL", "ACD", "K"):
            baseline_values = [record[f"{name}_{eye}_baseline"] for eye in EYES]
            follow_values = [record[f"{name}_{eye}_follow"] for eye in EYES]
            record[f"{name}_baseline"] = mean_pair(*baseline_values)
            record[f"{name}_follow"] = mean_pair(*follow_values)
            if interval_years > 0:
                rates = [
                    (record[f"{name}_{eye}_follow"] - record[f"{name}_{eye}_baseline"])
                    / interval_years
                    for eye in EYES
                ]
                record[f"{name}_rate_OD"] = rates[0]
                record[f"{name}_rate_OS"] = rates[1]
                record[f"{name}_rate"] = mean_pair(*rates)
                record[f"{name}_rate_discordance"] = abs(rates[0] - rates[1])

        record["physiologic_al_model"] = (
            0.5 <= interval_years <= 3.5
            and all(
                in_range(record[f"AL_{eye}_{visit}"], PHYSICAL_RANGES["AL"])
                for eye in EYES
                for visit in ("baseline", "follow")
            )
            and all(
                in_range(record[f"K_{eye}_baseline"], PHYSICAL_RANGES["K"])
                for eye in EYES
            )
            and all(
                in_range(record[f"ACD_{eye}_baseline"], PHYSICAL_RANGES["ACD"])
                for eye in EYES
            )
        )
        record["hard_al_qc"] = (
            record["physiologic_al_model"]
            and all(-0.10 <= record[f"AL_rate_{eye}"] <= 1.00 for eye in EYES)
            and record["AL_rate_discordance"] <= 0.30
        )

        reasons = []
        if not name_match:
            reasons.append("name_mismatch_between_visits")
        if dob_status == "conflict":
            reasons.append("date_of_birth_conflict")
        if follow_day_imputed:
            reasons.append("followup_exam_day_imputed_to_15")
        if age_source != "stored_age_months":
            reasons.append(f"baseline_age_from_{age_source}")
        if not 0.5 <= interval_years <= 3.5:
            reasons.append("interval_outside_0.5_to_3.5_years")
        if not record["physiologic_al_model"]:
            reasons.append("physical_range_flag")
        if any(not -0.10 <= record[f"AL_rate_{eye}"] <= 1.00 for eye in EYES):
            reasons.append("AL_rate_outside_-0.10_to_1.00")
        if record["AL_rate_discordance"] > 0.30:
            reasons.append("bilateral_AL_rate_discordance_gt_0.30")
        record["qc_reasons"] = reasons
        records.append(record)

    return records, dict(excluded)


def eligible_records(records):
    return [record for record in records if record["interval"] > 0]


def matrix(records, key):
    return np.asarray([record[key] for record in records], dtype=float)


def add_intercept(design):
    design = np.asarray(design, dtype=float)
    if design.ndim == 1:
        design = design[:, None]
    return np.column_stack([np.ones(len(design)), design])


def solve_ols(design, outcome):
    x = add_intercept(design)
    y = np.asarray(outcome, dtype=float)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    return beta, x @ beta


def age_sex_residual(records, visit, outcome_name):
    """Residualize one biometric measure on the visit-specific age and sex."""

    age_key = "age" if visit == "baseline" else "follow_age"
    age = matrix(records, age_key)
    sex = matrix(records, "female")
    values = matrix(records, f"{outcome_name}_{visit}")
    spline = RestrictedCubicSpline().fit(age)
    design = np.column_stack([spline.transform(age), sex])
    _, fitted = solve_ols(design, values)
    return values - fitted


def continuous_geometry_associations(records):
    """Match the clinical-cohort partial-Spearman analysis at both school visits."""

    result = {}
    for visit in ("baseline", "follow"):
        al_residual = age_sex_residual(records, visit, "AL")
        result[visit] = {}
        for outcome_name in ("K", "ACD"):
            outcome_residual = age_sex_residual(
                records, visit, outcome_name
            )
            association = stats.spearmanr(al_residual, outcome_residual)
            result[visit][outcome_name] = {
                "rho": float(association.statistic),
                "p_value": float(association.pvalue),
            }
    return result


def threshold_24_summary(records):
    baseline_al = matrix(records, "AL_baseline")
    at_or_above = baseline_al >= 24.0
    return {
        "n": len(records),
        "n_at_or_above_24": int(np.sum(at_or_above)),
        "percent_at_or_above_24": float(np.mean(at_or_above) * 100.0),
        "n_between_23_5_and_24_5": int(
            np.sum((baseline_al >= 23.5) & (baseline_al <= 24.5))
        ),
        "minimum": float(np.min(baseline_al)),
        "maximum": float(np.max(baseline_al)),
    }


def fit_ols(design, outcome, names):
    x = add_intercept(design)
    y = np.asarray(outcome, dtype=float)
    n, p = x.shape
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    fitted = x @ beta
    residual = y - fitted
    sse = float(residual @ residual)
    centered = y - np.mean(y)
    sst = float(centered @ centered)
    rank = int(np.linalg.matrix_rank(x))
    df_resid = max(n - rank, 1)
    xtx_inv = np.linalg.pinv(x.T @ x)
    leverage = np.einsum("ij,jk,ik->i", x, xtx_inv, x)
    scaled = residual / np.maximum(1.0 - leverage, 1e-8)
    meat = x.T @ (x * (scaled**2)[:, None])
    covariance = xtx_inv @ meat @ xtx_inv
    standard_error = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    statistic = np.divide(
        beta,
        standard_error,
        out=np.full_like(beta, np.nan),
        where=standard_error > 0,
    )
    p_values = 2.0 * stats.t.sf(np.abs(statistic), df_resid)
    critical = stats.t.ppf(0.975, df_resid)
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    adjusted_r2 = 1.0 - (1.0 - r2) * (n - 1.0) / df_resid
    sigma2 = sse / df_resid
    classical_covariance = xtx_inv * sigma2
    coefficients = {}
    for index, name in enumerate(["intercept", *names]):
        coefficients[name] = {
            "estimate": float(beta[index]),
            "se_hc3": float(standard_error[index]),
            "lower_95": float(beta[index] - critical * standard_error[index]),
            "upper_95": float(beta[index] + critical * standard_error[index]),
            "p_value": float(p_values[index]),
        }
    return {
        "n": n,
        "p": p,
        "rank": rank,
        "df_resid": df_resid,
        "sse": sse,
        "r2": float(r2),
        "adjusted_r2": float(adjusted_r2),
        "rmse_in_sample": float(math.sqrt(np.mean(residual**2))),
        "aic": float(n * math.log(max(sse / n, 1e-15)) + 2 * rank),
        "bic": float(n * math.log(max(sse / n, 1e-15)) + math.log(n) * rank),
        "coefficients": coefficients,
        "_beta": beta,
        "_covariance_hc3": covariance,
        "_covariance_classical": classical_covariance,
        "_names": ["intercept", *names],
        "_fitted": fitted,
    }


def nested_comparison(reduced, full):
    df_num = full["rank"] - reduced["rank"]
    if df_num <= 0:
        raise ValueError("Full model must contain additional independent columns")
    df_den = full["df_resid"]
    numerator = max(reduced["sse"] - full["sse"], 0.0) / df_num
    denominator = full["sse"] / df_den
    f_statistic = numerator / denominator if denominator > 0 else math.inf
    partial_r2 = max(reduced["sse"] - full["sse"], 0.0) / reduced["sse"]
    return {
        "df_num": int(df_num),
        "df_den": int(df_den),
        "f_statistic": float(f_statistic),
        "p_value": float(stats.f.sf(f_statistic, df_num, df_den)),
        "partial_r2": float(partial_r2),
    }


def linear_combination(fit, weights):
    beta = fit["_beta"]
    covariance = fit["_covariance_hc3"]
    vector = np.zeros_like(beta)
    for name, weight in weights.items():
        vector[fit["_names"].index(name)] = weight
    estimate = float(vector @ beta)
    standard_error = float(math.sqrt(max(vector @ covariance @ vector, 0.0)))
    critical = stats.t.ppf(0.975, fit["df_resid"])
    statistic = estimate / standard_error if standard_error > 0 else math.nan
    return {
        "estimate": estimate,
        "se_hc3": standard_error,
        "lower_95": estimate - critical * standard_error,
        "upper_95": estimate + critical * standard_error,
        "p_value": float(2.0 * stats.t.sf(abs(statistic), fit["df_resid"])),
    }


def fit_age_spline(age):
    return RestrictedCubicSpline(quantiles=(0.05, 0.35, 0.65, 0.95)).fit(age)


def fit_al_spline(al):
    return RestrictedCubicSpline(quantiles=(0.05, 0.35, 0.65, 0.95)).fit(al)


def cohort_arrays(records, outcome_override=None):
    arrays = {
        key: matrix(records, key)
        for key in ("age", "female", "interval", "AL_baseline", "K_baseline", "ACD_baseline")
    }
    arrays["K_radius"] = 337.5 / arrays["K_baseline"]
    arrays["outcome"] = (
        np.asarray(outcome_override, dtype=float)
        if outcome_override is not None
        else matrix(records, "AL_rate")
    )
    return arrays


def build_in_sample_models(records, outcome_override=None):
    data = cohort_arrays(records, outcome_override)
    age_spline = fit_age_spline(data["age"])
    age_basis = age_spline.transform(data["age"])
    age_names = [f"age_rcs_{index + 1}" for index in range(age_basis.shape[1])]

    expected_design = np.column_stack([age_basis, data["female"]])
    expected_beta, expected_al = solve_ols(expected_design, data["AL_baseline"])
    al_residual = data["AL_baseline"] - expected_al

    al_spline = fit_al_spline(data["AL_baseline"])
    al_basis = al_spline.transform(data["AL_baseline"])
    al_spline_names = [f"AL_rcs_{index + 1}" for index in range(al_basis.shape[1])]

    common = np.column_stack([age_basis, data["female"], data["interval"]])
    common_names = [*age_names, "female", "interval_years"]
    models = {
        "kjo_exact": (
            np.column_stack(
                [data["age"], data["female"], data["AL_baseline"], data["K_radius"]]
            ),
            ["age", "female", "baseline_AL", "baseline_K_radius"],
        ),
        "age_sex_interval": (common, common_names),
        "raw_al": (
            np.column_stack([common, data["AL_baseline"]]),
            [*common_names, "baseline_AL"],
        ),
        "al_residual": (
            np.column_stack([common, al_residual]),
            [*common_names, "AL_residual"],
        ),
        "raw_al_k": (
            np.column_stack([common, data["AL_baseline"], data["K_baseline"]]),
            [*common_names, "baseline_AL", "baseline_K"],
        ),
        "raw_al_k_acd": (
            np.column_stack(
                [common, data["AL_baseline"], data["K_baseline"], data["ACD_baseline"]]
            ),
            [*common_names, "baseline_AL", "baseline_K", "baseline_ACD"],
        ),
        "al_spline_k_acd": (
            np.column_stack([common, al_basis, data["K_baseline"], data["ACD_baseline"]]),
            [*common_names, *al_spline_names, "baseline_K", "baseline_ACD"],
        ),
        "al_hinge24_k_acd": (
            np.column_stack(
                [
                    common,
                    data["AL_baseline"],
                    np.maximum(data["AL_baseline"] - 24.0, 0.0),
                    data["K_baseline"],
                    data["ACD_baseline"],
                ]
            ),
            [
                *common_names,
                "baseline_AL",
                "AL_above_24_hinge",
                "baseline_K",
                "baseline_ACD",
            ],
        ),
    }
    fits = {
        name: fit_ols(design, data["outcome"], names)
        for name, (design, names) in models.items()
    }
    raw_residual_prediction_difference = float(
        np.max(np.abs(fits["raw_al"]["_fitted"] - fits["al_residual"]["_fitted"]))
    )
    comparisons = {
        "add_raw_AL_to_age_sex_interval": nested_comparison(
            fits["age_sex_interval"], fits["raw_al"]
        ),
        "add_K_after_raw_AL": nested_comparison(fits["raw_al"], fits["raw_al_k"]),
        "add_ACD_after_raw_AL_K": nested_comparison(
            fits["raw_al_k"], fits["raw_al_k_acd"]
        ),
        "nonlinear_AL_terms": nested_comparison(
            fits["raw_al_k_acd"], fits["al_spline_k_acd"]
        ),
        "AL_hinge_at_24": nested_comparison(
            fits["raw_al_k_acd"], fits["al_hinge24_k_acd"]
        ),
    }
    hinge = fits["al_hinge24_k_acd"]
    slopes = {
        "below_or_at_24": linear_combination(hinge, {"baseline_AL": 1.0}),
        "above_24": linear_combination(
            hinge,
            {"baseline_AL": 1.0, "AL_above_24_hinge": 1.0},
        ),
    }
    return {
        "data": data,
        "fits": fits,
        "comparisons": comparisons,
        "hinge_slopes": slopes,
        "al_residual": al_residual,
        "expected_al_beta": expected_beta,
        "raw_residual_max_prediction_difference": raw_residual_prediction_difference,
    }


def fit_predict_fold(train_records, test_records, model_name, train_outcome, test_outcome):
    train = cohort_arrays(train_records, train_outcome)
    test = cohort_arrays(test_records, test_outcome)

    if model_name == "kjo_exact":
        train_x = np.column_stack(
            [train["age"], train["female"], train["AL_baseline"], train["K_radius"]]
        )
        test_x = np.column_stack(
            [test["age"], test["female"], test["AL_baseline"], test["K_radius"]]
        )
    else:
        age_spline = fit_age_spline(train["age"])
        train_age = age_spline.transform(train["age"])
        test_age = age_spline.transform(test["age"])
        train_common = np.column_stack([train_age, train["female"], train["interval"]])
        test_common = np.column_stack([test_age, test["female"], test["interval"]])

        if model_name == "age_sex_interval":
            train_x, test_x = train_common, test_common
        elif model_name in {"raw_al", "al_residual"}:
            if model_name == "raw_al":
                train_al, test_al = train["AL_baseline"], test["AL_baseline"]
            else:
                expected_train_x = np.column_stack([train_age, train["female"]])
                expected_test_x = np.column_stack([test_age, test["female"]])
                expected_beta, _ = solve_ols(expected_train_x, train["AL_baseline"])
                train_expected = add_intercept(expected_train_x) @ expected_beta
                test_expected = add_intercept(expected_test_x) @ expected_beta
                train_al = train["AL_baseline"] - train_expected
                test_al = test["AL_baseline"] - test_expected
            train_x = np.column_stack([train_common, train_al])
            test_x = np.column_stack([test_common, test_al])
        elif model_name == "raw_al_k":
            train_x = np.column_stack(
                [train_common, train["AL_baseline"], train["K_baseline"]]
            )
            test_x = np.column_stack(
                [test_common, test["AL_baseline"], test["K_baseline"]]
            )
        elif model_name == "raw_al_k_acd":
            train_x = np.column_stack(
                [
                    train_common,
                    train["AL_baseline"],
                    train["K_baseline"],
                    train["ACD_baseline"],
                ]
            )
            test_x = np.column_stack(
                [
                    test_common,
                    test["AL_baseline"],
                    test["K_baseline"],
                    test["ACD_baseline"],
                ]
            )
        elif model_name == "al_spline_k_acd":
            al_spline = fit_al_spline(train["AL_baseline"])
            train_x = np.column_stack(
                [
                    train_common,
                    al_spline.transform(train["AL_baseline"]),
                    train["K_baseline"],
                    train["ACD_baseline"],
                ]
            )
            test_x = np.column_stack(
                [
                    test_common,
                    al_spline.transform(test["AL_baseline"]),
                    test["K_baseline"],
                    test["ACD_baseline"],
                ]
            )
        elif model_name == "al_hinge24_k_acd":
            train_x = np.column_stack(
                [
                    train_common,
                    train["AL_baseline"],
                    np.maximum(train["AL_baseline"] - 24.0, 0.0),
                    train["K_baseline"],
                    train["ACD_baseline"],
                ]
            )
            test_x = np.column_stack(
                [
                    test_common,
                    test["AL_baseline"],
                    np.maximum(test["AL_baseline"] - 24.0, 0.0),
                    test["K_baseline"],
                    test["ACD_baseline"],
                ]
            )
        else:
            raise KeyError(model_name)

    beta, _ = solve_ols(train_x, train["outcome"])
    prediction = add_intercept(test_x) @ beta
    return prediction


def repeated_cross_validation(records, outcomes, repeats, splits, seed):
    outcomes = np.asarray(outcomes, dtype=float)
    splitter = RepeatedKFold(n_splits=splits, n_repeats=repeats, random_state=seed)
    storage = {name: [] for name in MODEL_ORDER}
    raw_residual_max_difference = 0.0

    for repeat_index in range(repeats):
        predictions = {name: np.full(len(records), np.nan) for name in MODEL_ORDER}
        start = repeat_index * splits
        all_splits = list(
            RepeatedKFold(
                n_splits=splits,
                n_repeats=1,
                random_state=seed + repeat_index,
            ).split(np.arange(len(records)))
        )
        if len(all_splits) != splits:
            raise RuntimeError(f"Unexpected fold count at repeat {start}")
        for train_index, test_index in all_splits:
            train_records = [records[index] for index in train_index]
            test_records = [records[index] for index in test_index]
            for model_name in MODEL_ORDER:
                predictions[model_name][test_index] = fit_predict_fold(
                    train_records,
                    test_records,
                    model_name,
                    outcomes[train_index],
                    outcomes[test_index],
                )
        raw_residual_max_difference = max(
            raw_residual_max_difference,
            float(np.max(np.abs(predictions["raw_al"] - predictions["al_residual"]))),
        )
        centered = outcomes - np.mean(outcomes)
        sst = float(centered @ centered)
        for model_name in MODEL_ORDER:
            residual = outcomes - predictions[model_name]
            sse = float(residual @ residual)
            storage[model_name].append(
                {
                    "rmse": math.sqrt(float(np.mean(residual**2))),
                    "r2": 1.0 - sse / sst if sst > 0 else 0.0,
                }
            )

    summary = {}
    for model_name, values in storage.items():
        summary[model_name] = {}
        for metric in ("rmse", "r2"):
            metric_values = np.asarray([value[metric] for value in values], dtype=float)
            summary[model_name][metric] = {
                "mean": float(np.mean(metric_values)),
                "sd_across_repeats": float(np.std(metric_values, ddof=1)) if repeats > 1 else 0.0,
                "lower_95_repeats": float(np.quantile(metric_values, 0.025)),
                "upper_95_repeats": float(np.quantile(metric_values, 0.975)),
            }
    return {
        "repeats": repeats,
        "folds": splits,
        "models": summary,
        "raw_residual_max_prediction_difference": raw_residual_max_difference,
    }


def winsorize(values, lower=0.01, upper=0.99):
    values = np.asarray(values, dtype=float)
    limits = np.quantile(values, [lower, upper])
    return np.clip(values, limits[0], limits[1]), {
        "lower_quantile": lower,
        "upper_quantile": upper,
        "lower_value": float(limits[0]),
        "upper_value": float(limits[1]),
    }


def eye_specific_sensitivity(records):
    age = matrix(records, "age")
    female = matrix(records, "female")
    interval = matrix(records, "interval")
    age_spline = fit_age_spline(age)
    age_basis = age_spline.transform(age)
    common = np.column_stack([age_basis, female, interval])
    common_names = [
        *[f"age_rcs_{index + 1}" for index in range(age_basis.shape[1])],
        "female",
        "interval_years",
    ]
    result = {}
    for predictor_eye, outcome_eye in (
        ("OD", "OD"),
        ("OS", "OS"),
        ("OD", "OS"),
        ("OS", "OD"),
    ):
        label = f"{predictor_eye}_baseline_to_{outcome_eye}_growth"
        baseline_al = matrix(records, f"AL_{predictor_eye}_baseline")
        baseline_k = matrix(records, f"K_{predictor_eye}_baseline")
        k_radius = 337.5 / baseline_k
        outcome, limits = winsorize(matrix(records, f"AL_rate_{outcome_eye}"))
        kjo_fit = fit_ols(
            np.column_stack([age, female, baseline_al, k_radius]),
            outcome,
            ["age", "female", "baseline_AL", "baseline_K_radius"],
        )
        expanded_fit = fit_ols(
            np.column_stack([common, baseline_al]),
            outcome,
            [*common_names, "baseline_AL"],
        )
        result[label] = {
            "predictor_eye": predictor_eye,
            "outcome_eye": outcome_eye,
            "winsor_limits": limits,
            "kjo_exact": strip_private_fit_fields(kjo_fit),
            "age_spline_model": strip_private_fit_fields(expanded_fit),
        }
    return result


def fit_huber_original_scale(design, outcome, epsilon=1.35):
    design = np.asarray(design, dtype=float)
    outcome = np.asarray(outcome, dtype=float)
    center = np.mean(design, axis=0)
    scale = np.std(design, axis=0)
    scale[scale == 0] = 1.0
    standardized = (design - center) / scale
    model = HuberRegressor(
        epsilon=epsilon,
        alpha=0.0,
        max_iter=5000,
        tol=1e-9,
    ).fit(standardized, outcome)
    coefficients = model.coef_ / scale
    intercept = model.intercept_ - float(coefficients @ center)
    prediction = intercept + design @ coefficients
    return intercept, coefficients, prediction


def robust_al_sensitivity(records, bootstrap_replicates, seed):
    age = matrix(records, "age")
    female = matrix(records, "female")
    interval = matrix(records, "interval")
    baseline_al = matrix(records, "AL_baseline")
    outcome = matrix(records, "AL_rate")
    age_spline = fit_age_spline(age)
    design = np.column_stack(
        [age_spline.transform(age), female, interval, baseline_al]
    )
    _, coefficients, prediction = fit_huber_original_scale(design, outcome)
    al_index = design.shape[1] - 1

    rng = np.random.default_rng(seed)
    bootstrap = []
    for _ in range(bootstrap_replicates):
        index = rng.integers(0, len(records), len(records))
        try:
            _, sample_coefficients, _ = fit_huber_original_scale(
                design[index], outcome[index]
            )
        except (ValueError, RuntimeError):
            continue
        bootstrap.append(sample_coefficients[al_index])
    bootstrap = np.asarray(bootstrap, dtype=float)

    epsilon_sensitivity = {}
    for epsilon in (1.20, 1.35, 1.50, 2.00):
        _, epsilon_coefficients, _ = fit_huber_original_scale(
            design, outcome, epsilon=epsilon
        )
        epsilon_sensitivity[f"{epsilon:.2f}"] = float(epsilon_coefficients[al_index])

    residual = outcome - prediction
    return {
        "n": len(records),
        "method": "Huber M-estimator with age spline, sex, interval, and raw baseline AL",
        "epsilon": 1.35,
        "baseline_AL": {
            "estimate": float(coefficients[al_index]),
            "lower_95_bootstrap": float(np.quantile(bootstrap, 0.025)),
            "upper_95_bootstrap": float(np.quantile(bootstrap, 0.975)),
        },
        "bootstrap_requested": bootstrap_replicates,
        "bootstrap_completed": len(bootstrap),
        "rmse_in_sample": float(math.sqrt(np.mean(residual**2))),
        "mae_in_sample": float(np.mean(np.abs(residual))),
        "epsilon_sensitivity": epsilon_sensitivity,
    }


def strip_private_fit_fields(value):
    if isinstance(value, dict):
        return {
            key: strip_private_fit_fields(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [strip_private_fit_fields(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def coefficient_text(coefficient):
    return (
        f"{coefficient['estimate']:+.4f} "
        f"[{coefficient['lower_95']:+.4f}, {coefficient['upper_95']:+.4f}]"
    )


def write_report(path, source_path, result):
    primary = result["analyses"]["obvious_severe_outliers_removed"]
    fits = primary["fits"]
    comparisons = primary["comparisons"]
    cv = primary["cross_validation"]["models"]
    lines = [
        "# Pediatric longitudinal axial-growth model comparison",
        "",
        f"- Source: `{source_path.name}`",
        f"- Follow-up linkage source: `{Path(result['follow_source']).name}`",
        f"- Generated: {result['generated_at']}",
        "- Outcome: patient-level mean of bilateral annual AL change",
        "- Status: exploratory until source records for flagged longitudinal outliers are adjudicated",
        "- Cycloplegic refraction is unavailable in the matched file",
        "- Myopia-control treatment was not used in this historical cohort according to the investigator",
        "",
        "## Cohort flow",
        "",
    ]
    for key, value in result["cohort_counts"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Direct KJO model reproduction",
            "",
            "Model: annual AL change ~ baseline age + sex + baseline AL + baseline K radius.",
            "",
            f"- Reference analysis N: {fits['kjo_exact']['n']} exact-name-linked children after removing six obvious records (one nonphysiologic AL and five severe longitudinal inconsistencies)",
            f"- Baseline AL coefficient: {coefficient_text(fits['kjo_exact']['coefficients']['baseline_AL'])} mm/year per mm",
            f"- Adjusted R2: {fits['kjo_exact']['adjusted_r2']:.4f}",
            f"- Repeated 10-fold CV RMSE: {cv['kjo_exact']['rmse']['mean']:.4f} mm/year",
            f"- Repeated 10-fold CV R2: {cv['kjo_exact']['r2']['mean']:.4f}",
            "",
            "## Sequential model comparison",
            "",
            "| Model | Adjusted R2 | In-sample RMSE | CV RMSE | CV R2 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name in MODEL_ORDER:
        fit = fits[name]
        lines.append(
            f"| {name} | {fit['adjusted_r2']:.4f} | {fit['rmse_in_sample']:.4f} | "
            f"{cv[name]['rmse']['mean']:.4f} | {cv[name]['r2']['mean']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## Incremental information",
            "",
            "| Added term | Partial R2 | p-value |",
            "|---|---:|---:|",
        ]
    )
    for name, comparison in comparisons.items():
        lines.append(
            f"| {name} | {comparison['partial_r2']:.4f} | {comparison['p_value']:.4g} |"
        )

    lines.extend(
        [
            "",
            "## Raw AL versus age/sex AL residual",
            "",
            f"- Maximum in-sample prediction difference: {primary['raw_residual_max_prediction_difference']:.3e} mm/year",
            f"- Maximum cross-validated prediction difference: {primary['cross_validation']['raw_residual_max_prediction_difference']:.3e} mm/year",
            "- With the same age-spline and sex basis in the outcome model, raw AL and its age/sex residual span the same model space. Residualization changes interpretation, not fit or predictive accuracy.",
            "",
            "## Robust regression without outcome trimming",
            "",
            f"- Huber AL coefficient: {result['robust_al_sensitivity']['baseline_AL']['estimate']:+.4f} mm/year per mm",
            f"- Patient-bootstrap 95% interval: [{result['robust_al_sensitivity']['baseline_AL']['lower_95_bootstrap']:+.4f}, {result['robust_al_sensitivity']['baseline_AL']['upper_95_bootstrap']:+.4f}]",
            f"- Bootstrap completed: {result['robust_al_sensitivity']['bootstrap_completed']} of {result['robust_al_sensitivity']['bootstrap_requested']}",
            f"- Epsilon sensitivity: {result['robust_al_sensitivity']['epsilon_sensitivity']}",
            "",
            "## Nonlinearity around AL 24 mm",
            "",
            f"- Restricted cubic spline nonlinear-term p: {comparisons['nonlinear_AL_terms']['p_value']:.4g}",
            f"- Added hinge-at-24 p: {comparisons['AL_hinge_at_24']['p_value']:.4g}",
            f"- Slope at/below 24 mm: {coefficient_text(primary['hinge_slopes']['below_or_at_24'])} mm/year per mm",
            f"- Slope above 24 mm: {coefficient_text(primary['hinge_slopes']['above_24'])} mm/year per mm",
            "",
            "## Same-eye and fellow-eye sensitivity",
            "",
            "Outcomes were winsorized separately at the 1st and 99th percentiles. The fellow-eye models use baseline AL from one eye to predict growth in the opposite eye.",
            "",
            "| Predictor to outcome | KJO-model AL coefficient [95% CI] | Age-spline AL coefficient [95% CI] |",
            "|---|---:|---:|",
        ]
    )
    for label, sensitivity in result["eye_specific_sensitivity"].items():
        kjo_coefficient = sensitivity["kjo_exact"]["coefficients"]["baseline_AL"]
        expanded_coefficient = sensitivity["age_spline_model"]["coefficients"]["baseline_AL"]
        lines.append(
            f"| {label} | {coefficient_text(kjo_coefficient)} | "
            f"{coefficient_text(expanded_coefficient)} |"
        )

    lines.extend(
        [
            "",
            "## Sensitivity of the baseline AL coefficient",
            "",
            "| Analysis set | N | KJO-model AL coefficient [95% CI] | Adjusted R2 |",
            "|---|---:|---:|---:|",
        ]
    )
    for analysis_name, analysis in result["analyses"].items():
        fit = analysis["fits"]["kjo_exact"]
        lines.append(
            f"| {analysis_name} | {fit['n']} | {coefficient_text(fit['coefficients']['baseline_AL'])} | "
            f"{fit['adjusted_r2']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- A statistically significant AL coefficient is not equivalent to strong individual prediction; CV R2 and RMSE determine practical value.",
            "- K and ACD should be claimed as predictive additions only if partial R2 and cross-validated RMSE improve consistently.",
            "- The 24-mm claim requires a significant nonlinear or hinge term; visual flattening alone is insufficient.",
            "- Hard-QC is an outcome-based sensitivity analysis, not a substitute for source-record adjudication.",
            "- Long/Typical/Short categories remain descriptive secondary analyses; continuous AL is primary.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_model_csv(path, result):
    fields = [
        "analysis_set",
        "model",
        "n",
        "adjusted_r2",
        "rmse_in_sample",
        "cv_rmse",
        "cv_r2",
        "baseline_al_estimate",
        "baseline_al_lower_95",
        "baseline_al_upper_95",
        "baseline_al_p",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for analysis_name, analysis in result["analyses"].items():
            for model_name in MODEL_ORDER:
                fit = analysis["fits"][model_name]
                cv = analysis["cross_validation"]["models"][model_name]
                coefficient = fit["coefficients"].get("baseline_AL")
                writer.writerow(
                    {
                        "analysis_set": analysis_name,
                        "model": model_name,
                        "n": fit["n"],
                        "adjusted_r2": fit["adjusted_r2"],
                        "rmse_in_sample": fit["rmse_in_sample"],
                        "cv_rmse": cv["rmse"]["mean"],
                        "cv_r2": cv["r2"]["mean"],
                        "baseline_al_estimate": coefficient["estimate"] if coefficient else "",
                        "baseline_al_lower_95": coefficient["lower_95"] if coefficient else "",
                        "baseline_al_upper_95": coefficient["upper_95"] if coefficient else "",
                        "baseline_al_p": coefficient["p_value"] if coefficient else "",
                    }
                )


def write_flagged_csv(path, records):
    fields = [
        "patient_id",
        "school",
        "age",
        "interval",
        "AL_baseline",
        "AL_follow",
        "AL_rate_OD",
        "AL_rate_OS",
        "AL_rate",
        "AL_rate_discordance",
        "qc_reasons",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            if not record["qc_reasons"]:
                continue
            writer.writerow(
                {
                    key: (
                        ";".join(record[key])
                        if key == "qc_reasons"
                        else record.get(key, "")
                    )
                    for key in fields
                }
            )


def run_analysis(records, cv_repeats, cv_folds, seed, outcome_override=None):
    built = build_in_sample_models(records, outcome_override)
    outcomes = (
        np.asarray(outcome_override, dtype=float)
        if outcome_override is not None
        else matrix(records, "AL_rate")
    )
    cross_validation = repeated_cross_validation(
        records,
        outcomes,
        repeats=cv_repeats,
        splits=cv_folds,
        seed=seed,
    )
    built["cross_validation"] = cross_validation
    for transient_key in ("data", "al_residual", "expected_al_beta"):
        built.pop(transient_key, None)
    return strip_private_fit_fields(built)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default=DEFAULT_SOURCE)
    parser.add_argument("--follow-source", default=DEFAULT_FOLLOW_SOURCE)
    parser.add_argument("--output-dir", default="outputs/pediatric_longitudinal_growth")
    parser.add_argument("--cv-repeats", type=int, default=100)
    parser.add_argument("--cv-folds", type=int, default=10)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260714)
    args = parser.parse_args()

    source_path = Path(args.source)
    follow_source_path = Path(args.follow_source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_records, loader_exclusions = load_records(source_path, follow_source_path)
    eligible = eligible_records(all_records)
    name_matched = [record for record in eligible if record["name_match"]]
    physiologic = [
        record for record in name_matched if record["physiologic_al_model"]
    ]
    obvious_outliers_removed = [
        record
        for record in physiologic
        if all(-1.00 <= record[f"AL_rate_{eye}"] <= 1.50 for eye in EYES)
        and record["AL_rate_discordance"] <= 1.00
    ]
    hard_qc = [record for record in name_matched if record["hard_al_qc"]]
    winsorized_outcome, winsor_limits = winsorize(matrix(physiologic, "AL_rate"))

    analysis_inputs = {
        "all_linked_unfiltered": (eligible, None),
        "exact_name_matched": (name_matched, None),
        "name_matched_physiologic": (physiologic, None),
        "obvious_severe_outliers_removed": (obvious_outliers_removed, None),
        "hard_al_qc": (hard_qc, None),
        "name_matched_physiologic_winsorized_1_99": (physiologic, winsorized_outcome),
    }
    analyses = {}
    for offset, (name, (records, outcome_override)) in enumerate(analysis_inputs.items()):
        analyses[name] = run_analysis(
            records,
            args.cv_repeats,
            args.cv_folds,
            args.seed + offset * 1000,
            outcome_override,
        )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_path),
        "follow_source": str(follow_source_path),
        "analysis_notes": {
            "unit": "patient",
            "eye_handling": "mean of both eyes",
            "linkage_primary": "exact normalized name match across 2012 and 2014 records",
            "interval": "exact examination-date difference; invalid follow-up day imputed to day 15",
            "outcome": "annual axial-length change in mm/year",
            "cycloplegic_refraction": "not available in matched dataset",
            "myopia_control": "investigator reports no treatment exposure in this historical cohort",
            "hard_al_qc": {
                "interval_years": [0.5, 3.5],
                "eye_level_AL_rate_mm_per_year": [-0.10, 1.00],
                "maximum_bilateral_AL_rate_discordance": 0.30,
                "physical_ranges": PHYSICAL_RANGES,
            },
            "obvious_severe_outlier_exclusion": {
                "eye_level_AL_rate_mm_per_year": [-1.00, 1.50],
                "maximum_bilateral_AL_rate_discordance": 1.00,
                "note": "Applied after exact-name linkage and physical-range checks",
            },
            "winsorization": winsor_limits,
        },
        "loader_exclusions": loader_exclusions,
        "cohort_counts": {
            "source_rows": len(all_records),
            "positive_interval": len(eligible),
            "exact_name_match": len(name_matched),
            "name_mismatch": sum(not record["name_match"] for record in eligible),
            "dob_exact_match": sum(record["dob_status"] == "exact_match" for record in eligible),
            "dob_conflict": sum(record["dob_status"] == "conflict" for record in eligible),
            "followup_day_imputed": sum(record["follow_day_imputed"] for record in eligible),
            "baseline_age_corrected_from_dob": sum(
                record["age_source"] != "stored_age_months" for record in eligible
            ),
            "name_matched_physiologic_ranges": len(physiologic),
            "obvious_severe_outliers_removed": len(obvious_outliers_removed),
            "severe_longitudinal_records_excluded": len(physiologic)
            - len(obvious_outliers_removed),
            "hard_al_qc": len(hard_qc),
            "flagged_records": sum(bool(record["qc_reasons"]) for record in all_records),
        },
        "cohort_summary": {
            "reference_population": "exact_name_matched",
            "baseline_age_mean": float(np.mean(matrix(name_matched, "age"))),
            "baseline_age_median": float(np.median(matrix(name_matched, "age"))),
            "baseline_age_min": float(np.min(matrix(name_matched, "age"))),
            "baseline_age_max": float(np.max(matrix(name_matched, "age"))),
            "followup_years_median": float(np.median(matrix(name_matched, "interval"))),
            "female_n": int(np.sum(matrix(name_matched, "female"))),
            "schools": dict(Counter(record["school"] for record in name_matched)),
            "AL_rate_median": float(np.median(matrix(name_matched, "AL_rate"))),
            "AL_rate_mean": float(np.mean(matrix(name_matched, "AL_rate"))),
        },
        "primary_continuous_geometry": continuous_geometry_associations(
            obvious_outliers_removed
        ),
        "primary_threshold_24_summary": threshold_24_summary(
            obvious_outliers_removed
        ),
        "robust_al_sensitivity": robust_al_sensitivity(
            physiologic,
            args.bootstrap_replicates,
            args.seed + 90000,
        ),
        "eye_specific_sensitivity": eye_specific_sensitivity(physiologic),
        "analyses": analyses,
    }

    json_path = output_dir / "pediatric_longitudinal_model_results.json"
    report_path = output_dir / "pediatric_longitudinal_model_report.md"
    model_csv_path = output_dir / "pediatric_longitudinal_model_comparison.csv"
    flagged_path = output_dir / "pediatric_longitudinal_flagged_records.csv"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(report_path, source_path, result)
    write_model_csv(model_csv_path, result)
    write_flagged_csv(flagged_path, all_records)
    for path in (report_path, json_path, model_csv_path, flagged_path):
        print(path)


if __name__ == "__main__":
    main()
