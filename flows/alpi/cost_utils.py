"""ALPI cost column key helpers."""

from __future__ import annotations

from flows.alpi.config import CURRENCY_COL, FLAT_COL


def currency_key(cost_name: str) -> str:
    return f"{cost_name}||{CURRENCY_COL}"


def flat_key(cost_name: str) -> str:
    return f"{cost_name}||{FLAT_COL}"


def bracket_key(cost_name: str, bracket: str) -> str:
    return f"{cost_name}||{bracket}"
