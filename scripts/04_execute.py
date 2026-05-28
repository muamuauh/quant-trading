"""Plan orders from latest predictions, run risk gates, submit (or dry-run) to paper account."""

from __future__ import annotations

import argparse
import json

from qtf.orchestrator.daily_cycle import run_daily


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="Show planned orders without submitting")
    args = p.parse_args()
    result = run_daily(skip_ingest=True, retrain=False, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
