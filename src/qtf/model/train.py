"""Train the LightGBM+Alpha158 qlib workflow defined in configs/workflow_us5_lgb.yaml."""

from __future__ import annotations

from pathlib import Path

from qtf.config import settings
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


def train(workflow_yaml: Path | None = None, experiment_name: str = "us5_lgb") -> str:
    """Run the workflow via qlib's CLI entry. Returns the mlflow recorder_id."""
    from qlib.cli.run import workflow as qlib_workflow

    cfg_path = workflow_yaml or settings.workflow_yaml
    log_event(log, "train.start", experiment=experiment_name, config=str(cfg_path))
    qlib_workflow(str(cfg_path), experiment_name=experiment_name, uri_folder=str(settings.mlruns_dir))
    log_event(log, "train.done", experiment=experiment_name)
    return experiment_name
