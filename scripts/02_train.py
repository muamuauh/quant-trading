"""Train LightGBM+Alpha158 on the staged qlib data."""

from __future__ import annotations

import os
import sys

from qtf.model.train import train


def main() -> None:
    rid = train()
    print(f"recorder_id = {rid}")
    # Flush then hard-exit. qlib's LightGBM path uses joblib/loky, whose
    # resource_tracker raises FileNotFoundError warnings while cleaning up
    # temp memmap folders at interpreter shutdown on Windows -- harmless to the
    # saved model (pred.pkl is already written) but it can leave the process
    # with a non-zero exit code. os._exit(0) skips that teardown so callers
    # (run_daily.bat) see a clean success.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
