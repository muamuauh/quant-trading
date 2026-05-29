"""Pull universe daily K-lines → write per-symbol CSV → invoke qlib dump_bin → write instruments file."""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from qtf.config import PROJECT_ROOT, settings, load_universe
from qtf.data.moomoo_kline import fetch_daily_kline
from qtf.data.schema import symbol_from_code
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)
DUMP_BIN = PROJECT_ROOT / "qlib" / "scripts" / "dump_bin.py"


def _default_start(years: int) -> str:
    return (date.today() - timedelta(days=365 * years)).isoformat()


def _default_end() -> str:
    return date.today().isoformat()


def stage_csv(code: str, df: pd.DataFrame, csv_dir: Path) -> Path:
    """Write one ticker's DataFrame as <symbol>.csv (qlib dump_bin convention)."""
    csv_dir.mkdir(parents=True, exist_ok=True)
    path = csv_dir / f"{symbol_from_code(code)}.csv"
    df.to_csv(path, index=False)
    return path


def dump_qlib_bin(csv_dir: Path, qlib_dir: Path) -> None:
    """Shell out to qlib's dump_bin.py to convert staged CSVs into the .bin store."""
    dump_bin = DUMP_BIN
    if not dump_bin.exists():
        raise FileNotFoundError(f"qlib dump_bin.py not found at {dump_bin}")
    qlib_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(dump_bin),
        "dump_all",
        "--data_path", str(csv_dir),
        "--qlib_dir", str(qlib_dir),
        "--freq", "day",
        "--date_field_name", "date",
        "--symbol_field_name", "symbol",
        "--include_fields", "open,close,high,low,volume,factor",
    ]
    log_event(log, "dump_bin.start", cmd=" ".join(cmd))
    # errors="replace": dump_bin's progress lines are in the Windows console
    # codepage (GBK on zh-CN), not UTF-8. Without this, the subprocess reader
    # thread raises UnicodeDecodeError on process exit -- harmless to data but
    # leaves an alarming traceback in our stderr log.
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"dump_bin failed (exit {proc.returncode}): {proc.stderr or proc.stdout}")
    log_event(log, "dump_bin.done", stdout_tail=proc.stdout[-500:])


def write_instruments(universe: list[str], qlib_dir: Path, start: str, end: str) -> Path:
    """Create qlib's per-market instruments file (`<market>.txt`).

    qlib expects: <symbol>\t<start_date>\t<end_date> per line (tab-separated, no header).
    """
    instruments_dir = qlib_dir / "instruments"
    instruments_dir.mkdir(parents=True, exist_ok=True)
    path = instruments_dir / "us5.txt"
    lines = [f"{symbol_from_code(code)}\t{start}\t{end}" for code in universe]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ingest_all(years: int = 3) -> dict[str, int]:
    """End-to-end ingest. Returns {code: bar_count}."""
    universe = load_universe()
    start = _default_start(years)
    end = _default_end()

    csv_dir = settings.raw_csv_dir
    qlib_dir = settings.qlib_provider_uri

    max_workers = max(1, int(settings.ingest_max_workers))
    counts: dict[str, int] = {}
    failed: list[str] = []

    def _fetch_one(code: str) -> tuple[str, int | None]:
        """Fetch + stage one ticker. Returns (code, nrows) or (code, None) on failure."""
        try:
            df = fetch_daily_kline(code, start, end)
        except Exception as e:  # noqa: BLE001 — one bad ticker shouldn't kill the run
            log_event(log, "ingest.skip", code=code, error=str(e))
            return code, None
        path = stage_csv(code, df, csv_dir)
        log_event(log, "ingest.fetched", code=code, rows=len(df), csv=str(path))
        return code, len(df)

    if max_workers == 1:
        results = [_fetch_one(code) for code in universe]
    else:
        log_event(log, "ingest.parallel.start", workers=max_workers, n=len(universe))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_fetch_one, universe))

    for code, n in results:
        if n is None:
            failed.append(code)
        else:
            counts[code] = n

    if not counts:
        raise RuntimeError("ingest produced zero tickers — aborting (check OpenD).")

    # Only write instruments for tickers we actually have data for, so qlib
    # doesn't choke on a ticker with no .bin files.
    ingested = [c for c in universe if c not in failed]
    dump_qlib_bin(csv_dir, qlib_dir)
    write_instruments(ingested, qlib_dir, start, end)
    log_event(log, "ingest.done", counts=counts,
              n_ok=len(counts), n_failed=len(failed), failed=failed,
              qlib_dir=str(qlib_dir))
    return counts
