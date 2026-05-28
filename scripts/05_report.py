"""Generate today's daily trading report (standalone — does NOT touch orders).

Captures the current portfolio snapshot, updates the equity-history CSV,
computes lifetime metrics, and writes reports/YYYY-MM-DD.md.

Re-running on the same day overwrites that day's snapshot and report.
"""

from __future__ import annotations

import argparse

from qtf.report.daily_report import generate


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-write", action="store_true", help="Print to stdout instead of writing reports/<date>.md")
    args = p.parse_args()

    path, md = generate(write_to_disk=not args.no_write)
    if path:
        print(f"Report written: {path}")
    print()
    print(md)


if __name__ == "__main__":
    main()
