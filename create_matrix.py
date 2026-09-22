"""
Build rate-card matrix workbooks from Rates + Fuel.

Prefer the end-to-end entry point:

  python run_pipeline.py

This module remains as a thin alias for the same pipeline.
Works locally and in Colab (see run_pipeline.py docstring).

FTL logic lives under flows/ftl/.
"""

from __future__ import annotations

from run_pipeline import main


if __name__ == "__main__":
    raise SystemExit(main())
