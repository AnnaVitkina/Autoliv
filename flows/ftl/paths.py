"""
Project / data-folder paths for all flows.

Local (default):
  <repo>/input, <repo>/output

Colab:
  code  → /content/Autoliv
  data  → Google Drive shared folder (RMT_Autoliv)

Override anytime:
  AUTOLIV_DATA_DIR=/path/to/RMT_Autoliv
  AUTOLIV_CODE_DIR=/content/Autoliv   (sys.path / package root)
"""

from __future__ import annotations

import os
from pathlib import Path

# Google Drive shared folder used when running in Colab (unless AUTOLIV_DATA_DIR is set)
DEFAULT_COLAB_DATA_DIR = Path(
    "/content/drive/Shareddrives/FA Ops Europe: Rate Maintenance Team "
    "/Documents/AI Adoption RMT/RMT_Autoliv"
)
DEFAULT_COLAB_CODE_DIR = Path("/content/Autoliv")

FLOW_INPUT_DIRS: dict[str, str] = {
    "ftl": "FTL",
    "ltl": "LTL",
    "alpi": "Road ALPI",
}

# Module-level paths — always read via this module (paths.OUTPUT_DIR), not
# `from paths import OUTPUT_DIR`, so configure_paths() stays effective.
BASE_DIR: Path
CODE_DIR: Path
INPUT_DIR: Path
OUTPUT_DIR: Path
FUEL_DIR: Path
PREVIOUS_RATE_CARD_DIR: Path


def is_colab() -> bool:
    try:
        import google.colab  # noqa: F401

        return True
    except ImportError:
        return False


def resolve_code_dir(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("AUTOLIV_CODE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # Package lives two levels above flows/ftl/paths.py
    try:
        return Path(__file__).resolve().parents[2]
    except NameError:
        pass
    if DEFAULT_COLAB_CODE_DIR.is_dir():
        return DEFAULT_COLAB_CODE_DIR.resolve()
    return Path.cwd().resolve()


def resolve_base_dir(explicit: str | Path | None = None) -> Path:
    """Data root (input/ + output/). Local repo root, or Drive folder on Colab."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("AUTOLIV_DATA_DIR") or os.environ.get("AUTOLIV_BASE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    if is_colab():
        return DEFAULT_COLAB_DATA_DIR
    return resolve_code_dir()


def configure_paths(
    data_dir: str | Path | None = None,
    *,
    code_dir: str | Path | None = None,
) -> Path:
    """
    (Re)bind BASE_DIR / INPUT_DIR / OUTPUT_DIR / … for the process.
    Call before running a flow when overriding the default location.
    """
    global BASE_DIR, CODE_DIR, INPUT_DIR, OUTPUT_DIR, FUEL_DIR
    global PREVIOUS_RATE_CARD_DIR

    CODE_DIR = resolve_code_dir(code_dir)
    BASE_DIR = resolve_base_dir(data_dir)
    INPUT_DIR = BASE_DIR / "input"
    OUTPUT_DIR = BASE_DIR / "output"
    FUEL_DIR = INPUT_DIR / "Fuel"
    PREVIOUS_RATE_CARD_DIR = INPUT_DIR / "previous rate card"
    return BASE_DIR


def ensure_data_dirs() -> None:
    """Create the standard input/output folder tree under BASE_DIR."""
    if is_colab() and not BASE_DIR.exists():
        print(
            "WARNING: data folder not found on Drive:\n"
            f"  {BASE_DIR}\n"
            "Mount Google Drive first, e.g.:\n"
            "  from google.colab import drive\n"
            "  drive.mount('/content/drive')"
        )
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for folder in (
        FUEL_DIR,
        PREVIOUS_RATE_CARD_DIR,
        *(INPUT_DIR / name for name in FLOW_INPUT_DIRS.values()),
    ):
        folder.mkdir(parents=True, exist_ok=True)


def flow_rates_dir(flow_id: str) -> Path:
    folder = FLOW_INPUT_DIRS.get(flow_id, flow_id.upper())
    return INPUT_DIR / folder


def describe_runtime() -> str:
    mode = "colab" if is_colab() else "local"
    return f"mode={mode}; code={CODE_DIR}; data={BASE_DIR}"


# Defaults at import (local repo, or Colab Drive when google.colab is present)
configure_paths()
