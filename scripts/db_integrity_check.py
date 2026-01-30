import asyncio
import asyncpg
import os

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "inarbit")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "inarbit_secret_2026")
PG_DATABASE = os.getenv("POSTGRES_DB", "inarbit")

async def main() -> None:
    conn = await asyncpg.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        database=PG_DATABASE,
    )
    try:
        users = await conn.fetch(
            "SELECT id, username, created_at FROM users ORDER BY created_at LIMIT 3"
        )
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        print(f"users count: {user_count}")
        for row in users:
            print("user:", dict(row))

        if users:
            user_id = users[0]["id"]
            sim = await conn.fetchrow(
                """
                SELECT user_id, initial_capital, current_balance, realized_pnl, unrealized_pnl
                FROM simulation_config WHERE user_id=$1
                """,
                user_id,
            )
            print("simulation_config:", dict(sim) if sim else None)

            pp_count = await conn.fetchval(
                "SELECT COUNT(*) FROM paper_positions WHERE user_id=$1",
                user_id,
            )
            paper_positions = await conn.fetch(
                """
                SELECT instrument, quantity, avg_price
                FROM paper_positions WHERE user_id=$1
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 5
                """,
                user_id,
            )
            print(f"paper_positions count: {pp_count}")
            for row in paper_positions:
                print("paper_position:", dict(row))
        else:
            print("No users found.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
