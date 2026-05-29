"""Train LightGBM+Alpha158 and persist daily predictions.

We deliberately do NOT run qlib's full `workflow()` (SignalRecord +
SigAnaRecord + PortAnaRecord). qtf has its own execution / risk / moomoo
layers, so qlib's built-in backtest (PortAnaRecord) is dead weight -- and on
Windows the LightGBM + joblib/loky teardown after those extra records can hard-
kill the process with a non-zero exit code even though the model trained fine.

So we run only what we need: fit the model, save it, and generate the
SignalRecord (which writes pred.pkl that strategy/predict.py reads).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from qtf.config import settings
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


def train(workflow_yaml: Path | None = None, experiment_name: str = "us5_lgb") -> str:
    """Fit model + save pred.pkl. Returns the mlflow recorder_id."""
    import qlib
    from qlib.utils import init_instance_by_config
    from qlib.workflow import R
    from qlib.workflow.record_temp import SignalRecord

    cfg_path = workflow_yaml or settings.workflow_yaml
    with cfg_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    log_event(log, "train.start", experiment=experiment_name, config=str(cfg_path))

    qlib.init(**cfg["qlib_init"], exp_manager={
        "class": "MLflowExpManager",
        "module_path": "qlib.workflow.expm",
        "kwargs": {
            "uri": "file:" + str(settings.mlruns_dir.resolve()),
            "default_exp_name": experiment_name,
        },
    })

    task = cfg["task"]
    model = init_instance_by_config(task["model"])
    dataset = init_instance_by_config(task["dataset"])

    recorder_id: str
    with R.start(experiment_name=experiment_name):
        model.fit(dataset)
        R.save_objects(**{"params.pkl": model})
        rec = R.get_recorder()
        recorder_id = rec.id
        # SignalRecord writes pred.pkl (the only artifact strategy/predict.py needs).
        SignalRecord(model=model, dataset=dataset, recorder=rec).generate()

    log_event(log, "train.done", experiment=experiment_name, recorder_id=recorder_id)
    return recorder_id
