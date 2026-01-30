# Inarbit HFT 系统实施计划

本项目旨在建立一个虚拟币中高频套利系统，支持多种套利策略，并提供 WebUI 管理界面。

---

## 1. 服务器配置推荐

| 配置项 | 入门级 | 进阶级 |
|--------|--------|--------|
| 实例类型 | `c7.xlarge` (4C8G) | `c7.2xlarge` (8C16G) |
| 云盘 | 40GB ESSD | 100GB ESSD |
| 网络 | 5 Gbps | 10 Gbps |
| 推荐区域 | 东京 / 香港 | 东京 |

推荐服务商: UCloud、Vultr、华为云

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend                          │
│                    (Management UI)                          │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/WebSocket
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                           │
│               (REST API + WebSocket)                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐
│ PostgreSQL  │  │    Redis    │  │  Rust Trading Engine    │
│  (持久化)   │  │  (实时缓存)  │  │  (策略执行 + 交易所连接) │
└─────────────┘  └─────────────┘  └─────────────────────────┘
```

---

## 3. 策略模块

| 策略 | 算法 | 说明 |
|------|------|------|
| 三角套利 | 数学计算 | A→B→C→A 价格差套利 |
| 图搜索套利 | Bellman-Ford | N 跳路径寻找负权环 |
| 期现套利 | 资金费率 | 现货+永续对冲 |
| 网格交易 | 区间震荡 | 高抛低吸 |
| 配对交易 | Z-Score | 相关币种价差回归 |

---

## 4. 数据库设计

### PostgreSQL 表

- `users` - 用户账户
- `exchange_configs` - 交易所 API 配置 (加密存储)
- `strategy_configs` - 策略配置
- `order_history` - 订单历史
- `pnl_records` - 盈亏记录
- `system_logs` - 系统日志

### Redis 键命名

- `ticker:{exchange}:{symbol}` - 实时行情
- `orderbook:{exchange}:{symbol}:bids/asks` - 深度数据
- `funding:{exchange}:{symbol}` - 资金费率
- `opportunities:{strategy_type}` - 套利机会

---

## 5. API 端点

### REST API (`/api/v1`)

- `GET/POST /exchanges` - 交易所管理
- `GET/POST/PATCH /strategies` - 策略管理
- `POST /strategies/{id}/toggle` - 策略开关
- `GET /orders` - 订单历史
- `GET /pnl/summary` - 盈亏汇总
- `GET /logs` - 系统日志

### WebSocket (`/ws`)

- `/signals` - 套利信号推送
- `/tickers/{exchange}` - 行情推送
- `/logs` - 日志推送
- `/orders` - 订单状态推送

---

## 6. 验证计划

| 类型 | 方法 |
|------|------|
| 单元测试 | pytest (Python) / cargo test (Rust) |
| Mock 测试 | 模拟交易所 API |
| 本地回测 | 历史数据验证 |
| 沙盒测试 | 交易所 Testnet |
| UI 测试 | 前后端联调 |
