#!/usr/bin/env python3
"""Render ForecastMap with real Quickshell in a disposable offscreen window.

With --fixture, reuse a saved backend result and its local images without HTTP.
Without it, the project renderer uses explicitly synthetic layout fixtures.
"""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--legend", action="store_true", help="Also render the expanded official legend")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    command = [sys.executable, str(root / "qa/render_controls.py"), "--only", "ForecastMap", "--only", "ForecastMap-disabled"]
    if args.legend:
        command += ["--only", "ForecastMap-legend"]
    if args.fixture:
        command += ["--forecast-fixture", str(args.fixture.resolve())]
    raise SystemExit(subprocess.run(command, cwd=root).returncode)


if __name__ == "__main__":
    main()
