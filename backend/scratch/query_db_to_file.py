import asyncio
import json
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

def default_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    return str(obj)

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    # query document with ID 6a17d0cf4545c188a252e1b8 (tampered payslip)
    analysis = await db.analyses.find_one({"document_id": "6a17d0cf4545c188a252e1b8"})
    if not analysis:
        # Fallback to get any analysis
        analysis = await db.analyses.find_one()
        
    if analysis:
        with open('scratch/analysis_dump.json', 'w') as f:
            json.dump(analysis, f, indent=2, default=default_serializer)
        print("Success dumping analysis to scratch/analysis_dump.json")
    else:
        print("No analysis found in database")

asyncio.run(main())
