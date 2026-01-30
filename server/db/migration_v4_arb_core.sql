CREATE TABLE IF NOT EXISTS paper_fills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES paper_orders(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,
    account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp')),
    symbol VARCHAR(60) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(20),
    external_trade_id VARCHAR(120),
    external_order_id VARCHAR(120),
    raw JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_fills_user_created ON paper_fills(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_fills_order ON paper_fills(order_id);
CREATE INDEX IF NOT EXISTS idx_paper_fills_exchange_symbol ON paper_fills(exchange_id, symbol);
CREATE INDEX IF NOT EXISTS idx_paper_fills_external_trade_id ON paper_fills(external_trade_id);


CREATE TABLE IF NOT EXISTS live_fills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES live_orders(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,
    account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp')),
    symbol VARCHAR(60) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(20),
    external_trade_id VARCHAR(120),
    external_order_id VARCHAR(120),
    raw JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_fills_user_created ON live_fills(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_fills_order ON live_fills(order_id);
CREATE INDEX IF NOT EXISTS idx_live_fills_exchange_symbol ON live_fills(exchange_id, symbol);
CREATE INDEX IF NOT EXISTS idx_live_fills_external_trade_id ON live_fills(external_trade_id);


ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS client_order_id VARCHAR(120);
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp'));
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS plan_id UUID;
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS leg_id VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_orders_user_client_order_id
    ON paper_orders(user_id, client_order_id)
    WHERE client_order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_orders_plan_id ON paper_orders(plan_id);


ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS client_order_id VARCHAR(120);
ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp'));
ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS plan_id UUID;
ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS leg_id VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS uq_live_orders_user_client_order_id
    ON live_orders(user_id, client_order_id)
    WHERE client_order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_live_orders_plan_id ON live_orders(plan_id);


CREATE TABLE IF NOT EXISTS paper_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('triangle', 'basis', 'funding')),
    expected_pnl DECIMAL(20, 8),
    capacity DECIMAL(20, 8),
    ttl_ms INT NOT NULL DEFAULT 1000,
    score DECIMAL(20, 8),
    legs JSONB NOT NULL DEFAULT '[]'::jsonb,
    risks JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'accepted', 'rejected', 'expired', 'executed')),
    decision_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expired_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_paper_opportunities_user_created ON paper_opportunities(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_opportunities_user_status ON paper_opportunities(user_id, status);
CREATE INDEX IF NOT EXISTS idx_paper_opportunities_exchange_kind ON paper_opportunities(exchange_id, kind);


CREATE TABLE IF NOT EXISTS live_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('triangle', 'basis', 'funding')),
    expected_pnl DECIMAL(20, 8),
    capacity DECIMAL(20, 8),
    ttl_ms INT NOT NULL DEFAULT 1000,
    score DECIMAL(20, 8),
    legs JSONB NOT NULL DEFAULT '[]'::jsonb,
    risks JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'accepted', 'rejected', 'expired', 'executed')),
    decision_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expired_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_live_opportunities_user_created ON live_opportunities(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_opportunities_user_status ON live_opportunities(user_id, status);
CREATE INDEX IF NOT EXISTS idx_live_opportunities_exchange_kind ON live_opportunities(exchange_id, kind);


CREATE TABLE IF NOT EXISTS paper_execution_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES paper_opportunities(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('triangle', 'basis', 'funding')),
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'running', 'completed', 'failed', 'cancelled')),
    legs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_paper_execution_plans_user_created ON paper_execution_plans(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_execution_plans_user_status ON paper_execution_plans(user_id, status);
CREATE INDEX IF NOT EXISTS idx_paper_execution_plans_opportunity_id ON paper_execution_plans(opportunity_id);


CREATE TABLE IF NOT EXISTS live_execution_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES live_opportunities(id) ON DELETE SET NULL,
    exchange_id VARCHAR(50) NOT NULL,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('triangle', 'basis', 'funding')),
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'running', 'completed', 'failed', 'cancelled')),
    legs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_live_execution_plans_user_created ON live_execution_plans(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_execution_plans_user_status ON live_execution_plans(user_id, status);
CREATE INDEX IF NOT EXISTS idx_live_execution_plans_opportunity_id ON live_execution_plans(opportunity_id);


ALTER TABLE paper_orders
    ADD CONSTRAINT fk_paper_orders_plan_id
    FOREIGN KEY (plan_id) REFERENCES paper_execution_plans(id) ON DELETE SET NULL;

ALTER TABLE live_orders
    ADD CONSTRAINT fk_live_orders_plan_id
    FOREIGN KEY (plan_id) REFERENCES live_execution_plans(id) ON DELETE SET NULL;


CREATE TABLE IF NOT EXISTS paper_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,
    account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp')),
    instrument VARCHAR(80) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL DEFAULT 0,
    avg_price DECIMAL(20, 8),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, exchange_id, account_type, instrument)
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_user_exchange ON paper_positions(user_id, exchange_id);


CREATE TABLE IF NOT EXISTS live_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50) NOT NULL,
    account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp')),
    instrument VARCHAR(80) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL DEFAULT 0,
    avg_price DECIMAL(20, 8),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, exchange_id, account_type, instrument)
);

CREATE INDEX IF NOT EXISTS idx_live_positions_user_exchange ON live_positions(user_id, exchange_id);


CREATE TABLE IF NOT EXISTS paper_ledger_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50),
    account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp')),
    asset VARCHAR(30) NOT NULL,
    delta DECIMAL(20, 8) NOT NULL,
    ref_type VARCHAR(30) NOT NULL,
    ref_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_ledger_entries_user_created ON paper_ledger_entries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_ledger_entries_ref ON paper_ledger_entries(ref_type, ref_id);


CREATE TABLE IF NOT EXISTS live_ledger_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(50),
    account_type VARCHAR(10) NOT NULL DEFAULT 'spot' CHECK (account_type IN ('spot', 'perp')),
    asset VARCHAR(30) NOT NULL,
    delta DECIMAL(20, 8) NOT NULL,
    ref_type VARCHAR(30) NOT NULL,
    ref_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_ledger_entries_user_created ON live_ledger_entries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_ledger_entries_ref ON live_ledger_entries(ref_type, ref_id);
