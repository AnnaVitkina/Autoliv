"""LTL flow configuration."""

from __future__ import annotations

ALLOWED_CARRIERS: dict[int, str] = {
    907316: "Vectra International SRL",
    918914: "SOSTMEIER",
    919832: "EKOL LOJISTIK AS",
    926587: "CEVA Ground Logistics Espana SA",
    931285: "NTG Road AB",
    933354: "GERMANETTI S.R.L.",
    934383: "CEVA Logistics Ground & Rail France",
    966742: "DSV Bosnia",
    966743: "SCHENKER DOOEL",
    966831: "TRANSMEC RO SRL",
    973881: "DSV ROAD SPAIN S.A.U",
    976738: "Sara Transporte AG",
    983569: "Meyer & Meyer",
    984710: "Alpi Sweden AB",
}

HERO_CARRIERS: dict[int, str] = {
    914844: "Hero Group Sp Zoo",
    915317: "HERO Group GmbH",
    922130: "Hero Group kft",
    935567: "Hero Group Logistics Experts",
}

GERMANETTI_CARRIER_NO = 933354

FORWARDER_COMMON_RULES: list[tuple[str, int, str]] = [
    ("Alpi Sweden AB", 984710, "Alpi Sweden AB"),
    ("NTG Road AB", 931285, "NTG Road AB"),
    ("Transmec", 966831, "TRANSMEC RO SRL"),
    ("VECTRA INTERNATIONAL", 907316, "Vectra International SRL"),
    ("Sara Transporte", 976738, "Sara Transporte AG"),
    ("Sostmeier", 918914, "SOSTMEIER"),
    ("GERMANETTI", 933354, "GERMANETTI S.R.L."),
    ("DB Schenker", 966743, "SCHENKER DOOEL"),
    ("DSV Spain", 973881, "DSV ROAD SPAIN S.A.U"),
    ("Ekol", 919832, "EKOL LOJISTIK AS"),
    ("CEVA Logistics Ground & Rail France", 934383, "CEVA Logistics Ground & Rail France"),
    ("Meyer & Meyer Transport Logistics", 983569, "Meyer & Meyer"),
]

CURRENCY_REPLACEMENTS: dict[str, str] = {
    "LEI": "RON",
}

CURRENCY_COL = "Currency"
FLAT_COL = "Flat"  # unused for bracket costs; kept for consistency
RATE_BY_PALLET = "Rate by: Pallet/Load Pallet"

COST_LTL = "Transport cost"
COST_LTL_GERMANETTI = "Transport cost (GERMANETTI)"
COST_LDM = "Transport cost (LDM)"
COST_BOX_PREFIX = "Transport cost"  # + (QuantityUnit) e.g. Transport cost (box)
COST_GROUPED = "Grouped cost: Transport cost"

# When a lane has 2+ of these filled, move them under COST_GROUPED
GROUPABLE_COSTS: tuple[str, ...] = (
    COST_LTL,
    COST_LTL_GERMANETTI,
    COST_LDM,
)

RATE_BY_BOX = "Rate by: Per box"

# LTL unit_price_* column -> weight-bracket header
LTL_PRICE_BRACKETS: list[tuple[str, str]] = [
    ("unit_price_0_1", "<=1"),
    ("unit_price_2_4", "<=4"),
    ("unit_price_5_8", "<=8"),
    ("unit_price_9_12", "<=12"),
    ("unit_price_13_16", "<=16"),
    ("unit_price_17_20", "<=20"),
    ("unit_price_21_24", "<=24"),
    ("unit_price_25_28", "<=28"),
    ("unit_price_29_32", "<=32"),
    ("unit_price_32_36", "<=36"),
    ("unit_price_37_40", "<=40"),
    ("unit_price_41_44", "<=44"),
    ("unit_price_up_45", ">44"),
]

# LDM price columns -> LDM brackets (Price1..9 + Price10_13)
LDM_PRICE_BRACKETS: list[tuple[str, str]] = [
    ("Price1LDM", "<=1"),
    ("Price2LDM", "<=2"),
    ("Price3LDM", "<=3"),
    ("Price4LDM", "<=4"),
    ("Price5LDM", "<=5"),
    ("Price6LDM", "<=6"),
    ("Price7LDM", "<=7"),
    ("Price8LDM", "<=8"),
    ("Price9LDM", "<=9"),
    ("Price10_13LDM", "<=13"),
]

SHEET_MATRIX = "Matrix"
SHEET_HERO = "HERO Group"
SHEET_CONDITIONS = "Conditions"

ATTR_FORWARDER_REPLACED = "forwarder_replaced"
ATTR_DUPLICATE_LANE = "duplicate_lane"

# Internal names; Excel headers for *_2 columns drop the suffix
DETAIL_COLUMNS = [
    "lane #",
    "Lane ID",
    "Forwarder",
    "CarrierNo",
    "Paying_Plant",
    "CustomerNo",
    "Shippers_Loading",
    "OriginalSender",
    "Loading_Country",
    "Loading_Zip",
    "Origin City",
    "OriginNo",
    "Unloading_Place",
    "Unloading_Country",
    "Unloading_Zip",
    "Unloading_City",
    "DestinationNo",
    "Weight_pallet_kg",
    "Weight_pallet_kg_2",
    "Pallet_stackable",
    "Pallet_stackable_2",
    "Collection_day",
    "Collection_day_2",
    "Valid from",
    "Valid to",
]

DETAIL_HEADER_ALIASES = {
    "Weight_pallet_kg_2": "Weight_pallet_kg",
    "Pallet_stackable_2": "Pallet_stackable",
    "Collection_day_2": "Collection_day",
}

DEDUP_COLS = ["Forwarder", "Paying_Plant", "OriginNo", "DestinationNo"]

# Merge LTL + LDM rows that describe the same shipment
LANE_MERGE_COLS = ["Paying_Plant", "OriginNo", "DestinationNo", "CarrierNo"]
