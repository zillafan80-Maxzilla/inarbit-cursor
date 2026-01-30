---
description: Inarbit 高频交易系统 - 全程任务清单
---
# Inarbit HFT 系统全程任务

每次开始会话时，请按照本任务清单继续执行未完成的任务项。

---

## 项目概述

**Inarbit** 是一个高频加密货币套利系统，包含：

- **Python API 层**: FastAPI + WebSocket
- **Rust 核心引擎**: 高性能策略执行
- **React 前端**: 管理界面
- **数据库**: PostgreSQL + Redis
- **风险管理**: 全局风控体系

---

## 阶段 0: 同步与清理 ✅

- [x] 同步到 upstream-vscode/main
- [x] 清理 Firebase/遗留模块
- [x] 统一 WebSocket 与 API 默认端口
- [x] 清理无用入口与空目录

## 阶段 1: 运行配置一致性 ✅

- [x] 文档/脚本端口统一为 `8000`
- [x] 前端 WS/代理配置一致
- [x] `.env.example` 仅保留 API/WS 配置

## 阶段 2: 数据与机会管线 🔄

- [ ] 行情写入 Redis 与指标验证
- [ ] 三角/期现机会输出验证
- [ ] 决策服务约束链路验证
- [ ] metrics/monitoring 指标核对

## 阶段 3: OMS 执行闭环 🔄

- [ ] 执行计划创建与状态回写
- [ ] 订单/成交/PNL 表闭环验证
- [ ] 对账/取消/刷新接口健壮性验证
- [ ] WS 订单推送字段规范化

## 阶段 4: 风控闭环 🔄

- [ ] RiskManager 连接器实现完备
- [ ] 风控阈值/规则可配置化
- [ ] panic/reset/reload_keys 端到端验证

## 阶段 5: Rust 引擎完善 🔄

- [ ] executor 真实下单与回报处理
- [ ] risk 模块检查逻辑补齐
- [ ] 与 Python/Redis 联调验证

## 阶段 6: 测试与文档 🔄

- [ ] 集成测试与回归测试补齐
- [ ] 前端关键路径 E2E
- [ ] walkthrough 文档复核

---

## 执行说明

1. 优先完成阶段 2/3 的核心链路验证
2. 然后补齐阶段 4/5 的风控与引擎 TODO
3. 最后完善测试与文档
