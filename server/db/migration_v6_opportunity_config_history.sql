-- Opportunity config history + templates
CREATE TABLE IF NOT EXISTS opportunity_config_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_type strategy_type NOT NULL,
    version INT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opportunity_config_history_user ON opportunity_config_history(user_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_config_history_type ON opportunity_config_history(strategy_type);

CREATE TABLE IF NOT EXISTS opportunity_config_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_type strategy_type NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (strategy_type, name)
);

CREATE INDEX IF NOT EXISTS idx_opportunity_config_templates_type ON opportunity_config_templates(strategy_type);

-- Seed basic templates for admin
INSERT INTO opportunity_config_templates (strategy_type, name, description, config, created_by)
SELECT 'graph', '默认图搜索', '基础图搜索配置', '{"min_profit_rate": 0.002, "max_path_length": 5}'::jsonb, id
FROM users WHERE username = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO opportunity_config_templates (strategy_type, name, description, config, created_by)
SELECT 'grid', '默认网格', '空网格模板', '{"grids": []}'::jsonb, id
FROM users WHERE username = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO opportunity_config_templates (strategy_type, name, description, config, created_by)
SELECT 'pair', '默认配对', '基础配对配置', '{"pair_a": "BTC/USDT", "pair_b": "ETH/USDT", "entry_z_score": 2.0, "exit_z_score": 0.5, "lookback_period": 100}'::jsonb, id
FROM users WHERE username = 'admin'
ON CONFLICT DO NOTHING;
