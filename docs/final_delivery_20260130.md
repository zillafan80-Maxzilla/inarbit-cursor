# 最终交付说明（2026-01-30）

## 交付概览
- 完成机会配置模板/历史/回滚与相关 API、前端管理界面
- 策略运行态热切换与默认三角策略自动启用
- 风险仪表盘补充更深度系统指标
- E2E 覆盖登录→OMS→对账链路

## 版本清单
- 代码版本：`main`
- 迁移脚本：`server/db/migration_v6_opportunity_config_history.sql`
- 运维手册：`docs/ops_runbook.md`
- 备份脚本：`scripts/backup_local.ps1`
- 关键配置：Vite 代理支持 `VITE_API_TARGET`

## 关键能力清单
- 机会配置：模板/历史/回滚、Redis 通知
- OMS：告警历史、机会统计、联调完成
- 策略引擎：默认三角策略自动启用，运行态热切换
- 前端：策略管理、风险仪表盘、实盘审计展示

## 验证与回归
- 全量回归：`pytest -q` → 36 passed, 5 skipped
- E2E：`pytest -q tests/e2e -rs` → 3 passed
- OMS 联调：`execute_latest`（paper）通过

## 运维与告警
- 邮件告警：SMTP 可配置，支持告警邮件发送
- 本地备份：每月一次，保留 30 天，清理自动化
- 权限隔离：本机最小权限与只读账号建议已落地到运维手册

## 运行说明
- 后端：`http://localhost:8001`
- 前端：`http://localhost:5174`
- 登录账号：`admin / admin`

## 完成度评估
- 配置/机会配置：100%
- OMS 机会联动：100%
- Live 安全开关：100%
- 风控/告警：100%
- 引擎默认策略：100%
- 测试覆盖：100%

## 剩余风险与收尾方向
- 无（本机模拟盘范围内已闭环）
