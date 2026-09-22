"""
Shared fuel helpers — Valid from resolution used by FTL / LTL / ALPI.

Fuel files live in input/Fuel. Status=Accepted rows supply validFrom,
matched by creditor number or CarrierReferenceName ↔ Forwarder.

Matrix Valid from = fuel date, unless the rates-file validFrom is later
(then rates date is used and the cell is highlighted purple).
"""

from __future__ import annotations

import pandas as pd

from flows.ftl.values import norm_key, to_carrier_int


def format_date_ddmmyyyy(value) -> str:
    """Format date as dd.mm.yyyy; leave empty when missing/invalid."""
    if pd.isna(value) or value == "" or value is None:
        return ""
    ts = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(ts):
        return ""
    return ts.strftime("%d.%m.%Y")


def pick_later_valid_from(fuel_valid, rates_valid) -> tuple[object, bool]:
    """
    Choose Valid from for the matrix.

    Prefer the fuel Accepted validFrom. When the rates-file validFrom is
    strictly later, use that rates date instead and flag True (purple).
    """
    fuel_ts = pd.to_datetime(fuel_valid, errors="coerce")
    rates_ts = pd.to_datetime(rates_valid, errors="coerce")
    if pd.isna(fuel_ts) and pd.isna(rates_ts):
        return pd.NaT, False
    if pd.isna(fuel_ts):
        return rates_ts, False
    if pd.isna(rates_ts):
        return fuel_ts, False
    if rates_ts > fuel_ts:
        return rates_ts, True
    return fuel_ts, False


def format_valid_from_with_flag(fuel_valid, rates_valid) -> tuple[str, bool]:
    """Return (dd.mm.yyyy Valid from, rates-later purple flag)."""
    chosen, later = pick_later_valid_from(fuel_valid, rates_valid)
    return format_date_ddmmyyyy(chosen), later


def build_fuel_lookup(fuel: pd.DataFrame) -> tuple[dict[int, object], dict[str, object]]:
    """
    Build validFrom lookups from Accepted fuel rows.

    Primary key: Carrier - Creditor number
    Fallback key: CarrierReferenceName (matches rates Forwarder when creditor IDs differ)
    When multiple Accepted rows exist, use the latest validFrom.
    """
    required = {"Status", "validFrom"}
    missing = required - set(fuel.columns)
    if missing:
        raise KeyError(f"Fuel file missing columns: {sorted(missing)}")

    accepted = fuel[fuel["Status"].astype(str).str.strip().str.upper() == "ACCEPTED"].copy()
    accepted["validFrom"] = pd.to_datetime(accepted["validFrom"], errors="coerce")

    by_creditor: dict[int, object] = {}
    by_name: dict[str, object] = {}

    if "Carrier - Creditor number" in accepted.columns:
        tmp = accepted.dropna(subset=["Carrier - Creditor number"]).copy()
        tmp["_creditor"] = tmp["Carrier - Creditor number"].map(to_carrier_int)
        tmp = tmp.dropna(subset=["_creditor"])
        for creditor, group in tmp.groupby("_creditor"):
            latest = group["validFrom"].max()
            by_creditor[int(creditor)] = latest

    if "CarrierReferenceName" in accepted.columns:
        tmp = accepted.copy()
        tmp["_name"] = tmp["CarrierReferenceName"].map(norm_key)
        tmp = tmp[tmp["_name"] != ""]
        for name, group in tmp.groupby("_name"):
            latest = group["validFrom"].max()
            by_name[name] = latest

    return by_creditor, by_name


def resolve_fuel_valid_from(
    carrier_no,
    forwarder,
    by_creditor: dict[int, object],
    by_name: dict[str, object],
):
    carrier_int = to_carrier_int(carrier_no)
    if carrier_int is not pd.NA and int(carrier_int) in by_creditor:
        return by_creditor[int(carrier_int)]

    name_key = norm_key(forwarder)
    if name_key in by_name:
        return by_name[name_key]

    return pd.NaT


def attach_fuel_valid_from(
    df: pd.DataFrame,
    by_creditor: dict[int, object],
    by_name: dict[str, object],
    carrier_col: str = "CarrierNo",
    forwarder_col: str = "Forwarder",
    out_col: str = "_fuel_valid_from",
) -> pd.DataFrame:
    """Add fuel Valid-from column onto a rates dataframe (shared by all flows)."""
    out = df.copy()
    out[out_col] = [
        resolve_fuel_valid_from(
            getattr(row, carrier_col),
            getattr(row, forwarder_col),
            by_creditor,
            by_name,
        )
        for row in out.itertuples(index=False)
    ]
    return out
