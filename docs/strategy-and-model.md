# 策略与模型

## 选股流程

```
50 只大盘股 (configs/universe_us5.txt)
        │
        ▼
qlib Alpha158 特征工程
   (158 个手工因子: 动量、波动率、量价、技术指标 ...)
        │
        ▼
LightGBM (max_depth=8, num_leaves=128)
   - 训练目标: 下一交易日收益（log return）
   - 训练窗口: 2022-01-01 .. 2024-05-31
   - 验证窗口: 2024-06-01 .. 2024-12-31
   - 测试窗口: 2025-01-01 .. 2026-05-23
        │
        ▼
对每个 (date, instrument) 输出标量 score
        │
        ▼
topk_equal_weight(scores, k=5, total_weight=0.90)
   - 按 score 降序取 top-5
   - 等权 18% × 5 = 90% 部署，10% 现金缓冲
        │
        ▼
{US.CRM: 0.18, US.ORCL: 0.18, ...}
```

## 为什么选 qlib + Alpha158 + LightGBM

| 组件 | 替代选项 | 选这个的理由 |
|------|---------|------------|
| **qlib** | zipline, backtrader, vectorbt | 自带 Alpha158 / Alpha360 因子库 + MLflow + 中国本土优化（美股也跑得通）|
| **Alpha158** | Alpha360 / 自写因子 | 158 个手工因子，**LightGBM 等树模型的最佳搭档**（Alpha360 是 360 维原始时序，更适合 LSTM/Transformer）|
| **LightGBM** | XGBoost / Random Forest / DL 模型 | 在量化领域工业级首选：训练快、可解释、稳定、对缺失值容忍 |

### Alpha158 是什么

158 个由 qlib 团队手工设计的因子，按维度分：

- **Kbar 类**（基础形态）：实体大小、影线长度、K 线类型
- **价格类**：收益率、ROC、价差（涵盖 5/10/20/30/60 日窗口）
- **波动率类**：标准差、ATR 类
- **量价类**：换手率、VWAP 偏离、量价相关性
- **趋势类**：MA、EMA、MACD
- **技术指标**：RSI、KDJ、Bollinger Bands、CCI

具体定义见 [`qlib/qlib/contrib/data/handler.py:Alpha158`](https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py)。

### 为什么不是 Alpha360

Alpha360 是把过去 60 天 × 6 个字段（OHLCV + amount）的**原始时序**展开成 360 维输入，没做特征工程。

- 树模型啃不动原始时序（无法自动捕捉时间维度的非线性）
- 适配的是 GRU / LSTM / Transformer / TCN 等序列模型
- 训练慢、不稳定、且本骨架的 LightGBM 反而退化

## 票池设计

### 当前 50 只

[`configs/universe_us5.txt`](../configs/universe_us5.txt) —— S&P 100 头部大盘股，覆盖：

- **大型科技**：AAPL, MSFT, NVDA, GOOGL, AMZN, META, AVGO, ADBE, CRM, ORCL, INTU, NFLX, INTC, QCOM, IBM, CSCO, AMD
- **金融**：JPM, V, MA, BAC, GS
- **医药**：LLY, UNH, JNJ, ABBV, MRK, ABT, DHR, TMO, PFE
- **消费**：WMT, COST, KO, PG, PEP, HD, MCD, DIS, NEE
- **能源/工业**：XOM, CVX, CAT, RTX, GE, LIN, PLD, T, ACN

### 为什么 50 只是甜点

```
票池 < 10: Alpha158 横截面因子退化为 0
票池 ≈ 30: 信号能跑，但分数只有 3 档
票池 ≈ 50: 信号充分（11+ 档），调仓有意义
票池 > 100: 配额、计算时间显著上升，骨架 demo 不需要
```

骨架阶段 50 只是性价比最高的：moomoo K 线配额够用、训练 < 2 分钟、信号区分度好。

## 数据流（深入）

### 训练日期切分

```yaml
# configs/workflow_us5_lgb.yaml
data_handler_config:
    start_time: 2022-01-01
    end_time: 2026-05-23
    fit_start_time: 2022-01-01      # 用于因子标准化的拟合窗口
    fit_end_time: 2024-05-31        # 仅用训练段拟合，防 lookahead
segments:
    train: [2022-01-01, 2024-05-31]
    valid: [2024-06-01, 2024-12-31]
    test:  [2025-01-01, 2026-05-23]
```

测试段不参与训练 / 不影响标准化参数，是真正的 out-of-sample。

### qlib bin 格式

[`data/qlib_bin/us_data/`](../data/qlib_bin/) 结构：

```
calendars/day.txt          所有交易日（升序）
instruments/us5.txt        票池 + 起止日期 (tab 分隔)
features/<symbol>/
    open.day.bin           5 年日线 × 4 字节 float
    close.day.bin
    high.day.bin
    low.day.bin
    volume.day.bin
    factor.day.bin         复权因子（moomoo 已前复权，统一为 1.0）
```

二进制读取比 CSV 快 ~10×，qlib 训练完全跑这套。

## 当前模型局限

### 1. LightGBM 早停

训练日志会显示：

```
Training until validation scores don't improve for 50 rounds
[20] train l2: 0.967 valid l2: 0.981
[40] train l2: 0.956 valid l2: 0.983
Early stopping, best iteration is: [1]
```

模型在第 1 轮就早停了。这是因为：

- 短期收益本身**高噪音**（信号/噪声比 < 0.05）
- Alpha158 在 50 只票上仍是相对粗糙的特征
- LightGBM 看到 valid loss 不降就停

实际跑出来 11+ 档信号已经够用，但**模型本身没有过拟合的余地**——这也意味着真实的预测能力相当有限，IC（信息系数）通常在 0.02-0.05 之间。

### 2. Alpha158 横截面假设

部分因子（如 rank、quantile）依赖横截面分布。50 只票的横截面是**统计意义稀薄**的。要做认真的研究，把票池扩到 200+ 才稳。

### 3. 训练频率

骨架默认是**手动重训**（`02_train.py`）。生产场景应该：

- 滚动训练窗口（rolling window）每月一次
- 或者用 qlib 的 `RollingDataHandler` 自动滚动

## 调参指南

### 想要更细的分档

[`configs/workflow_us5_lgb.yaml`](../configs/workflow_us5_lgb.yaml) 里：

```yaml
max_depth: 8          # 调到 10 让树更深
num_leaves: 128       # 跟着 depth 调，最多 2^depth
lambda_l1: 80         # 降到 20-50 减弱稀疏惩罚
lambda_l2: 200        # 降到 100 减弱平滑惩罚
learning_rate: 0.05   # 降到 0.02 让训练更慢更精
```

注意：**过拟合容易 IC 反而下降**。建议每次调参后看 `mlflow ui` 的 IC / Rank IC 指标。

### 想换因子库

把 `workflow_us5_lgb.yaml` 里的 handler class 改成 Alpha360：

```yaml
handler:
    class: Alpha360
    module_path: qlib.contrib.data.handler
```

但记得同时换模型为序列模型（如 qlib 的 `GRU` 或 `LSTM`），否则效果会变差。
