import asyncio
import json
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

def serialize(obj):
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    return obj

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    # Let's fetch analyses
    cursor = db.analyses.find()
    analyses = []
    async for doc in cursor:
        doc_id = doc.get("document_id")
        doc_info = await db.documents.find_one({"_id": ObjectId(doc_id) if isinstance(doc_id, str) else doc_id})
        filename = doc_info.get("filename") if doc_info else "unknown"
        
        serialized_doc = serialize(doc)
        serialized_doc["_filename_debug"] = filename
        analyses.append(serialized_doc)
        
    with open('scratch/mongo_data.json', 'w', encoding='utf-8') as f:
        json.dump(analyses, f, indent=2)
    print(f"Dumped {len(analyses)} analyses to scratch/mongo_data.json")

asyncio.run(main())
