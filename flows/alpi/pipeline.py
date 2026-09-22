"""ALPI end-to-end pipeline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flows.alpi.config import ATTR_DEST_COMBINED, ATTR_DUPLICATE_LANE, SHEET_MATRIX
from flows.alpi.dedup import mark_duplicate_lanes
from flows.alpi.excel_write import save_workbook
from flows.alpi.rates import build_matrix, filter_rates, validate_rates_columns
from flows.ftl.fuel import build_fuel_lookup
from flows.ftl.io import ask_fuel_file, ask_rates_file, list_rates_files, read_table
from flows.ftl.paths import flow_rates_dir
from flows.ftl.rate_card_compare import (
    apply_rate_card_diff,
    ask_previous_rate_card_file,
)
from flows.ftl.schema import (
    ATTR_CHANGED_CELLS,
    ATTR_NEW_LANE,
    ATTR_REMOVED_LANE,
    ATTR_VALID_FROM_RATES,
)

ALPI_RATE_CARD_MATCH_COLS = [
    "Paying_Plant",
    "OriginNo",
    "DestinationNo",
]


def build_workbook_sheets(
    rates: pd.DataFrame, fuel: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    validate_rates_columns(rates)
    by_creditor, by_name = build_fuel_lookup(fuel)
    filtered = filter_rates(rates, by_creditor, by_name)
    matrix = build_matrix(filtered)
    matrix = mark_duplicate_lanes(matrix)
    return {SHEET_MATRIX: matrix}


def _print_stats(sheets: dict[str, pd.DataFrame]) -> None:
    for name, matrix in sheets.items():
        blocks = matrix.attrs.get("cost_blocks", [])
        n_dup = sum(1 for f in matrix.attrs.get(ATTR_DUPLICATE_LANE, []) if f)
        n_dest = sum(1 for f in matrix.attrs.get(ATTR_DEST_COMBINED, []) if f)
        n_chg = sum(1 for s in matrix.attrs.get(ATTR_CHANGED_CELLS, []) if s)
        n_new = sum(1 for f in matrix.attrs.get(ATTR_NEW_LANE, []) if f)
        n_rem = sum(1 for f in matrix.attrs.get(ATTR_REMOVED_LANE, []) if f)
        n_vf = sum(1 for f in matrix.attrs.get(ATTR_VALID_FROM_RATES, []) if f)
        print(
            f"  [{name}] {len(matrix)} lanes, {len(blocks)} cost blocks, "
            f"gathered Dest: {n_dest}; duplicates: {n_dup}; "
            f"changed: {n_chg}; new: {n_new}; removed: {n_rem}; "
            f"valid_from_rates: {n_vf}"
        )
        for block in blocks[:12]:
            if block["kind"] == "brackets":
                print(
                    f"      - {block['name']} "
                    f"[{len(block.get('brackets', []))} brackets]"
                )
            else:
                print(f"      - {block['name']} [Currency|Flat]")
        if len(blocks) > 12:
            print(f"      ... +{len(blocks) - 12} more")


def run_alpi() -> Path:
    rates_dir = flow_rates_dir("alpi")
    rates_files = list_rates_files(rates_dir)
    rates_file = ask_rates_file(rates_files)
    fuel_file = ask_fuel_file()

    print(f"\nFlow        : Road ALPI")
    print(f"Rates file  : {rates_file.name}")
    print(f"Fuel file   : {fuel_file.name}")

    rates = read_table(rates_file)
    fuel = read_table(fuel_file)

    sheets = build_workbook_sheets(rates, fuel)

    previous = ask_previous_rate_card_file(label="previous rates file")
    previous_sheets = None
    if previous is not None:
        print(f"Previous rates file : {previous.name}")
        previous_sheets = build_workbook_sheets(read_table(previous), fuel)

    sheets = apply_rate_card_diff(sheets, previous_sheets, ALPI_RATE_CARD_MATCH_COLS)

    out_path = save_workbook(sheets, rates_file)

    print(f"\nSaved to: {out_path}")
    _print_stats(sheets)
    return out_path
