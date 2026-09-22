"""FTL flow configuration — carriers, forwarder rules, surcharge keywords."""

from __future__ import annotations

ALLOWED_CARRIERS: dict[int, str] = {
    906973: "Alpi Eesti Ou",
    907316: "Vectra International SRL",
    908360: "Duvenbeck Logistik SRL",
    910483: "TRANSPORTES CAMPILLO S.A.",
    918914: "SOSTMEIER",
    919832: "EKOL LOJISTIK AS",
    922843: "Polonia Logistyka sp z o.o",
    926587: "CEVA Ground Logistics Espana SA",
    931285: "NTG Road AB",
    933354: "GERMANETTI S.R.L.",
    934383: "CEVA Logistics Ground & Rail France",
    963288: "Seifert Polska Spolka",
    966742: "DSV Bosnia",
    966743: "SCHENKER DOOEL",
    966831: "TRANSMEC RO SRL",
    976738: "Sara Transporte AG",
    983569: "Meyer & Meyer",
    984710: "Alpi Sweden AB",
    986347: "DSV Road Rouen",
}

HERO_CARRIERS: dict[int, str] = {
    914844: "Hero Group Sp Zoo",
    915317: "HERO Group GmbH",
    922130: "Hero Group kft",
    935567: "Hero Group Logistics Experts",
}

# Common Forwarder rating: (common Forwarder value, CarrierNo, carrier label in condition)
FORWARDER_COMMON_RULES: list[tuple[str, int, str]] = [
    ("DB Schenker", 966743, "SCHENKER DOOEL"),
    ("Duvenbeck Logistik", 908360, "Duvenbeck Logistik SRL"),
    ("CEVA Ground Logistics Espana", 926587, "CEVA Ground Logistics Espana SA"),
    ("Transmec", 966831, "TRANSMEC RO SRL"),
    ("VECTRA INTERNATIONAL", 907316, "Vectra International SRL"),
    ("Sara Transporte", 976738, "Sara Transporte AG"),
    ("GERMANETTI", 933354, "GERMANETTI S.R.L."),
    ("NTG Road AB", 931285, "NTG Road AB"),
    ("Sostmeier", 918914, "SOSTMEIER"),
    ("NTG POLAR", 931285, "NTG Road AB"),
    ("Alpi Sweden AB", 984710, "Alpi Sweden AB"),
    ("Ekol", 919832, "EKOL LOJISTIK AS"),
    ("CEVA Logistics Ground & Rail France", 934383, "CEVA Logistics Ground & Rail France"),
    ("Seifert Polska", 963288, "Seifert Polska Spolka"),
    ("Meyer & Meyer Transport Logistics", 983569, "Meyer & Meyer"),
    ("Polonia Logistyka", 922843, "Polonia Logistyka sp z o.o"),
    ("Transportes Campillo", 910483, "TRANSPORTES CAMPILLO S.A."),
    ("DSV Road Rouen", 986347, "DSV Road Rouen"),
]

TRANSPORT_COST_NAME = "Transport cost (Price_FTL)"
SURCHARGE_KEYWORDS = ("Marpol", "ETS", "BAF", "EFS")
SURCHARGE_SLOT_COUNT = 9

# Currency codes written to the matrix (rates may still say LEI)
CURRENCY_REPLACEMENTS: dict[str, str] = {
    "LEI": "RON",
}
