"""File listing, prompts, and table loading shared by all flows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flows.ftl import paths as project_paths


def list_excel_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and not p.name.startswith("~$")
        and p.suffix.lower() in {".xlsx", ".xls", ".xlsm", ".csv"}
    )


def list_rates_files(rates_dir: Path) -> list[Path]:
    if not rates_dir.exists():
        raise FileNotFoundError(f"Rates folder not found: {rates_dir}")
    files = list_excel_files(rates_dir)
    if not files:
        raise FileNotFoundError(f"No Excel/CSV files found in {rates_dir}")
    return files


def ask_choice(prompt: str, items: list[str], allow_zero: bool = False) -> int:
    """Return 1-based index, or 0 when allow_zero and user picks skip."""
    while True:
        choice = input(prompt).strip()
        if not choice.isdigit():
            print("Please enter a number.")
            continue
        idx = int(choice)
        if allow_zero and idx == 0:
            return 0
        if 1 <= idx <= len(items):
            return idx
        lo = 0 if allow_zero else 1
        hi = len(items)
        if allow_zero and not items:
            print("No files available — enter 0 to skip.")
        else:
            print(f"Please enter a number between {lo} and {hi}.")


def ask_rates_file(files: list[Path]) -> Path:
    print("\nRates files:")
    names = [p.name for p in files]
    for i, name in enumerate(names, start=1):
        print(f"  {i}. {name}")
    idx = ask_choice("\nSelect rates file number: ", names)
    return files[idx - 1]


def ask_multi_rates_files(files: list[Path]) -> list[Path]:
    """
    Ask which rates files to process (comma-separated numbers, or A for all).
    At least one file must be selected.
    """
    print("\nRates files:")
    for i, path in enumerate(files, start=1):
        print(f"  {i}. {path.name}")
    print("  A. All")

    while True:
        raw = input(
            "\nSelect file numbers to process (e.g. 1,3) or A for all: "
        ).strip()
        if not raw:
            print("Please enter a selection.")
            continue
        if raw.casefold() in {"a", "all"}:
            return list(files)

        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        if not parts or not all(p.isdigit() for p in parts):
            print("Please enter numbers like 1,2 or A for all.")
            continue
        idxs = [int(p) for p in parts]
        if any(i < 1 or i > len(files) for i in idxs):
            print(f"Please enter numbers between 1 and {len(files)}, or A.")
            continue
        # Preserve order, drop duplicates
        seen: set[int] = set()
        selected: list[Path] = []
        for i in idxs:
            if i not in seen:
                seen.add(i)
                selected.append(files[i - 1])
        if not selected:
            print("Select at least one file.")
            continue
        return selected


def list_previous_ra_files(folder: Path, label: str) -> list[Path]:
    """Return RA files in folder; empty list if folder missing or has no files."""
    if not folder.exists():
        print(f"Note: '{label}' folder not found ({folder}) — can skip.")
        return []
    files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and not p.name.startswith("~$")
        and p.suffix.lower() in {".xlsx", ".xls", ".xlsm"}
    )
    if not files:
        print(f"Note: no Excel files in '{label}' — can skip.")
    return files


def ask_previous_ra_file(files: list[Path], label: str) -> Path | None:
    """
    Ask which previous RA to use. Returns None if user skips
    (no sorting / no green change highlight for that sheet group).
    """
    print(f"\nFiles in '{label}' folder:")
    if not files:
        print("  (none)")
    else:
        for i, path in enumerate(files, start=1):
            print(f"  {i}. {path.name}")
    print("  0. Skip (no sort / no green highlight)")

    names = [p.name for p in files]
    idx = ask_choice(
        f"\nSelect previous RA for {label} (or 0 to skip): ",
        names,
        allow_zero=True,
    )
    if idx == 0:
        return None
    return files[idx - 1]


def list_fuel_files(fuel_dir: Path | None = None) -> list[Path]:
    """Excel/CSV files in input/Fuel (prefer names containing 'fuel')."""
    folder = fuel_dir or project_paths.FUEL_DIR
    if not folder.exists():
        raise FileNotFoundError(f"Fuel folder not found: {folder}")
    files = list_excel_files(folder)
    fuel_files = [p for p in files if "fuel" in p.name.lower()]
    if not fuel_files:
        fuel_files = files
    if not fuel_files:
        raise FileNotFoundError(
            f"No fuel file found in {folder} (filename should contain 'Fuel')."
        )
    return fuel_files


def ask_fuel_file(fuel_dir: Path | None = None) -> Path:
    """Always prompt which fuel workbook to use from input/Fuel."""
    fuel_files = list_fuel_files(fuel_dir)
    print(f"\nFuel folder: {fuel_dir or project_paths.FUEL_DIR}")
    print("Fuel files:")
    names = [p.name for p in fuel_files]
    for i, name in enumerate(names, start=1):
        print(f"  {i}. {name}")
    idx = ask_choice("\nSelect fuel file number: ", names)
    return fuel_files[idx - 1]


def find_fuel_file(fuel_dir: Path | None = None) -> Path:
    """Alias for ask_fuel_file (kept for older call sites)."""
    return ask_fuel_file(fuel_dir)


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)
