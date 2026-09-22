"""LTL/LDM rates filtering, detail assembly, and cost pivots."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from flows.ftl.fuel import (
    attach_fuel_valid_from,
    format_date_ddmmyyyy,
    format_valid_from_with_flag,
)
from flows.ftl.schema import ATTR_VALID_FROM_RATES
from flows.ftl.values import cmp_value, norm_key_part, safe_amount, to_carrier_int, drop_fully_duplicate_rows
from flows.ltl.config import (
    ALLOWED_CARRIERS,
    ATTR_DUPLICATE_LANE,
    COST_BOX_PREFIX,
    COST_GROUPED,
    COST_LDM,
    COST_LTL,
    COST_LTL_GERMANETTI,
    CURRENCY_REPLACEMENTS,
    DEDUP_COLS,
    DETAIL_COLUMNS,
    GERMANETTI_CARRIER_NO,
    GROUPABLE_COSTS,
    HERO_CARRIERS,
    LANE_MERGE_COLS,
    LDM_PRICE_BRACKETS,
    LTL_PRICE_BRACKETS,
    RATE_BY_BOX,
    RATE_BY_PALLET,
)
from flows.ltl.cost_utils import (
    block_data_keys,
    bracket_key,
    currency_key,
    grouped_bracket_key,
    grouped_currency_key,
)


def normalize_currency(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return CURRENCY_REPLACEMENTS.get(text.upper(), text)


def _clean(value) -> object:
    if pd.isna(value):
        return ""
    return value


def _customer_col(df: pd.DataFrame) -> str:
    if "CustomerNo" in df.columns:
        return "CustomerNo"
    if "Customer_No" in df.columns:
        return "Customer_No"
    raise KeyError("Rates file missing CustomerNo / Customer_No")


def _unload_place_col(df: pd.DataFrame) -> str:
    if "Unloading_Place" in df.columns:
        return "Unloading_Place"
    if "Unloading_Name" in df.columns:
        return "Unloading_Name"
    return ""


def filter_by_carriers_and_plant(
    rates: pd.DataFrame, carrier_ids: set[int]
) -> pd.DataFrame:
    df = rates.copy()
    df["CarrierNo"] = df["CarrierNo"].map(to_carrier_int)
    df = df[df["CarrierNo"].isin(carrier_ids)]
    df = df[df["Paying_Plant"].astype(str).str.contains("_CH", na=False)]
    df = drop_fully_duplicate_rows(df, label="LTL/LDM/Boxes source rows")
    return df.reset_index(drop=True)


def _merge_key_from_row(row: pd.Series) -> tuple:
    return tuple(norm_key_part(row.get(c, "")) for c in LANE_MERGE_COLS)


def _detail_dict(
    row: pd.Series,
    *,
    customer_col: str,
    unload_col: str,
    weight_col: str,
    stack_col: str,
    fuel_valid,
) -> tuple[dict, bool]:
    valid_from, rates_later = format_valid_from_with_flag(
        fuel_valid, row.get("validFrom")
    )
    detail = {
        "Lane ID": _clean(row.get("RateCode")),
        "Forwarder": _clean(row.get("Forwarder")),
        "CarrierNo": row.get("CarrierNo"),
        "Paying_Plant": _clean(row.get("Paying_Plant")),
        "CustomerNo": _clean(row.get(customer_col)),
        "Shippers_Loading": _clean(row.get("Shippers_Loading")),
        "OriginalSender": _clean(row.get("OriginalSender")),
        "Loading_Country": _clean(row.get("Loading_Country")),
        "Loading_Zip": _clean(row.get("Loading_Zip")),
        "Origin City": _clean(row.get("Loading_City")),
        "OriginNo": _clean(row.get("OriginNo")),
        "Unloading_Place": _clean(row.get(unload_col)) if unload_col else "",
        "Unloading_Country": _clean(row.get("Unloading_Country")),
        "Unloading_Zip": _clean(row.get("Unloading_Zip")),
        "Unloading_City": _clean(row.get("Unloading_City")),
        "DestinationNo": _clean(row.get("DestinationNo")),
        "Weight_pallet_kg": _clean(row.get(weight_col)) if weight_col else "",
        "Weight_pallet_kg_2": "",
        "Pallet_stackable": _clean(row.get(stack_col)) if stack_col else "",
        "Pallet_stackable_2": "",
        "Collection_day": _clean(row.get("Collection_day")),
        "Collection_day_2": "",
        "Valid from": valid_from,
        "Valid to": format_date_ddmmyyyy(row.get("validTo")),
    }
    return detail, rates_later


def _parse_valid_from(value) -> object:
    return pd.to_datetime(value, errors="coerce", dayfirst=True)


def _prefer_later_valid_from(existing: dict, incoming: dict) -> None:
    """Keep the later Valid from when merging lane records; OR purple flags."""
    cur_ts = _parse_valid_from(existing["detail"].get("Valid from"))
    new_ts = _parse_valid_from(incoming["detail"].get("Valid from"))
    new_flag = bool(incoming.get("valid_from_rates_later"))
    if pd.isna(cur_ts) or (pd.notna(new_ts) and new_ts > cur_ts):
        existing["detail"]["Valid from"] = incoming["detail"].get("Valid from", "")
        existing["valid_from_rates_later"] = new_flag
    elif pd.notna(new_ts) and pd.notna(cur_ts) and new_ts == cur_ts:
        existing["valid_from_rates_later"] = (
            bool(existing.get("valid_from_rates_later")) or new_flag
        )


def _ltl_cost_values(row: pd.Series) -> tuple[str, dict[str, object]]:
    """Return (cost_name, {col_key: value}) for one LTL rates row."""
    carrier = to_carrier_int(row.get("CarrierNo"))
    try:
        carrier_int = int(carrier) if carrier is not pd.NA else None
    except (TypeError, ValueError):
        carrier_int = None
    cost_name = (
        COST_LTL_GERMANETTI
        if carrier_int == GERMANETTI_CARRIER_NO
        else COST_LTL
    )
    currency = normalize_currency(row.get("Currency"))
    values: dict[str, object] = {currency_key(cost_name): currency}
    for src_col, bracket in LTL_PRICE_BRACKETS:
        if src_col not in row.index:
            continue
        amount = safe_amount(row.get(src_col))
        if amount is None:
            continue
        values[bracket_key(cost_name, bracket)] = amount
    return cost_name, values


def _ldm_cost_values(row: pd.Series) -> dict[str, object]:
    currency = normalize_currency(row.get("Currency"))
    values: dict[str, object] = {currency_key(COST_LDM): currency}
    for src_col, bracket in LDM_PRICE_BRACKETS:
        if src_col not in row.index:
            continue
        amount = safe_amount(row.get(src_col))
        if amount is None:
            continue
        values[bracket_key(COST_LDM, bracket)] = amount
    return values


def _format_qty(value) -> str:
    num = float(value)
    if num.is_integer():
        return str(int(num))
    return f"{num:.10f}".rstrip("0").rstrip(".")


def boxes_cost_name(quantity_unit) -> str:
    unit = "" if pd.isna(quantity_unit) else str(quantity_unit).strip()
    if not unit:
        return f"{COST_BOX_PREFIX} (box)"
    return f"{COST_BOX_PREFIX} ({unit})"


def boxes_bracket_label(quantity_from, quantity_to) -> str:
    """Bracket header from QuantityFrom-QuantityTo, e.g. 1-999."""
    return f"{_format_qty(quantity_from)}-{_format_qty(quantity_to)}"


def _boxes_cost_values(row: pd.Series) -> tuple[str, str, dict[str, object]] | None:
    """
    One Boxes price row -> cost name, bracket label, cell values.
    Cost = Transport cost ({QuantityUnit}); bracket = From-To.
    """
    fr = row.get("QuantityFrom")
    to = row.get("QuantityTo")
    if pd.isna(fr) or pd.isna(to):
        return None
    amount = safe_amount(row.get("Price"))
    if amount is None:
        return None
    cost_name = boxes_cost_name(row.get("QuantityUnit"))
    bracket = boxes_bracket_label(fr, to)
    currency = normalize_currency(row.get("Currency"))
    values = {
        currency_key(cost_name): currency,
        bracket_key(cost_name, bracket): amount,
    }
    return cost_name, bracket, values


def _ingest_ltl(
    df: pd.DataFrame,
    by_creditor: dict,
    by_name: dict,
) -> list[dict]:
    """Each rates row -> lane record {key, detail, costs}."""
    customer_col = _customer_col(df)
    unload_col = _unload_place_col(df)
    df = attach_fuel_valid_from(df, by_creditor, by_name)
    records = []
    for _, row in df.iterrows():
        cost_name, cost_vals = _ltl_cost_values(row)
        detail, rates_later = _detail_dict(
            row,
            customer_col=customer_col,
            unload_col=unload_col,
            weight_col="Weight_pallet_kg",
            stack_col="Pallet_stackable",
            fuel_valid=row.get("_fuel_valid_from"),
        )
        records.append(
            {
                "key": _merge_key_from_row(pd.Series({**detail, "CarrierNo": row["CarrierNo"]})),
                "detail": detail,
                "costs": cost_vals,
                "cost_names": {cost_name},
                "source": "ltl",
                "valid_from_rates_later": rates_later,
            }
        )
    return records


def _ingest_ldm(
    df: pd.DataFrame,
    by_creditor: dict,
    by_name: dict,
) -> list[dict]:
    customer_col = _customer_col(df)
    unload_col = _unload_place_col(df)
    df = attach_fuel_valid_from(df, by_creditor, by_name)
    records = []
    for _, row in df.iterrows():
        detail, rates_later = _detail_dict(
            row,
            customer_col=customer_col,
            unload_col=unload_col,
            weight_col="PalletWeightKG" if "PalletWeightKG" in df.columns else "",
            stack_col="Stackability" if "Stackability" in df.columns else "",
            fuel_valid=row.get("_fuel_valid_from"),
        )
        # Prefer LTL-style field names already in detail; CarrierNo from row
        key_row = {
            "Paying_Plant": detail["Paying_Plant"],
            "OriginNo": detail["OriginNo"],
            "DestinationNo": detail["DestinationNo"],
            "CarrierNo": row["CarrierNo"],
        }
        records.append(
            {
                "key": _merge_key_from_row(pd.Series(key_row)),
                "detail": detail,
                "costs": _ldm_cost_values(row),
                "cost_names": {COST_LDM},
                "source": "ldm",
                "valid_from_rates_later": rates_later,
            }
        )
    return records


def _ingest_boxes(
    df: pd.DataFrame,
    by_creditor: dict,
    by_name: dict,
) -> list[dict]:
    """
    Boxes: one Transport cost ({QuantityUnit}) per lane; brackets = From-To
    (e.g. 1-999). Multiple quantity rows on the same lane become extra brackets.
    """
    customer_col = _customer_col(df)
    unload_col = _unload_place_col(df)
    df = attach_fuel_valid_from(df, by_creditor, by_name)
    records = []
    for _, row in df.iterrows():
        parsed = _boxes_cost_values(row)
        if parsed is None:
            continue
        cost_name, bracket, cost_vals = parsed
        detail, rates_later = _detail_dict(
            row,
            customer_col=customer_col,
            unload_col=unload_col,
            weight_col="",
            stack_col="",
            fuel_valid=row.get("_fuel_valid_from"),
        )
        key_row = {
            "Paying_Plant": detail["Paying_Plant"],
            "OriginNo": detail["OriginNo"],
            "DestinationNo": detail["DestinationNo"],
            "CarrierNo": row["CarrierNo"],
        }
        records.append(
            {
                "key": _merge_key_from_row(pd.Series(key_row)),
                "detail": detail,
                "costs": cost_vals,
                "cost_names": {cost_name},
                "box_brackets": {cost_name: [bracket]},
                "source": "boxes",
                "valid_from_rates_later": rates_later,
            }
        )
    return records


def _dedup_key_from_detail(detail: dict) -> tuple:
    return tuple(norm_key_part(detail.get(col, "")) for col in DEDUP_COLS)


def _record_fingerprint(rec: dict) -> tuple:
    """Identity for fully-duplicate rate records (ignore empty lane #)."""
    detail = {
        k: cmp_value(v)
        for k, v in rec.get("detail", {}).items()
        if k != "lane #"
    }
    costs = tuple(sorted((k, cmp_value(v)) for k, v in rec.get("costs", {}).items()))
    boxes = tuple(
        sorted(
            (name, tuple(brs))
            for name, brs in rec.get("box_brackets", {}).items()
        )
    )
    return (rec.get("source"), rec.get("key"), tuple(sorted(detail.items())), costs, boxes)


def _dedupe_identical_records(records: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    dropped = 0
    for rec in records:
        fp = _record_fingerprint(rec)
        if fp in seen:
            dropped += 1
            continue
        seen.add(fp)
        out.append(rec)
    if dropped:
        print(f"  Dropped {dropped} fully duplicate ingested rate rows")
    return out


def _source_duplicate_keys(records: list[dict]) -> set[tuple]:
    """
    Forwarder+Paying_Plant+OriginNo+DestinationNo keys that appear with more
    than one *distinct* source content (exact duplicates already removed).
    """
    ltl_fps: dict[tuple, set[tuple]] = defaultdict(set)
    ldm_fps: dict[tuple, set[tuple]] = defaultdict(set)
    box_fps: dict[tuple, set[tuple]] = defaultdict(set)

    for rec in records:
        key4 = _dedup_key_from_detail(rec["detail"])
        source = rec.get("source")
        fp = _record_fingerprint(rec)
        if source == "ltl":
            ltl_fps[key4].add(fp)
        elif source == "ldm":
            ldm_fps[key4].add(fp)
        elif source == "boxes":
            for name, brs in rec.get("box_brackets", {}).items():
                for br in brs:
                    box_fps[(key4, name, br)].add(fp)

    dup_keys: set[tuple] = set()
    for key4, fps in ltl_fps.items():
        if len(fps) > 1:
            dup_keys.add(key4)
    for key4, fps in ldm_fps.items():
        if len(fps) > 1:
            dup_keys.add(key4)
    for (key4, _name, _br), fps in box_fps.items():
        if len(fps) > 1:
            dup_keys.add(key4)
    return dup_keys


def _merge_records(records: list[dict]) -> list[dict]:
    """Merge LTL+LDM+Boxes on Plant+Origin+Dest+Carrier."""
    records = _dedupe_identical_records(records)
    source_dups = _source_duplicate_keys(records)
    order: list[tuple] = []
    by_key: dict[tuple, dict] = {}
    for rec in records:
        key = rec["key"]
        key4 = _dedup_key_from_detail(rec["detail"])
        is_source_dup = key4 in source_dups
        if key not in by_key:
            order.append(key)
            by_key[key] = {
                "detail": dict(rec["detail"]),
                "costs": dict(rec["costs"]),
                "cost_names": set(rec["cost_names"]),
                "box_brackets": {
                    n: list(brs) for n, brs in rec.get("box_brackets", {}).items()
                },
                "sources": [rec["source"]],
                "source_duplicate": is_source_dup,
                "valid_from_rates_later": bool(rec.get("valid_from_rates_later")),
            }
            continue
        existing = by_key[key]
        for col, val in rec["detail"].items():
            if col == "Valid from":
                continue
            cur = existing["detail"].get(col, "")
            if (cur == "" or cur is None) and val != "" and val is not None:
                existing["detail"][col] = val
        _prefer_later_valid_from(existing, rec)
        # Do not overwrite existing cost cells with empty / later duplicates
        for col, val in rec["costs"].items():
            if col not in existing["costs"] or existing["costs"][col] in ("", None):
                existing["costs"][col] = val
        existing["cost_names"].update(rec["cost_names"])
        for name, brs in rec.get("box_brackets", {}).items():
            existing["box_brackets"].setdefault(name, [])
            for br in brs:
                if br not in existing["box_brackets"][name]:
                    existing["box_brackets"][name].append(br)
        existing["sources"].append(rec["source"])
        existing["source_duplicate"] = existing["source_duplicate"] or is_source_dup
    return [by_key[k] for k in order]


def _bracket_sort_key(label: str) -> tuple:
    """Sort 1-999 before 2-10, etc."""
    parts = str(label).split("-", 1)
    try:
        lo = float(parts[0])
    except ValueError:
        lo = 0.0
    try:
        hi = float(parts[1]) if len(parts) > 1 else lo
    except ValueError:
        hi = lo
    return (lo, hi)


def _cost_blocks_for_merged(merged: list[dict]) -> list[dict]:
    names: set[str] = set()
    box_brackets: dict[str, set[str]] = defaultdict(set)
    for rec in merged:
        names.update(rec["cost_names"])
        for name, brs in rec.get("box_brackets", {}).items():
            box_brackets[name].update(brs)

    blocks: list[dict] = []
    if COST_LTL in names:
        blocks.append(
            {
                "name": COST_LTL,
                "rate_by": RATE_BY_PALLET,
                "kind": "brackets",
                "brackets": [b for _, b in LTL_PRICE_BRACKETS],
            }
        )
    if COST_LTL_GERMANETTI in names:
        blocks.append(
            {
                "name": COST_LTL_GERMANETTI,
                "rate_by": RATE_BY_PALLET,
                "kind": "brackets",
                "brackets": [b for _, b in LTL_PRICE_BRACKETS],
            }
        )
    if COST_LDM in names:
        blocks.append(
            {
                "name": COST_LDM,
                "rate_by": RATE_BY_PALLET,
                "kind": "brackets",
                "brackets": [b for _, b in LDM_PRICE_BRACKETS],
            }
        )
    for name in sorted(box_brackets.keys()):
        brackets = sorted(box_brackets[name], key=_bracket_sort_key)
        blocks.append(
            {
                "name": name,
                "rate_by": RATE_BY_BOX,
                "kind": "brackets",
                "brackets": brackets,
            }
        )
    return blocks


def _cell_has_value(value) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    return True


def _apply_grouped_transport_costs(matrix: pd.DataFrame) -> pd.DataFrame:
    """
    When a lane has 2+ of Transport cost / GERMANETTI / LDM filled, move those
    calculations under Grouped cost: Transport cost (as separate child costs)
    and clear them from the original cost columns for that lane.
    """
    blocks: list[dict] = list(matrix.attrs.get("cost_blocks", []))
    by_name = {b["name"]: b for b in blocks}
    groupable = [name for name in GROUPABLE_COSTS if name in by_name]
    if len(groupable) < 2:
        return matrix

    rows_to_group: list[tuple[object, list[str]]] = []
    child_names_needed: set[str] = set()
    for idx, row in matrix.iterrows():
        filled = [
            name
            for name in groupable
            if _cell_has_value(row.get(currency_key(name), ""))
        ]
        if len(filled) >= 2:
            rows_to_group.append((idx, filled))
            child_names_needed.update(filled)

    if not rows_to_group:
        return matrix

    children: list[dict] = []
    for name in GROUPABLE_COSTS:
        if name not in child_names_needed:
            continue
        src = by_name[name]
        children.append(
            {
                "name": name,
                "rate_by": src.get("rate_by", ""),
                "brackets": list(src.get("brackets", [])),
            }
        )

    grouped_block = {
        "name": COST_GROUPED,
        "kind": "grouped",
        "children": children,
        "brackets": [],
    }

    for child in children:
        child_name = child["name"]
        cur_col = grouped_currency_key(COST_GROUPED, child_name)
        if cur_col not in matrix.columns:
            matrix[cur_col] = pd.Series([""] * len(matrix), index=matrix.index, dtype=object)
        for br in child["brackets"]:
            br_col = grouped_bracket_key(COST_GROUPED, child_name, br)
            if br_col not in matrix.columns:
                matrix[br_col] = pd.Series(
                    [""] * len(matrix), index=matrix.index, dtype=object
                )

    for idx, filled in rows_to_group:
        for name in filled:
            src_block = by_name[name]
            src_cur = currency_key(name)
            dst_cur = grouped_currency_key(COST_GROUPED, name)
            matrix.at[idx, dst_cur] = matrix.at[idx, src_cur]
            matrix.at[idx, src_cur] = ""
            for br in src_block.get("brackets", []):
                src_br = bracket_key(name, br)
                dst_br = grouped_bracket_key(COST_GROUPED, name, br)
                if src_br in matrix.columns:
                    matrix.at[idx, dst_br] = matrix.at[idx, src_br]
                    matrix.at[idx, src_br] = ""

    insert_at = 0
    for i, block in enumerate(blocks):
        if block["name"] in GROUPABLE_COSTS:
            insert_at = i + 1
    blocks.insert(insert_at, grouped_block)
    matrix.attrs["cost_blocks"] = blocks
    matrix.attrs["cost_names"] = [b["name"] for b in blocks]
    return matrix


def build_matrix_from_sources(
    *,
    ltl_df: pd.DataFrame | None,
    ldm_df: pd.DataFrame | None,
    boxes_df: pd.DataFrame | None,
    by_creditor: dict,
    by_name: dict,
    carrier_ids: set[int],
) -> pd.DataFrame:
    records: list[dict] = []
    if ltl_df is not None and len(ltl_df):
        filtered = filter_by_carriers_and_plant(ltl_df, carrier_ids)
        records.extend(_ingest_ltl(filtered, by_creditor, by_name))
    if ldm_df is not None and len(ldm_df):
        filtered = filter_by_carriers_and_plant(ldm_df, carrier_ids)
        records.extend(_ingest_ldm(filtered, by_creditor, by_name))
    if boxes_df is not None and len(boxes_df):
        filtered = filter_by_carriers_and_plant(boxes_df, carrier_ids)
        records.extend(_ingest_boxes(filtered, by_creditor, by_name))

    merged = _merge_records(records)
    if not merged:
        empty = pd.DataFrame(columns=DETAIL_COLUMNS)
        empty.attrs["cost_blocks"] = []
        empty.attrs["cost_names"] = []
        empty.attrs[ATTR_DUPLICATE_LANE] = []
        empty.attrs[ATTR_VALID_FROM_RATES] = []
        return empty

    cost_blocks = _cost_blocks_for_merged(merged)

    cost_cols: list[str] = []
    for block in cost_blocks:
        cost_cols.extend(block_data_keys(block))

    detail_rows = []
    cost_rows = []
    source_dup_flags: list[bool] = []
    valid_from_rates_flags: list[bool] = []
    for lane_no, rec in enumerate(merged, start=1):
        detail = dict(rec["detail"])
        detail["lane #"] = lane_no
        detail_rows.append(detail)
        cost_rows.append({col: rec["costs"].get(col, "") for col in cost_cols})
        source_dup_flags.append(bool(rec.get("source_duplicate")))
        valid_from_rates_flags.append(bool(rec.get("valid_from_rates_later")))

    details = pd.DataFrame(detail_rows)
    for col in DETAIL_COLUMNS:
        if col not in details.columns:
            details[col] = ""
    details = details[DETAIL_COLUMNS]
    costs = pd.DataFrame(cost_rows) if cost_cols else pd.DataFrame(index=details.index)
    matrix = pd.concat([details, costs], axis=1)
    matrix.attrs["cost_blocks"] = cost_blocks
    matrix.attrs["cost_names"] = [b["name"] for b in cost_blocks]
    # Seed red highlight for lanes that had duplicate source rows on
    # Forwarder + Paying_Plant + OriginNo + DestinationNo (collapsed on merge).
    matrix.attrs[ATTR_DUPLICATE_LANE] = source_dup_flags
    matrix.attrs[ATTR_VALID_FROM_RATES] = valid_from_rates_flags
    matrix = _apply_grouped_transport_costs(matrix)
    return matrix


def build_workbook_frames(
    ltl_df: pd.DataFrame | None,
    ldm_df: pd.DataFrame | None,
    boxes_df: pd.DataFrame | None,
    fuel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from flows.ftl.fuel import build_fuel_lookup

    by_creditor, by_name = build_fuel_lookup(fuel)
    matrix = build_matrix_from_sources(
        ltl_df=ltl_df,
        ldm_df=ldm_df,
        boxes_df=boxes_df,
        by_creditor=by_creditor,
        by_name=by_name,
        carrier_ids=set(ALLOWED_CARRIERS.keys()),
    )
    hero = build_matrix_from_sources(
        ltl_df=ltl_df,
        ldm_df=ldm_df,
        boxes_df=boxes_df,
        by_creditor=by_creditor,
        by_name=by_name,
        carrier_ids=set(HERO_CARRIERS.keys()),
    )
    return matrix, hero
