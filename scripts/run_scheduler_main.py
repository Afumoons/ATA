#!/usr/bin/env python3
"""Launch autonomous_trading_ai.scheduler.main safely from any working directory.

Usage:
    python scripts/run_scheduler_main.py

    # Verify that the scheduler module can be imported without starting MT5/jobs:
    python scripts/run_scheduler_main.py --check

Double-click usage on Windows:
    Run run_ata_scheduler.cmd from the project root. The CMD launcher calls this
    script and keeps the console open if startup fails.

Notes:
    - Default mode executes `autonomous_trading_ai.scheduler.main` as `__main__`,
      so it follows the same behavior as:
          python -m autonomous_trading_ai.scheduler.main
    - The scheduler is long-running. Stop it with Ctrl+C in the console window.
    - This script adds the package parent directory to sys.path, so it works even
      when launched by double-click from Windows Explorer.
"""
from __future__ import annotations

import argparse
import importlib
import os
import runpy
import sys
from pathlib import Path

PACKAGE_NAME = "autonomous_trading_ai"
MODULE_NAME = f"{PACKAGE_NAME}.scheduler.main"


def configure_paths() -> Path:
    """Set cwd and sys.path so relative project files and package imports work."""
    project_root = Path(__file__).resolve().parents[1]
    package_parent = project_root.parent
    os.chdir(project_root)
    package_parent_str = str(package_parent)
    if package_parent_str not in sys.path:
        sys.path.insert(0, package_parent_str)
    return project_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run autonomous_trading_ai.scheduler.main")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Import scheduler.main and exit without starting the scheduler.",
    )
    args = parser.parse_args(argv)

    project_root = configure_paths()

    if args.check:
        module = importlib.import_module(MODULE_NAME)
        if not hasattr(module, "start_scheduler"):
            raise RuntimeError(f"{MODULE_NAME} imported, but start_scheduler() was not found")
        print(f"OK: imported {MODULE_NAME}")
        print(f"Project root: {project_root}")
        return 0

    print(f"Starting {MODULE_NAME} from {project_root}")
    print("Stop with Ctrl+C.")
    runpy.run_module(MODULE_NAME, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
