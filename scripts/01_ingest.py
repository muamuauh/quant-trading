"""Pull historical daily K-line for the universe, dump to qlib bin."""

from __future__ import annotations

import argparse

from qtf.data.ingest import ingest_all


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=3, help="History window in years (default: 3)")
    args = p.parse_args()
    counts = ingest_all(years=args.years)
    for code, n in counts.items():
        print(f"  {code:<12} {n:>5} bars")


if __name__ == "__main__":
    main()
