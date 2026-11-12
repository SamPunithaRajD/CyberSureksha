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
    
    cursor = db.analyses.find()
    analyses = []
    for doc in cursor:
        doc_id = doc.get("document_id")
        doc_info = db.documents.find_one({"_id": ObjectId(doc_id) if isinstance(doc_id, str) else doc_id})
        filename = doc_info.get("filename") if doc_info else "unknown"
        
        serialized_doc = serialize(doc)
        serialized_doc["_filename_debug"] = filename
        analyses.append(serialized_doc)
        
    with open('scratch/mongo_data.json', 'w', encoding='utf-8') as f:
        json.dump(analyses, f, indent=2)
    print(f"Dumped {len(analyses)} analyses to scratch/mongo_data.json")

if __name__ == "__main__":
    main()
