"""Load the latest trained model's predictions from mlflow."""

from __future__ import annotations

import pandas as pd


def load_latest_predictions(experiment_name: str = "us5_lgb") -> pd.Series:
    """Return the most recent trained run's prediction series (MultiIndex: datetime, instrument)."""
    import qlib
    from qlib.workflow import R

    import yaml
    from qtf.config import settings

    cfg = yaml.safe_load(settings.workflow_yaml.read_text(encoding="utf-8"))
    qlib.init(**cfg["qlib_init"])

    exp = R.get_exp(experiment_name=experiment_name, create=False)
    recorders = exp.list_recorders()
    if not recorders:
        raise RuntimeError(f"No recorders under experiment '{experiment_name}'. Train first.")
    # latest by end_time
    latest_id = sorted(
        recorders.keys(),
        key=lambda rid: getattr(recorders[rid], "end_time", "") or "",
        reverse=True,
    )[0]
    rec = exp.get_recorder(recorder_id=latest_id)
    pred = rec.load_object("pred.pkl")  # type: ignore[no-untyped-call]
    if isinstance(pred, pd.DataFrame):
        pred = pred.iloc[:, 0]
    return pred


def latest_date_scores(pred: pd.Series) -> pd.Series:
    """Slice the prediction series down to the most recent date. Index: instrument symbol."""
    latest_dt = pred.index.get_level_values("datetime").max()
    snap = pred.xs(latest_dt, level="datetime")
    return snap.sort_values(ascending=False)
