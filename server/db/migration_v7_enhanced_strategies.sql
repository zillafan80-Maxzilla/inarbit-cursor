-- ============================================
-- 增强策略配置 - 波段套利 + 杠杆做空
-- OKX 真实手续费: maker 0.08%, taker 0.1%
-- ============================================

-- 1. 更新三角套利策略 - 使用OKX真实手续费
UPDATE strategy_configs 
SET config = '{
    "min_profit_rate": 0.0015,
    "max_slippage": 0.0003,
    "base_currencies": ["USDT", "BTC", "ETH"],
    "scan_interval_ms": 100,
    "taker_fee": 0.001,
    "maker_fee": 0.0008,
    "max_position_usdt": 500,
    "leverage": 1,
    "auto_execute": true
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'triangular';

-- 2. 更新期现套利策略 - 支持杠杆(最多4倍)
UPDATE strategy_configs 
SET config = '{
    "min_funding_rate": 0.0001,
    "position_mode": "hedge",
    "leverage": 2,
    "max_leverage": 4,
    "rebalance_threshold": 0.03,
    "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"],
    "taker_fee": 0.001,
    "maker_fee": 0.0008,
    "funding_fee": 0.0001,
    "max_position_usdt": 1000,
    "stop_loss_rate": 0.05,
    "take_profit_rate": 0.02,
    "auto_leverage_adjust": true
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'funding_rate';

-- 3. 更新网格策略 - 波段操作
UPDATE strategy_configs 
SET config = '{
    "symbol": "BTC/USDT",
    "upper_price": 110000,
    "lower_price": 85000,
    "grid_count": 20,
    "amount_per_grid": 50,
    "taker_fee": 0.001,
    "maker_fee": 0.0008,
    "leverage": 1,
    "trailing_stop": true,
    "trailing_stop_rate": 0.02,
    "auto_rebalance": true
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'grid';

-- 4. 更新配对交易策略
UPDATE strategy_configs 
SET config = '{
    "pair_a": "BTC/USDT",
    "pair_b": "ETH/USDT",
    "lookback_period": 100,
    "entry_z_score": 2.0,
    "exit_z_score": 0.5,
    "taker_fee": 0.001,
    "maker_fee": 0.0008,
    "max_position_usdt": 500,
    "correlation_threshold": 0.7
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'pair';

-- 5. 添加做空/杠杆策略 (新增)
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, is_enabled, config)
SELECT 
    id, 
    'short_leverage', 
    '做空杠杆策略', 
    '市场大跌时自动做空，支持最多4倍杠杆', 
    6,
    true,
    '{
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "market_drop_threshold": -0.03,
        "leverage": 2,
        "max_leverage": 4,
        "position_size_usdt": 200,
        "max_position_usdt": 800,
        "taker_fee": 0.001,
        "maker_fee": 0.0008,
        "stop_loss_rate": 0.03,
        "take_profit_rate": 0.05,
        "trailing_stop": true,
        "trailing_stop_rate": 0.02,
        "cooldown_minutes": 30,
        "volatility_threshold": 0.02,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "auto_close_on_reversal": true,
        "max_daily_trades": 10
    }'::jsonb
FROM users WHERE username = 'admin'
ON CONFLICT (user_id, strategy_type) DO UPDATE SET
    config = EXCLUDED.config,
    is_enabled = true,
    updated_at = NOW();

-- 6. 添加波段趋势策略 (新增)
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, is_enabled, config)
SELECT 
    id, 
    'trend_following', 
    '波段趋势策略', 
    '跟随市场趋势进行波段操作，支持双向交易', 
    7,
    true,
    '{
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"],
        "timeframe": "1h",
        "fast_ma_period": 12,
        "slow_ma_period": 26,
        "signal_period": 9,
        "leverage": 2,
        "max_leverage": 4,
        "position_size_usdt": 150,
        "max_position_usdt": 600,
        "taker_fee": 0.001,
        "maker_fee": 0.0008,
        "stop_loss_rate": 0.025,
        "take_profit_rate": 0.04,
        "trailing_stop": true,
        "trailing_stop_activation": 0.02,
        "trailing_stop_callback": 0.01,
        "volume_filter": true,
        "min_volume_usdt": 100000,
        "atr_multiplier": 1.5,
        "risk_per_trade": 0.02
    }'::jsonb
FROM users WHERE username = 'admin'
ON CONFLICT (user_id, strategy_type) DO UPDATE SET
    config = EXCLUDED.config,
    is_enabled = true,
    updated_at = NOW();

-- 7. 更新全局设置
UPDATE global_settings SET
    trading_mode = 'paper',
    bot_status = 'running',
    risk_level = 'medium',
    max_leverage = 4,
    updated_at = NOW();

-- 8. 确保交易对都是启用状态
UPDATE trading_pairs SET is_active = true;

-- 9. 确保OKX交易所是启用状态
UPDATE exchange_configs SET is_active = true WHERE exchange_id = 'okx';

-- 显示更新后的策略配置
SELECT strategy_type, name, is_enabled, 
       config->>'leverage' as leverage,
       config->>'max_leverage' as max_leverage,
       config->>'taker_fee' as taker_fee
FROM strategy_configs 
ORDER BY priority;
