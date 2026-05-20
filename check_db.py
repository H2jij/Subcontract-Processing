import asyncio
import asyncpg

async def main():
    # 先连 postgres 默认库，列出所有数据库
    try:
        c = await asyncpg.connect(
            host='localhost', port=5432,
            user='postgres', password='1234',
            database='postgres'
        )
        rows = await c.fetch('SELECT datname FROM pg_database ORDER BY datname')
        print('ALL DATABASES:', [r['datname'] for r in rows])
        await c.close()
    except Exception as e:
        print('CONNECT postgres FAIL:', type(e).__name__, repr(str(e))[:300])

asyncio.run(main())
