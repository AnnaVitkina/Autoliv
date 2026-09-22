"""LTL Forwarder common-rating and Conditions tab data."""

from __future__ import annotations

import pandas as pd

from flows.ltl.config import FORWARDER_COMMON_RULES


def resolve_common_forwarder(carrier_no, current_forwarder: str) -> str | None:
    try:
        carrier_int = int(carrier_no)
    except (TypeError, ValueError):
        return None
    matches = [rule for rule in FORWARDER_COMMON_RULES if rule[1] == carrier_int]
    if not matches:
        return None
    return matches[0][0]


def apply_forwarder_common_rating(
    details: pd.DataFrame,
) -> tuple[pd.DataFrame, list[bool], list[dict]]:
    out = details.copy()
    replaced_flags: list[bool] = []
    replacement_map: dict[tuple, dict] = {}

    for idx, row in out.iterrows():
        original = "" if pd.isna(row["Forwarder"]) else str(row["Forwarder"]).strip()
        common = resolve_common_forwarder(row["CarrierNo"], original)
        if common is None:
            replaced_flags.append(False)
            continue
        out.at[idx, "Forwarder"] = common
        replaced_flags.append(True)
        carrier_int = int(row["CarrierNo"])
        carrier_label = next(
            label for name, no, label in FORWARDER_COMMON_RULES if no == carrier_int
        )
        key = (original, common, carrier_int, carrier_label)
        if key not in replacement_map:
            replacement_map[key] = {
                "Field": "Forwarder",
                "Original value": original,
                "Common value": common,
                "Condition": f"CARRIER equals '{carrier_int} {carrier_label}'",
                "Rows": 0,
            }
        replacement_map[key]["Rows"] += 1

    return out, replaced_flags, list(replacement_map.values())


def build_conditions_records(replacements: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rules_rows = [
        {
            "Field": "Forwarder",
            "Common value": common_name,
            "Condition": f"CARRIER equals '{carrier_no} {carrier_label}'",
        }
        for common_name, carrier_no, carrier_label in FORWARDER_COMMON_RULES
    ]
    rules_df = pd.DataFrame(rules_rows)
    if replacements:
        applied = pd.DataFrame(replacements)[
            ["Field", "Original value", "Common value", "Condition", "Rows"]
        ].sort_values(["Common value", "Original value"])
    else:
        applied = pd.DataFrame(
            columns=["Field", "Original value", "Common value", "Condition", "Rows"]
        )
    return rules_df, applied


def merge_replacement_records(records: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for rec in records:
        key = (
            rec["Field"],
            rec["Original value"],
            rec["Common value"],
            rec["Condition"],
        )
        if key not in merged:
            merged[key] = dict(rec)
        else:
            merged[key]["Rows"] += rec["Rows"]
    return list(merged.values())
