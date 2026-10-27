"""ALPI rates filtering, lane collapse, and QuantityUnit cost blocks."""

from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

from flows.alpi.config import (
    ALLOWED_CARRIERS,
    ATTR_DEST_COMBINED,
    COST_TON_LTL,
    COST_TRP,
    CURRENCY_REPLACEMENTS,
    DETAIL_COLUMNS,
    LANE_GROUP_COLS,
    TRP_DEDICATED_RANGES,
    UNIT_PALLET,
    UNIT_PALLET_PLACE,
    UNIT_TON,
    UNIT_TRP,
)
from flows.alpi.cost_utils import bracket_key, currency_key, flat_key
from flows.ftl.fuel import (
    attach_fuel_valid_from,
    format_date_ddmmyyyy,
    format_valid_from_with_flag,
)
from flows.ftl.schema import ATTR_VALID_FROM_RATES
from flows.ftl.values import drop_fully_duplicate_rows, norm_key_part, safe_amount, to_carrier_int


def normalize_currency(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return CURRENCY_REPLACEMENTS.get(text.upper(), text)


def normalize_unit(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().casefold()


def destination_base(value) -> str:
    """
    Strip trailing _NN suffix for merge key, e.g. 920271_00 / 920271_13 -> 920271.
    Gathered values ('a_00, a_01') use the first token.
    """
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    first = text.split(",")[0].strip()
    match = re.fullmatch(r"(.+)_(\d+)", first)
    if match:
        return match.group(1).casefold()
    return first.casefold()


def _dest_sort_key(value: str) -> tuple:
    match = re.fullmatch(r"(.+)_(\d+)", value.strip())
    if match:
        return (match.group(1).casefold(), int(match.group(2)))
    return (value.strip().casefold(), -1)


def gather_destination_nos(values) -> tuple[str, bool]:
    """Return (display value, was_combined) from distinct DestinationNo values."""
    seen: list[str] = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.append(text)
    if not seen:
        return "", False
    seen.sort(key=_dest_sort_key)
    if len(seen) == 1:
        return seen[0], False
    return ", ".join(seen), True


def _is_empty_price(price) -> bool:
    """Missing or 0 = no real cost for that bracket (may be filled by another variant)."""
    if price is None or price == "":
        return True
    try:
        return float(price) == 0.0
    except (TypeError, ValueError):
        return False


def _dest_price_map(rows: pd.DataFrame) -> dict[tuple, tuple[str, float]]:
    """
    Map (unit, from, to) -> (currency, price) for one DestinationNo variant.
    First non-empty price wins when the same range appears twice.
    """
    prices: dict[tuple, tuple[str, float]] = {}
    for _, row in rows.iterrows():
        unit = normalize_unit(row.get("QuantityUnit"))
        fr = row.get("QuantityRangeFrom")
        to = row.get("QuantityRangeTo")
        amount = safe_amount(row.get("Price"))
        if amount is None or _is_empty_price(amount):
            continue
        fr_n = round(float(fr), 6) if pd.notna(fr) else None
        to_n = round(float(to), 6) if pd.notna(to) else None
        key = (unit, fr_n, to_n)
        if key in prices:
            continue
        prices[key] = (normalize_currency(row.get("Currency")), float(amount))
    return prices


def _prices_compatible(
    a: dict[tuple, tuple[str, float]],
    b: dict[tuple, tuple[str, float]],
) -> bool:
    """
    Compatible when there is no overlapping conflict:
      - same range empty/0 on one side → ok (complementary)
      - same range same currency+price → ok
      - same range both non-zero and different → not ok
    """
    for key in set(a) | set(b):
        if key not in a or key not in b:
            continue
        if a[key] != b[key]:
            return False
    return True


def _merge_price_maps(
    a: dict[tuple, tuple[str, float]],
    b: dict[tuple, tuple[str, float]],
) -> dict[tuple, tuple[str, float]]:
    out = dict(a)
    for key, val in b.items():
        if key not in out:
            out[key] = val
    return out


def _lane_subgroups_compatible_prices(group: pd.DataFrame) -> list[pd.DataFrame]:
    """
    Within Paying_Plant + OriginNo + destination-base, gather DestinationNo
    variants when prices match or do not overlap (zeros/gaps allowed).
    Conflicting non-zero prices on the same range → separate lanes.
    """
    dest_order: list[str] = []
    by_dest: dict[str, list] = defaultdict(list)
    for idx, row in group.iterrows():
        raw = row.get("DestinationNo")
        dest = "" if pd.isna(raw) else str(raw).strip()
        if dest not in by_dest:
            dest_order.append(dest)
        by_dest[dest].append(idx)

    dest_maps = {
        dest: _dest_price_map(group.loc[by_dest[dest]]) for dest in dest_order
    }

    clusters: list[dict] = []
    for dest in dest_order:
        placed = False
        for cluster in clusters:
            if _prices_compatible(cluster["map"], dest_maps[dest]):
                cluster["dests"].append(dest)
                cluster["map"] = _merge_price_maps(cluster["map"], dest_maps[dest])
                placed = True
                break
        if not placed:
            clusters.append({"dests": [dest], "map": dict(dest_maps[dest])})

    subgroups: list[pd.DataFrame] = []
    for cluster in clusters:
        idxs: list = []
        for dest in cluster["dests"]:
            idxs.extend(by_dest[dest])
        subgroups.append(group.loc[idxs])
    return subgroups


def format_range_number(value) -> str:
    """1.0 -> 1, 2.5 -> 2.5, 2500.0 -> 2500."""
    num = float(value)
    if num.is_integer():
        return str(int(num))
    text = f"{num:.10f}".rstrip("0").rstrip(".")
    return text


def bracket_label(to_value, unit: str) -> str:
    """Build <=N header from QuantityRangeTo (ton values × 1000)."""
    raw = float(to_value)
    if unit == UNIT_TON:
        raw = raw * 1000.0
    return f"<={format_range_number(raw)}"


def validate_rates_columns(rates: pd.DataFrame) -> None:
    required = {
        "Forwarder",
        "CarrierNo",
        "Paying_Plant",
        "CustomerNo",
        "OriginalSender",
        "Shippers_Loading",
        "Loading_Country",
        "Loading_Zip",
        "Loading_City",
        "OriginNo",
        "DestinationNo",
        "Unloading_Country",
        "Unloading_Zip",
        "Unloading_Place",
        "Unloading_City",
        "FinalDestination",
        "validTo",
        "QuantityUnit",
        "QuantityRangeFrom",
        "QuantityRangeTo",
        "Price",
        "Currency",
    }
    missing = required - set(rates.columns)
    if missing:
        raise KeyError(f"ALPI rates file missing columns: {sorted(missing)}")


def filter_rates(
    rates: pd.DataFrame,
    by_creditor: dict[int, object],
    by_name: dict[str, object],
) -> pd.DataFrame:
    """Keep CarrierNo in scope + Paying_Plant containing _CH; attach fuel Valid from."""
    df = rates.copy()
    df["CarrierNo"] = df["CarrierNo"].map(to_carrier_int)
    df = df[df["CarrierNo"].isin(set(ALLOWED_CARRIERS.keys()))]
    df = df[df["Paying_Plant"].astype(str).str.contains("_CH", na=False)]
    df = df.reset_index(drop=True)
    df = drop_fully_duplicate_rows(df, label="ALPI source rows")
    return attach_fuel_valid_from(df, by_creditor, by_name)


def _clean_cell(value) -> object:
    if pd.isna(value):
        return ""
    return value


def _lane_group_key(row: pd.Series) -> tuple:
    parts = []
    for col in LANE_GROUP_COLS:
        raw = row.get(col, "")
        if col == "DestinationNo":
            parts.append(destination_base(raw))
        else:
            parts.append(norm_key_part(raw))
    return tuple(parts)


def _detail_from_group(group: pd.DataFrame, lane_no: int) -> tuple[dict, bool, bool]:
    row = group.iloc[0]
    dest_display, dest_combined = gather_destination_nos(group["DestinationNo"])
    rates_valid = (
        group["validFrom"].max() if "validFrom" in group.columns else pd.NaT
    )
    valid_from, rates_later = format_valid_from_with_flag(
        row.get("_fuel_valid_from"), rates_valid
    )
    detail = {
        "lane #": lane_no,
        "Forwarder": _clean_cell(row["Forwarder"]),
        "CarrierNo": row["CarrierNo"],
        "Paying_Plant": _clean_cell(row["Paying_Plant"]),
        "CustomerNo": _clean_cell(row["CustomerNo"]),
        "OriginalSender": _clean_cell(row["OriginalSender"]),
        "Loading_Country": _clean_cell(row.get("Loading_Country", "")),
        "Shippers_Loading": _clean_cell(row["Shippers_Loading"]),
        "Loading_Zip": _clean_cell(row["Loading_Zip"]),
        "Origin Postal Code": "",
        "Loading_City": _clean_cell(row["Loading_City"]),
        "OriginNo": _clean_cell(row["OriginNo"]),
        "DestinationNo": dest_display,
        "Unloading_Zip": _clean_cell(row["Unloading_Zip"]),
        "Unloading_Country": _clean_cell(row["Unloading_Country"]),
        "Destination Postal Code": "",
        "Unloading_Place": _clean_cell(row["Unloading_Place"]),
        "Unloading_City": _clean_cell(row["Unloading_City"]),
        "FinalDestination": _clean_cell(row["FinalDestination"]),
        "Valid from": valid_from,
        "Valid to": format_date_ddmmyyyy(row.get("validTo")),
    }
    return detail, dest_combined, rates_later


def _range_key(fr, to) -> tuple[float, float]:
    return (round(float(fr), 6), round(float(to), 6))


def _ranges_intersect(
    a: tuple[float, float], b: tuple[float, float]
) -> bool:
    """Closed intervals — touching endpoints count as intersecting."""
    return not (a[1] < b[0] or b[1] < a[0])


def _pack_non_intersecting_ranges(
    ranges: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    """
    Greedy first-fit: place each range into the first block where it does not
    intersect any existing range; otherwise open a new block.
    """
    ordered = sorted(set(ranges))
    blocks: list[list[tuple[float, float]]] = []
    for rng in ordered:
        placed = False
        for block in blocks:
            if any(_ranges_intersect(rng, existing) for existing in block):
                continue
            block.append(rng)
            placed = True
            break
        if not placed:
            blocks.append([rng])
    return blocks


def _collect_bracket_prices(
    unit_rows: pd.DataFrame, unit: str
) -> tuple[str, dict[str, object]] | None:
    """
    Collect currency + {bracket_label: price} for one lane's unit rows.
    First price wins when the same bracket appears twice.
    """
    if len(unit_rows) == 0:
        return None

    prices: dict[str, object] = {}
    currency = ""
    for _, row in unit_rows.iterrows():
        to_val = row.get("QuantityRangeTo")
        if pd.isna(to_val):
            continue
        price = safe_amount(row.get("Price"))
        if price is None:
            continue
        cur = normalize_currency(row.get("Currency"))
        if cur and not currency:
            currency = cur
        label = bracket_label(to_val, unit)
        if label not in prices:
            prices[label] = price

    if not prices:
        return None
    return currency, prices


def _is_unit_step_ranges(unit_rows: pd.DataFrame) -> bool:
    """
    True when every range is From==To (e.g. 1-1, 2-2, 3-3, 4-4).
    Those 'pallet' rows behave like pallet-place brackets, not stepped 1-4/5-8/...
    """
    pairs: list[tuple[float, float]] = []
    for _, row in unit_rows.iterrows():
        fr = row.get("QuantityRangeFrom")
        to = row.get("QuantityRangeTo")
        if pd.isna(fr) or pd.isna(to):
            continue
        pairs.append((float(fr), float(to)))
    if not pairs:
        return False
    return all(a == b for a, b in pairs)


def _split_by_range_width(
    unit_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into (From==To unit-step, From!=To spanned)."""
    if len(unit_rows) == 0:
        empty = unit_rows.iloc[0:0]
        return empty, empty
    fr = unit_rows["QuantityRangeFrom"].astype(float)
    to = unit_rows["QuantityRangeTo"].astype(float)
    unit_step = unit_rows.loc[fr == to]
    spanned = unit_rows.loc[fr != to]
    return unit_step, spanned


def _rows_for_cost_unit(df: pd.DataFrame, unit: str) -> pd.DataFrame:
    """
    Select rate rows that feed a given cost block.
    Unit-step QuantityUnit=pallet (1-1, 2-2, ...) feeds pallet-place, not pallet.
    """
    unit_series = df["QuantityUnit"].map(normalize_unit)
    if unit == UNIT_TON:
        return df.loc[unit_series == UNIT_TON]

    if unit == UNIT_PALLET_PLACE:
        place = df.loc[unit_series == UNIT_PALLET_PLACE]
        pallet = df.loc[unit_series == UNIT_PALLET]
        if len(pallet) == 0:
            return place
        # Keep pallet rows that belong to a lane whose pallet ranges are unit-step
        keep_idx: list = []
        groups: dict[tuple, list] = defaultdict(list)
        for idx, row in pallet.iterrows():
            groups[_lane_group_key(row)].append(idx)
        for key, idxs in groups.items():
            sub = pallet.loc[idxs]
            if _is_unit_step_ranges(sub):
                keep_idx.extend(idxs)
        stepped_as_place = pallet.loc[keep_idx] if keep_idx else pallet.iloc[0:0]
        return pd.concat([place, stepped_as_place], axis=0)

    if unit == UNIT_PALLET:
        pallet = df.loc[unit_series == UNIT_PALLET]
        if len(pallet) == 0:
            return pallet
        keep_idx: list = []
        groups: dict[tuple, list] = defaultdict(list)
        for idx, row in pallet.iterrows():
            groups[_lane_group_key(row)].append(idx)
        for key, idxs in groups.items():
            sub = pallet.loc[idxs]
            if not _is_unit_step_ranges(sub):
                keep_idx.extend(idxs)
        return pallet.loc[keep_idx] if keep_idx else pallet.iloc[0:0]

    return df.loc[unit_series == unit]


def _global_bracket_meta(
    unit_rows: pd.DataFrame, unit: str, *, cost_name: str | None = None
) -> tuple[str, list[str]] | None:
    """
    Cost name + full bracket list for a set of QuantityUnit rows.
    Brackets = sorted union of all To values (unused cells stay empty per lane).
    """
    if len(unit_rows) == 0:
        return None

    label_unit = unit
    bracket_sort: dict[str, float] = {}
    tos: list[float] = []
    for _, row in unit_rows.iterrows():
        to_val = row.get("QuantityRangeTo")
        if pd.isna(to_val):
            continue
        tos.append(float(to_val))
        label = bracket_label(to_val, label_unit)
        sort_key = float(to_val) * (1000.0 if label_unit == UNIT_TON else 1.0)
        bracket_sort[label] = sort_key

    if not bracket_sort:
        return None

    brackets = [
        label for label, _ in sorted(bracket_sort.items(), key=lambda kv: kv[1])
    ]

    if cost_name is None:
        if unit == UNIT_TON:
            cost_name = COST_TON_LTL
        elif unit == UNIT_PALLET_PLACE:
            lo = format_range_number(min(tos))
            hi = format_range_number(max(tos))
            cost_name = f"Transport cost (pallet place {lo}-{hi})"
        elif unit == UNIT_PALLET:
            lo = format_range_number(min(tos))
            hi = format_range_number(max(tos))
            cost_name = f"Transport cost (pallet {lo}-{hi})"
        else:
            cost_name = f"Transport cost ({unit})"

    return cost_name, brackets


def _build_ton_ltl_blocks(df: pd.DataFrame) -> list[dict]:
    """
    Pack ton QuantityRangeFrom–To into non-intersecting blocks.
    All named Transport cost (ton (LTL)) / … 2 / … 3 …
    """
    ton_rows = _rows_for_cost_unit(df, UNIT_TON)
    ranges: list[tuple[float, float]] = []
    for _, row in ton_rows.iterrows():
        fr = row.get("QuantityRangeFrom")
        to = row.get("QuantityRangeTo")
        if pd.isna(fr) or pd.isna(to):
            continue
        ranges.append(_range_key(fr, to))
    if not ranges:
        return []

    packed = _pack_non_intersecting_ranges(ranges)
    blocks: list[dict] = []
    for idx, block_ranges in enumerate(packed):
        name = COST_TON_LTL if idx == 0 else f"Transport cost (ton (LTL) {idx + 1})"
        brackets = [
            bracket_label(to, UNIT_TON)
            for _fr, to in sorted(block_ranges, key=lambda r: r[1])
        ]
        # de-dupe labels while preserving order
        seen: set[str] = set()
        uniq_brackets: list[str] = []
        for br in brackets:
            if br not in seen:
                seen.add(br)
                uniq_brackets.append(br)
        range_to_bracket = {
            rng: bracket_label(rng[1], UNIT_TON) for rng in block_ranges
        }
        blocks.append(
            {
                "name": name,
                "kind": "brackets",
                "brackets": uniq_brackets,
                "unit": UNIT_TON,
                "range_to_bracket": range_to_bracket,
            }
        )
    return blocks


def _build_pallet_place_blocks(df: pd.DataFrame) -> list[dict]:
    """Unit-step (1-1, 6-6, …) and spanned (1-6, 7-10, …) as separate costs."""
    place_rows = _rows_for_cost_unit(df, UNIT_PALLET_PLACE)
    unit_step, spanned = _split_by_range_width(place_rows)
    blocks: list[dict] = []

    meta_step = _global_bracket_meta(unit_step, UNIT_PALLET_PLACE)
    if meta_step is not None:
        name, brackets = meta_step
        blocks.append(
            {
                "name": name,
                "kind": "brackets",
                "brackets": brackets,
                "unit": UNIT_PALLET_PLACE,
                "width": "unit_step",
            }
        )

    if len(spanned):
        tos = [
            float(v)
            for v in spanned["QuantityRangeTo"]
            if not pd.isna(v)
        ]
        frs = [
            float(v)
            for v in spanned["QuantityRangeFrom"]
            if not pd.isna(v)
        ]
        if tos and frs:
            lo = format_range_number(min(frs + tos))
            hi = format_range_number(max(frs + tos))
            span_name = f"Transport cost (pallet place ranges {lo}-{hi})"
            meta_span = _global_bracket_meta(
                spanned, UNIT_PALLET_PLACE, cost_name=span_name
            )
            if meta_span is not None:
                name, brackets = meta_span
                blocks.append(
                    {
                        "name": name,
                        "kind": "brackets",
                        "brackets": brackets,
                        "unit": UNIT_PALLET_PLACE,
                        "width": "span",
                    }
                )
    return blocks


def _build_pallet_block(df: pd.DataFrame) -> list[dict]:
    meta = _global_bracket_meta(
        _rows_for_cost_unit(df, UNIT_PALLET), UNIT_PALLET
    )
    if meta is None:
        return []
    name, brackets = meta
    return [
        {
            "name": name,
            "kind": "brackets",
            "brackets": brackets,
            "unit": UNIT_PALLET,
        }
    ]


def _trp_range_label(fr: float, to: float) -> str:
    return f"{format_range_number(fr)}-{format_range_number(to)}"


def _is_dedicated_trp(fr: float, to: float) -> bool:
    key = _range_key(fr, to)
    return any(_range_key(a, b) == key for a, b in TRP_DEDICATED_RANGES)


def _build_trp_blocks(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """
    Return (shared_flat_blocks, dedicated_flat_blocks).

    Shared: one Currency|Flat Transport cost (trp) for all non-dedicated ranges.
    Dedicated: separate flats for 23-24 and 22.6-24 (config order).
    """
    unit_series = df["QuantityUnit"].map(normalize_unit)
    trp = df.loc[unit_series == UNIT_TRP]
    if len(trp) == 0:
        return [], []

    has_rest = False
    dedicated_present: set[tuple[float, float]] = set()
    for _, row in trp.iterrows():
        fr = row.get("QuantityRangeFrom")
        to = row.get("QuantityRangeTo")
        if pd.isna(fr) or pd.isna(to):
            continue
        key = _range_key(fr, to)
        if _is_dedicated_trp(fr, to):
            dedicated_present.add(key)
        else:
            has_rest = True

    shared: list[dict] = []
    if has_rest:
        shared.append(
            {
                "name": COST_TRP,
                "kind": "flat",
                "brackets": [],
                "unit": UNIT_TRP,
                "trp_shared": True,
            }
        )

    dedicated: list[dict] = []
    for fr, to in TRP_DEDICATED_RANGES:
        key = _range_key(fr, to)
        if key not in dedicated_present:
            continue
        dedicated.append(
            {
                "name": f"Transport cost (trp {_trp_range_label(fr, to)})",
                "kind": "flat",
                "brackets": [],
                "unit": UNIT_TRP,
                "trp_range": key,
            }
        )
    return shared, dedicated


def _fill_bracket_block(
    values: dict[str, object],
    block: dict,
    unit_rows: pd.DataFrame,
    unit: str,
) -> None:
    collected = _collect_bracket_prices(unit_rows, unit)
    if not collected:
        return
    currency, prices = collected
    cost_name = block["name"]
    values[currency_key(cost_name)] = currency
    allowed = set(block.get("brackets", []))
    for br, price in prices.items():
        if br in allowed:
            values[bracket_key(cost_name, br)] = price


def _zero_fill_partial_brackets(
    values: dict[str, object], block: dict
) -> None:
    """
    If a lane has any price in a bracket cost, fill missing brackets with 0.
    Leave the whole cost empty when the lane has no prices for it.
    """
    if block.get("kind") != "brackets":
        return
    name = block["name"]
    brackets = list(block.get("brackets", []))
    if not brackets:
        return

    keys = [bracket_key(name, br) for br in brackets]

    def _has_price(val: object) -> bool:
        if val is None or val == "":
            return False
        if isinstance(val, float) and pd.isna(val):
            return False
        return True

    if not any(_has_price(values.get(k)) for k in keys):
        return

    for key in keys:
        if not _has_price(values.get(key)):
            values[key] = 0


def _build_lane_cost_values(
    group: pd.DataFrame,
    cost_blocks: list[dict],
) -> dict[str, object]:
    """Fill this lane's prices into the shared cost blocks."""
    values: dict[str, object] = {}
    unit_series = group["QuantityUnit"].map(normalize_unit)

    place_rows = group[unit_series == UNIT_PALLET_PLACE]
    pallet_rows = group[unit_series == UNIT_PALLET]
    ton_rows = group[unit_series == UNIT_TON]
    trp_rows = group[unit_series == UNIT_TRP]

    if len(pallet_rows) and _is_unit_step_ranges(pallet_rows):
        place_rows = pd.concat([place_rows, pallet_rows], axis=0)
        pallet_rows = pallet_rows.iloc[0:0]

    place_step, place_span = _split_by_range_width(place_rows)

    # Pre-index ton prices by (From, To)
    ton_by_range: dict[tuple[float, float], tuple[str, object]] = {}
    for _, row in ton_rows.iterrows():
        fr = row.get("QuantityRangeFrom")
        to = row.get("QuantityRangeTo")
        if pd.isna(fr) or pd.isna(to):
            continue
        price = safe_amount(row.get("Price"))
        if price is None:
            continue
        key = _range_key(fr, to)
        if key not in ton_by_range:
            ton_by_range[key] = (normalize_currency(row.get("Currency")), price)

    # Pre-index trp prices
    trp_by_range: dict[tuple[float, float], tuple[str, object]] = {}
    for _, row in trp_rows.iterrows():
        fr = row.get("QuantityRangeFrom")
        to = row.get("QuantityRangeTo")
        if pd.isna(fr) or pd.isna(to):
            continue
        price = safe_amount(row.get("Price"))
        if price is None:
            continue
        key = _range_key(fr, to)
        if key not in trp_by_range:
            trp_by_range[key] = (normalize_currency(row.get("Currency")), price)

    for block in cost_blocks:
        unit = block.get("unit")
        name = block["name"]

        if unit == UNIT_TON:
            mapping: dict[tuple[float, float], str] = block.get(
                "range_to_bracket", {}
            )
            currency = ""
            for rng, label in mapping.items():
                hit = ton_by_range.get(rng)
                if hit is None:
                    continue
                cur, price = hit
                if cur and not currency:
                    currency = cur
                values[bracket_key(name, label)] = price
            if currency or any(
                bracket_key(name, br) in values for br in block.get("brackets", [])
            ):
                values[currency_key(name)] = currency
            continue

        if unit == UNIT_PALLET_PLACE:
            width = block.get("width")
            rows = place_step if width == "unit_step" else place_span
            if len(rows):
                _fill_bracket_block(values, block, rows, UNIT_PALLET_PLACE)
            continue

        if unit == UNIT_PALLET:
            if len(pallet_rows):
                _fill_bracket_block(values, block, pallet_rows, UNIT_PALLET)
            continue

        if unit == UNIT_TRP and block.get("trp_shared"):
            # One flat: first non-dedicated trp price on this lane
            for rng in sorted(trp_by_range.keys()):
                if _is_dedicated_trp(*rng):
                    continue
                cur, price = trp_by_range[rng]
                values[currency_key(name)] = cur
                values[flat_key(name)] = price
                break
            continue

        if unit == UNIT_TRP and block["kind"] == "flat":
            rng = block.get("trp_range")
            if rng is None:
                continue
            hit = trp_by_range.get(_range_key(*rng))
            if hit is None:
                continue
            cur, price = hit
            values[currency_key(name)] = cur
            values[flat_key(name)] = price
            continue

    for block in cost_blocks:
        _zero_fill_partial_brackets(values, block)

    return values


def build_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse quantity/price rows into one matrix row per shipment lane,
    with pivoted Transport cost blocks.
    """
    if len(df) == 0:
        empty = pd.DataFrame(columns=DETAIL_COLUMNS)
        empty.attrs["cost_blocks"] = []
        empty.attrs["cost_names"] = []
        empty.attrs[ATTR_DEST_COMBINED] = []
        empty.attrs[ATTR_VALID_FROM_RATES] = []
        return empty

    place_blocks = _build_pallet_place_blocks(df)
    place_step = [b for b in place_blocks if b.get("width") == "unit_step"]
    place_span = [b for b in place_blocks if b.get("width") == "span"]
    pallet_blocks = _build_pallet_block(df)
    ton_blocks = _build_ton_ltl_blocks(df)
    trp_shared, trp_dedicated = _build_trp_blocks(df)

    # Requested column order
    cost_blocks: list[dict] = []
    cost_blocks.extend(place_step)
    cost_blocks.extend(pallet_blocks)
    cost_blocks.extend(trp_shared)
    cost_blocks.extend(ton_blocks)
    cost_blocks.extend(trp_dedicated)
    cost_blocks.extend(place_span)

    # Preserve input order; split dest-base groups when prices differ
    order_keys: list[tuple] = []
    groups: dict[tuple, list[int]] = defaultdict(list)
    for idx, row in df.iterrows():
        key = _lane_group_key(row)
        if key not in groups:
            order_keys.append(key)
        groups[key].append(idx)

    lane_groups: list[pd.DataFrame] = []
    for key in order_keys:
        lane_groups.extend(_lane_subgroups_compatible_prices(df.loc[groups[key]]))

    detail_rows: list[dict] = []
    dest_combined_flags: list[bool] = []
    valid_from_rates_flags: list[bool] = []
    cost_value_rows: list[dict] = []

    for lane_no, group in enumerate(lane_groups, start=1):
        detail, dest_combined, rates_later = _detail_from_group(group, lane_no)
        detail_rows.append(detail)
        dest_combined_flags.append(dest_combined)
        valid_from_rates_flags.append(rates_later)
        cost_value_rows.append(_build_lane_cost_values(group, cost_blocks))

    cost_cols: list[str] = []
    for block in cost_blocks:
        name = block["name"]
        cost_cols.append(currency_key(name))
        if block["kind"] == "flat":
            cost_cols.append(flat_key(name))
        else:
            for br in block["brackets"]:
                cost_cols.append(bracket_key(name, br))

    cost_data = {col: [] for col in cost_cols}
    for values in cost_value_rows:
        for col in cost_cols:
            cost_data[col].append(values.get(col, ""))

    details = pd.DataFrame(detail_rows)[DETAIL_COLUMNS]
    costs = pd.DataFrame(cost_data)
    matrix = pd.concat([details, costs], axis=1)
    matrix.attrs["cost_blocks"] = cost_blocks
    matrix.attrs["cost_names"] = [b["name"] for b in cost_blocks]
    matrix.attrs[ATTR_DEST_COMBINED] = dest_combined_flags
    matrix.attrs[ATTR_VALID_FROM_RATES] = valid_from_rates_flags
    return matrix
