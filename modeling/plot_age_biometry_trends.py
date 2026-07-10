#!/usr/bin/env python3
"""Create presentation-ready age trend figures from the V3.1 derivation cohort."""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path

import numpy as np

from biometry_ood import load_default_model
from modeling.train_bilateral_ood_v31 import prepare_bilateral_records


WIDTH = 1800
HEIGHT = 1100
FEATURES = [
    ("AL", "Axial length", "mm", "#157A83"),
    ("Mean_K", "Mean K", "D", "#B5523C"),
    ("ACD", "Anterior chamber depth", "mm", "#4267A9"),
    ("LT", "Lens thickness", "mm", "#9A6A18"),
]


def svg_text(x, y, value, size=14, weight=400, fill="#173E54", anchor="start"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{html.escape(str(value))}</text>'
    )


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


def bin_summary(records, bins, feature):
    summary = []
    for center, lower, upper in bins:
        values = [record[feature] for record in records if lower <= record["age"] < upper]
        if len(values) < 8:
            continue
        q25, median, q75 = np.quantile(values, [0.25, 0.5, 0.75])
        summary.append(
            {
                "age": center,
                "n": len(values),
                "q25": float(q25),
                "median": float(median),
                "q75": float(q75),
            }
        )
    return summary


def path_from_points(points):
    return " ".join(
        ("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}"
        for index, (x, y) in enumerate(points)
    )


def render_panel(x, y, width, height, feature, title, unit, color, records, bins, age_domain, core, shade_under_two=False):
    plot_x = x + 78
    plot_y = y + 60
    plot_width = width - 112
    plot_height = height - 116
    age_min, age_max = age_domain
    summary = bin_summary(records, bins, feature)
    fitted_ages = np.linspace(max(2.0, age_min), age_max, 180)
    fitted_values = [core.expected_by_age(feature, float(age)) for age in fitted_ages]
    visible_values = fitted_values + [item[key] for item in summary for key in ("q25", "q75")]
    raw_low, raw_high = min(visible_values), max(visible_values)
    padding = max((raw_high - raw_low) * 0.14, 0.08 if unit == "mm" else 0.2)
    y_min, y_max, y_ticks, y_step = nice_ticks(raw_low - padding, raw_high + padding)

    def sx(age):
        return plot_x + (age - age_min) / (age_max - age_min) * plot_width

    def sy(value):
        return plot_y + (y_max - value) / (y_max - y_min) * plot_height

    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="6" fill="#FFFFFF" stroke="#CBD6DC"/>',
        svg_text(x + 24, y + 34, title, size=20, weight=700),
        svg_text(x + width - 24, y + 34, unit, size=13, weight=600, fill="#667983", anchor="end"),
    ]

    if shade_under_two:
        shaded_width = max(0, sx(2) - sx(age_min))
        parts.append(
            f'<rect x="{sx(age_min):.1f}" y="{plot_y:.1f}" width="{shaded_width:.1f}" '
            f'height="{plot_height:.1f}" fill="#EEF1F3"/>'
        )

    x_ticks = list(range(1, 11)) if age_domain == (1, 10) else list(range(20, 91, 10))
    for tick in y_ticks:
        tick_y = sy(tick)
        parts.append(
            f'<line x1="{plot_x:.1f}" y1="{tick_y:.1f}" x2="{plot_x + plot_width:.1f}" '
            f'y2="{tick_y:.1f}" stroke="#E6ECEF" stroke-width="1"/>'
        )
        parts.append(svg_text(plot_x - 11, tick_y + 5, tick_label(tick, y_step), size=12, fill="#61747E", anchor="end"))
    for tick in x_ticks:
        tick_x = sx(tick)
        parts.append(
            f'<line x1="{tick_x:.1f}" y1="{plot_y:.1f}" x2="{tick_x:.1f}" '
            f'y2="{plot_y + plot_height:.1f}" stroke="#F1F4F5" stroke-width="1"/>'
        )
        parts.append(svg_text(tick_x, plot_y + plot_height + 24, tick, size=12, fill="#61747E", anchor="middle"))

    upper = [(sx(item["age"]), sy(item["q75"])) for item in summary]
    lower = [(sx(item["age"]), sy(item["q25"])) for item in reversed(summary)]
    polygon = " ".join(f"{px:.1f},{py:.1f}" for px, py in upper + lower)
    parts.append(f'<polygon points="{polygon}" fill="{color}" fill-opacity="0.14"/>')

    median_points = [(sx(item["age"]), sy(item["median"])) for item in summary]
    parts.append(
        f'<path d="{path_from_points(median_points)}" fill="none" stroke="{color}" '
        f'stroke-opacity="0.64" stroke-width="2" stroke-dasharray="5 5"/>'
    )
    for point_x, point_y in median_points:
        parts.append(
            f'<circle cx="{point_x:.1f}" cy="{point_y:.1f}" r="4.5" fill="#FFFFFF" '
            f'stroke="{color}" stroke-width="2.5"/>'
        )

    fitted_points = [(sx(float(age)), sy(value)) for age, value in zip(fitted_ages, fitted_values)]
    parts.append(
        f'<path d="{path_from_points(fitted_points)}" fill="none" stroke="{color}" '
        f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    parts.extend(
        [
            f'<line x1="{plot_x:.1f}" y1="{plot_y + plot_height:.1f}" x2="{plot_x + plot_width:.1f}" '
            f'y2="{plot_y + plot_height:.1f}" stroke="#8FA0A9"/>',
            f'<line x1="{plot_x:.1f}" y1="{plot_y:.1f}" x2="{plot_x:.1f}" '
            f'y2="{plot_y + plot_height:.1f}" stroke="#8FA0A9"/>',
            svg_text(plot_x + plot_width / 2, y + height - 15, "Age (years)", size=13, weight=600, fill="#526770", anchor="middle"),
        ]
    )
    return parts


def render_figure(output_path, title, subtitle, records, bins, age_domain, core, footnote, shade_under_two=False):
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<rect width="100%" height="100%" fill="#F7F9FA"/>',
        '<g font-family="Arial, Segoe UI, sans-serif">',
        svg_text(78, 58, title, size=31, weight=750),
        svg_text(78, 90, subtitle, size=15, fill="#5B707B"),
        '<line x1="1228" y1="82" x2="1278" y2="82" stroke="#173E54" stroke-width="4" stroke-linecap="round"/>',
        svg_text(1291, 87, "V3.1 fitted expectation", size=13, weight=600, fill="#526770"),
        '<rect x="1509" y="73" width="44" height="18" fill="#527C89" fill-opacity="0.14"/>',
        '<line x1="1509" y1="82" x2="1553" y2="82" stroke="#527C89" stroke-width="2" stroke-dasharray="5 5"/>',
        '<circle cx="1531" cy="82" r="4" fill="#FFFFFF" stroke="#527C89" stroke-width="2"/>',
        svg_text(1565, 87, "Bin median + IQR", size=13, weight=600, fill="#526770"),
    ]
    positions = [(68, 128), (918, 128), (68, 577), (918, 577)]
    for (feature, panel_title, unit, color), (x, y) in zip(FEATURES, positions):
        parts.extend(
            render_panel(
                x,
                y,
                814,
                408,
                feature,
                panel_title,
                unit,
                color,
                records,
                bins,
                age_domain,
                core,
                shade_under_two=shade_under_two,
            )
        )
    parts.extend(
        [
            svg_text(78, 1043, footnote, size=13, fill="#526770"),
            svg_text(1722, 1043, "Single-center descriptive reference", size=12, fill="#788991", anchor="end"),
            "</g>",
            "</svg>",
        ]
    )
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default="IOLMaster700_corrected_3.xlsx")
    parser.add_argument("--output-dir", default="reports/figures")
    args = parser.parse_args()

    records, _ = prepare_bilateral_records(args.source, ["AL", "Mean_K", "ACD", "LT"])
    derivation = [record for record in records if record["split"] == "derivation"]
    selector = load_default_model()
    core = next(model for model in selector.models if model.tier == "Core")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pediatric = [record for record in derivation if 2 <= record["age"] <= 10]
    pediatric_bins = [(float(age), age - 0.5, age + 0.5) for age in range(2, 11)]
    render_figure(
        output_dir / "age_biometry_1_10.svg",
        "Age-related biometry trends: 1–10 years",
        "V3.1 begins at age 2; the 1–<2 interval is shown but not modeled",
        pediatric,
        pediatric_bins,
        (1, 10),
        core,
        f"Derivation cohort: {len(pediatric):,} eyes · 1-year centered bins · Both eligible eyes retained with patient-level split",
        shade_under_two=True,
    )

    adult = [record for record in derivation if 20 <= record["age"] <= 90]
    adult_bins = [(lower + 2.5, lower, lower + 5) for lower in range(20, 90, 5)]
    render_figure(
        output_dir / "age_biometry_20_90.svg",
        "Age-related biometry trends: 20–90 years",
        "Age-bin distributions with the continuous V3.1 fitted expectation",
        adult,
        adult_bins,
        (20, 90),
        core,
        f"Derivation cohort: {len(adult):,} eyes · 5-year bins · Both eligible eyes retained with patient-level split",
    )
    print(output_dir / "age_biometry_1_10.svg")
    print(output_dir / "age_biometry_20_90.svg")


if __name__ == "__main__":
    main()
