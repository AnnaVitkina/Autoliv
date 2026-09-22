"""FTL rates filtering, detail columns, and cost blocks."""

from __future__ import annotations

import pandas as pd

from flows.ftl.config import (
    CURRENCY_REPLACEMENTS,
    SURCHARGE_KEYWORDS,
    SURCHARGE_SLOT_COUNT,
    TRANSPORT_COST_NAME,
)
from flows.ftl.cost_utils import currency_key, flat_key
from flows.ftl.fuel import (
    attach_fuel_valid_from,
    format_date_ddmmyyyy,
    format_valid_from_with_flag,
)
from flows.ftl.schema import ATTR_VALID_FROM_RATES, DETAIL_COLUMNS
from flows.ftl.values import drop_fully_duplicate_rows, safe_amount, to_carrier_int


def match_surcharge_keyword(description) -> str | None:
    """Return Marpol/ETS/BAF/EFS when description contains that keyword."""
    if pd.isna(description):
        return None
    text = str(description).strip().upper()
    if not text:
        return None
    for keyword in SURCHARGE_KEYWORDS:
        if keyword.upper() in text:
            return keyword
    return None


def normalize_currency(value) -> str:
    """Normalize currency codes for the matrix (e.g. LEI -> RON)."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return CURRENCY_REPLACEMENTS.get(text.upper(), text)


def validate_rates_columns(rates: pd.DataFrame) -> None:
    required_rates = {
        "RateCode",
        "Forwarder",
        "CarrierNo",
        "Paying_Plant",
        "CustomerNo",
        "Shippers_Loading",
        "Loading_Country",
        "Loading_Zip",
        "Loading_City",
        "OriginNo",
        "Unloading_Place",
        "Unloading_Country",
        "Unloading_Zip",
        "Unloading_City",
        "DestinationNo",
        "Singletrip_Roundtrip",
        "Special",
        "Collection_day",
        "validTo",
        "Price_FTL",
        "Currency_FTL",
    }
    for slot in range(1, SURCHARGE_SLOT_COUNT + 1):
        required_rates.add(f"Surcharge{slot}")
        required_rates.add(f"SurchargeDescription{slot}")

    missing = required_rates - set(rates.columns)
    if missing:
        raise KeyError(f"Rates file missing columns: {sorted(missing)}")


def filter_rates(
    rates: pd.DataFrame,
    carrier_ids: set[int],
    by_creditor: dict[int, object],
    by_name: dict[str, object],
) -> pd.DataFrame:
    """Filter to allowed carriers + Paying_Plant contains _CH; attach fuel Valid from."""
    df = rates.copy()
    df["CarrierNo"] = df["CarrierNo"].map(to_carrier_int)
    df = df[df["CarrierNo"].isin(carrier_ids)]
    df = df[df["Paying_Plant"].astype(str).str.contains("_CH", na=False)]
    df = df.reset_index(drop=True)
    df = drop_fully_duplicate_rows(df, label="FTL source rows")
    return attach_fuel_valid_from(df, by_creditor, by_name)


def build_details(df: pd.DataFrame) -> pd.DataFrame:
    def clean(series: pd.Series):
        return series.where(series.notna(), "").astype(object)

    rates_valid = (
        df["validFrom"] if "validFrom" in df.columns else pd.Series([pd.NaT] * len(df))
    )
    valid_from_vals: list[str] = []
    valid_from_rates_flags: list[bool] = []
    for fuel_v, rates_v in zip(df["_fuel_valid_from"].values, rates_valid.values):
        text, later = format_valid_from_with_flag(fuel_v, rates_v)
        valid_from_vals.append(text)
        valid_from_rates_flags.append(later)

    details = pd.DataFrame(
        {
            "lane #": range(1, len(df) + 1),
            "RateCode": clean(df["RateCode"]),
            "Forwarder": clean(df["Forwarder"]),
            "CarrierNo": df["CarrierNo"].values,
            "Paying_Plant": clean(df["Paying_Plant"]),
            "Paying_Plant_2": "",
            "CustomerNo": clean(df["CustomerNo"]),
            "Shippers_Loading": clean(df["Shippers_Loading"]),
            "Loading_Country": clean(df["Loading_Country"]),
            "Loading_Zip": clean(df["Loading_Zip"]),
            "Loading_City": clean(df["Loading_City"]),
            "OriginNo": clean(df["OriginNo"]),
            "Unloading_Place": clean(df["Unloading_Place"]),
            "Unloading_Country": clean(df["Unloading_Country"]),
            "Unloading_Zip": clean(df["Unloading_Zip"]),
            "Unloading_City": clean(df["Unloading_City"]),
            "DestinationNo": clean(df["DestinationNo"]),
            "Singletrip_Roundtrip": clean(df["Singletrip_Roundtrip"]),
            "Service": "",
            "equip": clean(df["Special"]),
            "Equipment Type": "",
            "Collection day": clean(df["Collection_day"]),
            "Valid from": valid_from_vals,
            "Valid to": [format_date_ddmmyyyy(v) for v in df["validTo"].values],
        }
    )[DETAIL_COLUMNS]
    details.attrs[ATTR_VALID_FROM_RATES] = valid_from_rates_flags
    return details


def build_keyword_cost_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Transport + Marpol/ETS/BAF/EFS cost blocks."""
    n = len(df)
    currencies = [""] * n
    transport_amounts = [""] * n
    surcharge_amounts: dict[str, list] = {
        keyword: [""] * n for keyword in SURCHARGE_KEYWORDS
    }
    surcharge_currencies: dict[str, list] = {
        keyword: [""] * n for keyword in SURCHARGE_KEYWORDS
    }
    used_surcharges: set[str] = set()

    for row_idx, row in df.iterrows():
        currency = normalize_currency(row.get("Currency_FTL"))
        currencies[row_idx] = currency

        amount = safe_amount(row.get("Price_FTL"))
        if currency and amount is not None:
            transport_amounts[row_idx] = amount

        if not currency:
            continue

        keyword_totals: dict[str, float] = {}
        for slot in range(1, SURCHARGE_SLOT_COUNT + 1):
            keyword = match_surcharge_keyword(row.get(f"SurchargeDescription{slot}"))
            if not keyword:
                continue
            amount_f = safe_amount(row.get(f"Surcharge{slot}"))
            if amount_f is None:
                continue
            keyword_totals[keyword] = round(
                keyword_totals.get(keyword, 0.0) + amount_f, 2
            )

        for keyword, total in keyword_totals.items():
            used_surcharges.add(keyword)
            surcharge_amounts[keyword][row_idx] = total
            surcharge_currencies[keyword][row_idx] = currency

    cost_names = [TRANSPORT_COST_NAME] + [
        keyword for keyword in SURCHARGE_KEYWORDS if keyword in used_surcharges
    ]

    data: dict[str, list] = {
        currency_key(TRANSPORT_COST_NAME): [
            currencies[i] if transport_amounts[i] != "" else "" for i in range(n)
        ],
        flat_key(TRANSPORT_COST_NAME): transport_amounts,
    }
    for keyword in cost_names[1:]:
        data[currency_key(keyword)] = surcharge_currencies[keyword]
        data[flat_key(keyword)] = surcharge_amounts[keyword]

    return pd.DataFrame(data), cost_names


def build_other_surcharge_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Remaining surcharges (anything except Marpol/ETS/BAF/EFS).
    Cost name = SurchargeDescription text; same description summed per lane.
    """
    n = len(df)
    totals: dict[str, list] = {}
    currencies: dict[str, list] = {}
    display_names: dict[str, str] = {}

    for row_idx, row in df.iterrows():
        currency = normalize_currency(row.get("Currency_FTL"))
        if not currency:
            continue

        row_totals: dict[str, float] = {}
        for slot in range(1, SURCHARGE_SLOT_COUNT + 1):
            desc = row.get(f"SurchargeDescription{slot}")
            if pd.isna(desc):
                continue
            name = str(desc).strip()
            if not name or match_surcharge_keyword(name):
                continue
            amount_f = safe_amount(row.get(f"Surcharge{slot}"))
            if amount_f is None:
                continue
            key = name.casefold()
            if key not in display_names:
                display_names[key] = name
            row_totals[key] = round(row_totals.get(key, 0.0) + amount_f, 2)

        for key, total in row_totals.items():
            name = display_names[key]
            if name not in totals:
                totals[name] = [""] * n
                currencies[name] = [""] * n
            totals[name][row_idx] = total
            currencies[name][row_idx] = currency

    cost_names = sorted(totals.keys(), key=lambda s: s.casefold())
    data: dict[str, list] = {}
    for name in cost_names:
        data[currency_key(name)] = currencies[name]
        data[flat_key(name)] = totals[name]

    return pd.DataFrame(data), cost_names
