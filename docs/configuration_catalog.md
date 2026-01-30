# 配置目录（Configuration Catalog）

本文件汇总系统中主要配置项与用途，作为运维与管理参考。

## 1) 环境变量（后端/引擎）

- `POSTGRES_HOST`/`POSTGRES_PORT`/`POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`：数据库连接
- `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD`/`REDIS_DB`：Redis 连接
- `ENGINE_MODE`：引擎模式，`simulation` 或 `live`
- `ENGINE_EXECUTE_SIGNALS`：是否执行信号（`true/1` 开启）
- `ENGINE_LIVE_CONFIRM`：实盘安全确认，需设置为 `CONFIRM_LIVE`
- `EXCHANGE_API_KEY_SECRET`：交易所密钥加密秘钥（建议替换默认值）
- `INARBIT_ENABLE_LIVE_OMS`：是否允许 OMS 实盘执行

## 2) 全局配置（DB）

表：`global_settings`  
用途：交易模式、默认策略、风控等级、最大损失与仓位限制等。

## 3) 交易所与交易对配置（DB）

表：`exchange_configs`、`exchange_status`、`trading_pairs`

- `exchange_configs`：用户交易所密钥配置（加密存储）
- `exchange_status`：交易所启用状态与UI展示信息
- `trading_pairs`：交易对启用与精度、最小量等参数

## 4) 策略配置（DB）

表：`strategy_configs`  
用途：策略启停、优先级、资金比例、策略参数（JSONB）。

## 5) 机会配置（DB + Redis）

表：`opportunity_configs`  
Redis：`config:opportunity:{user_id}:{strategy_type}`

策略类型：`graph` / `grid` / `pair`

示例（Graph）：
```json
{
  "min_profit_rate": 0.002,
  "max_path_length": 5
}
```

示例（Grid）：
```json
{
  "grids": [
    {
      "symbol": "BTC/USDT",
      "upper_price": 80000,
      "lower_price": 60000,
      "grid_count": 20
    }
  ]
}
```

示例（Pair）：
```json
{
  "pairs": [
    ["BTC/USDT", "ETH/USDT"],
    ["SOL/USDT", "AVAX/USDT"]
  ],
  "window_size": 100,
  "zscore_threshold": 2.0
}
```
