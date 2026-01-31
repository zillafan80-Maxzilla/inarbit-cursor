# 本地模拟盘运行与运维手册

## 1. 交易所 Key 配置位置

本机模拟盘使用 `server/.env`：

- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`
- `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_PASSPHRASE`
- `BYBIT_API_KEY` / `BYBIT_API_SECRET`

这些敏感信息不会提交到仓库（已在 `.gitignore` 中忽略）。

## 2. 模拟盘模式与安全开关

确保 `server/.env` 中为模拟盘：

- `ENGINE_MODE=simulation`
- `INARBIT_ENABLE_LIVE_OMS=0`
- `ENGINE_EXECUTE_SIGNALS=0`（建议本机演示保持关闭）

## 3. 邮件告警（SMTP）

在 `server/.env` 中配置：

```
EMAIL_ALERTS_ENABLED=1
ALERT_EMAIL_TO=479729980@qq.com
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=<你的邮箱账号>
SMTP_PASSWORD=<SMTP授权码>
SMTP_FROM=<发件人地址>
SMTP_TLS=1
SMTP_SSL=0
```

说明：
- QQ 邮箱通常需要使用“SMTP 授权码”，不是登录密码。
- `ALERT_EMAIL_TO` 支持多个收件人，用逗号分隔。

## 4. 本地备份（每月一次，保留 30 天）

脚本：`scripts/backup_local.ps1`

手动执行：

```
powershell -ExecutionPolicy Bypass -File scripts\backup_local.ps1 -RetentionDays 30
```

计划任务（每月 1 日 02:00）：

```
schtasks /create /tn "inarbit-backup" /sc monthly /d 1 /st 02:00 /tr "powershell -ExecutionPolicy Bypass -File C:\Users\周浩\.cursor\cursor-workspace\inarbit\scripts\backup_local.ps1 -RetentionDays 30" /ru SYSTEM
```

备份输出目录为仓库根目录下的 `backups/`，已加入 `.gitignore`。

## 5. 运行性能调优（可选）

以下环境变量可用于降低行情采集压力、减少延迟或提升稳定性：

- `MARKETDATA_MAX_TICKER_SYMBOLS`：spot ticker 拉取数量上限（默认 200）
- `MARKETDATA_MAX_ORDERBOOK_SYMBOLS`：orderbook 采样数量上限（默认 5）
- `MARKETDATA_MAX_FUTURES_SYMBOLS`：期货 ticker 拉取数量上限（默认 120）
- `MARKETDATA_MAX_FUNDING_SYMBOLS`：资金费率拉取数量上限（默认 80）
- `MARKETDATA_ORDERBOOK_LIMIT`：订单簿档位深度（默认 10）
- `MARKETDATA_FETCH_CONCURRENCY`：行情并发拉取并发度（默认 10）
- `DECISION_MAX_DATA_AGE_REFRESH_MS`：动态 `max_data_age_ms` 刷新周期（默认 5000）
- `DECISION_FUNDING_FAIL_OPEN`：资金费率异常时是否放行（默认 1；设为 0 可强制失败）

建议：
- 本机调试可降低 `MARKETDATA_MAX_TICKER_SYMBOLS` 与 `MARKETDATA_MAX_FUTURES_SYMBOLS`。
- 若 `metrics:market_data_service.last_loop_ms` 明显偏大，适当降低并发与拉取数量。

## 6. 权限隔离方案（本机）

建议最小化权限：

1. 运行服务使用普通账号（非管理员）。
2. 数据库为应用账号单独使用（`POSTGRES_USER`）。
3. 增加只读账号用于报表/审计：

```
CREATE ROLE inarbit_readonly WITH LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE inarbit TO inarbit_readonly;
GRANT USAGE ON SCHEMA public TO inarbit_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO inarbit_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO inarbit_readonly;
```

如需更强隔离（分库/分网段/容器隔离），建议在生产环境中通过独立用户与网络策略实现。
