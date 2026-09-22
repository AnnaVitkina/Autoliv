"""FTL end-to-end pipeline: build sheets, rate-card diff, save workbook."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flows.ftl.conditions import (
    apply_forwarder_common_rating,
    build_conditions_records,
    collect_generated_conditions,
    merge_replacement_records,
)
from flows.ftl.config import ALLOWED_CARRIERS, HERO_CARRIERS
from flows.ftl.dedup import apply_progressive_dedup_fields, mark_duplicate_lanes
from flows.ftl.rates import (
    build_details,
    build_keyword_cost_columns,
    build_other_surcharge_columns,
    filter_rates,
    validate_rates_columns,
)
from flows.ftl.conditions_text import (
    expand_collection_days,
    is_combined_code,
    is_comma_combined,
)
from flows.ftl.excel_write import save_workbook
from flows.ftl.fuel import build_fuel_lookup
from flows.ftl.io import ask_fuel_file, ask_rates_file, list_rates_files, read_table
from flows.ftl.paths import flow_rates_dir
from flows.ftl.rate_card_compare import (
    apply_rate_card_diff,
    ask_previous_rate_card_file,
)
from flows.ftl.schema import (
    ATTR_CHANGED_CELLS,
    ATTR_COLLECTION_COMBINED,
    ATTR_COMPANY_CODE_CONDITIONS,
    ATTR_DEST_COMBINED,
    ATTR_DUPLICATE_LANE,
    ATTR_FORWARDER_REPLACED,
    ATTR_FORWARDER_REPLACEMENTS,
    ATTR_NEW_LANE,
    ATTR_ORIGIN_COMBINED,
    ATTR_PAYING_PLANT_COMBINED,
    ATTR_REMOVED_LANE,
    ATTR_VALID_FROM_RATES,
    DETAIL_COLUMNS,
    SHEET_CONDITIONS,
    SHEET_HERO,
    SHEET_MATRIX,
    SHEET_OTHER,
)

# Stable lane identity for previous-rates compare
# (avoid Service / Equipment / Collection day — often blanked by progressive dedup)
FTL_RATE_CARD_MATCH_COLS = [
    "RateCode",
    "CarrierNo",
    "Paying_Plant",
    "OriginNo",
    "DestinationNo",
    "Singletrip_Roundtrip",
]


def assemble_sheet(
    df: pd.DataFrame,
    costs: pd.DataFrame,
    cost_names: list[str],
    apply_common_rating: bool = True,
) -> tuple[pd.DataFrame, list[dict]]:
    details = build_details(df)
    replacements: list[dict] = []
    replaced_flags = [False] * len(details)

    if apply_common_rating and len(details):
        details, replaced_flags, replacements = apply_forwarder_common_rating(details)

    origin_flags = [is_combined_code(v) for v in details["OriginNo"]]
    dest_flags = [is_combined_code(v) for v in details["DestinationNo"]]
    collection_flags = [
        expand_collection_days(v) is not None for v in details["Collection day"]
    ]
    paying_flags = [is_comma_combined(v) for v in details["Paying_Plant"]]

    matrix = pd.concat([details, costs], axis=1)
    matrix.attrs["cost_names"] = cost_names
    matrix.attrs[ATTR_FORWARDER_REPLACED] = replaced_flags
    matrix.attrs[ATTR_FORWARDER_REPLACEMENTS] = replacements
    matrix.attrs[ATTR_ORIGIN_COMBINED] = origin_flags
    matrix.attrs[ATTR_DEST_COMBINED] = dest_flags
    matrix.attrs[ATTR_COLLECTION_COMBINED] = collection_flags
    matrix.attrs[ATTR_PAYING_PLANT_COMBINED] = paying_flags
    matrix.attrs[ATTR_VALID_FROM_RATES] = list(
        details.attrs.get(ATTR_VALID_FROM_RATES, [False] * len(details))
    )
    matrix = apply_progressive_dedup_fields(matrix)
    return matrix, replacements


def build_workbook_sheets(
    rates: pd.DataFrame, fuel: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    validate_rates_columns(rates)
    by_creditor, by_name = build_fuel_lookup(fuel)

    main_df = filter_rates(
        rates, set(ALLOWED_CARRIERS.keys()), by_creditor, by_name
    )
    hero_df = filter_rates(rates, set(HERO_CARRIERS.keys()), by_creditor, by_name)

    main_costs, main_cost_names = build_keyword_cost_columns(main_df)
    other_costs, other_cost_names = build_other_surcharge_columns(main_df)
    hero_costs, hero_cost_names = build_keyword_cost_columns(hero_df)

    matrix, matrix_repl = assemble_sheet(main_df, main_costs, main_cost_names)
    other, other_repl = assemble_sheet(main_df, other_costs, other_cost_names)
    hero, hero_repl = assemble_sheet(hero_df, hero_costs, hero_cost_names)

    all_repl = merge_replacement_records(matrix_repl + hero_repl)
    rules_df, applied_df = build_conditions_records(all_repl)
    company_conds = collect_generated_conditions(
        matrix[DETAIL_COLUMNS],
        hero[DETAIL_COLUMNS],
    )

    conditions = rules_df.copy()
    conditions.attrs["applied_replacements"] = applied_df
    conditions.attrs[ATTR_COMPANY_CODE_CONDITIONS] = company_conds

    return {
        SHEET_MATRIX: matrix,
        SHEET_OTHER: other,
        SHEET_HERO: hero,
        SHEET_CONDITIONS: conditions,
    }


def _print_sheet_stats(sheets: dict[str, pd.DataFrame]) -> None:
    for name, matrix in sheets.items():
        if name == SHEET_CONDITIONS:
            applied = matrix.attrs.get("applied_replacements")
            company = matrix.attrs.get(ATTR_COMPANY_CODE_CONDITIONS)
            n_applied = 0 if applied is None else len(applied)
            n_company = 0 if company is None else len(company)
            print(
                f"  [{name}] {len(matrix)} Forwarder rules, "
                f"{n_applied} Forwarder replacements, "
                f"{n_company} generated field conditions"
            )
            continue
        cost_names = matrix.attrs.get("cost_names", [])
        n_rated = sum(1 for f in matrix.attrs.get(ATTR_FORWARDER_REPLACED, []) if f)
        n_origin = sum(1 for f in matrix.attrs.get(ATTR_ORIGIN_COMBINED, []) if f)
        n_dest = sum(1 for f in matrix.attrs.get(ATTR_DEST_COMBINED, []) if f)
        n_coll = sum(1 for f in matrix.attrs.get(ATTR_COLLECTION_COMBINED, []) if f)
        n_pay = sum(1 for f in matrix.attrs.get(ATTR_PAYING_PLANT_COMBINED, []) if f)
        n_chg = sum(1 for s in matrix.attrs.get(ATTR_CHANGED_CELLS, []) if s)
        n_new = sum(1 for f in matrix.attrs.get(ATTR_NEW_LANE, []) if f)
        n_rem = sum(1 for f in matrix.attrs.get(ATTR_REMOVED_LANE, []) if f)
        n_dup = sum(1 for f in matrix.attrs.get(ATTR_DUPLICATE_LANE, []) if f)
        n_vf = sum(1 for f in matrix.attrs.get(ATTR_VALID_FROM_RATES, []) if f)
        print(
            f"  [{name}] {len(matrix)} lanes, {len(cost_names)} cost blocks, "
            f"conditioned: Fwd {n_rated} / Origin {n_origin} / Dest {n_dest} / "
            f"CollDay {n_coll} / Plant {n_pay}; changed: {n_chg}; new: {n_new}; "
            f"removed: {n_rem}; duplicates: {n_dup}; "
            f"valid_from_rates: {n_vf}"
        )
        for cost_name in cost_names[:8]:
            print(f"      - {cost_name}")
        if len(cost_names) > 8:
            print(f"      ... +{len(cost_names) - 8} more")


def run_ftl() -> Path:
    """Interactive FTL matrix build."""
    rates_dir = flow_rates_dir("ftl")
    rates_files = list_rates_files(rates_dir)
    rates_file = ask_rates_file(rates_files)
    fuel_file = ask_fuel_file()

    print(f"\nFlow                 : FTL")
    print(f"Rates file           : {rates_file.name}")
    print(f"Fuel file            : {fuel_file.name}")

    rates = read_table(rates_file)
    fuel = read_table(fuel_file)

    sheets = build_workbook_sheets(rates, fuel)
    for name in (SHEET_MATRIX, SHEET_OTHER, SHEET_HERO):
        if name in sheets:
            sheets[name] = mark_duplicate_lanes(sheets[name])

    # Rebuild Conditions company-code attrs after any later sheet edits
    if SHEET_CONDITIONS in sheets:
        frames = []
        if SHEET_MATRIX in sheets:
            frames.append(sheets[SHEET_MATRIX][DETAIL_COLUMNS])
        if SHEET_HERO in sheets:
            frames.append(sheets[SHEET_HERO][DETAIL_COLUMNS])
        sheets[SHEET_CONDITIONS].attrs[ATTR_COMPANY_CODE_CONDITIONS] = (
            collect_generated_conditions(*frames)
        )

    previous = ask_previous_rate_card_file(label="previous rates file")
    previous_sheets = None
    if previous is not None:
        print(f"Previous rates file : {previous.name}")
        previous_sheets = build_workbook_sheets(read_table(previous), fuel)
        for name in (SHEET_MATRIX, SHEET_OTHER, SHEET_HERO):
            if name in previous_sheets:
                previous_sheets[name] = mark_duplicate_lanes(previous_sheets[name])

    sheets = apply_rate_card_diff(
        sheets,
        previous_sheets,
        FTL_RATE_CARD_MATCH_COLS,
    )

    out_path = save_workbook(sheets, rates_file)

    print(f"\nSaved to: {out_path}")
    _print_sheet_stats(sheets)
    return out_path
