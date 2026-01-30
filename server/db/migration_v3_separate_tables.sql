-- Inarbit 数据库架构升级 V3
-- 模拟盘/实盘数据完全分表隔离
-- 更安全、更清晰的数据管理

-- ============================================
-- 步骤1: 创建模拟盘订单表
-- ============================================

CREATE TABLE IF NOT EXISTS paper_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- 基本信息（与order_history相同结构）
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    
    -- 交易对信息
    symbol VARCHAR(30) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('market', 'limit', 'stop_loss', 'take_profit')),
    
    -- 数量和价格
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    average_price DECIMAL(20, 8),
    
    -- 订单状态
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'filled', 'partially_filled', 'cancelled', 'rejected')),
    
    -- 手续费
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(20),
    
    -- 外部订单ID
    external_order_id VARCHAR(100),
    
    -- 元数据
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    filled_at TIMESTAMP WITH TIME ZONE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_paper_orders_user ON paper_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_strategy ON paper_orders(strategy_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_exchange ON paper_orders(exchange_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status);
CREATE INDEX IF NOT EXISTS idx_paper_orders_created ON paper_orders(created_at DESC);

COMMENT ON TABLE paper_orders IS '模拟盘订单历史 - 仅包含模拟交易数据';


-- ============================================
-- 步骤2: 创建实盘订单表
-- ============================================

CREATE TABLE IF NOT EXISTS live_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- 与paper_orders结构完全相同
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    
    symbol VARCHAR(30) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('market', 'limit', 'stop_loss', 'take_profit')),
    
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    average_price DECIMAL(20, 8),
    
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'filled', 'partially_filled', 'cancelled', 'rejected')),
    
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(20),
    
    external_order_id VARCHAR(100),
    
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    filled_at TIMESTAMP WITH TIME ZONE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_live_orders_user ON live_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_strategy ON live_orders(strategy_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_exchange ON live_orders(exchange_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_symbol ON live_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_live_orders_status ON live_orders(status);
CREATE INDEX IF NOT EXISTS idx_live_orders_created ON live_orders(created_at DESC);

COMMENT ON TABLE live_orders IS '实盘订单历史 - 仅包含真实交易数据 ⚠️';


-- ============================================
-- 步骤3: 创建模拟盘收益表
-- ============================================

CREATE TABLE IF NOT EXISTS paper_pnl (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    
    -- 收益信息
    profit DECIMAL(20, 8) NOT NULL,
    profit_rate DECIMAL(10, 6),
    
    -- 交易信息
    entry_price DECIMAL(20, 8),
    exit_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8),
    
    -- 时间信息
    entry_time TIMESTAMP WITH TIME ZONE,
    exit_time TIMESTAMP WITH TIME ZONE,
    
    -- 元数据
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_paper_pnl_user ON paper_pnl(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_pnl_strategy ON paper_pnl(strategy_id);
CREATE INDEX IF NOT EXISTS idx_paper_pnl_exchange ON paper_pnl(exchange_id);
CREATE INDEX IF NOT EXISTS idx_paper_pnl_created ON paper_pnl(created_at DESC);

COMMENT ON TABLE paper_pnl IS '模拟盘收益记录 - 仅包含模拟交易盈亏';


-- ============================================
-- 步骤4: 创建实盘收益表
-- ============================================

CREATE TABLE IF NOT EXISTS live_pnl (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    
    profit DECIMAL(20, 8) NOT NULL,
    profit_rate DECIMAL(10, 6),
    
    entry_price DECIMAL(20, 8),
    exit_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8),
    
    entry_time TIMESTAMP WITH TIME ZONE,
    exit_time TIMESTAMP WITH TIME ZONE,
    
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_live_pnl_user ON live_pnl(user_id);
CREATE INDEX IF NOT EXISTS idx_live_pnl_strategy ON live_pnl(strategy_id);
CREATE INDEX IF NOT EXISTS idx_live_pnl_exchange ON live_pnl(exchange_id);
CREATE INDEX IF NOT EXISTS idx_live_pnl_created ON live_pnl(created_at DESC);

COMMENT ON TABLE live_pnl IS '实盘收益记录 - 仅包含真实交易盈亏 ⚠️';


-- ============================================
-- 步骤5: 数据迁移（从旧表迁移到新表）
-- ============================================

DO $$
DECLARE
    v_order_count INT := 0;
    v_pnl_count INT := 0;
    v_order_has_user_id BOOL := false;
    v_order_has_quantity BOOL := false;
    v_pnl_has_user_id BOOL := false;
    v_pnl_has_profit BOOL := false;
BEGIN
    -- 迁移模拟盘订单
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'order_history') THEN
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='order_history' AND column_name='user_id'
        ) INTO v_order_has_user_id;
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='order_history' AND column_name='quantity'
        ) INTO v_order_has_quantity;

        IF NOT (v_order_has_user_id AND v_order_has_quantity) THEN
            RAISE NOTICE '○ order_history 结构不兼容，跳过订单迁移';
        ELSE
        INSERT INTO paper_orders (
            id, user_id, strategy_id, exchange_id, symbol, side, order_type,
            quantity, price, filled_quantity, average_price, status,
            fee, fee_currency, external_order_id, metadata,
            created_at, updated_at, filled_at
        )
        SELECT 
            id, user_id, strategy_id, exchange_id, symbol, side, order_type,
            quantity, price, filled_quantity, average_price, status,
            fee, fee_currency, external_order_id, metadata,
            created_at, updated_at, filled_at
        FROM order_history
        WHERE trading_mode = 'paper' OR trading_mode IS NULL
        ON CONFLICT (id) DO NOTHING;
        
        GET DIAGNOSTICS v_order_count = ROW_COUNT;
        
        -- 迁移实盘订单
        INSERT INTO live_orders (
            id, user_id, strategy_id, exchange_id, symbol, side, order_type,
            quantity, price, filled_quantity, average_price, status,
            fee, fee_currency, external_order_id, metadata,
            created_at, updated_at, filled_at
        )
        SELECT 
            id, user_id, strategy_id, exchange_id, symbol, side, order_type,
            quantity, price, filled_quantity, average_price, status,
            fee, fee_currency, external_order_id, metadata,
            created_at, updated_at, filled_at
        FROM order_history
        WHERE trading_mode = 'live'
        ON CONFLICT (id) DO NOTHING;
        
        RAISE NOTICE '✓ 已迁移 % 条订单记录', v_order_count;
        END IF;
    END IF;
    
    -- 迁移模拟盘收益
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pnl_records') THEN
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='pnl_records' AND column_name='user_id'
        ) INTO v_pnl_has_user_id;
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='pnl_records' AND column_name='profit'
        ) INTO v_pnl_has_profit;

        IF NOT (v_pnl_has_user_id AND v_pnl_has_profit) THEN
            RAISE NOTICE '○ pnl_records 结构不兼容，跳过收益迁移';
        ELSE
        INSERT INTO paper_pnl (
            id, user_id, strategy_id, exchange_id, symbol,
            profit, profit_rate, entry_price, exit_price, quantity,
            entry_time, exit_time, metadata, created_at
        )
        SELECT 
            id, user_id, strategy_id, exchange_id, symbol,
            profit, profit_rate, entry_price, exit_price, quantity,
            entry_time, exit_time, metadata, created_at
        FROM pnl_records
        WHERE trading_mode = 'paper' OR trading_mode IS NULL
        ON CONFLICT (id) DO NOTHING;
        
        GET DIAGNOSTICS v_pnl_count = ROW_COUNT;
        
        -- 迁移实盘收益
        INSERT INTO live_pnl (
            id, user_id, strategy_id, exchange_id, symbol,
            profit, profit_rate, entry_price, exit_price, quantity,
            entry_time, exit_time, metadata, created_at
        )
        SELECT 
            id, user_id, strategy_id, exchange_id, symbol,
            profit, profit_rate, entry_price, exit_price, quantity,
            entry_time, exit_time, metadata, created_at
        FROM pnl_records
        WHERE trading_mode = 'live'
        ON CONFLICT (id) DO NOTHING;
        
        RAISE NOTICE '✓ 已迁移 % 条收益记录', v_pnl_count;
        END IF;
    END IF;
END $$;


-- ============================================
-- 步骤6: 创建统一视图（向后兼容）
-- ============================================

-- 统一订单视图
CREATE OR REPLACE VIEW v_all_orders AS
SELECT 
    id, user_id, strategy_id, exchange_id, symbol, side, order_type,
    quantity, price, filled_quantity, average_price, status,
    fee, fee_currency, external_order_id, metadata,
    created_at, updated_at, filled_at,
    'paper'::VARCHAR(20) as trading_mode
FROM paper_orders
UNION ALL
SELECT 
    id, user_id, strategy_id, exchange_id, symbol, side, order_type,
    quantity, price, filled_quantity, average_price, status,
    fee, fee_currency, external_order_id, metadata,
    created_at, updated_at, filled_at,
    'live'::VARCHAR(20) as trading_mode
FROM live_orders;

COMMENT ON VIEW v_all_orders IS '统一订单视图 - 用于向后兼容查询';


-- 统一收益视图
CREATE OR REPLACE VIEW v_all_pnl AS
SELECT 
    id, user_id, strategy_id, exchange_id, symbol,
    profit, profit_rate, entry_price, exit_price, quantity,
    entry_time, exit_time, metadata, created_at,
    'paper'::VARCHAR(20) as trading_mode
FROM paper_pnl
UNION ALL
SELECT 
    id, user_id, strategy_id, exchange_id, symbol,
    profit, profit_rate, entry_price, exit_price, quantity,
    entry_time, exit_time, metadata, created_at,
    'live'::VARCHAR(20) as trading_mode
FROM live_pnl;

COMMENT ON VIEW v_all_pnl IS '统一收益视图 - 用于向后兼容查询';


-- ============================================
-- 步骤7: 创建更新触发器
-- ============================================

-- paper_orders更新触发器
CREATE TRIGGER trigger_paper_orders_updated_at
    BEFORE UPDATE ON paper_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- live_orders更新触发器
CREATE TRIGGER trigger_live_orders_updated_at
    BEFORE UPDATE ON live_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ============================================
-- 步骤8: 标记旧表为deprecated
-- ============================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'order_history') THEN
        COMMENT ON TABLE order_history IS 'DEPRECATED: 使用 paper_orders 和 live_orders 代替。此表保留仅为向后兼容。';
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pnl_records') THEN
        COMMENT ON TABLE pnl_records IS 'DEPRECATED: 使用 paper_pnl 和 live_pnl 代替。此表保留仅为向后兼容。';
    END IF;
END $$;


-- ============================================
-- 步骤9: 创建便捷查询函数
-- ============================================

-- 获取模拟盘统计
CREATE OR REPLACE FUNCTION get_paper_stats(p_user_id UUID DEFAULT NULL)
RETURNS TABLE (
    total_orders BIGINT,
    total_profit NUMERIC,
    win_rate NUMERIC,
    avg_profit NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT po.id) as total_orders,
        COALESCE(SUM(pp.profit), 0) as total_profit,
        CASE 
            WHEN COUNT(pp.id) > 0 
            THEN ROUND(COUNT(CASE WHEN pp.profit > 0 THEN 1 END)::NUMERIC / COUNT(pp.id)::NUMERIC, 4)
            ELSE 0
        END as win_rate,
        COALESCE(AVG(pp.profit), 0) as avg_profit
    FROM paper_orders po
    LEFT JOIN paper_pnl pp ON po.user_id = pp.user_id
    WHERE (p_user_id IS NULL OR po.user_id = p_user_id);
END;
$$ LANGUAGE plpgsql;


-- 获取实盘统计
CREATE OR REPLACE FUNCTION get_live_stats(p_user_id UUID DEFAULT NULL)
RETURNS TABLE (
    total_orders BIGINT,
    total_profit NUMERIC,
    win_rate NUMERIC,
    avg_profit NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT lo.id) as total_orders,
        COALESCE(SUM(lp.profit), 0) as total_profit,
        CASE 
            WHEN COUNT(lp.id) > 0 
            THEN ROUND(COUNT(CASE WHEN lp.profit > 0 THEN 1 END)::NUMERIC / COUNT(lp.id)::NUMERIC, 4)
            ELSE 0
        END as win_rate,
        COALESCE(AVG(lp.profit), 0) as avg_profit
    FROM live_orders lo
    LEFT JOIN live_pnl lp ON lo.user_id = lp.user_id
    WHERE (p_user_id IS NULL OR lo.user_id = p_user_id);
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 完成提示
-- ============================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '============================================';
    RAISE NOTICE '✅ 数据库架构升级 V3 完成！';
    RAISE NOTICE '============================================';
    RAISE NOTICE '';
    RAISE NOTICE '新增表：';
    RAISE NOTICE '  ✓ paper_orders - 模拟盘订单';
    RAISE NOTICE '  ✓ live_orders - 实盘订单';
    RAISE NOTICE '  ✓ paper_pnl - 模拟盘收益';
    RAISE NOTICE '  ✓ live_pnl - 实盘收益';
    RAISE NOTICE '';
    RAISE NOTICE '新增视图：';
    RAISE NOTICE '  ✓ v_all_orders - 统一订单视图';
    RAISE NOTICE '  ✓ v_all_pnl - 统一收益视图';
    RAISE NOTICE '';
    RAISE NOTICE '新增函数：';
    RAISE NOTICE '  ✓ get_paper_stats() - 模拟盘统计';
    RAISE NOTICE '  ✓ get_live_stats() - 实盘统计';
    RAISE NOTICE '';
    RAISE NOTICE '✅ 模拟盘/实盘数据已完全隔离！';
    RAISE NOTICE '============================================';
END $$;
