"""Render a Chinese-language Markdown daily report from snapshot + metrics + cycle result."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from qtf.config import settings
from qtf.report.metrics import EquityMetrics, compute_metrics
from qtf.report.snapshot import Snapshot, append_history, capture, load_history
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


def _fmt_money(x: float, ccy: str = "USD") -> str:
    sign = "+" if x > 0 else ("-" if x < 0 else "")
    return f"{sign}${abs(x):,.2f}" if ccy == "USD" else f"{sign}{abs(x):,.2f} {ccy}"


def _fmt_pct(x: float) -> str:
    sign = "+" if x > 0 else ("-" if x < 0 else "")
    return f"{sign}{abs(x) * 100:.2f}%"


def _account_overview(snap: Snapshot, m: EquityMetrics) -> str:
    today_pct = (snap.today_pnl / snap.total_assets) if snap.total_assets else 0.0
    lines = [
        "## 账户概览",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 总资产 | ${snap.total_assets:,.2f} |",
        f"| 现金 | ${snap.cash:,.2f} |",
        f"| 持仓市值 | ${snap.market_val:,.2f} |",
        f"| 当日盈亏 | {_fmt_money(snap.today_pnl)} ({_fmt_pct(today_pct)}) |",
        f"| 累计盈亏（自首次运行 {m.inception_date or '今天'}） | {_fmt_money(m.inception_pnl_abs)} ({_fmt_pct(m.inception_pnl_pct)}) |",
        "",
    ]
    return "\n".join(lines)


def _positions_table(snap: Snapshot) -> str:
    if not snap.positions:
        return "## 当前持仓\n\n_无持仓_\n"
    lines = [
        "## 当前持仓",
        "",
        "| 代码 | 数量 | 均价 | 现价 | 市值 | 浮动盈亏 | 盈亏% |",
        "|------|------|------|------|------|----------|--------|",
    ]
    for p in snap.positions:
        code = p.get("code", "")
        qty = float(p.get("qty", 0))
        cost = float(p.get("average_cost", 0))
        last = float(p.get("nominal_price", 0))
        mv = float(p.get("market_val", 0))
        upl = float(p.get("unrealized_pl", 0))
        ratio = float(p.get("pl_ratio_avg_cost", 0))  # already in %
        lines.append(
            f"| {code} | {qty:.0f} | ${cost:,.2f} | ${last:,.2f} | "
            f"${mv:,.2f} | {_fmt_money(upl)} | {ratio:+.2f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def _risk_metrics_section(m: EquityMetrics) -> str:
    if m.days_recorded <= 1:
        return (
            "## 风险指标\n\n"
            f"_只有 {m.days_recorded} 天的快照数据，至少需要 2 天才能算出回撤/胜率。明天再来看。_\n"
        )
    lines = [
        "## 风险指标",
        "",
        f"- 历史最大回撤：**{_fmt_pct(m.max_drawdown_pct)}**（{m.max_drawdown_date}）",
        f"- 当前距最高点：{_fmt_pct(m.current_drawdown_pct)}（峰值 ${m.peak_equity:,.2f} @ {m.peak_date}）",
        f"- 已记录交易日数：{m.days_recorded}",
        f"- 正收益天数：{m.positive_days} | 负收益天数：{m.negative_days} | 胜率：{m.win_rate * 100:.1f}%",
        f"- 最佳单日：{_fmt_money(m.best_day_pnl)}（{m.best_day_date}）",
        f"- 最差单日：{_fmt_money(m.worst_day_pnl)}（{m.worst_day_date}）",
        "",
    ]
    return "\n".join(lines)


def _activity_section(cycle_result: dict[str, Any] | None) -> str:
    if not cycle_result:
        return "## 当日活动\n\n_未触发交易流水（本次只生成报告）。_\n"
    orders = cycle_result.get("orders", []) or []
    results = cycle_result.get("results", []) or []
    gates = cycle_result.get("gates", []) or []
    submitted = cycle_result.get("submitted", False)

    lines = ["## 当日活动", ""]
    if not orders:
        lines.append("- 无规划订单（信号或风控未通过）")
    else:
        lines.append(f"- 规划订单 **{len(orders)}** 笔：")
        for o in orders:
            side_zh = "买入" if o["side"] == "BUY" else "卖出"
            lines.append(f"  - {side_zh} {o['code']} × {o['quantity']} @ ${o['price']:.4f}")

    failed = [g for g in gates if not g.get("passed")]
    if failed:
        lines.append("")
        lines.append("- 风控**未通过**：")
        for g in failed:
            lines.append(f"  - ❌ {g['name']}: {g['reason']}")

    if results:
        lines.append("")
        lines.append("- 实际提交结果：")
        for r in results:
            status = r.get("status", "?")
            emoji = {"submitted": "✅", "dry_run": "🧪", "error": "❌"}.get(status, "❓")
            order_id = r.get("order_id", "-")
            lines.append(f"  - {emoji} {r.get('code')} {r.get('side')} × {r.get('quantity')} → {status} (order_id={order_id})")
    elif submitted is False and orders:
        lines.append("")
        lines.append("- 本次为 dry-run 或被风控拦截，未实际提交订单。")

    lines.append("")
    return "\n".join(lines)


def _agent_section(cycle_result: dict[str, Any] | None) -> str:
    if not cycle_result:
        return ""
    verdicts = cycle_result.get("agent_verdicts") or []
    if not verdicts:
        return ""
    lines = ["## 多 Agent 复核结果", ""]
    for v in verdicts:
        kept_emoji = "✅" if v.get("kept") else "❌"
        rationale = (v.get("rationale") or "").strip()
        if len(rationale) > 400:
            rationale = rationale[:400] + "…"
        lines.append(f"### {kept_emoji} {v['code']} — {v.get('rating', '?')}")
        if v.get("error"):
            lines.append(f"_错误：{v['error']}_")
        if rationale:
            lines.append("")
            lines.append("```")
            lines.append(rationale)
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def generate(
    cycle_result: dict[str, Any] | None = None,
    when: date | None = None,
    write_to_disk: bool = True,
) -> tuple[Path | None, str]:
    """Capture today's snapshot, refresh history, render markdown.

    Returns (report_path, markdown_string). `report_path` is None when
    `write_to_disk=False`.
    """
    when = when or date.today()
    snap = capture(when=when)
    append_history(snap)
    history = load_history()
    metrics = compute_metrics(history)

    md = "\n".join([
        f"# 每日交易报告 — {snap.date}",
        "",
        f"_账户：{settings.futu_acc_id}（{settings.futu_trd_env}） | "
        f"市场：{settings.futu_default_market} | 生成时间：{when.isoformat()}_",
        "",
        _account_overview(snap, metrics),
        _positions_table(snap),
        _risk_metrics_section(metrics),
        _activity_section(cycle_result),
        _agent_section(cycle_result),
        "---",
        "",
        f"<sub>由 qtf.report.daily_report 自动生成 | 历史快照：`{settings.equity_history_csv}`</sub>",
        "",
    ])

    path: Path | None = None
    if write_to_disk:
        settings.report_dir.mkdir(parents=True, exist_ok=True)
        path = settings.report_dir / f"{snap.date}.md"
        path.write_text(md, encoding="utf-8")
        log_event(log, "report.daily.written", path=str(path), date=snap.date)

    return path, md
