"""Road ALPI flow entry."""

from __future__ import annotations

from pathlib import Path

from flows.alpi.pipeline import run_alpi

FLOW_ID = "alpi"
FLOW_LABEL = "Road ALPI"


def run() -> Path:
    return run_alpi()
