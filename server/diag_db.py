
import asyncio
import os
import logging
from dotenv import load_dotenv
import asyncpg
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_diagnostic():
    load_dotenv()
    
    pg_host = os.getenv('POSTGRES_HOST', 'localhost')
    pg_port = int(os.getenv('POSTGRES_PORT', '5432'))
    pg_user = os.getenv('POSTGRES_USER', 'inarbit')
    pg_password = os.getenv('POSTGRES_PASSWORD', 'inarbit123')
    pg_database = os.getenv('POSTGRES_DB', 'inarbit')
    
    print(f"Connecting to {pg_host}:{pg_port} as {pg_user}...")
    
    try:
        conn = await asyncpg.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_password,
            database=pg_database
        )
        print("Connection successful!")
        
        # Try the query from routes.py
        print("Executing query...")
        rows = await conn.fetch("""
            SELECT id, strategy_type, name, description, is_enabled, priority,
                   capital_percent, per_trade_limit, config,
                   total_trades, total_profit, last_run_at
            FROM strategy_configs
            ORDER BY priority ASC, created_at DESC
        """)
        
        print(f"Query successful! Retrieved {len(rows)} rows.")
        for row in rows:
            print(f"Row: {dict(row)}")
            
        await conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
