"""ALPI duplicate-lane highlighting."""

from __future__ import annotations

import pandas as pd

from flows.alpi.config import ATTR_DUPLICATE_LANE, DEDUP_COLS
from flows.ftl.values import norm_key_part


def build_dedup_keys(matrix: pd.DataFrame, cols: list[str]) -> pd.Series:
    key = pd.Series([""] * len(matrix), index=matrix.index, dtype=object)
    for col in cols:
        part = matrix[col].map(norm_key_part) if col in matrix.columns else ""
        key = key + "||" + part
    return key


def mark_duplicate_lanes(matrix: pd.DataFrame) -> pd.DataFrame:
    """Flag duplicate lanes on Paying_Plant + OriginNo + DestinationNo (red)."""
    if len(matrix) == 0:
        matrix.attrs[ATTR_DUPLICATE_LANE] = []
        return matrix
    keys = build_dedup_keys(matrix, DEDUP_COLS)
    matrix.attrs[ATTR_DUPLICATE_LANE] = keys.duplicated(keep=False).tolist()
    return matrix
