"""Shared text helpers for multi-value condition cells (Origin/Dest/Collection/Plant)."""

from __future__ import annotations

import re

import pandas as pd

DAY_NAME_BY_ALIAS: dict[str, str] = {
    "MON": "MONDAY",
    "MONDAY": "MONDAY",
    "TUE": "TUESDAY",
    "TUES": "TUESDAY",
    "TUESDAY": "TUESDAY",
    "WED": "WEDNESDAY",
    "WEDNESDAY": "WEDNESDAY",
    "THU": "THURSDAY",
    "THUR": "THURSDAY",
    "THURS": "THURSDAY",
    "THURSDAY": "THURSDAY",
    "FRI": "FRIDAY",
    "FRIDAY": "FRIDAY",
    "SAT": "SATURDAY",
    "SATURDAY": "SATURDAY",
    "SUN": "SUNDAY",
    "SUNDAY": "SUNDAY",
}
DAY_ORDER = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]


def is_combined_code(value) -> bool:
    if pd.isna(value) or value == "":
        return False
    return "+" in str(value)


def is_comma_combined(value) -> bool:
    if pd.isna(value) or value == "":
        return False
    return "," in str(value)


def normalize_combined_codes(value) -> str:
    """928947+964507 / '911750 + 912608' -> 928947,964507 / 911750,912608."""
    parts = [p.strip() for p in str(value).split("+")]
    return ",".join(p for p in parts if p)


def normalize_comma_list(value) -> str:
    """RRS_CH, ARO_CH / 'TRS, TRA, TSW, TPC ' -> RRS_CH, ARO_CH style with ', '."""
    parts = [p.strip() for p in str(value).split(",")]
    return ", ".join(p for p in parts if p)


def parse_day_token(token: str) -> str | None:
    """Extract a day name from a token like 'Mon', 'FRI', 'Thu- if ...'."""
    text = token.strip()
    if not text:
        return None
    match = re.match(
        r"^(Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|"
        r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        key = text.upper().replace(".", "")
        return DAY_NAME_BY_ALIAS.get(key)
    key = match.group(1).upper()
    if key in DAY_NAME_BY_ALIAS:
        return DAY_NAME_BY_ALIAS[key]
    return DAY_NAME_BY_ALIAS.get(key[:3])


def expand_collection_days(value) -> str | None:
    """
    Mon, Fri -> MONDAY, FRIDAY
    MON+THU -> MONDAY, THURSDAY
    MON-FRI -> MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY
    Returns None when value is not a multi-day list we can parse.
    """
    if pd.isna(value) or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None

    range_match = re.fullmatch(
        r"\s*(Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|"
        r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
        r"\s*-\s*"
        r"(Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|"
        r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\s*",
        text,
        flags=re.IGNORECASE,
    )
    if range_match:
        start = parse_day_token(range_match.group(1))
        end = parse_day_token(range_match.group(2))
        if start and end and start in DAY_ORDER and end in DAY_ORDER:
            i, j = DAY_ORDER.index(start), DAY_ORDER.index(end)
            if i <= j:
                return ", ".join(DAY_ORDER[i : j + 1])
            return ", ".join(DAY_ORDER[i:] + DAY_ORDER[: j + 1])

    if "," not in text and "+" not in text:
        return None

    separator = "," if "," in text else "+"
    days: list[str] = []
    for part in text.split(separator):
        day = parse_day_token(part)
        if day and day not in days:
            days.append(day)

    if len(days) < 2:
        return None
    return ", ".join(days)
