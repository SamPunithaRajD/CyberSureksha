import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    doc = await db.analyses.find_one({"document_id": "6a134f4872d36c2828aca82b"})
    if doc:
        print(json.dumps(doc.get("results"), indent=2))
    else:
        print("Not found")

asyncio.run(main())
