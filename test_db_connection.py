import asyncio, traceback, sys, os, logging
from pathlib import Path

# Load environment from .env
os.chdir(Path(__file__).parent)
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG)

async def test():
    from server.db import DatabaseManager
    db = DatabaseManager.get_instance()
    print(f"PG: {db.pg_host}:{db.pg_port} user={db.pg_user} db={db.pg_database}")
    print(f"Redis: {db.redis_host}:{db.redis_port}")
    try:
        await db.initialize()
        print("✅ Database connections OK")
    except Exception as e:
        print("❌ Database init failed")
        traceback.print_exc()
        sys.exit(1)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(test())
