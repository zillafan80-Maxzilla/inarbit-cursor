-- Opportunity configs persistence
-- Per-user strategy-level configuration for Graph/Grid/Pair

CREATE TABLE IF NOT EXISTS opportunity_configs (
 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
 user_id UUID REFERENCES users(id) ON DELETE CASCADE,
 strategy_type strategy_type NOT NULL,
 config JSONB NOT NULL DEFAULT '{}'::jsonb,
 version INT NOT NULL DEFAULT 1,
 is_active BOOLEAN NOT NULL DEFAULT true,
 created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
 updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
 UNIQUE (user_id, strategy_type)
);

CREATE INDEX IF NOT EXISTS idx_opportunity_configs_user ON opportunity_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_configs_strategy ON opportunity_configs(strategy_type);
CREATE INDEX IF NOT EXISTS idx_opportunity_configs_active ON opportunity_configs(is_active) WHERE is_active = true;

-- Seed defaults for admin user when absent
INSERT INTO opportunity_configs (user_id, strategy_type, config)
SELECT id, 'graph', '{"min_profit_rate": 0.002, "max_path_length": 5}'::jsonb
FROM users WHERE username = 'admin'
ON CONFLICT (user_id, strategy_type) DO NOTHING;

INSERT INTO opportunity_configs (user_id, strategy_type, config)
SELECT id, 'grid', '{"grids": []}'::jsonb
FROM users WHERE username = 'admin'
ON CONFLICT (user_id, strategy_type) DO NOTHING;

INSERT INTO opportunity_configs (user_id, strategy_type, config)
SELECT id, 'pair', '{"pairs": []}'::jsonb
FROM users WHERE username = 'admin'
ON CONFLICT (user_id, strategy_type) DO NOTHING;
