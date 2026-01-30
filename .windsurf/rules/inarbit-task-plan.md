# Inarbit HFT 系统开发指南

每次开始会话时，请按照本任务清单继续执行未完成的任务项。

---

## 项目概述

**Inarbit** 是一个高频加密货币套利系统，包含：

- **Python API 层**: FastAPI + WebSocket
- **Rust 核心引擎**: 高性能策略执行ji下
- **React 前端**: 管理界面
- **数据库**: PostgreSQL + Redis

---

## 任务清单

### 阶段 1: 规划与准备 ✅

- [x] 分析现有项目结构
- [x] 识别需要移除的外部依赖 (Firebase)
- [x] 研究补充策略 (期现套利、网格、配对交易等)
- [x] 编写详细实施计划 (多策略+多交易所)
- [x] 用户审批实施计划

### 阶段 2: 数据库层重构 ✅

- [x] 设计 PostgreSQL Schema → `server/db/init.sql`
- [x] 设计 Redis 数据结构 → `server/db/redis_schema.py`
- [x] 实现数据库连接层 → `server/db/connection.py`

### 阶段 3: Python API 层重构 ✅

- [x] FastAPI REST API → `server/api/routes.py`
- [x] WebSocket 实时推送 → `server/api/websocket.py`
- [x] 策略选择器 API → 已整合到 routes.py

### 阶段 4: Rust 核心引擎 ✅

- [x] 多交易所 WebSocket 连接 → `engine/src/exchange.rs`
- [x] 策略引擎框架 → `engine/src/strategy.rs`
- [x] 三角套利策略 (已实现，编译验证通过)
- [x] 图搜索套利策略 (已实现，编译验证通过)
- [x] 期现套利策略 (已实现，编译验证通过)
- [x] 网格交易策略 (已实现，编译验证通过)
- [x] 配对交易策略 (已实现，编译验证通过)
- [x] 订单执行引擎 → `engine/src/executor.rs`

### 阶段 5: 前端重构 ✅

- [x] 移除 Firebase，对接本地 API → `client/src/api/`
- [x] 策略多选配置界面 → `client/src/pages/Strategies.jsx`
- [x] 多交易所管理界面 → `client/src/pages/ExchangeManagement.jsx`

### 阶段 6: 集成与验证 🔄

- [x] 开发环境配置 (Docker + WSL 更新)
- [ ] 数据库连接验证 (PostgreSQL + Redis)
- [ ] Python API 连通性测试
- [ ] Rust 引擎编译与启动
- [ ] 前端 E2E 交互验证
- [ ] 性能基准测试
- [ ] 实现全局策略与风控模块

---

## 架构设计

```
inarbit/
├── client/                  # React 前端
│   ├── src/api/            # 本地 API 客户端 (替代 Firebase)
│   └── src/pages/          # 页面组件
│
├── server/                  # Python API 层
│   ├── app.py              # FastAPI 入口
│   ├── api/                # REST + WebSocket
│   └── db/                 # 数据库层
│
└── engine/                  # Rust 核心引擎
    └── src/
        ├── main.rs         # 引擎入口
        ├── exchange.rs     # 交易所连接
        ├── strategy.rs     # 策略框架
        └── executor.rs     # 订单执行
```

---

## 支持的策略

| 策略类型 | 说明 | 状态 |
|---------|------|------|
| triangular | 三角套利 | 框架完成 |
| graph | 图搜索套利 | 框架完成 |
| funding_rate | 期现套利 | 框架完成 |
| grid | 网格交易 | 框架完成 |
| pair | 配对交易 | 框架完成 |

---

## 支持的交易所

- Binance
- OKX
- Bybit
- Gate.io
- Bitget
- MEXC

------
trigger: manual
---
当前工作总结（已完成内容）
1) 行情质量与套利计算
futures ticker：bid/ask 缺失时用 last 回填，提升 ticker_futures:binance:* 的 BBA 稳定性
cash&carry：优先用 spot orderbook TOB 的 bid/ask（更接近可成交价），缺失再回退 ticker
2) OMS 核心（paper + live）
orders/fills 落库
orders：写入 plan_id/leg_id/account_type/client_order_id/external_order_id
fills：写入 paper_fills/live_fills 并与 orders 关联
live：支持 多 fills（从 order.trades/fills/info.fills 解析），VWAP 计算均价
幂等
DB 幂等：client_order_id 唯一冲突自动复用既有 order_id
交易所幂等：live 下单携带 newClientOrderId/clientOrderId（由 plan/leg 生成并安全截断）
强保护
live 执行需要 confirm_live=true + INARBIT_ENABLE_LIVE_OMS=1 + Binance API key
兼容 BINANCE_SECRET_KEY / BINANCE_API_SECRET
3) OMS 查询与管理 API（新增/完善）
执行：POST /api/v1/oms/execute_latest
查询：
GET /api/v1/oms/plans/latest
GET /api/v1/oms/orders
GET /api/v1/oms/fills
对账/补偿：
POST /api/v1/oms/orders/{order_id}/refresh
POST /api/v1/oms/orders/{order_id}/cancel
POST /api/v1/oms/plans/{plan_id}/refresh
POST /api/v1/oms/plans/{plan_id}/cancel
4) 工作流（写入说明）
我无法直接写入 .windsurf/rules/inarbit-task-plan.md（路径写入受限）。
但我已把该文件加入了 Git 暂存（git add -A 已执行），你可以手动把我之前给你的“阶段 7: OMS Live Execution Integration”段落粘贴到该文件并保存，再提交即可。
下一步工作计划（建议按优先级）
[P0] arb-exec-018：cancel_plan 后同步更新 execution_plans.status='cancelled' 与 finished_at，让 plan 生命周期闭环一致
[P0] arb-exec-001 收尾：把 partially filled 的轮询刷新策略化（重试/超时/失败补偿/对账）
[P1] 风控再加固：live 账户白名单、限额、二次确认策略
[P1] 基础回放/验证：用历史 decision 驱动 paper OMS 做一致性验证
