# 系统报告（Inarbit）— 2026-02-03

> 本报告基于服务器运行时快照 + API/DB 检查结果生成，**不包含任何密钥/口令/令牌**等敏感信息。

## 摘要

- **GitHub/服务器连接**：本地 `git push` 正常；服务器侧 `git pull` 正常；SSH 连接正常。
- **后端服务**：`inarbit-api.service` 运行中（Uvicorn + FastAPI）。
- **行情/扫描/决策**：扫描器与决策链路可用，机会与决策可生成。
- **模拟执行（真实交易所行情+费率）**：已通过 OMS 接口完成一次 paper 执行并落库，组合估值与权益计算已修复为合理口径。

## 运行环境与版本

- **报告生成时间（UTC）**：2026-02-03T10:39:56Z
- **代码版本（Git HEAD）**：`6f989225e8295f3d99b4d041933bfb4112dcfe88`
- **Python**：3.10.12
- **服务状态**：`systemctl is-active inarbit-api.service` = `active`

## GitHub 与服务器同步验证

- **本地到 GitHub**：已多次完成提交并推送（包含本次修复：portfolio 估值、行情抓取优化）。
- **服务器从 GitHub 拉取**：服务器侧 `git pull` 快进更新成功，并已重启服务验证生效。

## 当前运行的策略（数量与配置来源）

### 运行数量

- **机器人状态**：`/api/v1/bot/status` 返回 `active_strategies = 3`，`trading_mode = paper`

### 策略列表（来自 DB 的 `strategy_configs`）

通过 `/api/v1/bot/strategies` 与 DB 查询一致，当前启用 3 个策略：

- **triangular（优先级 1）**：名称“`三角套利`”，启用
- **funding_rate（优先级 3）**：名称在当前输出中存在编码显示异常，但策略类型与启用状态正常
- **pair（优先级 4）**：名称在当前输出中存在编码显示异常，但策略类型与启用状态正常

> 说明：策略参数（`config` JSON）由 DB 提供，机器人通过 API 读取并运行。报告中不展开原始 JSON 以避免信息噪声；如需可在后续做脱敏后的参数摘要输出。

## 扫描器（Triangular / CashCarry）运行配置与状态

### 配置（运行时可动态调整）

- **Triangular**（`PUT /api/v1/scanners/triangular`）：
  - `exchange_id=okx`, `base_currency=USDT`, `min_profit_rate=-0.01`, `fee_rate=0.0004`
  - `refresh_interval_seconds=2`, `ttl_seconds=10`, `max_opportunities=50`
- **CashCarry**（`PUT /api/v1/scanners/cashcarry`）：
  - `exchange_id=okx`, `quote_currency=USDT`, `min_profit_rate=-0.01`
  - `spot_fee_rate=0.0004`, `perp_fee_rate=0.0004`, `funding_horizon_intervals=3`
  - `refresh_interval_seconds=2`, `ttl_seconds=10`, `max_opportunities=50`

### 快照指标（来自 `/api/v1/system/metrics`）

- **Triangular opportunities**：4
- **CashCarry opportunities**：10
- **Decisions**：5

## 行情服务（MarketDataService）稳定性与关键开关

### 当前运行指标（来自 `/api/v1/system/metrics`）

- `spot_symbols=10`
- `futures_symbols=5`
- `funding_symbols=5`
- `last_loop_ms≈3.3s`
- `market_data_fresh=true`（`market_data_age_ms≈861`，`max_age_ms=5000`）

### 关键变更（稳定性）

为避免默认抓取过多市场导致循环过慢、ticker 过期、UI/估值出现 `null`：

- **`MARKETDATA_EXPAND_USDT_MARKETS`**：控制是否扩展抓取“全市场 /USDT”现货 ticker（默认关闭）
- **`MARKETDATA_EXPAND_FUTURES_MARKETS`**：控制是否扩展抓取“全市场 :USDT”永续 ticker（默认关闭）

> 这两项开关关闭时，futures/funding 侧将优先根据配置/映射出的少量标的抓取，显著降低 loop 时长并提高稳定性。

## 模拟盘（初始 1000 USDT）与 OMS 执行验证

### 模拟配置与权益

- **simulation_config**（`/api/v1/config/simulation`）：
  - `initialCapital=1000 USDT`
  - `currentBalance≈1999.60 USDT`（见下文说明）
- **portfolio**（`/api/v1/config/simulation/portfolio`）：
  - `totalEquity≈999.74 USDT`
  - `unrealizedPnL≈0.14 USDT`

> 说明：当前一次 cash-carry 决策方向为 `short_spot_long_perp`，因此 **现货卖出会增加现金余额（currentBalance）**，同时 **现货负仓位市值为负**；`totalEquity = cash + spot市值 + perp浮动盈亏`，因此权益仍回到接近初始资金（扣费后略偏差）。

### OMS 最新执行计划（paper）

来自 `/api/v1/oms/plans/latest`：

- **plan_id**：`181c6dd8-53dc-461c-9655-5e41ee4bfb47`
- **exchange_id**：`okx`
- **kind**：`basis`
- **状态**：`completed`
- **legs**：2 笔订单（spot sell + perp buy），均已 `filled`
- **pnl_summary**：
  - `profit≈-0.6596 USDT`
  - `total_fee≈0.8 USDT`
  - `profit_rate≈-0.00032985`

### 落库检查（关键表计数）

DB 表计数（paper 模拟相关）：

- `paper_orders`: 2
- `paper_execution_plans`: 1
- `paper_positions`: 2
- `paper_fills`: 2
- `paper_opportunities`: 1
- `paper_pnl`: 1

## 本次已完成的关键修复（与影响）

- **DecisionService 冻结对象写入修复**：使用 `dataclasses.replace()`，避免 `FrozenInstanceError` 导致决策循环崩溃。
- **OMS 多交易所决策执行修复**：OMS 按 decision 的 `exchange_id` 动态选择交易对启用集，避免固定 `binance` 造成拒绝执行。
- **行情抓取扩展控制**：新增 `MARKETDATA_EXPAND_USDT_MARKETS` 与 `MARKETDATA_EXPAND_FUTURES_MARKETS`，默认不扩展全市场，降低 loop 时长、减少 ticker 过期与 UI `null`。
- **模拟组合估值修复**：
  - perp 仓位从 `ticker_futures:{exchange}:{symbol}` 取价（spot 缺失时对 spot 做了合理兜底）
  - perp 仓位价值按 **浮动盈亏** 估值，避免将名义本金计入权益导致“权益翻倍”

## 风险与待办建议（下一步可做）

- **模拟重置逻辑不完整**：`PUT /api/v1/config/simulation` 的 `resetNow` 当前仅清理了 `paper_pnl`，未清理 `paper_orders/paper_positions/...`，建议补齐为“一键清空模拟盘状态”的完整重置（或改为按 run_id 分组）。
- **策略配置输出编码问题**：`funding_rate` / `pair` 的名称在部分输出中显示异常，建议统一 DB/接口的 UTF-8 编码与序列化策略。
- **API 能力扩展建议**：
  - 增加 `POST /api/v1/simulation/reset_all`（清理 paper_* 全套表 + 回滚余额）
  - 增加 `GET /api/v1/marketdata/symbols`（显示当前抓取的 spot/futures/funding 符号集合与最后更新时间）
  - 增加 `POST /api/v1/bot/strategies/{id}/enable|disable`（可控启停策略，减少直接改 DB 的需求）

## 附录：本次验证过的关键接口清单

- `/api/v1/system/status`
- `/api/v1/system/metrics`
- `/api/v1/bot/status`
- `/api/v1/bot/strategies`
- `/api/v1/scanners/status`
- `/api/v1/scanners/triangular`（PUT）
- `/api/v1/scanners/cashcarry`（PUT）
- `/api/v1/decision/constraints`
- `/api/v1/config/simulation`
- `/api/v1/config/simulation/portfolio`
- `/api/v1/oms/plans/latest`
- `/api/v1/oms/orders`

