import json
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient

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

def main():
    client = MongoClient('mongodb://localhost:27017')
    db = client.docushield
    
    cursor = db.documents.find()
    docs = []
    for doc in cursor:
        docs.append(serialize(doc))
        
    with open('scratch/mongo_docs.json', 'w', encoding='utf-8') as f:
        json.dump(docs, f, indent=2)
    print(f"Dumped {len(docs)} documents to scratch/mongo_docs.json")

if __name__ == "__main__":
    main()
