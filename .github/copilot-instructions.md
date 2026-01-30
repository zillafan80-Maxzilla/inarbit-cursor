# Copilot Instructions for Inarbit HFT Trading System

## Architecture Overview

**Inarbit** is a high-frequency cryptocurrency arbitrage system with three major components:

- **Python API Layer** ([server/](server/)) - FastAPI backend with WebSocket real-time updates
- **Rust Engine** ([engine/](engine/)) - High-performance strategy execution and exchange connections  
- **React Frontend** ([client/](client/)) - Management UI for strategies and trading

Data flows: Rust engine → Market data → Python API → React UI. Database: PostgreSQL (persistent) + Redis (real-time cache).

## Critical Startup & Development

**Quick Start Sequence** (see [QUICKSTART.md](QUICKSTART.md)):
```bash
docker-compose up -d                    # PostgreSQL + Redis
cd server && pip install -r requirements.txt
cd .. && python test_system_init.py     # Initialize DB schema & admin user
uvicorn server.app:app --reload --port 8000
cd client && npm run dev                # Port 5173
# Access: http://localhost:5173 (user: admin/admin123)
```

**Key Insight**: Server startup in [server/app.py](server/app.py) lifespan uses `ServiceContainer` (singleton pattern) to initialize services in strict order: DB → Config → Opportunity Services (triangular + cashcarry) → Market Data → Decision Service. Services are background tasks that continuously scan for arbitrage opportunities and publish to Redis.

**Rust Engine**: Run `cd engine && cargo build --release` (slow first build). Engine connects to exchanges via WebSocket, executes strategies, and pushes logs to Redis.

## Service Architecture & Key Components

**ServiceContainer** ([server/services/__init__.py](server/services/__init__.py)): Dependency injection singleton. All services are lazy-loaded on first access. Available services:
- `get_triangular_opportunity_service()` - Finds 3-coin arbitrage (A→B→C→A paths)
- `get_cashcarry_opportunity_service()` - Spot + futures basis trading
- `get_market_data_service()` - Fetches real-time ticker/orderbook from exchanges
- `get_decision_service()` - Filters opportunities by risk constraints, selects top opportunities
- `get_order_service()` / `get_oms_service()` - Paper & live execution (OMS)

**Critical Pattern**: All services follow same lifecycle:
```python
async def start(self):     # Spawn background asyncio.Task
async def stop(self):      # Cancel task
async def _run(self):      # Main loop (scan → write to Redis/DB every 2 sec)
```

**Data Flow**: Opportunities live in Redis ([server/db/redis_schema.py](server/db/redis_schema.py)): `opportunities:{strategy_type}` (TTL 10s). Decision service polls Redis, applies risk filters, publishes selected decisions.

## Database Schema Key Points

PostgreSQL tables ([server/db/init.sql](server/db/init.sql)):
- `users` - Admin account, strategy configs
- `exchange_configs` - API keys (encrypted)
- `arbitrage_opportunities` - Detected opportunities (historical record)
- `execution_plans` - Planned trades with multi-leg structure (plan_id → legs)
- `orders` / `fills` - OMS tracking for paper & live modes

**OMS (Order Management)**: Paper mode simulates fills; live mode requires `INARBIT_ENABLE_LIVE_OMS=1` env var + Binance API key. Orders use client_order_id from plan/leg for idempotency.

## Project-Specific Patterns & Conventions

1. **Async/Await Everywhere**: Python uses `asyncpg` (async PostgreSQL) + `aiohttp`. Never use sync DB calls.

2. **Redis as Event Bus**: Services publish opportunities via Redis. Real-time updates pushed to WebSocket clients via `server/api/websocket.py`.

3. **Configuration as Code**: Strategy configs stored in PostgreSQL `strategy_configs.config` (JSONB) with fields like `min_profit_rate`, `max_slippage`, `scan_interval_ms`. Changes picked up by service on next cycle.

4. **Paper Mode Default**: System always runs in paper mode (simulated trading) unless live OMS explicitly enabled. Prevents accidental real trades.

5. **Error Tolerance**: Service startup failures logged as warnings (not fatal). Allows partial system operation even if one service fails.

6. **Single Exchange Focus**: Current implementation primarily supports Binance; other exchanges (OKX, Bybit, Gate.io) are enumerated but partially integrated.

## Integration Points & Cross-Component Communication

- **Frontend → Backend**: REST API in [server/api/routes.py](server/api/routes.py) + WebSocket in [server/api/websocket.py](server/api/websocket.py)
- **Backend → Redis**: Services publish opportunities/decisions; frontend polls via WebSocket subscriptions
- **Backend → Rust Engine**: Not directly coupled; Rust engine independently connects to exchanges, publishes logs to Redis
- **Config Changes**: Update `strategy_configs` in DB → service reads on next loop tick (no restart required)

## Testing & Validation

- `quick_test.py` - Validates imports, database connectivity (run before full init)
- `test_system_init.py` - Interactive setup: resets DB, creates admin, tests Binance connectivity, runs strategy validation
- Rust engine compile: Check [engine/src/](engine/src/) for errors; watch `cargo check` output in terminal

## Common Pitfalls

- **Missing Docker**: System requires PostgreSQL + Redis running. `docker-compose down && docker-compose up -d` if port conflicts.
- **Stale Node modules**: Clear `client/node_modules` and run `npm install` if frontend fails to start.
- **Rust rebuild**: Engine changes require `cargo build` (slow). Development typically only modifies Python/frontend.
- **Wrong working directory**: Commands like `python test_system_init.py` must run from project root, not subdirectories.
