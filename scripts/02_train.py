"""Train LightGBM+Alpha158 on the staged qlib data."""

from __future__ import annotations

from qtf.model.train import train


def main() -> None:
    rid = train()
    print(f"recorder_id = {rid}")


if __name__ == "__main__":
    main()
