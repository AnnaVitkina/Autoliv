"""ALPI (Road ALPI) flow configuration."""

from __future__ import annotations

# CarrierNo values in scope for Road ALPI
ALLOWED_CARRIERS: dict[int, str] = {
    906973: "Alpi Eesti Ou",
}

CURRENCY_REPLACEMENTS: dict[str, str] = {
    "LEI": "RON",
}

# QuantityUnit labels (case-insensitive match against rates)
UNIT_PALLET_PLACE = "pallet place"
UNIT_PALLET = "pallet"
UNIT_TON = "ton"
UNIT_TRP = "trp"

COST_TON_LTL = "Transport cost (ton (LTL))"
COST_TRP = "Transport cost (trp)"
# Dedicated trp flats (display order: 23-24 then 22.6-24)
TRP_DEDICATED_RANGES: tuple[tuple[float, float], ...] = (
    (23.0, 24.0),
    (22.6, 24.0),
)

RATE_BY_LABEL = "Rate by: Per shipment"
CURRENCY_COL = "Currency"
FLAT_COL = "Flat"

SHEET_MATRIX = "Matrix"

ATTR_DUPLICATE_LANE = "duplicate_lane"
ATTR_DEST_COMBINED = "dest_combined"  # DestinationNo gathered from _00/_01/... variants (blue)

# Shipment identity used when collapsing quantity/price rows into one lane
LANE_GROUP_COLS = [
    "Paying_Plant",
    "OriginNo",
    "DestinationNo",
]

DETAIL_COLUMNS = [
    "lane #",
    "Forwarder",
    "CarrierNo",
    "Paying_Plant",
    "CustomerNo",
    "OriginalSender",
    "Shippers_Loading",
    "Loading_Zip",
    "Origin Postal Code",  # filled later from Loading_Zip for dedup
    "Loading_City",
    "OriginNo",
    "DestinationNo",
    "Unloading_Country",
    "Unloading_Zip",
    "Destination Postal Code",  # filled later from Unloading_Zip for dedup
    "Unloading_Place",
    "Unloading_City",
    "FinalDestination",
    "Valid from",
    "Valid to",
]

# Red duplicate key (postal helpers stay empty for now)
DEDUP_COLS = ["Paying_Plant", "OriginNo", "DestinationNo"]
