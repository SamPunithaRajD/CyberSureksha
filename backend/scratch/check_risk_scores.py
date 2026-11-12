import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    cursor = db.analyses.find()
    async for doc in cursor:
        doc_id = doc.get("document_id")
        doc_info = await db.documents.find_one({"_id": doc_id}) if doc_id else None
        filename = doc_info.get("filename") if doc_info else "unknown"
        
        risk_score = doc.get("results", {}).get("risk_score", {})
        composite = risk_score.get("composite")
        tier = risk_score.get("tier")
        detected_issues = risk_score.get("detected_issues", [])
        
        print(f"File: {filename}")
        print(f"  Status: {doc.get('status')}")
        print(f"  Composite Score: {composite}")
        print(f"  Tier: {tier}")
        print(f"  Detected Issues Count: {len(detected_issues)}")
        for issue in detected_issues:
            print(f"    - {issue.get('issue')} ({issue.get('severity')}) | Penalty: {issue.get('penalty')} | Has bbox: {issue.get('bbox') is not None}")

asyncio.run(check())
