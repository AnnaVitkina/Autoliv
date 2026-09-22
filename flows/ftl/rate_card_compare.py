"""Compare newly built matrix sheets against sheets built from a previous rates file."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from flows.ftl.io import ask_choice, list_excel_files
from flows.ftl import paths as project_paths
from flows.ftl.schema import (
    ATTR_CHANGED_CELLS,
    ATTR_NEW_LANE,
    ATTR_REMOVED_LANE,
    SHEET_CONDITIONS,
)
from flows.ftl.values import cmp_value, norm_key_part


def list_previous_rate_card_files(folder: Path | None = None) -> list[Path]:
    """Original rates files in input/previous rate card."""
    root = folder or project_paths.PREVIOUS_RATE_CARD_DIR
    if not root.exists():
        return []
    return list_excel_files(root)


def ask_previous_rate_card_file(
    folder: Path | None = None,
    *,
    label: str = "previous rate card",
) -> Path | None:
    """
    Ask which previous *original rates* file to compare against (0 = skip).
    Files are listed from input/previous rate card.
    """
    root = folder or project_paths.PREVIOUS_RATE_CARD_DIR
    files = list_previous_rate_card_files(root)
    print(f"\nPrevious rate card folder: {root}")
    print(f"Original rates files for {label}:")
    if not files:
        print("  (none)")
        print("  0. Skip")
        ask_choice(f"\nSelect {label} (or 0 to skip): ", [], allow_zero=True)
        return None

    for i, path in enumerate(files, start=1):
        print(f"  {i}. {path.name}")
    print("  0. Skip (no yellow/green/removed highlights)")

    idx = ask_choice(
        f"\nSelect {label} (or 0 to skip): ",
        [p.name for p in files],
        allow_zero=True,
    )
    if idx == 0:
        return None
    return files[idx - 1]


def ask_previous_ltl_rate_files(
    folder: Path | None = None,
) -> tuple[Path | None, Path | None, Path | None] | None:
    """
    Ask which previous LTL/LDM/Boxes original rates to use.
    Returns None when the user skips compare entirely.
    """
    root = folder or project_paths.PREVIOUS_RATE_CARD_DIR
    files = list_previous_rate_card_files(root)
    print(f"\nPrevious rate card folder: {root}")
    print("Previous LTL / LDM / Boxes rates files:")
    if not files:
        print("  (none)")
        print("  0. Skip")
        ask_choice("\nSelect previous rates (or 0 to skip): ", [], allow_zero=True)
        return None

    for i, path in enumerate(files, start=1):
        print(f"  {i}. {path.name}")
    print("  A. All")
    print("  0. Skip (no yellow/green/removed highlights)")

    while True:
        raw = input(
            "\nSelect previous file numbers (e.g. 1,3), A for all, or 0 to skip: "
        ).strip()
        if not raw:
            print("Please enter a selection.")
            continue
        if raw == "0":
            return None
        if raw.casefold() in {"a", "all"}:
            selected = list(files)
            break
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        if not parts or not all(p.isdigit() for p in parts):
            print("Please enter numbers like 1,2 or A or 0.")
            continue
        idxs = [int(p) for p in parts]
        if any(i < 1 or i > len(files) for i in idxs):
            print(f"Please enter numbers between 1 and {len(files)}, or A / 0.")
            continue
        seen: set[int] = set()
        selected = []
        for i in idxs:
            if i not in seen:
                seen.add(i)
                selected.append(files[i - 1])
        break

    ltl = ldm = boxes = None
    for path in selected:
        name = path.name.casefold()
        if "ldm" in name and ldm is None:
            ldm = path
        elif "box" in name and boxes is None:
            boxes = path
        elif "ltl" in name and ltl is None:
            ltl = path
    if ltl is None and ldm is None and boxes is None:
        print(
            "Note: none of the selected files classified as LTL/LDM/Boxes "
            "(filename should contain LTL, LDM, or Boxes)."
        )
        return None
    return ltl, ldm, boxes


def _row_match_key(row: pd.Series, match_cols: list[str]) -> tuple:
    parts = []
    for col in match_cols:
        parts.append(norm_key_part(row[col] if col in row.index else ""))
    return tuple(parts)


def _fallback_match_cols(match_cols: list[str], columns) -> list[str]:
    """Shorter stable key used when the primary key fails to pair a lane."""
    preferred = [
        "CarrierNo",
        "Paying_Plant",
        "OriginNo",
        "DestinationNo",
        "Singletrip_Roundtrip",
    ]
    cols = [c for c in preferred if c in columns]
    if len(cols) >= 3:
        return cols
    # Fall back to primary cols without RateCode / Lane ID
    return [
        c
        for c in match_cols
        if c in columns and c not in {"RateCode", "Lane ID", "lane #"}
    ]


def _volatile_compare_cols() -> set[str]:
    """Fields that often change without meaning a different lane."""
    return {"lane #", "Valid from", "Valid to", "Lane ID", "RateCode"}


def _content_fingerprint(row: pd.Series, cols: list[str]) -> tuple:
    skip = _volatile_compare_cols()
    return tuple(
        (col, cmp_value(row.get(col, "")))
        for col in cols
        if col not in skip
    )


def compare_matrix_to_previous(
    matrix: pd.DataFrame,
    previous: pd.DataFrame,
    match_cols: list[str],
) -> pd.DataFrame:
    """
    Annotate matrix vs previous (both built from original rates):
      - new lanes -> ATTR_NEW_LANE (yellow)
      - changed cells -> ATTR_CHANGED_CELLS (green)
      - removed lanes appended from previous -> ATTR_REMOVED_LANE (removed-red)

    Matching is multi-pass so the same commercial lane is not marked both
    new and removed when RateCode / helper fields differ between extracts:
      1) primary match_cols
      2) fallback CarrierNo+Plant+Origin+Dest(+Singletrip)
      3) full content fingerprint (excluding volatile date/id fields)
    """
    attrs = dict(matrix.attrs)
    n = len(matrix)

    compare_cols = [
        c for c in matrix.columns if c in previous.columns and c != "lane #"
    ]
    primary_cols = [c for c in match_cols if c in matrix.columns]
    fallback_cols = _fallback_match_cols(primary_cols, matrix.columns)

    old_by_primary: dict[tuple, list[int]] = defaultdict(list)
    old_by_fallback: dict[tuple, list[int]] = defaultdict(list)
    old_by_content: dict[tuple, list[int]] = defaultdict(list)
    for idx in range(len(previous)):
        row = previous.iloc[idx]
        old_by_primary[_row_match_key(row, primary_cols)].append(idx)
        if fallback_cols:
            old_by_fallback[_row_match_key(row, fallback_cols)].append(idx)
        old_by_content[_content_fingerprint(row, compare_cols)].append(idx)

    paired_old: list[int | None] = [None] * n
    used_old: set[int] = set()

    def _take(bucket: dict[tuple, list[int]], key: tuple) -> int | None:
        candidates = [i for i in bucket.get(key, []) if i not in used_old]
        if not candidates:
            return None
        old_idx = candidates[0]
        used_old.add(old_idx)
        return old_idx

    # Pass 1 — primary key
    for r_idx, (_, row) in enumerate(matrix.iterrows()):
        old_idx = _take(old_by_primary, _row_match_key(row, primary_cols))
        if old_idx is not None:
            paired_old[r_idx] = old_idx

    # Pass 2 — fallback key for still-unmatched rows
    if fallback_cols:
        for r_idx, (_, row) in enumerate(matrix.iterrows()):
            if paired_old[r_idx] is not None:
                continue
            old_idx = _take(old_by_fallback, _row_match_key(row, fallback_cols))
            if old_idx is not None:
                paired_old[r_idx] = old_idx

    # Pass 3 — identical content (ignore volatile ids/dates)
    for r_idx, (_, row) in enumerate(matrix.iterrows()):
        if paired_old[r_idx] is not None:
            continue
        old_idx = _take(old_by_content, _content_fingerprint(row, compare_cols))
        if old_idx is not None:
            paired_old[r_idx] = old_idx

    changed_rows: list[set[str]] = []
    new_flags: list[bool] = []
    removed_flags: list[bool] = [False] * n

    for r_idx, (_, row) in enumerate(matrix.iterrows()):
        old_idx = paired_old[r_idx]
        if old_idx is None:
            new_flags.append(True)
            changed_rows.append(set())
            continue
        old_row = previous.iloc[old_idx]
        new_flags.append(False)
        changed: set[str] = set()
        for col in compare_cols:
            if cmp_value(row.get(col, "")) != cmp_value(old_row.get(col, "")):
                changed.add(col)
        changed_rows.append(changed)

    removed_records: list[dict] = []
    for idx in range(len(previous)):
        if idx in used_old:
            continue
        old_row = previous.iloc[idx]
        rec = {col: "" for col in matrix.columns}
        for col in matrix.columns:
            if col in previous.columns:
                val = old_row[col]
                rec[col] = "" if pd.isna(val) else val
        removed_records.append(rec)

    if removed_records:
        removed_df = pd.DataFrame(removed_records)
        out = pd.concat([matrix.reset_index(drop=True), removed_df], ignore_index=True)
        changed_rows.extend(set() for _ in removed_records)
        new_flags.extend(False for _ in removed_records)
        removed_flags.extend(True for _ in removed_records)
    else:
        out = matrix.reset_index(drop=True)

    if "lane #" in out.columns:
        out["lane #"] = range(1, len(out) + 1)

    n_removed = len(removed_records)
    for attr, values in list(attrs.items()):
        if attr in (ATTR_CHANGED_CELLS, ATTR_NEW_LANE, ATTR_REMOVED_LANE):
            continue
        if not isinstance(values, list) or len(values) != n:
            continue
        if not values:
            attrs[attr] = list(values) + [False] * n_removed
            continue
        sample = values[0]
        if isinstance(sample, set):
            attrs[attr] = list(values) + [set() for _ in range(n_removed)]
        elif isinstance(sample, bool):
            attrs[attr] = list(values) + [False] * n_removed
        else:
            attrs[attr] = list(values) + [None] * n_removed

    attrs[ATTR_CHANGED_CELLS] = changed_rows
    attrs[ATTR_NEW_LANE] = new_flags
    attrs[ATTR_REMOVED_LANE] = removed_flags
    out.attrs.update(attrs)
    return out


def apply_rate_card_diff(
    sheets: dict[str, pd.DataFrame],
    previous_sheets: dict[str, pd.DataFrame] | None,
    match_cols: list[str],
    *,
    skip_sheets: set[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Compare each matrix-like sheet to the same-named sheet built from the
    previous original rates file(s). Skip Conditions.
    """
    skip = set(skip_sheets or ())
    skip.add(SHEET_CONDITIONS)

    if previous_sheets is None:
        for name, matrix in sheets.items():
            if name in skip:
                continue
            matrix.attrs[ATTR_CHANGED_CELLS] = [set() for _ in range(len(matrix))]
            matrix.attrs[ATTR_NEW_LANE] = [False] * len(matrix)
            matrix.attrs[ATTR_REMOVED_LANE] = [False] * len(matrix)
            sheets[name] = matrix
            print(f"  [{name}] previous rate card skipped")
        return sheets

    for name, matrix in list(sheets.items()):
        if name in skip:
            continue
        previous = previous_sheets.get(name)
        if previous is None:
            matrix.attrs[ATTR_CHANGED_CELLS] = [set() for _ in range(len(matrix))]
            matrix.attrs[ATTR_NEW_LANE] = [False] * len(matrix)
            matrix.attrs[ATTR_REMOVED_LANE] = [False] * len(matrix)
            sheets[name] = matrix
            print(f"  [{name}] not in previous build — no compare")
            continue

        before = len(matrix)
        matrix = compare_matrix_to_previous(matrix, previous, match_cols)
        n_new = sum(1 for f in matrix.attrs.get(ATTR_NEW_LANE, []) if f)
        n_chg = sum(1 for s in matrix.attrs.get(ATTR_CHANGED_CELLS, []) if s)
        n_rem = sum(1 for f in matrix.attrs.get(ATTR_REMOVED_LANE, []) if f)
        print(
            f"  [{name}] vs previous rates: {before} -> {len(matrix)} lanes; "
            f"new={n_new}; changed={n_chg}; removed={n_rem}"
        )
        sheets[name] = matrix
    return sheets
