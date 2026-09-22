"""FTL progressive duplicate helper columns and duplicate flags."""

from __future__ import annotations

import re

import pandas as pd

from flows.ftl.conditions_text import expand_collection_days
from flows.ftl.schema import (
    ATTR_COLLECTION_COMBINED,
    ATTR_DUPLICATE_LANE,
    DEDUP_AFTER_PLANT_COLS,
    DEDUP_AFTER_SERVICE_COLS,
    DEDUP_CORE_COLS,
    DEDUP_FULL_COLS,
)
from flows.ftl.values import norm_key_part


def build_dedup_keys(matrix: pd.DataFrame, cols: list[str]) -> pd.Series:
    key = pd.Series([""] * len(matrix), index=matrix.index, dtype=object)
    for col in cols:
        part = matrix[col].map(norm_key_part) if col in matrix.columns else ""
        key = key + "||" + part
    return key


def map_service_from_trip(singletrip_roundtrip) -> str:
    text = "" if pd.isna(singletrip_roundtrip) else str(singletrip_roundtrip).strip()
    if not text or text == "0":
        return ""
    low = text.casefold()
    if "round" in low:
        return "ROUNDTRIP"
    if "single" in low:
        return "STANDARD"
    return ""


def map_equipment_type_from_equip(equip) -> str:
    """
    3.5 t -> FTL/VAN 3
    7.5 t -> FTL/Truck 7.5T
    other present values -> FTL/Truck {value}
    """
    if pd.isna(equip):
        return ""
    text = str(equip).strip()
    if not text or text == "0":
        return ""
    low = text.casefold().replace(",", ".")
    if re.search(r"3\s*[.]?\s*5\s*t", low) or low.startswith("3.5"):
        return "FTL/VAN 3"
    if re.search(r"7\s*[.]?\s*5\s*t", low) or low in {"7.5t", "7.5 t"}:
        return "FTL/Truck 7.5T"
    return f"FTL/Truck {text}"


def _distinct_norm_count(values) -> int:
    return len({norm_key_part(v) for v in values})


def apply_progressive_dedup_fields(matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Fill helper columns ONLY when the value actually helps split a duplicate group.
    Otherwise leave empty.
    """
    if len(matrix) == 0:
        matrix.attrs[ATTR_DUPLICATE_LANE] = []
        return matrix

    attrs = dict(matrix.attrs)
    out = matrix.copy().reset_index(drop=True)

    out["Paying_Plant_2"] = ""
    out["Service"] = ""
    out["Equipment Type"] = ""

    core_keys = build_dedup_keys(out, DEDUP_CORE_COLS)
    core_dup = core_keys.duplicated(keep=False)

    out.loc[~core_dup, "Collection day"] = ""

    for _, grp_idx in out.loc[core_dup].groupby(core_keys[core_dup], sort=False).groups.items():
        idx = list(grp_idx)
        plants = out.loc[idx, "Paying_Plant"]
        if _distinct_norm_count(plants) > 1:
            out.loc[idx, "Paying_Plant_2"] = out.loc[idx, "Paying_Plant"].values

    plant_keys = build_dedup_keys(out, DEDUP_AFTER_PLANT_COLS)
    plant_dup = plant_keys.duplicated(keep=False)

    out.loc[~plant_dup, "Collection day"] = ""

    for _, grp_idx in out.loc[plant_dup].groupby(plant_keys[plant_dup], sort=False).groups.items():
        idx = list(grp_idx)
        services = [map_service_from_trip(out.at[i, "Singletrip_Roundtrip"]) for i in idx]
        equips = [map_equipment_type_from_equip(out.at[i, "equip"]) for i in idx]
        combo = list(zip(services, equips))
        if len({(norm_key_part(s), norm_key_part(e)) for s, e in combo}) > 1:
            for i, (svc, eq) in zip(idx, combo):
                out.at[i, "Service"] = svc
                out.at[i, "Equipment Type"] = eq

    service_keys = build_dedup_keys(out, DEDUP_AFTER_SERVICE_COLS)
    service_dup = service_keys.duplicated(keep=False)

    out.loc[~service_dup, "Collection day"] = ""

    for _, grp_idx in out.loc[service_dup].groupby(
        service_keys[service_dup], sort=False
    ).groups.items():
        idx = list(grp_idx)
        coll_vals = out.loc[idx, "Collection day"]
        if _distinct_norm_count(coll_vals) <= 1:
            out.loc[idx, "Collection day"] = ""

    attrs[ATTR_COLLECTION_COMBINED] = [
        expand_collection_days(v) is not None for v in out["Collection day"]
    ]

    full_keys = build_dedup_keys(out, DEDUP_FULL_COLS)
    attrs[ATTR_DUPLICATE_LANE] = full_keys.duplicated(keep=False).tolist()

    out.attrs.update(attrs)
    return out


def mark_duplicate_lanes(matrix: pd.DataFrame) -> pd.DataFrame:
    """Flag remaining duplicate lanes on the full progressive dedup key."""
    if len(matrix) == 0:
        matrix.attrs[ATTR_DUPLICATE_LANE] = []
        return matrix

    keys = build_dedup_keys(matrix, DEDUP_FULL_COLS)
    matrix.attrs[ATTR_DUPLICATE_LANE] = keys.duplicated(keep=False).tolist()
    return matrix
