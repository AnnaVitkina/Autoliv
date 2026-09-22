"""LTL cost column key helpers."""

from __future__ import annotations

from flows.ltl.config import CURRENCY_COL


def currency_key(cost_name: str) -> str:
    return f"{cost_name}||{CURRENCY_COL}"


def bracket_key(cost_name: str, bracket: str) -> str:
    return f"{cost_name}||{bracket}"


def grouped_currency_key(parent: str, child: str) -> str:
    return f"{parent}||{child}||{CURRENCY_COL}"


def grouped_bracket_key(parent: str, child: str, bracket: str) -> str:
    return f"{parent}||{child}||{bracket}"


def block_data_keys(block: dict) -> list[str]:
    """Column keys for one cost block (plain brackets or grouped children)."""
    if block.get("kind") == "grouped":
        keys: list[str] = []
        parent = block["name"]
        for child in block.get("children", []):
            child_name = child["name"]
            keys.append(grouped_currency_key(parent, child_name))
            for br in child.get("brackets", []):
                keys.append(grouped_bracket_key(parent, child_name, br))
        return keys

    name = block["name"]
    keys = [currency_key(name)]
    for br in block.get("brackets", []):
        keys.append(bracket_key(name, br))
    return keys
