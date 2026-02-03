# 进度断点说明（2026-02-03）

本文件用于记录当前改动进度，便于下次登录从断点继续。目标是保持 **本地工作区 / GitHub 仓库 / 服务器 `/opt/inarbit-cursor`** 三者一致。

## 已完成的核心改动

### 管理菜单与页面合并
- **订单管理**：将 `订单管理控制台 (/oms)` 与 `订单管理参数 (/oms-config)` 合并为单一入口 **订单管理控制**。
  - `/oms-config` 保留为跳转到 `/oms` 的兼容路由。
  - OMS 默认参数保存/加载逻辑合并进 `OmsConsole`（localStorage）。
- **机器人控制**：确认 `控制面板 (/control)` 与 `机器人控制台 (/bot)` 功能重复后，已将机器人控制台能力合并进控制面板，并移除菜单入口。
  - `/bot` 保留为跳转到 `/control` 的兼容路由。

### 管理总览（AdminHub）紧凑化与对齐
- `管理总览 (/admin)` 的入口卡片已多次压缩为更窄/更扁布局，并对齐顺序、补齐缺失入口。
- 将原“实时总览”统一更名为 **收益总览**（导航/总览入口/页面标题一致）。

### 交易所真实连接状态（以“真实连通”为准）
- 后端新增 `/api/v2/exchanges/health`，前端在交易所相关页面展示真实连接状态（避免“已启用但未连通”的假象）。

## 收益/权益口径与展示说明（重要）

### 收益总览（`/realtime`）展示口径
- **总权益（模拟盘）**：来自 `simulation/portfolio.totalEquity`
- **权益变化**：\( \Delta = totalEquity - initialCapital \)，已改为带正负号展示
- **现金账户余额**：来自 `simulation_config.current_balance`（可能包含空头卖出所得）
- **仓位估值**：现货仓位市值（空头为负） + 合约浮盈亏（perp 仅计浮盈亏，不计名义本金）
- 页面内新增“公式行”用于对账：
  - `equity = cash + spot + perpPnL`

### 策略名称乱码修复
- 发现后端 realtime snapshot 同时返回 `strategies`（DB name，可能已脏/乱码）与 `strategy_types`（稳定）。
- 前端已改为优先使用 `strategy_types` 映射为标准中文名显示（绕开乱码源头）。
- `策略管理` 页也改为优先显示策略类型映射名，避免 DB name 乱码覆盖。

## “收益曲线不变但实时收益在变”的原因与修复

### 原因
- “收益展示（PnL）”原曲线主要基于 **OMS 已实现收益**（paper_pnl/live_pnl），如果没有新的已实现记录或按天聚合导致点很少，会看起来不动。
- “收益总览”实时变化通常来自 **未实现浮盈亏**（总权益 mark-to-market）。

### 修复
- `收益展示 (/pnl)` 增加曲线模式切换：
  - **总权益（模拟盘默认）**：定时采样 `simulation/portfolio.totalEquity`，曲线会随行情波动。
  - **已实现（OMS）**：按记录时间累加，避免“按天聚合导致平”的错觉。

## 关键文件
- 前端
  - `client/src/App.jsx`：路由与侧边栏菜单（重命名/跳转/合并入口）
  - `client/src/pages/AdminHub.jsx`：管理总览紧凑布局与入口顺序/命名
  - `client/src/pages/ControlPanel.jsx`：合并机器人控制面板
  - `client/src/pages/OmsConsole.jsx`：OMS 默认参数保存/加载
  - `client/src/pages/RealtimeOverview.jsx`：收益总览权益拆分、正负号、策略名映射
  - `client/src/pages/Strategies.jsx`：策略显示优先映射名
  - `client/src/pages/PnLOverview.jsx`：新增“总权益曲线/已实现曲线”模式
- 后端
  - `server/api/exchange_routes_v2.py`：`/api/v2/exchanges/health`
  - `server/services/realtime_snapshot.py`：realtime summary 输出 `strategies/strategy_types`
  - `server/api/config_routes.py`：`/api/v1/config/simulation/portfolio` 权益口径

## 部署/同步方式（下次继续用）
- 本地：`git status` 确认干净 → 提交 → `git push`
- 服务器：`cd /opt/inarbit-cursor && git pull --ff-only`
- 前端：`cd /opt/inarbit-cursor/client && npm run build && 重启前端服务（vite preview）`
- 后端：如改动后端 API，再重启 uvicorn 进程

## 当前状态（写入时）
- 本地工作区：已保持干净（无未提交变更）
- GitHub：已推送最新 UI 改动（收益曲线/口径说明/策略名修复等）
- 服务器：通过 `git pull + npm run build + 重启前端` 同步到最新

