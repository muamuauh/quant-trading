# 日常运行 / 计划任务 / 故障排查

## 每日运行入口

### 一键 bat（推荐）

```cmd
run_daily.bat                       :: 完整流程: 探活 → 拉数据 → 执行 → 报告
run_daily.bat --dry-run             :: 不真实下单
run_daily.bat --retrain             :: 顺便重训模型
run_daily.bat --skip-ingest         :: 跳过拉数据
run_daily.bat --no-pause --skip-open  :: 计划任务用
```

bat 内部每一步的 Python stderr 都会落盘到 `logs/0X_<step>_stderr.log`，cmd 窗口闪退也不丢错误。

### 防闪退启动器

`run_daily_safe.bat` 会把上面 bat 放进 cmd /k 保护壳里跑，即使 cmd 解析异常关掉，外层窗口仍在：

```cmd
run_daily_safe.bat --dry-run
```

### 单独跑某一步

```cmd
python scripts\01_ingest.py --years 5    :: 仅拉数据
python scripts\02_train.py                :: 仅训练
python scripts\03_predict.py              :: 仅出最新打分
python scripts\04_execute.py --dry-run    :: 出订单规划但不下单
python scripts\05_report.py               :: 仅刷新当日报告
```

## 挂自动跑

### 注册 Windows 计划任务

```cmd
setup_schedule.bat 21:35
```

会用 `schtasks /Create` 注册一条名为 `qtf_daily` 的每日任务，21:35 启动跑 `run_daily.bat --no-pause --skip-open`。

#### 美股开盘时间对照

| 季节 | 美东 | 北京时间 | 建议任务时间 |
|------|------|---------|-----------|
| 夏（DST，3 月-11 月）| 09:30 ET | 21:30 | **21:35** |
| 冬（EST，11 月-3 月）| 09:30 ET | 22:30 | **22:35** |

DST 切换日要手动调整。

### 撤销

```cmd
remove_schedule.bat
```

### 任务运行要求

- **用户必须登录**（屏幕锁屏 OK，注销不行）
- **moomoo OpenD 必须在跑**且已登录（建议加 Windows 启动项）
- **电源管理**：默认电池模式不启动，笔记本用户可在「任务计划程序」改

## 故障排查

### Step 1 探活失败

`logs/01_probe_stderr.log` 显示连不上 OpenD：

```
[ERROR] Cannot connect to OpenD (127.0.0.1:11111): ...
```

**检查清单**：
1. OpenD GUI 在跑吗？任务栏托盘有图标
2. OpenD 登录了吗？右上角显示账号名
3. `.env` 的 `FUTU_OPEND_HOST` / `FUTU_OPEND_PORT` 对吗？
4. 防火墙没拦 11111 端口吧？

### Step 2 拉数据慢/失败

50 只票 × 5 年 ≈ 25 分钟。如果某只票卡住，看 `logs/02_ingest_stderr.log` 的最后一行。

**配额超限**：moomoo 历史 K 线每只票 30 天窗口算 1 quota，一次拉 5 年触发 1 quota；重复拉同票同窗口免费。50 quota 不会超限，但**不要短时间内重启多次**。

### Step 4 订单被拒

最常见错误（看 `logs/04_execute_stderr.log` 或 `cycle.done` 事件的 `error` 字段）：

| 错误 | 原因 | 修复 |
|------|------|------|
| `价格参数精度不符合规范` | 美股价格 > $1 必须 2 位小数 | 已修：`order_planner._round_us_price` |
| `没有解锁交易` | 真盘未在 OpenD GUI 手动解锁 | OpenD 主界面点"解锁交易"按钮（仅真盘需要）|
| `Master account 不允许下单` | acc_id 选了汇总账户 | `.env` 改成 SIMULATE 子账户的 acc_id |
| `下单数量超过最大可用` | 现金不足 | 检查 `total_assets` / `cash` 数字 |

### 风控全部通过但 `submitted: false`

看 cycle.aborted 事件的 `reason`。常见：

- **`outside US RTH`**：当前不在美股常规时段，正常拦截
- **`post-trade cash X < required Y`**：单只权重过大，现金缓冲不够
- **`max single weight X > cap Y`**：单只目标权重超过 `risk_limits.yaml` 的上限

### 报告显示的持仓数 < 实际提交单数

moomoo 的 `position_list_query` 有几秒到几十秒的传播延迟。orchestrator 已经在 submit 后用 `_wait_for_positions` 等 30 秒，若仍超时：

- 看 `cycle.wait.timeout` 事件的 `missing` 字段
- 那只票通常**几分钟后**会出现在 `get_portfolio.py --json` 里
- 第二天报告会自动正确

### cmd 窗口闪退

**根因排查**：

1. `logs/01_probe_stderr.log` / `02_ingest_stderr.log` 等任一不为空 → Python 报错
2. 都为空但 cmd 仍闪退 → cmd 解析问题
3. 看 `logs/qtf.jsonl` 最后一行的 `ts`，对照任务触发时间，缺失意味着 bat 中途崩

**应对**：用 `run_daily_safe.bat` 替代直接双击 `run_daily.bat`。

### Agent 复核耗时太长

每只票 ~30-60 秒 LLM 串行调用，5 只票 5-10 分钟正常。如果 > 15 分钟：

- 看 `logs/qtf.jsonl` 的 `agents.review.verdict` 事件时间戳，定位卡哪只票
- 通常是 LLM 接口超时
- `FAIL_OPEN=1` 模式下会自动放行那只票

## 日志位置速查

```
logs/01_probe_stderr.log    探活 OpenD 的输出
logs/02_ingest_stderr.log   拉数据的输出
logs/03_train_stderr.log    训练的输出（仅 --retrain 时有）
logs/04_execute_stderr.log  执行 + 报告生成的输出
logs/qtf.jsonl              所有 cycle.* / agents.* / report.* 结构化事件
~/.futu_trade_audit.jsonl   每笔订单的审计记录（moomoo skill 自动写）
~/.tradingagents/logs/      TradingAgents 内部 LangGraph 日志
mlruns/                     训练历史 + IC / Rank IC 指标
```

## 重置流程

如果跑乱了想从头来：

```cmd
:: 清掉本地数据（保留代码）
rmdir /s /q data
rmdir /s /q mlruns
rmdir /s /q reports
del logs\*.log
del logs\qtf.jsonl

:: 重新拉数据 + 训练
python scripts\01_ingest.py
python scripts\02_train.py
```

`.env` 和 `configs/` 不会动。

## 监控接告警（进阶）

`logs/qtf.jsonl` 是结构化 JSON，每行一个事件。可以接 Promtail / Vector / Filebeat 推到 ELK / Loki，然后对 `cycle.fatal` / `cycle.aborted` / `agents.review.error` 设告警。
