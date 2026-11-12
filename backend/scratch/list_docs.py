import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    docs = await db.documents.find({}).to_list(100)
    print(f"Total documents in DB: {len(docs)}")
    for doc in docs:
        print(f"ID: {doc['_id']} | Filename: {doc.get('filename')} | Original: {doc.get('original_filename')} | Category: {doc.get('document_category')} | Pages: {doc.get('page_count')}")

if __name__ == '__main__':
    asyncio.run(main())
