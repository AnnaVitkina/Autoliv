"""FTL flow entry."""

from __future__ import annotations

from pathlib import Path

from flows.ftl.pipeline import run_ftl

FLOW_ID = "ftl"
FLOW_LABEL = "FTL"


def run() -> Path:
    return run_ftl()
