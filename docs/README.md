# Inarbit 项目文档

本目录包含项目的设计和规划文档。

## 文档列表

- [implementation_plan.md](./implementation_plan.md) - 系统实施计划
- [walkthrough.md](./walkthrough.md) - 端到端验证步骤

## 快速指标查看

- 默认后端端口: `8000`
- 系统指标: /api/v1/system/metrics
- 风控状态: /api/v1/risk/status

## 实时通道

- 订单更新: WebSocket `/ws/orders`（服务端发布 `order:{user_id}:{status}`）
- 开启详情: 环境变量 `OMS_PUBLISH_ORDER_DETAIL=1`
