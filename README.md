# qtf — qlib + moomoo + LLM 自动化交易骨架

> 端到端最小可用的量化交易骨架：从 moomoo OpenD 拉 50 只美股日 K → qlib LightGBM + Alpha158 选股 → TradingAgents 多 agent LLM 复核 → 5 道风控闸 → 限价单进 moomoo 模拟盘 → 中文 Markdown 日报。Windows 计划任务可一键挂上自动跑。

⚠️ **免责声明**：这是教学/研究骨架，**不构成投资建议**。所有验证都在模拟账户上做。切真盘前请充分回测并理解 [docs/operations.md](docs/operations.md) 里的所有 caveat。

---

## 30 秒看懂这是什么

```
moomoo OpenD ──► 拉日K ──► qlib LightGBM ──► top-5 候选 ──► TradingAgents LLM 复核
                                                                    │
moomoo 模拟盘 ◄── 限价单 ◄── MoomooExecutor ◄── 5 道风控闸 ◄── 保留 Buy/Overweight
                    │
                    ▼
              reports/YYYY-MM-DD.md（含 LLM 中文理由）
```

完整架构图见 [docs/architecture.md](docs/architecture.md)。

---

## 主要特性

- **50 只美股大盘股票池**（可在 `configs/universe_us5.txt` 自由扩缩）
- **qlib LightGBM + Alpha158** 因子库每日打分排序
- **TradingAgents 多 agent LLM 复核**（可选开关）：5 个分析师 + 2 个多空辩论 + 1 个交易员 + 3 个风险辩论 + 1 个 PM
- **5 道风控闸**：环境、时段、单仓上限、现金下限、单日止损
- **moomoo 模拟盘**限价单提交 + 持仓回查 + 等待异步成交
- **每日中文 Markdown 报告**：账户概览、持仓、风险指标、当日活动、agent 评级理由
- **Windows 计划任务**：双击 `setup_schedule.bat` 一键挂每日自动跑
- **LLM provider 自由切换**：OpenAI / Anthropic / DeepSeek / GLM / Qwen / Ollama 都支持

---

## 快速开始

### 1. 前置要求

- Windows 11
- [moomoo OpenD](https://openapi.moomoo.com) 已安装并登录（**至少有一个 US SIMULATE 子账户**）
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- [moomooapi](https://openapi.moomoo.com/skills) skill（Claude Code 用户）安装在 `C:\Users\<you>\.claude\skills\moomooapi\`

### 2. clone + 装环境

```powershell
# 1. clone 本仓库
git clone https://github.com/<you>/qtf.git
cd qtf

# 2. clone 两个 vendored 依赖（不在本仓库里，避免 nested git）
git clone https://github.com/microsoft/qlib qlib
git clone https://github.com/TauricResearch/TradingAgents TradingAgents

# 3. conda 环境
conda create -n qtf python=3.11 -y
conda activate qtf
conda install -c conda-forge numpy pandas cython scikit-learn lightgbm pyyaml -y

# 4. 装 qlib + TradingAgents + qtf 本身（editable）
pip install -e .\qlib
pip install -e .\TradingAgents
pip install "moomoo-api==10.6.6608" "protobuf>=3.20,<4" pydantic-settings python-dotenv pandas_market_calendars mlflow
pip install -e .

# 5. 配置
copy .env.example .env
python C:\Users\<you>\.claude\skills\moomooapi\scripts\trade\get_accounts.py --json
# 把模拟盘 acc_id 填进 .env 的 FUTU_ACC_ID=
# 想用 LLM 复核：QTF_AGENTS_ENABLED=1 + 填 OPENAI_API_KEY=
```

### 3. 跑一次

```powershell
python scripts\01_ingest.py       # 拉日 K，5 年 × 50 只票约 9 分钟（4 并发）
python scripts\02_train.py        # 训练 LightGBM
python scripts\06_backtest.py     # 回测：夏普/回撤/IC（评估模型选股能力）
python scripts\04_execute.py --dry-run   # 看规划但不下单
python scripts\04_execute.py      # 真实提交到模拟账户
```

或一键脚本（推荐）：

```powershell
run_daily.bat --dry-run                   # 看流程
run_daily.bat                              # 真实跑
setup_schedule.bat 21:35                   # 挂每日 21:35 自动跑（美股开盘后 5 分钟）
```

---

## 项目结构

```
src/qtf/             代码主体（按层组织，详见 docs/architecture.md）
  data/              moomoo K 线拉取 + qlib bin 转换
  model/             LightGBM 训练入口
  strategy/          top-K 选股 + 权重
  agents/            TradingAgents 复核层
  execution/         订单规划 + moomoo executor
  risk/              5 道风控闸
  backtest/          历史回测引擎 + 指标（夏普/回撤/IC）
  orchestrator/      daily_cycle 串联所有层
  report/            每日 Markdown 报告

configs/             股票池、qlib workflow YAML、风控阈值
scripts/             01_ingest / 02_train / 03_predict / 04_execute / 05_report / 06_backtest
tests/               33 个单元测试
docs/                架构文档、模型说明、运维手册

run_daily.bat        一键启动脚本
run_daily_safe.bat   crash-resistant 启动器（套两层 cmd）
setup_schedule.bat   注册 Windows 计划任务
remove_schedule.bat  撤销
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统架构 + 数据流 + 调用关系 |
| [docs/strategy-and-model.md](docs/strategy-and-model.md) | qlib + Alpha158 + LightGBM 因子设计与训练 |
| [docs/llm-review.md](docs/llm-review.md) | TradingAgents 集成 + provider 切换 + 成本估算 |
| [docs/operations.md](docs/operations.md) | 日常运行 / 计划任务 / 故障排查 / 已知坑 |

---

## 主要技术栈

- **数据**：moomoo OpenAPI + qlib bin
- **模型**：LightGBM + Alpha158（158 个手工因子）
- **LLM**：LangGraph 多 agent + OpenAI/Anthropic/DeepSeek
- **执行**：moomoo SDK（Python 子进程）
- **编排**：纯 Python + Windows bat
- **报告**：Markdown
- **测试**：pytest（33/33 通过）

---

## 安全提醒

1. **`.env` 含 API key**——已在 `.gitignore` 里，**永远不要 commit**
2. **`reports/` `logs/` `data/snapshots/`** 含账户金额信息——也已 gitignored
3. **moomoo 解锁交易必须在 OpenD GUI 手动**——SDK 调用 `unlock_trade` 是禁止的
4. 默认 `FUTU_TRD_ENV=SIMULATE`；切到 `REAL` 还需额外 `I_CONFIRM_REAL=1`
5. 所有 LLM 调用通过 TradingAgents 自己的 cache（位置在 `~/.tradingagents/cache/`），首次跑同一只票同一天会跑 12 次 LLM 调用

---

## 致谢

- [Microsoft qlib](https://github.com/microsoft/qlib) —— 量化框架
- [TauricResearch TradingAgents](https://github.com/TauricResearch/TradingAgents) —— 多 agent LLM 框架
- [moomoo OpenAPI](https://openapi.moomoo.com) —— 行情与交易接口

## 协议

MIT License，详见 [LICENSE](LICENSE)。
