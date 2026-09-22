"""LTL flow entry."""

from __future__ import annotations

from pathlib import Path

from flows.ltl.pipeline import run_ltl

FLOW_ID = "ltl"
FLOW_LABEL = "LTL"


def run() -> Path:
    return run_ltl()
