"""Print the latest-date prediction snapshot."""

from __future__ import annotations

from qtf.strategy.predict import latest_date_scores, load_latest_predictions


def main() -> None:
    pred = load_latest_predictions()
    snap = latest_date_scores(pred)
    print(snap.to_string())


if __name__ == "__main__":
    main()
