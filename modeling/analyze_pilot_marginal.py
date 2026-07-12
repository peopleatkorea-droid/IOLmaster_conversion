#!/usr/bin/env python3
"""Marginal-adjustment analysis for the biometry OOD postoperative pilot.

The analysis is deliberately patient-cluster aware and emits only aggregate
statistics.  No patient identifiers are written to the report.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biometry_ood import load_default_model
from modeling.train_ood_model import read_xlsx_rows


PREDICTION_COLUMNS = [
    "Pred_SE_Barrett_D",
    "Pred_SE_Barrett_TK_D",
    "Pred_SE_Haigis_D",
    "Pred_SE_Hoffer_Q_D",
    "Pred_SE_SRK_T_D",
    "Pred_SE_Cooke_K6_D",
    "Pred_SE_EVO_D",
    "Pred_SE_Hill_RBF_D",
    "Pred_SE_Hoffer_QST_D",
    "Pred_SE_Pearl_DGS_D",
]


def finite_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def is_post_lvc(row):
    return (
        finite_float(row.get("Pred_SE_Haigis_D")) is not None
        and finite_float(row.get("Pred_SE_Hoffer_Q_D")) is None
        and finite_float(row.get("Pred_SE_SRK_T_D")) is None
    )


def build_records(paths):
    selector = load_default_model()
    records = []
    flow = {}
    for wave, path in paths:
        rows = list(read_xlsx_rows(path))
        wave_flow = {"selected": len(rows), "evaluable": 0, "routine": 0, "post_lvc": 0}
        for row in rows:
            predictions = [finite_float(row.get(name)) for name in PREDICTION_COLUMNS]
            predictions = [value for value in predictions if value is not None]
            mrse = finite_float(row.get("MR_SE_D"))
            if mrse is None or len(predictions) < 3:
                continue

            values = {
                "age": finite_float(row.get("Age_at_Biometry")),
                "al": finite_float(row.get("AL_mm")),
                "mean_k": finite_float(row.get("Mean_K_D")),
                "acd": finite_float(row.get("ACD_mm")),
                "lt": finite_float(row.get("LT_mm")),
                "wtw": finite_float(row.get("WTW_mm")),
                "cct": finite_float(row.get("CCT_mm")),
            }
            score = selector.score_values(**values)
            if score["OOD_Status"] == "Not calculated":
                continue

            model = selector.select_model(values["age"], values["wtw"], values["cct"])
            profile = {item["name"]: item for item in score["OOD_Feature_Profile"]}
            marginal_z = {}
            for name in model.inputs:
                index = model.inputs.index(name)
                marginal_z[name] = abs(
                    (profile[name]["standardized_value"] - model.location[index])
                    / model.standard_deviations[index]
                )

            post_lvc = is_post_lvc(row)
            record = {
                "wave": wave,
                "patient": str(row.get("Pat_ID") or ""),
                "post_lvc": post_lvc,
                "age": values["age"],
                "al": values["al"],
                "mean_k": values["mean_k"],
                "al_marginal_z": marginal_z["AL"],
                "k_marginal_z": marginal_z["Mean_K"],
                "acd_marginal_z": marginal_z["ACD"],
                "lt_marginal_z": marginal_z["LT"],
                "wtw_marginal_z": marginal_z["WTW"],
                "cct_marginal_z": marginal_z["CCT"],
                "ood_percentile": score["OOD_Percentile"],
                "ood_status": score["OOD_Status"],
                "formula_count": len(predictions),
                "spread": max(predictions) - min(predictions),
                "median_abs_pe": statistics.median(abs(value - mrse) for value in predictions),
                "spread_ge_1d": float(max(predictions) - min(predictions) >= 1.0),
                "median_abs_pe_gt_0_5d": float(
                    statistics.median(abs(value - mrse) for value in predictions) > 0.5
                ),
                "all_formulas_miss_gt_0_5d": float(
                    all(abs(value - mrse) > 0.5 for value in predictions)
                ),
            }
            records.append(record)
            wave_flow["evaluable"] += 1
            wave_flow["post_lvc" if post_lvc else "routine"] += 1
        flow[wave] = wave_flow
    return records, flow


def add_literal_mean_deviations(records):
    routine = [record for record in records if not record["post_lvc"]]
    al_mean = statistics.mean(record["al"] for record in routine)
    k_mean = statistics.mean(record["mean_k"] for record in routine)
    for record in records:
        record["al_global_abs_dev"] = abs(record["al"] - al_mean)
        record["k_global_abs_dev"] = abs(record["mean_k"] - k_mean)
    return {"AL_mm": al_mean, "Mean_K_D": k_mean}


def design_matrix(records, marginal_names, include_ood, flexible=False, adjust_wave=False):
    columns = [np.ones(len(records), dtype=float)]
    names = ["Intercept"]
    for name in marginal_names:
        values = np.asarray([record[name] for record in records], dtype=float)
        scale = float(np.std(values, ddof=1)) or 1.0
        standardized = (values - float(np.mean(values))) / scale
        columns.append(standardized)
        names.append(name)
        if flexible:
            columns.append(standardized * standardized)
            names.append(f"{name}_squared")
    if adjust_wave:
        columns.append(np.asarray([record["wave"] == "P40" for record in records], dtype=float))
        names.append("P40_wave")
    if include_ood:
        columns.append(
            np.asarray([record["ood_percentile"] / 10.0 for record in records], dtype=float)
        )
        names.append("OOD_per_10_percentile")
    return np.column_stack(columns), names


def ols_cluster(records, outcome, marginal_names, flexible=False, adjust_wave=False):
    y = np.asarray([record[outcome] for record in records], dtype=float)
    x, names = design_matrix(
        records, marginal_names, include_ood=True, flexible=flexible, adjust_wave=adjust_wave
    )
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residuals = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    grouped = defaultdict(list)
    for index, record in enumerate(records):
        grouped[record["patient"]].append(index)
    meat = np.zeros((x.shape[1], x.shape[1]), dtype=float)
    for indices in grouped.values():
        xg = x[indices, :]
        ug = residuals[indices]
        score = xg.T @ ug
        meat += np.outer(score, score)
    n, k, groups = len(records), x.shape[1], len(grouped)
    correction = (groups / (groups - 1)) * ((n - 1) / (n - k))
    covariance = correction * bread @ meat @ bread
    standard_errors = np.sqrt(np.maximum(0.0, np.diag(covariance)))
    ood_index = names.index("OOD_per_10_percentile")
    estimate = float(beta[ood_index])
    se = float(standard_errors[ood_index])
    degrees_freedom = groups - 1
    critical = float(stats.t.ppf(0.975, degrees_freedom))
    p_value = float(2.0 * stats.t.sf(abs(estimate / se), degrees_freedom)) if se else 0.0

    base_x, _ = design_matrix(
        records, marginal_names, include_ood=False, flexible=flexible, adjust_wave=adjust_wave
    )
    base_residual = y - base_x @ np.linalg.lstsq(base_x, y, rcond=None)[0]
    sst = float(np.sum((y - np.mean(y)) ** 2))
    full_r2 = 1.0 - float(np.sum(residuals**2)) / sst if sst else 0.0
    base_r2 = 1.0 - float(np.sum(base_residual**2)) / sst if sst else 0.0
    return {
        "n_eyes": n,
        "n_patients": groups,
        "estimate_per_10_percentile": estimate,
        "cluster_robust_se": se,
        "cluster_robust_95_ci": [estimate - critical * se, estimate + critical * se],
        "cluster_robust_p": p_value,
        "base_r_squared": base_r2,
        "full_r_squared": full_r2,
        "delta_r_squared": full_r2 - base_r2,
        "condition_number": float(np.linalg.cond(x)),
    }


def partial_rank_cluster(records, outcome, marginal_names, adjust_wave=False):
    ranked = []
    for name in [outcome, "ood_percentile", *marginal_names]:
        ranked.append(stats.rankdata([record[name] for record in records]))
    y_rank, ood_rank, *marginal_ranks = ranked
    controls = [np.ones(len(records), dtype=float), *marginal_ranks]
    if adjust_wave:
        controls.append(np.asarray([record["wave"] == "P40" for record in records], dtype=float))
    z = np.column_stack(controls)
    y_residual = y_rank - z @ np.linalg.lstsq(z, y_rank, rcond=None)[0]
    ood_residual = ood_rank - z @ np.linalg.lstsq(z, ood_rank, rcond=None)[0]
    rho = float(np.corrcoef(y_residual, ood_residual)[0, 1])

    bootstrap = []
    grouped = defaultdict(list)
    for record in records:
        grouped[record["patient"]].append(record)
    clusters = list(grouped.values())
    rng = np.random.default_rng(20260712)
    for _ in range(5000):
        sampled = []
        for draw, index in enumerate(rng.integers(0, len(clusters), size=len(clusters))):
            for record in clusters[index]:
                copied = dict(record)
                copied["patient"] = f"bootstrap-{draw}"
                sampled.append(copied)
        ranked_sample = []
        for name in [outcome, "ood_percentile", *marginal_names]:
            ranked_sample.append(stats.rankdata([record[name] for record in sampled]))
        ys, os, *ms = ranked_sample
        zs = [np.ones(len(sampled), dtype=float), *ms]
        if adjust_wave:
            zs.append(np.asarray([record["wave"] == "P40" for record in sampled], dtype=float))
        control = np.column_stack(zs)
        yr = ys - control @ np.linalg.lstsq(control, ys, rcond=None)[0]
        orr = os - control @ np.linalg.lstsq(control, os, rcond=None)[0]
        value = float(np.corrcoef(yr, orr)[0, 1])
        if math.isfinite(value):
            bootstrap.append(value)
    return {
        "partial_spearman_rho": rho,
        "patient_cluster_bootstrap_95_ci": [
            float(np.quantile(bootstrap, 0.025)),
            float(np.quantile(bootstrap, 0.975)),
        ],
    }


def grouped_leave_one_patient_out(records, outcome, marginal_names, flexible=False, adjust_wave=False):
    actual = []
    base_predictions = []
    full_predictions = []
    patients = sorted({record["patient"] for record in records})
    for patient in patients:
        train = [record for record in records if record["patient"] != patient]
        test = [record for record in records if record["patient"] == patient]
        train_y = np.asarray([record[outcome] for record in train], dtype=float)
        test_y = np.asarray([record[outcome] for record in test], dtype=float)
        # Standardization must use training moments. Rebuild the test matrices with
        # those moments to avoid leakage and inconsistent column scaling.
        def matrices(include_ood):
            train_columns = [np.ones(len(train), dtype=float)]
            test_columns = [np.ones(len(test), dtype=float)]
            for name in marginal_names:
                train_values = np.asarray([record[name] for record in train], dtype=float)
                test_values = np.asarray([record[name] for record in test], dtype=float)
                mean = float(np.mean(train_values))
                scale = float(np.std(train_values, ddof=1)) or 1.0
                tr = (train_values - mean) / scale
                te = (test_values - mean) / scale
                train_columns.append(tr)
                test_columns.append(te)
                if flexible:
                    train_columns.append(tr * tr)
                    test_columns.append(te * te)
            if adjust_wave:
                train_columns.append(np.asarray([r["wave"] == "P40" for r in train], dtype=float))
                test_columns.append(np.asarray([r["wave"] == "P40" for r in test], dtype=float))
            if include_ood:
                train_columns.append(np.asarray([r["ood_percentile"] / 10 for r in train]))
                test_columns.append(np.asarray([r["ood_percentile"] / 10 for r in test]))
            return np.column_stack(train_columns), np.column_stack(test_columns)

        train_base, test_base = matrices(False)
        train_full, test_full = matrices(True)
        base_beta = np.linalg.lstsq(train_base, train_y, rcond=None)[0]
        full_beta = np.linalg.lstsq(train_full, train_y, rcond=None)[0]
        actual.extend(test_y.tolist())
        base_predictions.extend((test_base @ base_beta).tolist())
        full_predictions.extend((test_full @ full_beta).tolist())
    actual = np.asarray(actual)
    base_predictions = np.asarray(base_predictions)
    full_predictions = np.asarray(full_predictions)
    return {
        "base_rmse": float(np.sqrt(np.mean((actual - base_predictions) ** 2))),
        "full_rmse": float(np.sqrt(np.mean((actual - full_predictions) ** 2))),
        "rmse_change_full_minus_base": float(
            np.sqrt(np.mean((actual - full_predictions) ** 2))
            - np.sqrt(np.mean((actual - base_predictions) ** 2))
        ),
    }


def logistic_cluster(records, outcome, marginal_names, flexible=False, adjust_wave=False):
    y = np.asarray([record[outcome] for record in records], dtype=float)
    x, names = design_matrix(
        records, marginal_names, include_ood=True, flexible=flexible, adjust_wave=adjust_wave
    )

    def expit(values):
        return np.where(
            values >= 0,
            1.0 / (1.0 + np.exp(-values)),
            np.exp(values) / (1.0 + np.exp(values)),
        )

    beta = np.zeros(x.shape[1], dtype=float)
    for _ in range(100):
        probabilities = np.clip(expit(x @ beta), 1e-8, 1.0 - 1e-8)
        weights = probabilities * (1.0 - probabilities)
        information = x.T @ (weights[:, None] * x)
        step = np.linalg.pinv(information) @ (x.T @ (y - probabilities))
        beta += step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    probabilities = np.clip(expit(x @ beta), 1e-8, 1.0 - 1e-8)
    information_inverse = np.linalg.pinv(x.T @ ((probabilities * (1 - probabilities))[:, None] * x))
    grouped = defaultdict(list)
    for index, record in enumerate(records):
        grouped[record["patient"]].append(index)
    meat = np.zeros((x.shape[1], x.shape[1]), dtype=float)
    for indices in grouped.values():
        score = x[indices, :].T @ (y[indices] - probabilities[indices])
        meat += np.outer(score, score)
    n, k, groups = len(records), x.shape[1], len(grouped)
    correction = (groups / (groups - 1)) * ((n - 1) / (n - k))
    covariance = correction * information_inverse @ meat @ information_inverse
    ood_index = names.index("OOD_per_10_percentile")
    estimate = float(beta[ood_index])
    se = float(math.sqrt(max(0.0, covariance[ood_index, ood_index])))
    critical = float(stats.t.ppf(0.975, groups - 1))
    p_value = float(2.0 * stats.t.sf(abs(estimate / se), groups - 1)) if se else 0.0
    return {
        "n_eyes": n,
        "n_patients": groups,
        "events": int(np.sum(y)),
        "odds_ratio_per_10_percentile": math.exp(estimate),
        "cluster_robust_95_ci": [
            math.exp(estimate - critical * se),
            math.exp(estimate + critical * se),
        ],
        "cluster_robust_p": p_value,
    }


def grouped_logistic_validation(records, outcome, marginal_names, flexible=False, adjust_wave=False):
    actual = []
    base_predictions = []
    full_predictions = []

    def fit(x, y):
        beta = np.zeros(x.shape[1], dtype=float)
        for _ in range(100):
            linear = np.clip(x @ beta, -30.0, 30.0)
            probabilities = 1.0 / (1.0 + np.exp(-linear))
            weights = probabilities * (1.0 - probabilities)
            step = np.linalg.pinv(x.T @ (weights[:, None] * x)) @ (x.T @ (y - probabilities))
            beta += step
            if float(np.max(np.abs(step))) < 1e-9:
                break
        return beta

    patients = sorted({record["patient"] for record in records})
    for patient in patients:
        train = [record for record in records if record["patient"] != patient]
        test = [record for record in records if record["patient"] == patient]
        train_y = np.asarray([record[outcome] for record in train], dtype=float)
        test_y = np.asarray([record[outcome] for record in test], dtype=float)

        def matrices(include_ood):
            train_columns = [np.ones(len(train), dtype=float)]
            test_columns = [np.ones(len(test), dtype=float)]
            for name in marginal_names:
                train_values = np.asarray([record[name] for record in train], dtype=float)
                test_values = np.asarray([record[name] for record in test], dtype=float)
                mean = float(np.mean(train_values))
                scale = float(np.std(train_values, ddof=1)) or 1.0
                tr = (train_values - mean) / scale
                te = (test_values - mean) / scale
                train_columns.append(tr)
                test_columns.append(te)
                if flexible:
                    train_columns.append(tr * tr)
                    test_columns.append(te * te)
            if adjust_wave:
                train_columns.append(np.asarray([r["wave"] == "P40" for r in train], dtype=float))
                test_columns.append(np.asarray([r["wave"] == "P40" for r in test], dtype=float))
            if include_ood:
                train_columns.append(np.asarray([r["ood_percentile"] / 10 for r in train]))
                test_columns.append(np.asarray([r["ood_percentile"] / 10 for r in test]))
            return np.column_stack(train_columns), np.column_stack(test_columns)

        train_base, test_base = matrices(False)
        train_full, test_full = matrices(True)
        base_beta = fit(train_base, train_y)
        full_beta = fit(train_full, train_y)
        actual.extend(test_y.tolist())
        base_predictions.extend((1.0 / (1.0 + np.exp(-np.clip(test_base @ base_beta, -30, 30)))).tolist())
        full_predictions.extend((1.0 / (1.0 + np.exp(-np.clip(test_full @ full_beta, -30, 30)))).tolist())

    actual = np.asarray(actual)
    base_predictions = np.asarray(base_predictions)
    full_predictions = np.asarray(full_predictions)

    def auc(values):
        ranks = stats.rankdata(values)
        positive = actual == 1
        n_positive = int(np.sum(positive))
        n_negative = len(actual) - n_positive
        return float(
            (np.sum(ranks[positive]) - n_positive * (n_positive + 1) / 2)
            / (n_positive * n_negative)
        )

    return {
        "base_auc": auc(base_predictions),
        "full_auc": auc(full_predictions),
        "auc_change_full_minus_base": auc(full_predictions) - auc(base_predictions),
        "base_brier": float(np.mean((actual - base_predictions) ** 2)),
        "full_brier": float(np.mean((actual - full_predictions) ** 2)),
    }


def summarize_cohort(records, marginal_names, adjust_wave):
    analyses = {}
    for outcome in ("spread", "median_abs_pe"):
        analyses[outcome] = {
            "linear": ols_cluster(records, outcome, marginal_names, adjust_wave=adjust_wave),
            "flexible_quadratic": ols_cluster(
                records, outcome, marginal_names, flexible=True, adjust_wave=adjust_wave
            ),
            "partial_rank": partial_rank_cluster(
                records, outcome, marginal_names, adjust_wave=adjust_wave
            ),
            "leave_one_patient_out": grouped_leave_one_patient_out(
                records, outcome, marginal_names, adjust_wave=adjust_wave
            ),
        }
    analyses["spread_ge_1d"] = {
        "linear": logistic_cluster(
            records, "spread_ge_1d", marginal_names, adjust_wave=adjust_wave
        ),
        "flexible_quadratic": logistic_cluster(
            records,
            "spread_ge_1d",
            marginal_names,
            flexible=True,
            adjust_wave=adjust_wave,
        ),
        "leave_one_patient_out": grouped_logistic_validation(
            records, "spread_ge_1d", marginal_names, adjust_wave=adjust_wave
        ),
    }
    analyses["median_abs_pe_gt_0_5d"] = {
        "linear": logistic_cluster(
            records, "median_abs_pe_gt_0_5d", marginal_names, adjust_wave=adjust_wave
        ),
        "flexible_quadratic": logistic_cluster(
            records,
            "median_abs_pe_gt_0_5d",
            marginal_names,
            flexible=True,
            adjust_wave=adjust_wave,
        ),
        "leave_one_patient_out": grouped_logistic_validation(
            records, "median_abs_pe_gt_0_5d", marginal_names, adjust_wave=adjust_wave
        ),
    }
    return analyses


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pilot150",
        type=Path,
        default=Path("Pilot_150_extreme_biometry_signal_discovery_postop_collection_사우진.xlsx"),
    )
    parser.add_argument(
        "--pilot40",
        type=Path,
        default=Path("Pilot_40_second_wave_discordant_TK_astig_postop_collection_이동수.xlsx"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/pilot_marginal_adjustment.json")
    )
    args = parser.parse_args()

    records, flow = build_records([("P150", args.pilot150), ("P40", args.pilot40)])
    literal_means = add_literal_mean_deviations(records)
    routine = [record for record in records if not record["post_lvc"]]
    pilot150 = [record for record in routine if record["wave"] == "P150"]
    complete_nine_formula = [record for record in routine if record["formula_count"] == 9]

    report = {
        "analysis": "Marginal adjustment of active V3.1 Extended OOD association",
        "flow": flow,
        "cohorts": {
            "combined_routine": {
                "n_eyes": len(routine),
                "n_patients": len({record["patient"] for record in routine}),
            },
            "pilot150_routine": {
                "n_eyes": len(pilot150),
                "n_patients": len({record["patient"] for record in pilot150}),
            },
            "complete_nine_formula_routine": {
                "n_eyes": len(complete_nine_formula),
                "n_patients": len({record["patient"] for record in complete_nine_formula}),
            },
        },
        "literal_combined_routine_means": literal_means,
        "definitions": {
            "primary_marginal_adjustment": (
                "Absolute AL and Mean K marginal z deviations using the same age-adjusted, "
                "local-scale, robust-center reference as the active Extended OOD model."
            ),
            "literal_sensitivity": (
                "Absolute raw AL and Mean K deviations from their combined routine pilot means."
            ),
            "coefficient_unit": "Outcome change per 10 OOD percentile points.",
            "inference": "Patient-cluster CR1 sandwich covariance with t reference; partial-rank CI by 5000 patient-cluster bootstraps.",
        },
        "results": {
            "combined_routine_primary": summarize_cohort(
                routine, ("al_marginal_z", "k_marginal_z"), adjust_wave=True
            ),
            "pilot150_routine_primary": summarize_cohort(
                pilot150, ("al_marginal_z", "k_marginal_z"), adjust_wave=False
            ),
            "combined_routine_all_six_marginals": summarize_cohort(
                routine,
                (
                    "al_marginal_z",
                    "k_marginal_z",
                    "acd_marginal_z",
                    "lt_marginal_z",
                    "wtw_marginal_z",
                    "cct_marginal_z",
                ),
                adjust_wave=True,
            ),
            "pilot150_routine_all_six_marginals": summarize_cohort(
                pilot150,
                (
                    "al_marginal_z",
                    "k_marginal_z",
                    "acd_marginal_z",
                    "lt_marginal_z",
                    "wtw_marginal_z",
                    "cct_marginal_z",
                ),
                adjust_wave=False,
            ),
            "combined_routine_primary_formula_count_adjusted": summarize_cohort(
                routine,
                ("al_marginal_z", "k_marginal_z", "formula_count"),
                adjust_wave=True,
            ),
            "complete_nine_formula_routine_primary": summarize_cohort(
                complete_nine_formula,
                ("al_marginal_z", "k_marginal_z"),
                adjust_wave=True,
            ),
            "combined_routine_literal_sensitivity": summarize_cohort(
                routine, ("al_global_abs_dev", "k_global_abs_dev"), adjust_wave=True
            ),
            "pilot150_routine_literal_sensitivity": summarize_cohort(
                pilot150, ("al_global_abs_dev", "k_global_abs_dev"), adjust_wave=False
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
