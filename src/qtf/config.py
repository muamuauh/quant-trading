"""Type-safe access to env vars. The moomoo skill's common.py reads FUTU_* directly;
this module mirrors them so qtf code never has to read os.environ ad-hoc."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    futu_opend_host: str = "127.0.0.1"
    futu_opend_port: int = 11111
    futu_acc_id: int = 0
    futu_default_market: str = "US"
    futu_trd_env: str = "SIMULATE"
    i_confirm_real: int = 0
    moomoo_skill_dir: Path = Path(r"C:\Users\gjq00\.claude\skills\moomooapi")

    qlib_provider_uri: Path = PROJECT_ROOT / "data" / "qlib_bin" / "us_data"
    raw_csv_dir: Path = PROJECT_ROOT / "data" / "raw_csv"
    universe_file: Path = PROJECT_ROOT / "configs" / "universe_us5.txt"
    workflow_yaml: Path = PROJECT_ROOT / "configs" / "workflow_us5_lgb.yaml"
    risk_limits_yaml: Path = PROJECT_ROOT / "configs" / "risk_limits.yaml"
    mlruns_dir: Path = PROJECT_ROOT / "mlruns"
    log_dir: Path = PROJECT_ROOT / "logs"

    # --- TradingAgents LLM review layer ---
    qtf_agents_enabled: int = 0
    qtf_agents_min_rating: str = "Overweight"
    qtf_agents_fail_open: int = 1

    # --- Daily report ---
    report_dir: Path = PROJECT_ROOT / "reports"
    equity_history_csv: Path = PROJECT_ROOT / "data" / "snapshots" / "equity_history.csv"


settings = Settings()


def load_universe() -> list[str]:
    """Read configs/universe_us5.txt into ['US.AAPL', ...]."""
    return [
        line.strip()
        for line in settings.universe_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
