import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    doc = await db.analyses.find_one(sort=[('_id', -1)])
    if doc:
        print("Error in latest doc:", doc.get('results', {}).get('error', 'No error field found'))
    else:
        print('No doc')

asyncio.run(main())
