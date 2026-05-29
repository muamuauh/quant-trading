"""Render a Chinese Markdown backtest report from a BacktestResult."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from qtf.backtest.engine import BacktestResult
from qtf.backtest.metrics import BacktestMetrics
from qtf.config import settings
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


def _pct(x: float) -> str:
    sign = "+" if x > 0 else ("-" if x < 0 else "")
    return f"{sign}{abs(x) * 100:.2f}%"


def _metrics_table(strat: BacktestMetrics, bench: BacktestMetrics) -> str:
    rows = [
        ("交易日数", str(strat.n_days), str(bench.n_days)),
        ("累计收益", _pct(strat.total_return), _pct(bench.total_return)),
        ("年化收益", _pct(strat.annual_return), _pct(bench.annual_return)),
        ("年化波动", _pct(strat.annual_vol), _pct(bench.annual_vol)),
        ("夏普比率", f"{strat.sharpe:.2f}", f"{bench.sharpe:.2f}"),
        ("最大回撤", _pct(strat.max_drawdown), _pct(bench.max_drawdown)),
        ("Calmar", f"{strat.calmar:.2f}", f"{bench.calmar:.2f}"),
        ("胜率", f"{strat.win_rate * 100:.1f}%", f"{bench.win_rate * 100:.1f}%"),
        ("最佳单日", _pct(strat.best_day), _pct(bench.best_day)),
        ("最差单日", _pct(strat.worst_day), _pct(bench.worst_day)),
    ]
    lines = [
        "| 指标 | 策略 (top-K) | 基准 (等权持有全池) |",
        "|------|-------------|---------------------|",
    ]
    for name, s, b in rows:
        lines.append(f"| {name} | {s} | {b} |")
    return "\n".join(lines)


def render(result: BacktestResult, when: date | None = None) -> str:
    when = when or date.today()
    s = result.strategy
    verdict_excess = _pct(s.excess_annual_return)
    ic_quality = (
        "强" if abs(result.rank_ic) >= 0.05 else
        "中等" if abs(result.rank_ic) >= 0.03 else
        "弱"
    )

    md = "\n".join([
        f"# 策略回测报告 — {when.isoformat()}",
        "",
        f"_票池: 50 只美股 | top-K={result.k} 等权 | 换手成本={result.cost_per_turnover * 1e4:.0f}bp_",
        f"_回测区间: {result.daily_returns.index.min().date()} ~ {result.daily_returns.index.max().date()}_",
        "",
        "## 核心结论",
        "",
        f"- 策略年化收益 **{_pct(s.annual_return)}**，基准 {_pct(result.benchmark.annual_return)}，超额 **{verdict_excess}**",
        f"- 夏普比率 **{s.sharpe:.2f}**，最大回撤 **{_pct(s.max_drawdown)}**",
        f"- 预测能力 IC={result.ic:.4f}，Rank IC={result.rank_ic:.4f}（信号强度：**{ic_quality}**）",
        "",
        "## 收益与风险指标",
        "",
        _metrics_table(s, result.benchmark),
        "",
        "## 指标说明",
        "",
        "- **夏普比率**：单位波动的超额收益，>1 不错、>2 优秀（无风险利率按 0 计）",
        "- **最大回撤**：历史最惨的从高点跌幅，衡量最坏情况下的痛苦程度",
        "- **Calmar**：年化收益 / 最大回撤，越高说明赚钱效率相对回撤越好",
        "- **IC / Rank IC**：预测值与次日真实收益的横截面相关性。Rank IC ≥ 0.03 即有可用信号，"
        "≥ 0.05 为较强信号。这是判断模型选股能力的核心指标。",
        "",
        "## 重要 caveat",
        "",
        "- 本回测用**收盘价**理想化撮合，**无滑点 / 无部分成交 / 无冲击成本**，"
        "真实表现（含 moomoo 模拟盘）通常更差。",
        "- 测试区间较短，单一区间结果有偶然性；换不同时间段结论可能不同。",
        "- Alpha158 在 50 只票上信号偏弱（见 docs/strategy-and-model.md），"
        "本回测是相对评估工具，不是收益承诺。",
        "",
        "---",
        f"<sub>由 qtf.backtest 生成 | 调参后重跑可对比指标变化</sub>",
        "",
    ])
    return md


def generate(result: BacktestResult, when: date | None = None,
             write_to_disk: bool = True) -> tuple[Path | None, str]:
    when = when or date.today()
    md = render(result, when)
    path: Path | None = None
    if write_to_disk:
        settings.report_dir.mkdir(parents=True, exist_ok=True)
        path = settings.report_dir / f"backtest_{when.isoformat()}.md"
        path.write_text(md, encoding="utf-8")
        log_event(log, "backtest.report.written", path=str(path))
    return path, md
