import asyncio
from db import db

async def test():
    await db["chat_context"].insert_one({"test": "ok"})
    doc = await db["chat_context"].find_one({"test": "ok"})
    print(doc)

asyncio.run(test())
