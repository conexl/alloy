import asyncio
import os
import asyncpg

DSN = os.getenv("DB_DSN", "postgres://postgres:postgres@postgres:5432/tender?sslmode=disable")

async def main():
    conn = await asyncpg.connect(DSN)
    ids = [r[0] for r in await conn.fetch("SELECT id FROM items WHERE rfq_id = 2")]
    ids += [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    placeholders = ",".join(str(i) for i in ids)
    
    await conn.execute(f"DELETE FROM supplier_search_results WHERE item_id IN ({placeholders})")
    await conn.execute(f"DELETE FROM search_log WHERE item_id IN ({placeholders})")
    
    print(f"БД сброшена: {len(ids)} items очищены")
    await conn.close()

asyncio.run(main())