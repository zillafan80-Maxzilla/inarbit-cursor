-- Inarbit 数据库架构优化 V2 (修正版)
-- 修复逻辑缺陷，完善数据关联
-- 此脚本是幂等的，可以安全地重复执行

-- ============================================
-- 步骤1: 添加交易模式字段（区分模拟/实盘）
-- ============================================

DO $$ 
BEGIN
    -- 订单历史添加交易模式
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='order_history' AND column_name='trading_mode'
    ) THEN
        ALTER TABLE order_history 
        ADD COLUMN trading_mode VARCHAR(20) DEFAULT 'paper' 
        CHECK (trading_mode IN ('paper', 'live'));
        
        RAISE NOTICE '✓ 已添加 order_history.trading_mode 字段';
    ELSE
        RAISE NOTICE '○ order_history.trading_mode 字段已存在';
    END IF;

    -- 收益记录添加交易模式
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='pnl_records' AND column_name='trading_mode'
    ) THEN
        ALTER TABLE pnl_records 
        ADD COLUMN trading_mode VARCHAR(20) DEFAULT 'paper' 
        CHECK (trading_mode IN ('paper', 'live'));
        
        RAISE NOTICE '✓ 已添加 pnl_records.trading_mode 字段';
    ELSE
        RAISE NOTICE '○ pnl_records.trading_mode 字段已存在';
    END IF;
END $$;

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_order_history_trading_mode ON order_history(trading_mode);
CREATE INDEX IF NOT EXISTS idx_pnl_records_trading_mode ON pnl_records(trading_mode);


-- ============================================
-- 步骤2: 创建交易所-交易对关联表
-- ============================================

CREATE TABLE IF NOT EXISTS exchange_trading_pairs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange_config_id UUID NOT NULL REFERENCES exchange_configs(id) ON DELETE CASCADE,
    trading_pair_id UUID NOT NULL REFERENCES trading_pairs(id) ON DELETE CASCADE,
    
    -- 启用状态
    is_enabled BOOLEAN DEFAULT true,
    
    -- 该交易对在此交易所的特定配置
    min_order_amount DECIMAL(20, 8),
    max_order_amount DECIMAL(20, 8),
    price_precision INT DEFAULT 8,
    amount_precision INT DEFAULT 8,
    
    -- 手续费配置（可能不同交易所不同）
    maker_fee DECIMAL(10, 6) DEFAULT 0.001,
    taker_fee DECIMAL(10, 6) DEFAULT 0.001,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 唯一约束
    UNIQUE(exchange_config_id, trading_pair_id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_exchange_pairs_exchange ON exchange_trading_pairs(exchange_config_id);
CREATE INDEX IF NOT EXISTS idx_exchange_pairs_pair ON exchange_trading_pairs(trading_pair_id);
CREATE INDEX IF NOT EXISTS idx_exchange_pairs_enabled ON exchange_trading_pairs(is_enabled) WHERE is_enabled = true;


-- ============================================
-- 步骤3: 创建策略-交易对关联表
-- ============================================

CREATE TABLE IF NOT EXISTS strategy_pairs (
    strategy_id UUID NOT NULL REFERENCES strategy_configs(id) ON DELETE CASCADE,
    trading_pair_id UUID NOT NULL REFERENCES trading_pairs(id) ON DELETE CASCADE,
    
    -- 该交易对在策略中的权重
    weight DECIMAL(5, 2) DEFAULT 1.0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (strategy_id, trading_pair_id)
);

CREATE INDEX IF NOT EXISTS idx_strategy_pairs_strategy ON strategy_pairs(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_pairs_pair ON strategy_pairs(trading_pair_id);


-- ============================================
-- 步骤4: 添加软删除字段
-- ============================================

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='exchange_configs' AND column_name='deleted_at'
    ) THEN
        ALTER TABLE exchange_configs 
        ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
        
        RAISE NOTICE '✓ 已添加 exchange_configs.deleted_at 字段';
    ELSE
        RAISE NOTICE '○ exchange_configs.deleted_at 字段已存在';
    END IF;
END $$;


-- ============================================
-- 步骤5: 创建删除日志表
-- ============================================

CREATE TABLE IF NOT EXISTS deletion_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    deletion_type VARCHAR(20) NOT NULL,
    deleted_by UUID REFERENCES users(id),
    metadata JSONB,
    deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deletion_logs_entity ON deletion_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_deletion_logs_time ON deletion_logs(deleted_at DESC);


-- ============================================
-- 步骤6: 创建便捷视图
-- ============================================

-- 活跃交易所的交易对视图
CREATE OR REPLACE VIEW v_active_exchange_pairs AS
SELECT 
    ec.id as exchange_id,
    ec.exchange_id as exchange_name,
    tp.id as pair_id,
    tp.symbol,
    tp.base_currency,
    tp.quote_currency,
    etp.is_enabled,
    etp.min_order_amount,
    etp.max_order_amount,
    etp.maker_fee,
    etp.taker_fee
FROM exchange_configs ec
JOIN exchange_trading_pairs etp ON ec.id = etp.exchange_config_id
JOIN trading_pairs tp ON etp.trading_pair_id = tp.id
WHERE ec.is_active = true 
  AND (ec.deleted_at IS NULL OR ec.deleted_at > NOW())
  AND etp.is_enabled = true
  AND tp.is_active = true;


-- 策略详情视图
CREATE OR REPLACE VIEW v_strategy_details AS
SELECT 
    sc.id as strategy_id,
    sc.strategy_type,
    sc.name as strategy_name,
    sc.is_enabled as strategy_enabled,
    array_remove(array_agg(DISTINCT ec.exchange_id), NULL) as exchanges,
    array_remove(array_agg(DISTINCT tp.symbol), NULL) as trading_pairs,
    sc.total_trades,
    sc.total_profit,
    sc.last_run_at
FROM strategy_configs sc
LEFT JOIN strategy_exchanges se ON sc.id = se.strategy_id
LEFT JOIN exchange_configs ec ON se.exchange_config_id = ec.id
LEFT JOIN strategy_pairs sp ON sc.id = sp.strategy_id
LEFT JOIN trading_pairs tp ON sp.trading_pair_id = tp.id
GROUP BY sc.id, sc.strategy_type, sc.name, sc.is_enabled, 
         sc.total_trades, sc.total_profit, sc.last_run_at;


-- ============================================
-- 步骤7: 更新触发器
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_exchange_trading_pairs_updated_at ON exchange_trading_pairs;
CREATE TRIGGER trigger_exchange_trading_pairs_updated_at
    BEFORE UPDATE ON exchange_trading_pairs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================
-- 步骤8: 数据迁移
-- ============================================

DO $$
DECLARE
    v_exchange_id UUID;
    v_pair_id UUID;
    v_migrated_count INT := 0;
BEGIN
    -- 为每个现有交易所添加常见交易对
    FOR v_exchange_id IN 
        SELECT id FROM exchange_configs WHERE is_active = true
    LOOP
        FOR v_pair_id IN 
            SELECT id FROM trading_pairs 
            WHERE symbol IN ('BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT')
              AND is_active = true
        LOOP
            INSERT INTO exchange_trading_pairs (
                exchange_config_id, 
                trading_pair_id, 
                is_enabled,
                min_order_amount,
                maker_fee,
                taker_fee
            )
            VALUES (
                v_exchange_id, 
                v_pair_id, 
                true,
                0.00001,
                0.001,
                0.001
            )
            ON CONFLICT (exchange_config_id, trading_pair_id) DO NOTHING;
            
            v_migrated_count := v_migrated_count + 1;
        END LOOP;
    END LOOP;
    
    IF v_migrated_count > 0 THEN
        RAISE NOTICE '✓ 已迁移 % 条交易所-交易对关联', v_migrated_count;
    ELSE
        RAISE NOTICE '○ 无需迁移交易所-交易对关联';
    END IF;
END $$;


-- ============================================
-- 完成提示
-- ============================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '============================================';
    RAISE NOTICE '✅ 数据库架构优化 V2 完成！';
    RAISE NOTICE '============================================';
    RAISE NOTICE '';
    RAISE NOTICE '新增内容：';
    RAISE NOTICE '  ✓ order_history.trading_mode 字段';
    RAISE NOTICE '  ✓ pnl_records.trading_mode 字段';
    RAISE NOTICE '  ✓ exchange_trading_pairs 表';
    RAISE NOTICE '  ✓ strategy_pairs 表';
    RAISE NOTICE '  ✓ deletion_logs 表';
    RAISE NOTICE '  ✓ exchange_configs.deleted_at 字段';
    RAISE NOTICE '  ✓ v_active_exchange_pairs 视图';
    RAISE NOTICE '  ✓ v_strategy_details 视图';
    RAISE NOTICE '';
    RAISE NOTICE '优化功能：';
    RAISE NOTICE '  ✓ 模拟盘/实盘数据隔离';
    RAISE NOTICE '  ✓ 交易所-交易对正确关联';
    RAISE NOTICE '  ✓ 策略-交易对精细配置';
    RAISE NOTICE '  ✓ 软删除支持（保留历史）';
    RAISE NOTICE '  ✓ 删除操作审计日志';
    RAISE NOTICE '';
    RAISE NOTICE '============================================';
END $$;
