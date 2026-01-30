import os, sys, traceback, asyncio, logging
from pathlib import Path

# Ensure .env exists (already created above)
env_path = Path('.env')
if not env_path.exists():
    env_path.write_text(
        "POSTGRES_HOST=localhost\n"
        "POSTGRES_PORT=5432\n"
        "POSTGRES_USER=inarbit\n"
        "POSTGRES_PASSWORD=inarbit123\n"
        "POSTGRES_DB=inarbit\n"
        "REDIS_HOST=localhost\n"
        "REDIS_PORT=6379\n"
    )
    print('.env created')

# Initialize DB connections
from server.db import DatabaseManager

async def init_db():
    try:
        db = DatabaseManager.get_instance()
        await db.initialize()
        print('✅ Database connections OK')
    except Exception as e:
        print('❌ Database init failed')
        traceback.print_exc()
        sys.exit(1)

async def start_server():
    import uvicorn
    config = uvicorn.Config(
        "server.app:app",
        host="127.0.0.1",
        port=8000,
        log_level="debug",
        reload=False,
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await init_db()
    await start_server()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
