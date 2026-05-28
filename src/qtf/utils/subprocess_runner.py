"""Uniform wrapper around the moomoo skill's CLI scripts.

The skill ships ~100 standalone Python scripts under
    %MOOMOO_SKILL_DIR%\\scripts\\{quote,trade,subscribe}\\*.py

Each accepts --json and prints a single JSON object on stdout. This module:
- builds the command line (sys.executable + script path + args)
- forwards FUTU_* env vars (the skill's common.py reads them)
- parses the JSON, raising MoomooSkillError on non-zero exit or {"error": ...}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from qtf.config import settings


class MoomooSkillError(RuntimeError):
    def __init__(self, script: str, returncode: int, stderr: str, payload: Any = None) -> None:
        super().__init__(f"{script} failed (exit {returncode}): {stderr.strip() or payload}")
        self.script = script
        self.returncode = returncode
        self.stderr = stderr
        self.payload = payload


def _skill_env() -> dict[str, str]:
    """Subset of env vars the skill's common.py reads, plus the parent env."""
    env = os.environ.copy()
    env["FUTU_OPEND_HOST"] = settings.futu_opend_host
    env["FUTU_OPEND_PORT"] = str(settings.futu_opend_port)
    env["FUTU_TRD_ENV"] = settings.futu_trd_env
    env["FUTU_DEFAULT_MARKET"] = settings.futu_default_market
    if settings.futu_acc_id:
        env["FUTU_ACC_ID"] = str(settings.futu_acc_id)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_skill(category: str, name: str, *args: str, timeout: int = 60) -> dict[str, Any]:
    """Invoke `<skill_dir>/scripts/<category>/<name>.py --json <args...>` and return parsed JSON.

    Example:
        run_skill("quote", "get_kline", "US.AAPL", "--ktype", "1d",
                  "--start", "2025-01-01", "--end", "2025-01-31")
    """
    script: Path = settings.moomoo_skill_dir / "scripts" / category / f"{name}.py"
    if not script.exists():
        raise FileNotFoundError(f"Skill script not found: {script}")

    cmd = [sys.executable, str(script), *args, "--json"]
    proc = subprocess.run(
        cmd,
        env=_skill_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        # moomoo SDK / OpenD warnings can come through in the Windows console
        # codepage (GBK), not UTF-8. errors="replace" stops the reader thread
        # from raising UnicodeDecodeError on process exit.
        errors="replace",
        timeout=timeout,
        check=False,
    )

    payload: Any = None
    if proc.stdout.strip():
        # Some skill scripts print warnings before the JSON; take the last non-empty line.
        for line in reversed(proc.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

    if proc.returncode != 0 or (isinstance(payload, dict) and "error" in payload):
        raise MoomooSkillError(f"{category}/{name}", proc.returncode, proc.stderr, payload)

    if payload is None:
        raise MoomooSkillError(
            f"{category}/{name}", proc.returncode, proc.stderr or "no JSON in stdout", proc.stdout
        )
    return payload
