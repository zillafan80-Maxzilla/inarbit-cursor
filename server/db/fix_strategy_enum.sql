-- 修复策略类型枚举和表结构
-- ============================================

-- 1. 添加新的策略类型到 enum (如果是enum类型的话)
-- 首先检查 strategy_type 列的类型
DO $$
BEGIN
    -- 尝试添加新值到enum
    BEGIN
        ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'short_leverage';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'short_leverage value already exists or not an enum';
    END;
    
    BEGIN
        ALTER TYPE strategy_type ADD VALUE IF NOT EXISTS 'trend_following';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'trend_following value already exists or not an enum';
    END;
END $$;

-- 2. 如果 strategy_type 是 varchar，直接插入即可
-- 如果上面的enum添加失败，说明可能是varchar类型，继续执行

-- 3. 添加 max_leverage 列到 global_settings (如果不存在)
ALTER TABLE global_settings ADD COLUMN IF NOT EXISTS max_leverage INTEGER DEFAULT 4;

-- 4. 更新三角套利策略配置（使用OKX真实手续费）
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

-- 5. 更新其他已存在的策略
UPDATE strategy_configs 
SET config = '{
    "min_funding_rate": 0.0001,
    "position_mode": "hedge",
    "leverage": 2,
    "max_leverage": 4,
    "rebalance_threshold": 0.03,
    "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    "taker_fee": 0.001,
    "stop_loss_rate": 0.05,
    "take_profit_rate": 0.02
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'funding_rate';

UPDATE strategy_configs 
SET config = '{
    "symbol": "BTC/USDT",
    "upper_price": 110000,
    "lower_price": 85000,
    "grid_count": 20,
    "amount_per_grid": 50,
    "taker_fee": 0.001,
    "leverage": 1
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'grid';

UPDATE strategy_configs 
SET config = '{
    "pair_a": "BTC/USDT",
    "pair_b": "ETH/USDT",
    "lookback_period": 100,
    "entry_z_score": 2.0,
    "exit_z_score": 0.5,
    "taker_fee": 0.001,
    "leverage": 2,
    "max_leverage": 4
}'::jsonb,
    is_enabled = true,
    updated_at = NOW()
WHERE strategy_type = 'pair';

-- 6. 更新全局设置
UPDATE global_settings SET
    trading_mode = 'paper',
    bot_status = 'running',
    updated_at = NOW();

-- 7. 启用所有交易对
UPDATE trading_pairs SET is_active = true;

-- 8. 启用OKX交易所
UPDATE exchange_configs SET is_active = true WHERE exchange_id = 'okx';

-- 9. 清空并重建Redis统计缓存 (通过重启服务实现)

-- 10. 显示最终配置
SELECT 
    strategy_type, 
    name, 
    is_enabled,
    config->>'leverage' as leverage,
    config->>'max_leverage' as max_leverage,
    config->>'taker_fee' as taker_fee
FROM strategy_configs 
WHERE is_enabled = true
ORDER BY priority;
