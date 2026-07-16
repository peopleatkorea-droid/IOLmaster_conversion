"""Pure helpers for the conservative ESCRS formula-spread pilot.

This module deliberately contains no browser code.  It prepares anonymized
biometry payloads, validates units, selects a common Barrett-anchored IOL power,
and calculates formula spread from formula/power/refraction result tables.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Iterable, Mapping, Sequence


TARGET_REFRACTION_D = -0.25
K_INDEX = 1.3375
ZCB00_MIN_POWER_D = 5.0
ZCB00_MAX_POWER_D = 34.0
ZCB00_POWER_STEP_D = 0.5

FORMULA_ALIASES = {
    "Barrett Universal II": ("barrett universal ii", "barrett"),
    "Cooke K6": ("cooke k6", "k6"),
    "EVO 2.0": ("evo 2.0", "evo"),
    "Hill-RBF 3.0": ("hill-rbf 3.0", "hill-rbf", "hill rbf"),
    "Hoffer QST": ("hoffer qst", "hoffer® qst"),
    "Kane": ("kane",),
    "PEARL-DGS": ("pearl-dgs", "pearl dgs"),
}

SENSITIVE_FIELD_NAMES = {
    "pat_id",
    "patient_id",
    "last_name",
    "first_name",
    "name",
    "dob",
    "date_of_birth",
    "resident_number",
    "medical_record_number",
    "mrn",
}


@dataclass(frozen=True)
class PreparedCase:
    public_id: str
    source_row: int
    source_eye: str
    gender: str
    al_mm: float
    k1_d: float
    k2_d: float
    acd_mm: float
    lt_mm: float
    cct_um: float
    wtw_mm: float
    target_refraction_d: float = TARGET_REFRACTION_D
    k_index: float = K_INDEX
    manufacturer: str = "Johnson & Johnson Vision"
    iol_model: str = "TECNIS 1-Piece ZCB00"
    calculator_slot: str = "right"

    def browser_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("source_row")
        payload.pop("source_eye")
        assert_anonymized_payload(payload)
        return payload


@dataclass(frozen=True)
class FormulaCandidate:
    power_d: float
    predicted_refraction_d: float


def finite_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def first_number(row: Mapping[str, object], names: Sequence[str]) -> float | None:
    for name in names:
        number = finite_float(row.get(name))
        if number is not None:
            return number
    return None


def canonical_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def canonical_date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = canonical_text(value)
    if not text:
        return ""
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return text


def normalize_eye(value) -> str | None:
    text = canonical_text(value).upper()
    if text in {"R", "RIGHT", "OD", "우", "우안"}:
        return "R"
    if text in {"L", "LEFT", "OS", "좌", "좌안"}:
        return "L"
    return None


def normalize_gender(value) -> str | None:
    text = canonical_text(value).lower()
    if text in {"m", "male", "man", "남", "남자", "남성", "1"}:
        return "Male"
    if text in {"f", "female", "woman", "여", "여자", "여성", "2"}:
        return "Female"
    return None


def radius_mm_to_diopters(radius_mm: float, k_index: float = K_INDEX) -> float:
    if not 5.0 <= radius_mm <= 11.0:
        raise ValueError(f"Corneal radius is outside the expected range: {radius_mm}")
    return (k_index - 1.0) * 1000.0 / radius_mm


def normalize_cct_um(value: float) -> float:
    if 0.3 <= value <= 0.9:
        value *= 1000.0
    if not 300.0 <= value <= 900.0:
        raise ValueError(f"CCT is outside the expected range: {value}")
    return value


def make_public_id(
    secret: bytes,
    patient_id: object,
    acquisition_date: object,
    eye_side: object,
) -> str:
    if len(secret) < 16:
        raise ValueError("The anonymization key must contain at least 16 bytes.")
    eye = normalize_eye(eye_side) or canonical_text(eye_side).upper()
    source = "|".join(
        (
            canonical_text(patient_id),
            canonical_date(acquisition_date),
            eye,
        )
    )
    digest = hmac.new(secret, source.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ESCRS-{digest[:12].upper()}"


def gender_lookup_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        canonical_text(row.get("Pat_ID")),
        canonical_date(row.get("Acquisition_Date")),
        normalize_eye(row.get("Eye_Side")) or "",
    )


def _validate_range(name: str, value: float, lower: float, upper: float) -> float:
    if not lower <= value <= upper:
        raise ValueError(f"{name} is outside the expected range: {value}")
    return value


def prepare_case(
    row: Mapping[str, object],
    source_row: int,
    gender: object,
    id_secret: bytes,
) -> PreparedCase:
    eye = normalize_eye(row.get("Eye_Side"))
    normalized_gender = normalize_gender(gender)
    if not canonical_text(row.get("Pat_ID")):
        raise ValueError("Patient linkage key is missing.")
    if not canonical_date(row.get("Acquisition_Date")):
        raise ValueError("Acquisition date linkage key is missing.")
    if eye is None:
        raise ValueError("Eye side is missing or invalid.")
    if normalized_gender is None:
        raise ValueError("Gender is missing or invalid.")

    al = first_number(row, ("AL_mm", "AL"))
    k1 = first_number(row, ("K1_D", "K1"))
    k2 = first_number(row, ("K2_D", "K2"))
    if k1 is None or k2 is None:
        r1 = first_number(row, ("R1_mm", "R1"))
        r2 = first_number(row, ("R2_mm", "R2"))
        if r1 is None or r2 is None:
            raise ValueError("Both K values and corneal radii are missing.")
        k_values = sorted((radius_mm_to_diopters(r1), radius_mm_to_diopters(r2)))
        k1, k2 = k_values
    else:
        k1, k2 = sorted((k1, k2))

    acd = first_number(row, ("ACD_mm", "ACD"))
    lt = first_number(row, ("LT_mm", "LT"))
    cct = first_number(row, ("CCT_mm", "CCT"))
    wtw = first_number(row, ("WTW_mm", "W2W", "WTW"))
    required = {"AL": al, "ACD": acd, "LT": lt, "CCT": cct, "WTW": wtw}
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError("Missing required values: " + ", ".join(missing))

    assert al is not None and acd is not None and lt is not None
    assert cct is not None and wtw is not None
    public_id = make_public_id(
        id_secret,
        row.get("Pat_ID"),
        row.get("Acquisition_Date"),
        eye,
    )
    return PreparedCase(
        public_id=public_id,
        source_row=int(source_row),
        source_eye=eye,
        gender=normalized_gender,
        al_mm=round(_validate_range("AL", al, 14.0, 38.0), 4),
        k1_d=round(_validate_range("K1", k1, 28.0, 65.0), 4),
        k2_d=round(_validate_range("K2", k2, 28.0, 65.0), 4),
        acd_mm=round(_validate_range("ACD", acd, 1.0, 6.5), 4),
        lt_mm=round(_validate_range("LT", lt, 2.0, 8.0), 4),
        cct_um=round(normalize_cct_um(cct), 1),
        wtw_mm=round(_validate_range("WTW", wtw, 8.0, 16.0), 4),
    )


def assert_anonymized_payload(payload: Mapping[str, object]) -> None:
    lowered = {str(name).strip().lower() for name in payload}
    forbidden = sorted(lowered & SENSITIVE_FIELD_NAMES)
    if forbidden:
        raise ValueError(
            "Browser payload contains prohibited identifying fields: "
            + ", ".join(forbidden)
        )
    for value in payload.values():
        if isinstance(value, Mapping):
            assert_anonymized_payload(value)


def select_evenly_across_al(
    cases: Sequence[PreparedCase],
    limit: int,
) -> list[PreparedCase]:
    if limit <= 0:
        return []
    ordered = sorted(cases, key=lambda case: (case.al_mm, case.public_id))
    if len(ordered) <= limit:
        return ordered
    if limit == 1:
        return [ordered[len(ordered) // 2]]
    indices = {
        round(position * (len(ordered) - 1) / (limit - 1))
        for position in range(limit)
    }
    return [ordered[index] for index in sorted(indices)]


def select_anchor_candidate(
    candidates: Iterable[FormulaCandidate],
    target_d: float = TARGET_REFRACTION_D,
    band_low_d: float = -0.50,
    band_high_d: float = 0.00,
) -> FormulaCandidate | None:
    in_range = [
        candidate
        for candidate in candidates
        if ZCB00_MIN_POWER_D <= candidate.power_d <= ZCB00_MAX_POWER_D
        and abs(
            (candidate.power_d - ZCB00_MIN_POWER_D) / ZCB00_POWER_STEP_D
            - round(
                (candidate.power_d - ZCB00_MIN_POWER_D) / ZCB00_POWER_STEP_D
            )
        )
        <= 0.01
        and band_low_d <= candidate.predicted_refraction_d <= band_high_d
    ]
    if not in_range:
        return None
    return min(
        in_range,
        key=lambda candidate: (
            round(abs(candidate.predicted_refraction_d - target_d), 8),
            candidate.predicted_refraction_d,
            candidate.power_d,
        ),
    )


def common_power_refractions(
    formula_results: Mapping[str, Sequence[FormulaCandidate]],
    anchor_power_d: float,
    tolerance: float = 0.011,
) -> dict[str, float]:
    result = {}
    for formula, candidates in formula_results.items():
        matching = [
            candidate
            for candidate in candidates
            if abs(candidate.power_d - anchor_power_d) <= tolerance
        ]
        if matching:
            best = min(
                matching,
                key=lambda candidate: abs(candidate.power_d - anchor_power_d),
            )
            result[formula] = best.predicted_refraction_d
    return result


def formula_spread(refractions: Mapping[str, float], minimum_formulas: int = 3):
    finite = {
        name: value
        for name, value in refractions.items()
        if finite_float(value) is not None
    }
    if len(finite) < minimum_formulas:
        return None
    values = list(finite.values())
    return max(values) - min(values)


def summarize_formula_results(
    formula_results: Mapping[str, Sequence[FormulaCandidate]],
    anchor_formula: str = "Barrett Universal II",
) -> dict[str, object]:
    anchor = select_anchor_candidate(formula_results.get(anchor_formula, ()))
    if anchor is None:
        return {
            "status": "not_evaluable",
            "reason": "No Barrett candidate in the prespecified target band.",
        }
    refractions = common_power_refractions(formula_results, anchor.power_d)
    spread = formula_spread(refractions)
    return {
        "status": "complete" if spread is not None else "partial",
        "anchor_formula": anchor_formula,
        "anchor_power_d": anchor.power_d,
        "anchor_predicted_refraction_d": anchor.predicted_refraction_d,
        "common_power_refractions_d": refractions,
        "formula_count_at_anchor": len(refractions),
        "formula_spread_d": spread,
    }


def parse_decimal(value: str) -> float:
    return float(value.strip().replace(",", "."))


def parse_formula_segment(
    text: str,
    pair_pattern: str,
) -> list[FormulaCandidate]:
    candidates = []
    for match in re.finditer(pair_pattern, text, flags=re.IGNORECASE | re.MULTILINE):
        power = parse_decimal(match.group("power"))
        refraction = parse_decimal(match.group("refraction"))
        if (
            -20.0 <= power <= 80.0
            and -10.0 <= refraction <= 10.0
        ):
            candidates.append(FormulaCandidate(power, refraction))
    unique = {
        (round(item.power_d, 4), round(item.predicted_refraction_d, 4)): item
        for item in candidates
    }
    return list(unique.values())
