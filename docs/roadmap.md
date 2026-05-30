# 优化路线图 / TODO

记录可继续优化的方向。按「投入产出比」分三档。每条都附上**为什么**（当前现状/数据）和**怎么做**（涉及文件）。

> 现状基线（截至 2026-05-30）：50 只票池，LightGBM+Alpha158，Rank IC ≈ 0.013，
> agent 复核启用（OpenAI），回测年化 +46%（主要靠市场 beta，信号本身弱）。

---

## 高优先级（最该先做）

### 1. 提升模型信号质量（Rank IC 0.013 → 0.03+）

**为什么**：回测显示 Rank IC 只有 0.0128，低于 0.03 的"可用信号"门槛。当前 +46% 年化
主要来自市场上涨，不是模型预测力。这是整套系统最大的短板——执行/风控/报告都很扎实，
但**信号本身偏弱**。

**怎么做**（按尝试顺序）：
- 扩票池到 100-200 只（Alpha158 横截面因子在更大池子上才稳）→ 改 `configs/universe_us5.txt`
- 调 LightGBM 超参，每次改完跑 `python scripts/06_backtest.py` 看 Rank IC 变化 → `configs/workflow_us5_lgb.yaml`
- 试 label 改进：当前预测次日收益（噪音极大），可改 5 日/10 日前瞻收益降噪
- 试加自定义因子（动量、行业中性化）补充 Alpha158
- **判据**：盯 `reports/backtest_<date>.md` 的 Rank IC，不是收益曲线

**注意**：过拟合会让 IC 反而下降。每次调参必须回测验证，别盲调。

### 2. 滚动重训（避免模型过时）

**为什么**：现在模型是手动 `02_train.py` 一次性训练，时间一长就过时。生产系统应定期重训。

**怎么做**：
- 简单版：计划任务每周日加跑一次 `run_daily.bat --retrain`
- 进阶版：用 qlib 的 `RollingDataHandler` 做滚动窗口训练
- 涉及 `scripts/02_train.py`、`configs/workflow_us5_lgb.yaml` 的日期切分

### 3. 真盘前的滑点处理

**为什么**：实测 moomoo 模拟盘滑点 ~23bps（限价 311.91 成交在 312.62），是手续费(0.4bp)的
50 倍。回测假设无滑点，**真盘收益会明显低于回测**。切真盘前必须正视这点。

**怎么做**：
- 限价策略改保守：挂更靠近买卖中间价，或分批下单 → `src/qtf/execution/order_planner.py`
- 回测里把 `cost_per_turnover` 调到接近真实滑点（如 0.002）重新评估 → `scripts/06_backtest.py --cost 0.002`
- 考虑用 TWAP/VWAP 分批而非一次性市价

---

## 中优先级（锦上添花）

### 4. 降低 LLM 复核成本/耗时

**为什么**：技术指标修复后，agent 复核从 ~5 分钟涨到 ~18 分钟（5 票 × 完整 5 分析师 + 辩论）。
OpenAI 成本约 $0.2-0.5/天。

**怎么做**：
- 切 DeepSeek（性价比最高，~$0.01-0.05/天）→ `.env` 改 `TRADINGAGENTS_LLM_PROVIDER=deepseek`
- 降辩论轮数 `TRADINGAGENTS_MAX_DEBATE_ROUNDS=0`（省 2 次调用/票）
- 或减少候选数（top-3 而非 top-5）→ `src/qtf/orchestrator/daily_cycle.py` 的 `topk_equal_weight(k=...)`

### 5. Reddit 情绪源（可选）

**为什么**：当前情绪分析靠 StockTwits + 新闻，Reddit 因 403 跳过。Reddit 能补散户情绪
（尤其 wallstreetbets）。

**怎么做**：去 https://www.reddit.com/prefs/apps 注册 script app（注意先点页面顶部
"register to use the API" 完成 API 注册），把 id/secret 填进 `.env` 的
`REDDIT_CLIENT_ID/SECRET`。代码侧已支持 OAuth，填上自动启用。详见 [docs/llm-review.md](llm-review.md)。

### 6. 持仓再平衡频率

**为什么**：现在每天全量调仓，换手高（虽然手续费低但滑点累积）。

**怎么做**：
- 加"漂移阈值"：目标权重与当前偏离 < X% 时不调仓，减少无谓换手
- 或改成每周调仓而非每日 → `src/qtf/orchestrator/daily_cycle.py`

---

## 低优先级（工程完善）

### 7. CI / 测试自动化

- GitHub Actions 跑 `pytest`（当前 61 个测试），加 CI 徽章到 README
- 涉及新建 `.github/workflows/test.yml`

### 8. 报告增强

- README/docs 加实际报告截图
- 报告里加收益曲线图（matplotlib，已装）
- 把每日报告推送到飞书/微信/邮件

### 9. 监控告警

- `logs/qtf.jsonl` 是结构化 JSON，可接 Loki/ELK
- 对 `cycle.fatal` / `cycle.aborted` / 订单失败设告警

### 10. 多账户 / 多策略

- 当前单账户单策略。可扩展成多策略路由（不同票池/模型）
- 较大改动，需重构 orchestrator

---

## 不建议做（避免过度工程）

- 实时 tick 级交易（本系统是日频，不适合）
- 自建回测引擎（qlib + 我们的 `src/qtf/backtest/` 已够用）
- 期权/期货/加密（先把股票做扎实）
- Web UI / 仪表盘（命令行 + Markdown 报告已满足需求）

---

## 怎么用这份文档

每次想优化时：
1. 从高优先级挑一条
2. 改完**必跑回测** `python scripts/06_backtest.py` 看 Rank IC / 夏普有没有变好
3. 改 vendored 代码（qlib/TradingAgents）记得它们 gitignored，需更新 `scripts/patch_*.py`
4. 改完跑 `pytest` 确认没破坏现有功能
