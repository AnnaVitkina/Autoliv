"""Shared matrix schema, sheet names, and per-row attrs."""

from __future__ import annotations

DETAIL_COLUMNS = [
    "lane #",
    "RateCode",
    "Forwarder",
    "CarrierNo",
    "Paying_Plant",
    "Paying_Plant_2",  # left empty for now (written as "Paying_Plant" in Excel)
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
    "Service",
    "equip",
    "Equipment Type",
    "Collection day",
    "Valid from",
    "Valid to",
]

RATE_BY_LABEL = "Rate by: Per shipment"
CURRENCY_COL = "Currency"
FLAT_COL = "Flat"

SHEET_MATRIX = "Matrix"
SHEET_OTHER = "Other surcharges"
SHEET_HERO = "HERO Group"
SHEET_CONDITIONS = "Conditions"

RATE_CARD_SHEET = "Rate card"

ATTR_FORWARDER_REPLACED = "forwarder_replaced"
ATTR_FORWARDER_REPLACEMENTS = "forwarder_replacements"
ATTR_ORIGIN_COMBINED = "origin_combined"
ATTR_DEST_COMBINED = "dest_combined"
ATTR_COLLECTION_COMBINED = "collection_combined"
ATTR_PAYING_PLANT_COMBINED = "paying_plant_combined"
ATTR_COMPANY_CODE_CONDITIONS = "company_code_conditions"
ATTR_CHANGED_CELLS = "changed_cells"
ATTR_NEW_LANE = "new_lane"
ATTR_REMOVED_LANE = "removed_lane"
ATTR_DUPLICATE_LANE = "duplicate_lane"
ATTR_RA_MATCH = "ra_match"
# Valid from taken from rates file because it is after the fuel date (purple)
ATTR_VALID_FROM_RATES = "valid_from_from_rates"

PER_ROW_ATTRS = (
    ATTR_FORWARDER_REPLACED,
    ATTR_ORIGIN_COMBINED,
    ATTR_DEST_COMBINED,
    ATTR_COLLECTION_COMBINED,
    ATTR_PAYING_PLANT_COMBINED,
    ATTR_CHANGED_CELLS,
    ATTR_NEW_LANE,
    ATTR_REMOVED_LANE,
    ATTR_DUPLICATE_LANE,
    ATTR_VALID_FROM_RATES,
)

# Map RA Rate card detail headers -> DETAIL_COLUMNS names
RA_DETAIL_HEADER_MAP = {
    "Lane #": "lane #",
    "RateCode": "RateCode",
    "Forwarder": "Forwarder",
    "CarrierNo": "CarrierNo",
    "Paying plant": "Paying_Plant",
    "Paying Plant": "Paying_Plant_2",
    "Customer No": "CustomerNo",
    "Shippers_Loading": "Shippers_Loading",
    "Loading_Country": "Loading_Country",
    "Loading_Zip": "Loading_Zip",
    "Loading_City": "Loading_City",
    "Origin No": "OriginNo",
    "Unloading Place": "Unloading_Place",
    "Unloading_Country": "Unloading_Country",
    "Unloading_Zip": "Unloading_Zip",
    "Unloading_City": "Unloading_City",
    "Destination No": "DestinationNo",
    "Singletrip_Roundtrip": "Singletrip_Roundtrip",
    "Service": "Service",
    "equip": "equip",
    "Equipment Type": "Equipment Type",
    "Collection day": "Collection day",
    "Valid from": "Valid from",
    "Valid to": "Valid to",
}

# When the same RateCode appears multiple times, disambiguate by these fields
LANE_MATCH_COLS = [
    "Forwarder",
    "CarrierNo",
    "Paying_Plant",
    "Paying_Plant_2",
    "CustomerNo",
    "OriginNo",
    "DestinationNo",
    "Singletrip_Roundtrip",
    "Service",
    "equip",
    "Equipment Type",
    "Collection day",
]

DEDUP_CORE_COLS = ["Forwarder", "OriginNo", "DestinationNo"]
DEDUP_AFTER_PLANT_COLS = DEDUP_CORE_COLS + ["Paying_Plant_2"]
DEDUP_AFTER_SERVICE_COLS = DEDUP_AFTER_PLANT_COLS + ["Service", "Equipment Type"]
DEDUP_FULL_COLS = DEDUP_AFTER_SERVICE_COLS + ["Collection day"]
