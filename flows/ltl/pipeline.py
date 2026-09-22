"""LTL end-to-end pipeline — LTL / LDM / Boxes inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flows.ftl.io import ask_fuel_file, ask_multi_rates_files, list_rates_files, read_table
from flows.ftl.paths import flow_rates_dir
from flows.ftl.rate_card_compare import (
    apply_rate_card_diff,
    ask_previous_ltl_rate_files,
)
from flows.ftl.schema import (
    ATTR_CHANGED_CELLS,
    ATTR_NEW_LANE,
    ATTR_REMOVED_LANE,
    ATTR_VALID_FROM_RATES,
)
from flows.ltl.conditions import (
    apply_forwarder_common_rating,
    build_conditions_records,
    merge_replacement_records,
)
from flows.ltl.config import (
    ATTR_DUPLICATE_LANE,
    ATTR_FORWARDER_REPLACED,
    DETAIL_COLUMNS,
    SHEET_CONDITIONS,
    SHEET_HERO,
    SHEET_MATRIX,
)
from flows.ltl.dedup import mark_duplicate_lanes
from flows.ltl.excel_write import save_workbook
from flows.ltl.rates import build_workbook_frames

# Stable lane identity for previous-rates compare (avoid RateCode-only churn)
LTL_RATE_CARD_MATCH_COLS = [
    "CarrierNo",
    "Paying_Plant",
    "OriginNo",
    "DestinationNo",
]


def classify_input_files(
    files: list[Path],
) -> tuple[Path | None, Path | None, Path | None]:
    """Pick LTL / LDM / Boxes files by filename keywords (first match each)."""
    ltl = ldm = boxes = None
    for path in files:
        name = path.name.casefold()
        if "ldm" in name and ldm is None:
            ldm = path
        elif "box" in name and boxes is None:
            boxes = path
        elif "ltl" in name and ltl is None:
            ltl = path
    return ltl, ldm, boxes


def ask_ltl_input_files(
    files: list[Path],
) -> tuple[Path | None, Path | None, Path | None]:
    """
    Prompt which rates files to process, then classify as LTL / LDM / Boxes.
    """
    selected = ask_multi_rates_files(files)
    ltl_path, ldm_path, boxes_path = classify_input_files(selected)
    unclassified = [
        p
        for p in selected
        if p not in {ltl_path, ldm_path, boxes_path}
    ]
    if unclassified:
        names = ", ".join(p.name for p in unclassified)
        print(
            f"Note: skipped (filename needs LTL, LDM, or Boxes): {names}"
        )
    if ltl_path is None and ldm_path is None and boxes_path is None:
        raise FileNotFoundError(
            "None of the selected files could be classified as LTL, LDM, or Boxes "
            "(filename should contain LTL, LDM, or Boxes)."
        )
    return ltl_path, ldm_path, boxes_path


def _apply_common_rating(matrix: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    if len(matrix) == 0:
        matrix.attrs[ATTR_FORWARDER_REPLACED] = []
        return matrix, []
    details = matrix[DETAIL_COLUMNS].copy()
    details, flags, replacements = apply_forwarder_common_rating(details)
    for col in DETAIL_COLUMNS:
        matrix[col] = details[col].values
    matrix.attrs[ATTR_FORWARDER_REPLACED] = flags
    return matrix, replacements


def build_workbook_sheets(
    ltl_df: pd.DataFrame | None,
    ldm_df: pd.DataFrame | None,
    boxes_df: pd.DataFrame | None,
    fuel: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    matrix, hero = build_workbook_frames(ltl_df, ldm_df, boxes_df, fuel)
    matrix, matrix_repl = _apply_common_rating(matrix)
    hero, hero_repl = _apply_common_rating(hero)
    matrix = mark_duplicate_lanes(matrix)
    hero = mark_duplicate_lanes(hero)

    all_repl = merge_replacement_records(matrix_repl + hero_repl)
    rules_df, applied_df = build_conditions_records(all_repl)
    conditions = rules_df.copy()
    conditions.attrs["applied_replacements"] = applied_df

    return {
        SHEET_MATRIX: matrix,
        SHEET_HERO: hero,
        SHEET_CONDITIONS: conditions,
    }


def _print_stats(sheets: dict[str, pd.DataFrame]) -> None:
    for name, matrix in sheets.items():
        if name == SHEET_CONDITIONS:
            applied = matrix.attrs.get("applied_replacements")
            n_applied = 0 if applied is None else len(applied)
            print(f"  [{name}] {len(matrix)} Forwarder rules, {n_applied} replacements")
            continue
        blocks = matrix.attrs.get("cost_blocks", [])
        n_dup = sum(1 for f in matrix.attrs.get(ATTR_DUPLICATE_LANE, []) if f)
        n_fwd = sum(1 for f in matrix.attrs.get(ATTR_FORWARDER_REPLACED, []) if f)
        n_chg = sum(1 for s in matrix.attrs.get(ATTR_CHANGED_CELLS, []) if s)
        n_new = sum(1 for f in matrix.attrs.get(ATTR_NEW_LANE, []) if f)
        n_rem = sum(1 for f in matrix.attrs.get(ATTR_REMOVED_LANE, []) if f)
        n_vf = sum(1 for f in matrix.attrs.get(ATTR_VALID_FROM_RATES, []) if f)
        print(
            f"  [{name}] {len(matrix)} lanes, {len(blocks)} cost blocks, "
            f"Fwd rated: {n_fwd}; duplicates: {n_dup}; "
            f"changed: {n_chg}; new: {n_new}; removed: {n_rem}; "
            f"valid_from_rates: {n_vf}"
        )
        for block in blocks:
            print(
                f"      - {block['name']} "
                f"[{len(block.get('brackets', []))} brackets]"
            )


def run_ltl() -> Path:
    rates_dir = flow_rates_dir("ltl")
    files = list_rates_files(rates_dir)
    ltl_path, ldm_path, boxes_path = ask_ltl_input_files(files)

    fuel_file = ask_fuel_file()

    print(f"\nFlow        : LTL")
    print(f"LTL file    : {ltl_path.name if ltl_path else '(none)'}")
    print(f"LDM file    : {ldm_path.name if ldm_path else '(none)'}")
    print(f"Boxes file  : {boxes_path.name if boxes_path else '(none)'}")
    print(f"Fuel file   : {fuel_file.name}")

    ltl_df = read_table(ltl_path) if ltl_path else None
    ldm_df = read_table(ldm_path) if ldm_path else None
    boxes_df = read_table(boxes_path) if boxes_path else None
    fuel = read_table(fuel_file)

    sheets = build_workbook_sheets(ltl_df, ldm_df, boxes_df, fuel)

    previous_sel = ask_previous_ltl_rate_files()
    previous_sheets = None
    if previous_sel is not None:
        prev_ltl, prev_ldm, prev_boxes = previous_sel
        print(
            f"Previous LTL/LDM/Boxes: "
            f"{prev_ltl.name if prev_ltl else '(none)'} / "
            f"{prev_ldm.name if prev_ldm else '(none)'} / "
            f"{prev_boxes.name if prev_boxes else '(none)'}"
        )
        previous_sheets = build_workbook_sheets(
            read_table(prev_ltl) if prev_ltl else None,
            read_table(prev_ldm) if prev_ldm else None,
            read_table(prev_boxes) if prev_boxes else None,
            fuel,
        )

    sheets = apply_rate_card_diff(sheets, previous_sheets, LTL_RATE_CARD_MATCH_COLS)

    stem_parts = []
    if ltl_path:
        stem_parts.append(ltl_path.stem)
    elif ldm_path:
        stem_parts.append(ldm_path.stem)
    elif boxes_path:
        stem_parts.append(boxes_path.stem)
    rates_stem = stem_parts[0] if stem_parts else "LTL"

    out_path = save_workbook(sheets, rates_stem)
    print(f"\nSaved to: {out_path}")
    _print_stats(sheets)
    return out_path
