import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    doc = await db.documents.find_one({'filename': {'$regex': 'AccountStatement'}})
    if not doc:
        print('Document not found')
        return
        
    analysis = await db.analyses.find_one({'document_id': str(doc['_id'])})
    if not analysis:
        print('Analysis not found')
        return
        
    issues = analysis.get('risk_score', {}).get('detected_issues', [])
    for issue in issues:
        if issue.get('issue') == 'Salary Manipulation':
            import pprint
            pprint.pprint(issue)

if __name__ == '__main__':
    asyncio.run(main())
