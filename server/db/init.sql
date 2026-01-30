-- Inarbit 数据库初始化脚本
-- PostgreSQL Schema for HFT Trading System

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- 用户管理
-- ============================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 默认管理员用户 (密码: admin123)
INSERT INTO users (username, password_hash, email) VALUES 
('admin', crypt('admin123', gen_salt('bf')), 'admin@inarbit.local');

-- ============================================
-- 模拟盘配置
-- ============================================
CREATE TABLE simulation_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    initial_capital DECIMAL(20, 8) DEFAULT 1000.00,
    quote_currency VARCHAR(20) DEFAULT 'USDT',
    current_balance DECIMAL(20, 8) DEFAULT 1000.00,
    realized_pnl DECIMAL(20, 8) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
    total_trades INT DEFAULT 0,
    win_rate DECIMAL(5, 4) DEFAULT 0,
    reset_on_start BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 默认模拟配置
INSERT INTO simulation_config (user_id, initial_capital, current_balance, realized_pnl)
SELECT id, 1000.00, 1012.54, 12.54 FROM users WHERE username = 'admin';

-- ============================================
-- 全局设置
-- ============================================
CREATE TABLE global_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    trading_mode VARCHAR(20) DEFAULT 'paper',  -- paper, live
    bot_status VARCHAR(20) DEFAULT 'stopped',  -- running, stopped
    default_strategy VARCHAR(50) DEFAULT 'triangular',
    risk_level VARCHAR(20) DEFAULT 'medium',  -- low, medium, high
    max_daily_loss DECIMAL(20, 8) DEFAULT 500.00,
    max_position_size DECIMAL(20, 8) DEFAULT 10000.00,
    enable_notifications BOOLEAN DEFAULT true,
    notification_email VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 默认全局设置
INSERT INTO global_settings (user_id, trading_mode, default_strategy)
SELECT id, 'paper', 'triangular' FROM users WHERE username = 'admin';

-- ============================================
-- 交易所配置
-- ============================================
CREATE TABLE exchange_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,  -- binance, okx, bybit, gate, bitget, mexc
    display_name VARCHAR(100),
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT NOT NULL,
    passphrase_encrypted TEXT,  -- OKX/KuCoin 需要
    is_spot_enabled BOOLEAN DEFAULT true,
    is_futures_enabled BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    extra_config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, exchange_id)
);


-- 创建索引
CREATE INDEX idx_exchange_configs_user ON exchange_configs(user_id);
CREATE INDEX idx_exchange_configs_active ON exchange_configs(is_active) WHERE is_active = true;

-- ============================================
-- 交易所状态（统一配置）
-- ============================================
CREATE TABLE exchange_status (
    exchange_id VARCHAR(50) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    icon VARCHAR(10) DEFAULT '🔵',
    bg_color VARCHAR(50) DEFAULT 'rgba(0,0,0,0.1)',
    border_color VARCHAR(20) DEFAULT '#666666',
    is_connected BOOLEAN DEFAULT false,
    is_spot_enabled BOOLEAN DEFAULT true,
    is_futures_enabled BOOLEAN DEFAULT false,
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 默认交易所配置
INSERT INTO exchange_status (exchange_id, display_name, icon, bg_color, border_color) VALUES
('binance', 'Binance', '🟡', 'rgba(181, 137, 0, 0.12)', '#b58900'),
('okx', 'OKX', '⚪', 'rgba(131, 148, 150, 0.12)', '#839496'),
('bybit', 'Bybit', '🟠', 'rgba(203, 75, 22, 0.10)', '#cb4b16'),
('gate', 'Gate.io', '🔵', 'rgba(38, 139, 210, 0.10)', '#268bd2'),
('bitget', 'Bitget', '🟢', 'rgba(133, 153, 0, 0.10)', '#859900');

-- ============================================
-- 交易对配置（统一管理）
-- ============================================
CREATE TABLE trading_pairs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(30) NOT NULL UNIQUE,
    base_currency VARCHAR(20) NOT NULL,
    quote_currency VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    supported_exchanges TEXT[] DEFAULT '{}',
    min_trade_amount DECIMAL(20, 8) DEFAULT 0,
    price_precision INT DEFAULT 8,
    amount_precision INT DEFAULT 8,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_trading_pairs_active ON trading_pairs(is_active) WHERE is_active = true;
CREATE INDEX idx_trading_pairs_base ON trading_pairs(base_currency);
CREATE INDEX idx_trading_pairs_quote ON trading_pairs(quote_currency);

-- 默认交易对配置
INSERT INTO trading_pairs (symbol, base_currency, quote_currency, supported_exchanges) VALUES
('BTC/USDT', 'BTC', 'USDT', ARRAY['binance', 'okx', 'bybit', 'gate']),
('ETH/USDT', 'ETH', 'USDT', ARRAY['binance', 'okx', 'bybit', 'gate']),
('BNB/USDT', 'BNB', 'USDT', ARRAY['binance']),
('SOL/USDT', 'SOL', 'USDT', ARRAY['binance', 'okx', 'bybit']),
('XRP/USDT', 'XRP', 'USDT', ARRAY['binance', 'okx', 'bybit', 'gate']),
('DOGE/USDT', 'DOGE', 'USDT', ARRAY['binance', 'okx']),
('ADA/USDT', 'ADA', 'USDT', ARRAY['binance', 'okx', 'bybit']),
('MATIC/USDT', 'MATIC', 'USDT', ARRAY['binance', 'okx']),
('AVAX/USDT', 'AVAX', 'USDT', ARRAY['binance', 'okx', 'bybit']),
('LINK/USDT', 'LINK', 'USDT', ARRAY['binance', 'okx', 'bybit', 'gate']);


-- ============================================
-- 策略配置
-- ============================================
CREATE TYPE strategy_type AS ENUM (
    'triangular',      -- 三角套利
    'graph',           -- 图搜索套利
    'funding_rate',    -- 期现套利
    'grid',            -- 网格交易
    'pair'             -- 配对交易
);

CREATE TABLE strategy_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_type strategy_type NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT false,
    priority INT DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    
    -- 资金分配
    capital_percent DECIMAL(5, 2) DEFAULT 20.00 CHECK (capital_percent >= 0 AND capital_percent <= 100),
    per_trade_limit DECIMAL(20, 8) DEFAULT 100.00,
    
    -- 策略参数 (JSON 格式，不同策略有不同参数)
    config JSONB NOT NULL DEFAULT '{}',
    
    -- 运行统计
    total_trades INT DEFAULT 0,
    total_profit DECIMAL(20, 8) DEFAULT 0,
    last_run_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_strategy_configs_user ON strategy_configs(user_id);
CREATE INDEX idx_strategy_configs_enabled ON strategy_configs(is_enabled) WHERE is_enabled = true;
CREATE INDEX idx_strategy_configs_type ON strategy_configs(strategy_type);

-- 策略-交易所关联 (多对多)
CREATE TABLE strategy_exchanges (
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE CASCADE,
    exchange_config_id UUID REFERENCES exchange_configs(id) ON DELETE CASCADE,
    PRIMARY KEY (strategy_id, exchange_config_id)
);

-- ============================================
-- 默认策略配置模板
-- ============================================
-- 注意：这些是模板，实际运行时需要用户配置交易所

-- 三角套利默认配置
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config) 
SELECT id, 'triangular', '三角套利', '同交易所内三个交易对的价格差套利', 1, 
'{
    "min_profit_rate": 0.001,
    "max_slippage": 0.0005,
    "base_currencies": ["USDT", "BTC", "ETH"],
    "scan_interval_ms": 100
}'::jsonb
FROM users WHERE username = 'admin';

-- 图搜索套利默认配置
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config) 
SELECT id, 'graph', '图搜索套利', 'Bellman-Ford 算法寻找 N 跳套利路径', 2, 
'{
    "min_profit_rate": 0.002,
    "max_path_length": 5,
    "start_currencies": ["USDT"],
    "scan_interval_ms": 500
}'::jsonb
FROM users WHERE username = 'admin';

-- 期现套利默认配置
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config) 
SELECT id, 'funding_rate', '期现套利', '多现货+空永续合约，赚取资金费率', 3, 
'{
    "min_funding_rate": 0.0001,
    "position_mode": "hedge",
    "leverage": 1,
    "rebalance_threshold": 0.05,
    "symbols": ["BTC/USDT", "ETH/USDT"]
}'::jsonb
FROM users WHERE username = 'admin';

-- 网格交易默认配置
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config) 
SELECT id, 'grid', '网格交易', '区间内高抛低吸', 5, 
'{
    "symbol": "BTC/USDT",
    "upper_price": 50000,
    "lower_price": 40000,
    "grid_count": 10,
    "amount_per_grid": 100
}'::jsonb
FROM users WHERE username = 'admin';

-- 配对交易默认配置
INSERT INTO strategy_configs (user_id, strategy_type, name, description, priority, config) 
SELECT id, 'pair', '配对交易', '相关币种价差回归套利', 4, 
'{
    "pair_a": "BTC/USDT",
    "pair_b": "ETH/USDT",
    "lookback_period": 100,
    "entry_z_score": 2.0,
    "exit_z_score": 0.5
}'::jsonb
FROM users WHERE username = 'admin';

-- ============================================
-- 订单历史
-- ============================================
CREATE TABLE order_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    exchange_order_id VARCHAR(100),
    symbol VARCHAR(30) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- buy, sell
    order_type VARCHAR(20) NOT NULL,  -- market, limit
    amount DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    filled_amount DECIMAL(20, 8) DEFAULT 0,
    avg_fill_price DECIMAL(20, 8),
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(20),
    status VARCHAR(20) NOT NULL,  -- pending, filled, cancelled, failed
    error_message TEXT,
    latency_ms INT,  -- 执行延迟毫秒
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    filled_at TIMESTAMP WITH TIME ZONE
);

-- 创建索引
CREATE INDEX idx_order_history_strategy ON order_history(strategy_id);
CREATE INDEX idx_order_history_exchange ON order_history(exchange_id);
CREATE INDEX idx_order_history_created ON order_history(created_at DESC);

-- ============================================
-- 盈亏记录
-- ============================================
CREATE TABLE pnl_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategy_configs(id) ON DELETE SET NULL,
    strategy_type strategy_type,
    exchange_id VARCHAR(50),
    path TEXT,  -- 套利路径描述
    gross_profit DECIMAL(20, 8) NOT NULL,
    fees DECIMAL(20, 8) DEFAULT 0,
    net_profit DECIMAL(20, 8) NOT NULL,
    profit_rate DECIMAL(10, 6),
    execution_time_ms INT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_pnl_records_strategy ON pnl_records(strategy_id);
CREATE INDEX idx_pnl_records_type ON pnl_records(strategy_type);
CREATE INDEX idx_pnl_records_date ON pnl_records(executed_at DESC);

-- ============================================
-- 系统日志
-- ============================================
CREATE TABLE system_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    level VARCHAR(10) NOT NULL,  -- DEBUG, INFO, WARN, ERROR
    source VARCHAR(50),  -- engine, strategy, exchange
    message TEXT NOT NULL,
    extra JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_system_logs_level ON system_logs(level);
CREATE INDEX idx_system_logs_user ON system_logs(user_id);
CREATE INDEX idx_system_logs_created ON system_logs(created_at DESC);

-- 自动清理 30 天前的日志
CREATE OR REPLACE FUNCTION cleanup_old_logs() RETURNS void AS $$
BEGIN
    DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 更新时间戳触发器
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_exchange_configs_updated_at
    BEFORE UPDATE ON exchange_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_strategy_configs_updated_at
    BEFORE UPDATE ON strategy_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- 完成提示
-- ============================================
DO $$
BEGIN
    RAISE NOTICE 'Inarbit 数据库初始化完成!';
END $$;
