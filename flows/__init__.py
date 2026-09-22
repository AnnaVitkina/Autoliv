"""Flow registry — user picks FTL / LTL / Road ALPI."""

from __future__ import annotations

from types import ModuleType

from flows import alpi, ftl, ltl
from flows.ftl.io import ask_choice

FLOWS: list[ModuleType] = [ftl, ltl, alpi]


def ask_flow() -> ModuleType:
    print("\nSelect flow:")
    labels = [m.FLOW_LABEL for m in FLOWS]
    for i, label in enumerate(labels, start=1):
        print(f"  {i}. {label}")
    idx = ask_choice("\nSelect flow number: ", labels)
    return FLOWS[idx - 1]
