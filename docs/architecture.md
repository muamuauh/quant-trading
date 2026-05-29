# 系统架构

## 总览

```mermaid
flowchart TD
    subgraph EXT[外部依赖]
        A[moomoo OpenD<br/>localhost:11111]
        B[OpenAI / DeepSeek / Anthropic<br/>LLM API]
    end

    subgraph PIPE[每日 pipeline]
        I[01 ingest<br/>拉日K + qlib bin] --> M[02 train<br/>LightGBM + Alpha158]
        M --> P[03 predict<br/>最新一根 K 打分]
        P --> S[topk_equal_weight<br/>选 top-5 等权]
        S --> AG{QTF_AGENTS<br/>_ENABLED?}
        AG -->|yes| LR[agents.review<br/>per-ticker LLM 复核]
        AG -->|no| RG
        LR --> RG[5 道风控闸<br/>env / hours / pos / cash / loss]
        RG -->|all pass| EX[MoomooExecutor<br/>限价单提交]
        EX --> WAIT[等待 positions<br/>列表 propagate]
        WAIT --> RP[generate_report<br/>Markdown]
    end

    A -.subprocess.- I
    A -.subprocess.- EX
    A -.subprocess.- WAIT
    B -.LangGraph.- LR

    subgraph OUT[产物]
        D1[data/raw_csv/]
        D2[data/qlib_bin/]
        D3[mlruns/]
        D4[data/snapshots/equity_history.csv]
        D5[reports/YYYY-MM-DD.md]
        D6[logs/qtf.jsonl]
    end

    I --> D1 --> D2
    M --> D3
    RP --> D4
    RP --> D5
    PIPE -.结构化日志.- D6
```

## 6 层模块

```
src/qtf/
├── utils/         共享 utility（subprocess 包装、JSON 日志）
├── data/          数据层
├── model/         模型训练
├── strategy/      选股 + 权重
├── agents/        TradingAgents LLM 复核（可选）
├── execution/     订单规划 + moomoo executor
├── risk/          5 道风控闸
├── backtest/      历史回测引擎 + 指标（夏普/回撤/IC）
├── report/        快照 + 指标 + Markdown 渲染
└── orchestrator/  daily_cycle 串联所有层
```

> 注：`backtest/` 是**离线评估工具**，不在每日 pipeline 里（每日跑的是实盘流程）。
> 它独立运行 `scripts/06_backtest.py`，用历史预测评估策略选股质量，
> 替代了 qlib 自带的 PortAnaRecord（后者在美股配置下不可用且会触发 joblib teardown 崩溃）。

每层职责严格隔离，便于单测和替换：

| 层 | 关键文件 | 输入 | 输出 |
|----|---------|------|------|
| data | `moomoo_kline.py` / `ingest.py` | 票池、日期范围 | `data/qlib_bin/` |
| model | `train.py` | qlib YAML | mlflow run + `pred.pkl` |
| strategy | `predict.py` / `topk_weights.py` | mlflow predictions | `{code: weight}` dict |
| agents | `review.py` | top-K weights + date | filtered weights + verdicts |
| execution | `order_planner.py` / `moomoo_executor.py` | weights + current portfolio | Order list / submit results |
| risk | `gates.py` / `market_hours.py` | orders + portfolio | (passed, [GateResult]) |
| report | `snapshot.py` / `metrics.py` / `daily_report.py` | cycle_result + history | `reports/YYYY-MM-DD.md` |

## 数据流

### 拉数据 → qlib bin

```mermaid
sequenceDiagram
    autonumber
    participant ING as 01_ingest.py
    participant SK as moomoo skill<br/>get_kline.py
    participant OD as OpenD
    participant CSV as data/raw_csv/
    participant DB as qlib dump_bin.py
    participant BIN as data/qlib_bin/

    loop 50 tickers
        ING->>SK: subprocess (US.AAPL, 5y, 1d)
        SK->>OD: WebSocket query_history_kline
        OD-->>SK: JSON K-line array
        SK-->>ING: stdout: {data: [...]}
        ING->>CSV: write aapl.csv
    end
    ING->>DB: subprocess dump_all
    DB->>BIN: 6 个 .bin 文件 per ticker
    ING->>BIN: write instruments/us5.txt
```

### 模型 → 选股 → 执行

```mermaid
sequenceDiagram
    autonumber
    participant CY as daily_cycle.run_daily
    participant PR as predict.py
    participant ML as mlflow
    participant TK as topk_equal_weight
    participant AG as agents.review
    participant LLM as TradingAgents Graph
    participant RG as risk.gates
    participant EX as MoomooExecutor
    participant OD as OpenD

    CY->>PR: load_latest_predictions()
    PR->>ML: 读 pred.pkl
    ML-->>PR: pd.Series (date × instrument)
    PR-->>CY: latest_date_scores
    CY->>TK: topk_equal_weight(scores, k=5)
    TK-->>CY: {US.CRM: 0.18, ...}

    opt agents enabled
        CY->>AG: review_candidates(weights, today)
        loop 5 tickers
            AG->>LLM: propagate(CRM, 2026-05-28)
            LLM-->>AG: (state, "Overweight")
        end
        AG-->>CY: filtered_weights + verdicts
    end

    CY->>EX: get_portfolio()
    EX->>OD: subprocess get_portfolio.py
    OD-->>EX: funds + positions
    CY->>RG: run_all_gates(...)
    RG-->>CY: (passed, gates[])

    alt all passed
        CY->>EX: submit(orders, dry_run=False)
        loop per order
            EX->>OD: subprocess place_order.py
            OD-->>EX: order_id
        end
        CY->>EX: 等待 positions catch up (max 30s)
    end
```

## 配置 / 状态

| 类型 | 位置 | 提交? |
|------|------|------|
| 不变配置 | `configs/*.yaml` / `*.txt` | ✓ |
| 凭据 | `.env` | ✗（gitignored）|
| 模板 | `.env.example` | ✓ |
| 拉到的数据 | `data/raw_csv/` / `data/qlib_bin/` | ✗ |
| 训练产物 | `mlruns/` | ✗ |
| 快照 | `data/snapshots/equity_history.csv` | ✗ |
| 报告 | `reports/*.md` | ✗ |
| 日志 | `logs/qtf.jsonl` | ✗ |

## 子进程 + JSON 通信约定

所有 moomoo skill 调用都通过 [`src/qtf/utils/subprocess_runner.py`](../src/qtf/utils/subprocess_runner.py) 的 `run_skill(category, name, *args)`：

```python
payload = run_skill(
    "quote", "get_kline",
    "US.AAPL", "--ktype", "1d",
    "--start", "2025-01-01", "--end", "2025-05-28",
)
# payload = {"code": "US.AAPL", "data": [...]}
```

`--json` 标志自动加。skill 必需的 `FUTU_*` 环境变量从 `qtf.config.settings` 自动注入。

## 日志规范

所有运行时事件用 `qtf.utils.logging.log_event()` 写到：

- **stdout**（实时可见）
- **`logs/qtf.jsonl`**（结构化 JSON，每行一个事件）

事件命名：`<phase>.<step>[.<status>]`，例：
- `cycle.predict` / `cycle.scores` / `cycle.weights`
- `cycle.agents.review` / `agents.review.verdict` / `agents.review.done`
- `cycle.risk` / `cycle.aborted`
- `report.snapshot.captured` / `report.daily.written`

便于离线 grep / 复盘 / 接告警。
