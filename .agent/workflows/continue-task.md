---
description: inarbit 高频交易系统重构任务清单
---

# Inarbit HFT 系统开发指南

每次开始会话时，请按照本任务清单继续执行未完成的任务项。

---

## 项目概述

**Inarbit** 是一个高频加密货币套利系统，包含：

- **Python API 层**: FastAPI + WebSocket
- **Rust 核心引擎**: 高性能策略执行
- **React 前端**: 管理界面
- **数据库**: PostgreSQL + Redis

---

## 任务清单（以当前系统现状为准）

### 阶段 0: 同步与清理 ✅

- [x] 同步仓库到 upstream-vscode/main
- [x] 清理 Firebase 依赖与遗留模块
- [x] 统一前端代理与 WebSocket 默认端口
- [x] 移除遗留入口 `server/main.py`

### 阶段 1: 运行配置一致性 ✅

- [x] 文档/脚本端口说明统一为 `8000`
- [x] 前端 WS 默认 `ws://<host>:8000/ws`
- [x] `.env.example` 仅保留 API/WS 配置

### 阶段 2: 数据与机会管线 🔄

- [ ] 行情服务写入 Redis 指标校验
- [ ] 三角/期现机会服务产出稳定性验证
- [ ] 决策服务约束筛选链路验证
- [ ] `/api/v1/system/metrics` 指标核对

### 阶段 3: OMS 执行闭环 🔄

- [ ] 执行计划创建与状态回写
- [ ] 订单/成交/PNL 数据闭环
- [ ] OMS 对账流程与接口健壮性
- [ ] WS 订单推送字段一致性检查

### 阶段 4: 风控闭环 🔄

- [ ] RiskManager 数据获取与缓存实现完备
- [ ] 风控规则与阈值可配置化
- [ ] panic/reset/reload_keys 流程验证

### 阶段 5: Rust 引擎完善 🔄

- [ ] executor 真实下单逻辑补全
- [ ] risk 模块检查逻辑补全
- [ ] 与 Python/Redis 的运行时联调

### 阶段 6: 测试与文档 🔄

- [ ] 集成测试补齐（OMS/决策/风控）
- [ ] 前端关键路径 E2E
- [ ] 端到端 walkthrough 完成与复核

---

## 架构设计（当前）

```
inarbit/
├── client/                  # React 前端
│   ├── src/api/            # 本地 API 客户端
│   └── src/pages/          # 页面组件
│
├── server/                  # Python API 层
│   ├── app.py              # FastAPI 入口
│   ├── api/                # REST + WebSocket
│   ├── services/           # 行情/机会/决策/OMS
│   └── db/                 # 数据库层
│
└── engine/                  # Rust 核心引擎
    └── src/
        ├── main.rs         # 引擎入口
        ├── exchange.rs     # 交易所连接
        ├── strategy.rs     # 策略框架
        ├── executor.rs     # 订单执行
        └── risk.rs         # 风控检查
```

---

## 支持的策略（当前）

| 策略类型 | 说明 | 状态 |
|---------|------|------|
| triangular | 三角套利 | 服务端完善 / 引擎待补全 |
| cashcarry | 期现套利 | 服务端完善 / 引擎待补全 |
| graph | 图搜索套利 | 旧引擎存在缺口 |
| grid | 网格交易 | 旧引擎存在缺口 |
| pair | 配对交易 | 旧引擎存在缺口 |

---

## 支持的交易所

- Binance
- OKX
- Bybit
- Gate.io
- Bitget
- MEXC

---

## 快速启动

```bash
# 1. 启动数据库
docker-compose up -d

# 2. 初始化表结构
psql -U inarbit -d inarbit -f server/db/init.sql

# 3. 启动 Python API
cd server && uvicorn app:app --reload --port 8000

# 4. 启动前端
cd client && npm run dev

# 5. 编译 Rust 引擎
cd engine && cargo build --release
```

---

## 下一步任务

优先完成：

1. [ ] 行情/机会/决策 Redis 链路验证
2. [ ] OMS 计划与订单闭环验证
3. [ ] 风控检查与 panic 流程验证
4. [ ] Rust 引擎 executor/risk TODO 补全

---

## 全仓库结构与功能分析计划

- 覆盖模块：`client/`、`server/`、`engine/`、`tests/`、配置与文档目录
- 产出目标：模块级结构与功能分析、关键流程与数据流、生产就绪完成度评估、实施计划与里程碑
- 调研路径：
  - 入口与架构：`client/src/main.jsx`、`client/src/App.jsx`、`server/app.py`、`engine/src/main.rs`
  - 后端分层：`server/api/`、`server/services/`、`server/db/`、`server/config.py`
  - 引擎核心：`engine/src/strategy.rs`、`engine/src/exchange.rs`、`engine/src/executor.rs`、`engine/src/risk.rs`
  - 前端数据流：`client/src/api/client.js`、`client/src/api/hooks.js`、`client/src/pages/`
  - 测试覆盖：`server/tests/`、`tests/integration/`

---

## 生产就绪完成度评估（基准：可上线运行）

- 功能完整性：2.5/5
- 稳定性与可靠性：2.5/5
- 可观测性：2/5
- 安全性：2/5
- 可运维性：2/5
- 测试覆盖：2/5

结论：当前阶段更适合演示/内测，生产就绪需要补齐真实执行、风控闭环、安全与可观测性、回归测试。

---

## 模块功能矩阵（接口 / 依赖 / 状态 / 风险）

| 模块 | 关键接口 | 关键依赖 | 状态 | 主要风险 |
| --- | --- | --- | --- | --- |
| client | REST `/api/v1/*`；WS `/ws/*` | FastAPI、WebSocket | 功能完整 | 401处理与权限细化不足、异常提示有限 |
| client/pages | 管理页面路由与表单 | API 客户端 | 覆盖完整 | 复杂表单联动与空状态提示可加强 |
| server/api | REST 路由与WS | services、db、auth | 完成度高 | 部分接口缺少限流/审计；密钥加密策略需加强 |
| server/auth | `/api/v1/auth/*` | Redis、PostgreSQL | 完成度高 | 会话管理未做设备/来源绑定 |
| server/services.market | 行情抓取与缓存 | ccxt、Redis | 关键链路可用 | 数据时延与缓存清理策略需验证 |
| server/services.opportunity | 三角/期现机会 | Redis、行情服务 | 关键链路可用 | 机会质量与噪声过滤策略需长期观测 |
| server/services.decision | 决策与约束 | Redis、配置服务 | 关键链路可用 | 约束配置误配会导致无决策 |
| server/services.oms | 执行/对账/告警 | PostgreSQL、Redis、交易所 | 关键链路可用 | 真实交易回滚/补偿场景需压测 |
| server/services.risk | 风控规则 | PostgreSQL、Redis | 基础可用 | 风控策略与覆盖度仍需完善 |
| server/db | 连接池与缓存 | asyncpg、redis | 稳定 | 运行时健康与指标可观测性不足 |
| engine | 策略引擎、信号发布 | Redis、PostgreSQL、交易所WS | 半完成 | 真实执行与风险检查未接入主流程 |
| tests | 单测/集成/E2E | pytest、服务运行环境 | 基础 | 覆盖不足、缺少长跑与容灾验证 |
| config/docs | 快速启动/实施计划 | Docker、脚本 | 基础 | 与生产化部署差距大 |

---

## 执行清单（实现级任务拆解）

### M1：核心闭环可用
- Engine：实现 `executor` 真实下单与错误回滚逻辑
- Engine：将 `risk` 检查接入 `strategy.run` 主循环
- Engine：多交易所 ticker 合并与分发策略（不再仅取首个连接）
- Server：打通 “引擎信号→决策→OMS执行” 的统一管线
- Server：确认 `OMS_PUBLISH_ORDER_DETAIL` 字段一致性
- 数据：补齐 Redis 指标与机会链路校验脚本
- OMS：执行计划创建→订单→成交→PNL 完整写入
- 前端：策略热切换与默认策略自动启用流程联动验证

### M2：稳定性与可观测性
- 指标：统一 metrics 输出（行情、机会、决策、OMS、风控）
- 日志：结构化日志 + 关键路径 trace_id
- 异常：OMS 失败补偿与重试策略验证
- WebSocket：断线重连与限速压测
- 数据：Redis/PG 连接池与慢查询监控
- 安全：API key 加密存储与最小权限校验

### M3：安全与运维生产化
- 安全：密钥管理替换固定密钥字符串
- 部署：提供可复用部署模板（Docker Compose 或 k8s）
- 测试：OMS/决策/风控端到端回归与E2E覆盖
- 运维：发布流程、回滚策略、环境隔离
- 监控：告警接入与值班通知闭环
- 审计：关键操作日志保留与导出

---

## M1/M2/M3 验收标准与指标清单

### M1 验收（核心闭环）
- 引擎信号可触发 OMS 执行计划创建与完成状态回写
- OMS 订单与成交数据可完整写入并可查询
- 风控检查在执行链路中生效（可模拟拒绝）
- Redis 关键指标存在且更新频率符合预期

### M2 验收（稳定性）
- 关键服务 metrics 覆盖率 >= 80%
- OMS 失败补偿流程覆盖主要错误场景
- WebSocket 断线重连成功率 >= 99%（压测）
- 关键路径日志可按 trace_id 追踪

### M3 验收（生产就绪）
- 密钥与敏感信息不再硬编码，集中管理
- 具备可复制的部署与回滚流程
- 端到端回归通过率 >= 95%，覆盖核心交易路径

---

## 执行记录（最新）

- 后端健康：`GET /` 返回 `status=running`
- 指标快照：`/api/v1/system/metrics` 返回三角机会 12、期现机会 13、决策 2
- 机会/决策抽样：`/api/v1/arbitrage/opportunities` 三角=0、期现=5；`/api/v1/decision/decisions` 决策=2（与指标存在差异需确认刷新节奏）
- 数据新鲜度：首次 `market_data_fresh=false`（age 8173ms > max 5000ms），二次检查为 `true`（age 4312ms），需继续观察稳定性
- 决策约束：`/api/v1/decision/constraints` 与 `constraints/auto/effective` 正常返回（auto 中有黑名单与平均数据延迟）
- OMS 告警：`/api/v1/oms/alerts` 返回 0 条记录（当前无告警样本）
