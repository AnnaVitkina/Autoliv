"""LTL duplicate-lane highlighting."""

from __future__ import annotations

import pandas as pd

from flows.ftl.values import norm_key_part
from flows.ltl.config import ATTR_DUPLICATE_LANE, DEDUP_COLS


def build_dedup_keys(matrix: pd.DataFrame, cols: list[str]) -> pd.Series:
    key = pd.Series([""] * len(matrix), index=matrix.index, dtype=object)
    for col in cols:
        part = matrix[col].map(norm_key_part) if col in matrix.columns else ""
        key = key + "||" + part
    return key


def mark_duplicate_lanes(matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Red flag on Forwarder + Paying_Plant + OriginNo + DestinationNo.

    Combines:
    - matrix rows that share that key (after Forwarder common rating)
    - lanes already flagged from duplicate source rows (collapsed on merge)
    """
    if len(matrix) == 0:
        matrix.attrs[ATTR_DUPLICATE_LANE] = []
        return matrix
    keys = build_dedup_keys(matrix, DEDUP_COLS)
    matrix_dups = keys.duplicated(keep=False).tolist()
    seeded = list(matrix.attrs.get(ATTR_DUPLICATE_LANE, []))
    if len(seeded) != len(matrix):
        seeded = [False] * len(matrix)
    matrix.attrs[ATTR_DUPLICATE_LANE] = [
        bool(seed) or bool(dup) for seed, dup in zip(seeded, matrix_dups)
    ]
    return matrix
