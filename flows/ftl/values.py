"""Small value helpers shared across flows."""

from __future__ import annotations

import re

import pandas as pd

_PLAIN_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def norm_key(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def to_carrier_int(value):
    if pd.isna(value):
        return pd.NA
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return pd.NA


def norm_key_part(value) -> str:
    """
    Normalize key parts for matching/merging.
    Integers and integer-like floats/strings map to the same token
    (915317, 915317.0, \"915317.0\" -> \"915317\") so rate extracts
    with different Excel types still match.
    Strings with underscores (e.g. 920271_00) are left unchanged.
    """
    if pd.isna(value):
        return ""
    if isinstance(value, bool):
        return str(value).casefold()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.12g}".casefold()
    text = str(value).strip().casefold()
    if not text:
        return ""
    # Avoid float(\"920271_00\") which Python parses via digit separators
    if _PLAIN_NUMBER.fullmatch(text):
        num = float(text)
        if num.is_integer():
            return str(int(num))
    return text


def safe_amount(value):
    if pd.isna(value):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def cmp_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    text = str(value).strip()
    if text == "":
        return ""
    try:
        return round(float(text), 2)
    except ValueError:
        return text.casefold()


def drop_fully_duplicate_rows(
    df: pd.DataFrame,
    *,
    ignore_cols: list[str] | None = None,
    label: str = "rate rows",
) -> pd.DataFrame:
    """
    Keep the first row when multiple rows are identical on all compared columns.
    """
    if len(df) == 0:
        return df
    ignore = set(ignore_cols or ())
    subset = [c for c in df.columns if c not in ignore]
    if not subset:
        return df.reset_index(drop=True)
    before = len(df)
    out = df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
    removed = before - len(out)
    if removed:
        print(f"  Dropped {removed} fully duplicate {label}")
    return out
