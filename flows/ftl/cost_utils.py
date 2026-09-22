"""Cost column key helpers and fuzzy cost-name matching."""

from __future__ import annotations

import re

from flows.ftl.schema import CURRENCY_COL, FLAT_COL


def currency_key(cost_name: str) -> str:
    return f"{cost_name}||{CURRENCY_COL}"


def flat_key(cost_name: str) -> str:
    return f"{cost_name}||{FLAT_COL}"


def cost_names_match(ours: str, ra_name: str) -> bool:
    """
    Match cost names across naming styles, e.g.:
      EFS  <->  Emergency Fuel Surcharge (EFS)
      Marpol  <->  Marpol fee
      ETS  <->  Emissions Trading System surcharge (ETS)
    """
    o = (ours or "").strip().casefold()
    r = (ra_name or "").strip().casefold()
    if not o or not r:
        return False
    if o == r:
        return True
    paren = re.search(r"\(([^)]+)\)\s*$", (ra_name or "").strip())
    if paren and paren.group(1).strip().casefold() == o:
        return True
    paren_o = re.search(r"\(([^)]+)\)\s*$", (ours or "").strip())
    if paren_o and paren_o.group(1).strip().casefold() == r:
        return True
    if len(o) >= 3 and o in r:
        return True
    if len(r) >= 3 and r in o:
        return True
    if "transport cost" in o and "transport cost" in r:
        return True
    return False
