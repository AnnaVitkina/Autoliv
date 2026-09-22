"""
End-to-end pipeline entry point.

Steps:
  1) Choose flow (FTL / LTL / Road ALPI)
  2) Flow prompts for rates (+ previous original rates for compare)
  3) Fuel Valid-from is applied from input/Fuel
  4) Flow builds matrix workbook(s) into output/

Local:
  python run_pipeline.py
  (data = this project folder: ./input, ./output)

Google Colab (code under /content/Autoliv, data on Drive):
  from google.colab import drive
  drive.mount('/content/drive')
  import os
  exec(open('/content/Autoliv/run_pipeline.py').read())

Optional overrides:
  AUTOLIV_DATA_DIR  — input/output root (default: local repo or Colab Drive folder)
  AUTOLIV_CODE_DIR  — package root on sys.path (default: /content/Autoliv or this repo)
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


DEFAULT_COLAB_CODE_DIR = Path("/content/Autoliv")
DEFAULT_COLAB_DATA_DIR = Path(
    "/content/drive/Shareddrives/FA Ops Europe: Rate Maintenance Team "
    "/Documents/AI Adoption RMT/RMT_Autoliv"
)


def _resolve_code_root() -> Path:
    env = os.environ.get("AUTOLIV_CODE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # Normal `python run_pipeline.py` / import
    if "__file__" in globals():
        return Path(__file__).resolve().parent
    # `exec(open(...).read())` in Colab — __file__ is unset
    if DEFAULT_COLAB_CODE_DIR.is_dir():
        return DEFAULT_COLAB_CODE_DIR.resolve()
    return Path.cwd().resolve()


def bootstrap(data_dir: str | Path | None = None) -> Path:
    """
    Put the package on sys.path and bind input/output paths.
    Safe to call multiple times.
    """
    code_root = _resolve_code_root()
    code_str = str(code_root)
    if code_str not in sys.path:
        sys.path.insert(0, code_str)

    from flows.ftl import paths as project_paths

    project_paths.configure_paths(data_dir, code_dir=code_root)
    project_paths.ensure_data_dirs()
    return project_paths.BASE_DIR


def _print_banner() -> None:
    from flows.ftl import paths as project_paths

    print("=" * 60)
    print(" Autoliv rate-card matrix pipeline")
    print("=" * 60)
    print(f" Runtime : {project_paths.describe_runtime()}")
    print(f" Code    : {project_paths.CODE_DIR}")
    print(f" Data    : {project_paths.BASE_DIR}")
    print(f" Input   : {project_paths.INPUT_DIR}")
    print(f" Fuel    : {project_paths.FUEL_DIR}")
    print(f" Output  : {project_paths.OUTPUT_DIR}")


def run_pipeline(data_dir: str | Path | None = None) -> Path | None:
    """
    Run the full interactive pipeline for the selected flow.
    Returns the output workbook path when the flow produces one.

    data_dir: optional override for the Drive / local data root
              (same as AUTOLIV_DATA_DIR).
    """
    bootstrap(data_dir)

    from flows import ask_flow

    _print_banner()

    print("\n[1/3] Select flow")
    flow = ask_flow()
    print(f"      → {flow.FLOW_LABEL}")

    print(f"\n[2/3] Run {flow.FLOW_LABEL} pipeline")
    print("      (rates / fuel / previous rate-card prompts follow)")
    result = flow.run()

    print("\n[3/3] Done")
    out_path: Path | None = result if isinstance(result, Path) else None
    if out_path is not None:
        print(f"      Output: {out_path}")
    return out_path


def main(data_dir: str | Path | None = None) -> int:
    try:
        run_pipeline(data_dir)
        return 0
    except NotImplementedError as exc:
        print(f"\nFlow not ready: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _in_notebook_or_exec() -> bool:
    """True in Colab / IPython / exec(open(...).read()) — avoid SystemExit there."""
    if "__file__" not in globals():
        return True
    try:
        get_ipython()  # type: ignore[name-defined]
        return True
    except NameError:
        return False


if __name__ == "__main__":
    _rc = main()
    # SystemExit in Colab/IPython triggers: "To exit: use 'exit', 'quit', or Ctrl-D."
    if not _in_notebook_or_exec():
        raise SystemExit(_rc)
