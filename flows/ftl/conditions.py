"""FTL Forwarder common-rating and generated Conditions rules."""

from __future__ import annotations

import pandas as pd

from flows.ftl.config import FORWARDER_COMMON_RULES
from flows.ftl.conditions_text import (
    expand_collection_days,
    is_combined_code,
    is_comma_combined,
    normalize_combined_codes,
    normalize_comma_list,
)


def resolve_common_forwarder(carrier_no, current_forwarder: str) -> str | None:
    """Return common Forwarder for CarrierNo, or None if no rule applies."""
    try:
        carrier_int = int(carrier_no)
    except (TypeError, ValueError):
        return None

    matches = [rule for rule in FORWARDER_COMMON_RULES if rule[1] == carrier_int]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0][0]

    current = (current_forwarder or "").strip().upper()
    for common_name, _, _ in matches:
        if "POLAR" in common_name.upper() and "POLAR" in current:
            return common_name
    for common_name, _, _ in matches:
        if "POLAR" not in common_name.upper():
            return common_name
    return matches[0][0]


def apply_forwarder_common_rating(
    details: pd.DataFrame,
) -> tuple[pd.DataFrame, list[bool], list[dict]]:
    """
    Replace Forwarder with common rating value when CarrierNo matches a rule.
    Returns updated details, per-row replaced flags, and unique replacement records.
    """
    out = details.copy()
    replaced_flags: list[bool] = []
    replacement_map: dict[tuple[str, str, int, str], dict] = {}

    for idx, row in out.iterrows():
        original = "" if pd.isna(row["Forwarder"]) else str(row["Forwarder"]).strip()
        carrier_no = row["CarrierNo"]
        common = resolve_common_forwarder(carrier_no, original)
        if common is None:
            replaced_flags.append(False)
            continue

        out.at[idx, "Forwarder"] = common
        changed = original != common
        replaced_flags.append(True)

        carrier_int = int(carrier_no)
        carrier_label = next(
            (
                label
                for name, no, label in FORWARDER_COMMON_RULES
                if no == carrier_int and name == common
            ),
            next(
                label for name, no, label in FORWARDER_COMMON_RULES if no == carrier_int
            ),
        )
        key = (original, common, carrier_int, carrier_label)
        if key not in replacement_map:
            replacement_map[key] = {
                "Field": "Forwarder",
                "Original value": original,
                "Common value": common,
                "Condition": f"CARRIER equals '{carrier_int} {carrier_label}'",
                "Rows": 0,
                "Changed": changed,
            }
        replacement_map[key]["Rows"] += 1

    return out, replaced_flags, list(replacement_map.values())


def empty_generated_conditions() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Field",
            "Original value",
            "Attribute",
            "Operator",
            "Value",
            "Scope",
            "Rows",
        ]
    )


def _add_condition_record(
    records: dict[tuple[str, str], dict],
    field_label: str,
    original: str,
    attribute: str,
    value: str,
    operator: str = "equals",
    scope: str = "in all items",
) -> None:
    key = (field_label, original)
    if key in records:
        records[key]["Rows"] += 1
        return
    records[key] = {
        "Field": field_label,
        "Original value": original,
        "Attribute": attribute,
        "Operator": operator,
        "Value": value,
        "Scope": scope,
        "Rows": 1,
    }


def collect_generated_conditions(*detail_frames: pd.DataFrame) -> pd.DataFrame:
    """
    Auto-build Conditions for multi-value cells as 4 columns:
      Attribute | Operator | Value | Scope
    """
    records: dict[tuple[str, str], dict] = {}

    for details in detail_frames:
        if details is None or len(details) == 0:
            continue

        for value in details["OriginNo"]:
            if not is_combined_code(value):
                continue
            original = str(value).strip()
            normalized = normalize_combined_codes(original)
            _add_condition_record(
                records, "Origin No", original, "SHIP_COMPANY_CODE", normalized
            )

        for value in details["DestinationNo"]:
            if not is_combined_code(value):
                continue
            original = str(value).strip()
            normalized = normalize_combined_codes(original)
            _add_condition_record(
                records, "Destination No", original, "CUST_COMPANY_CODE", normalized
            )

        for value in details["Collection day"]:
            expanded = expand_collection_days(value)
            if not expanded:
                continue
            original = str(value).strip()
            _add_condition_record(
                records, "Collection day", original, "COLLECTION_DAY", expanded
            )

        for value in details["Paying_Plant"]:
            if not is_comma_combined(value):
                continue
            original = str(value).strip()
            normalized = normalize_comma_list(original)
            _add_condition_record(
                records, "Paying Plant", original, "BU_NAME", normalized
            )

    if not records:
        return empty_generated_conditions()

    out = pd.DataFrame(records.values())
    field_order = {
        "Origin No": 0,
        "Destination No": 1,
        "Collection day": 2,
        "Paying Plant": 3,
    }
    out["_ord"] = out["Field"].map(lambda f: field_order.get(f, 99))
    return (
        out.sort_values(["_ord", "Original value"])
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )


def build_conditions_records(replacements: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Conditions tab: rule catalog + actual replacements found in the data."""
    rules_rows = []
    for common_name, carrier_no, carrier_label in FORWARDER_COMMON_RULES:
        rules_rows.append(
            {
                "Field": "Forwarder",
                "Common value": common_name,
                "Condition": f"CARRIER equals '{carrier_no} {carrier_label}'",
            }
        )
    rules_df = pd.DataFrame(rules_rows)

    if replacements:
        applied = pd.DataFrame(replacements)
        applied = applied[
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
