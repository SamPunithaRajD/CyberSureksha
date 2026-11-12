import asyncio
import requests
import json
from motor.motor_asyncio import AsyncIOMotorClient

async def reprocess():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    # Authenticate to get a token
    r_login = requests.post("http://localhost:8000/api/v1/auth/login", json={
        "email": "admin@bank.com",
        "password": "Password123"
    })
    token = r_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Find all documents
    cursor = db.documents.find()
    async for doc in cursor:
        doc_id = str(doc["_id"])
        filename = doc["filename"]
        # Skip dummy PDF files (files that don't start with standard pdf bytes and thus failed during testing)
        if "test_e2e_document" in filename:
            print(f"Skipping E2E test file: {filename}")
            continue
            
        print(f"\nTriggering analysis for {filename} (ID: {doc_id})...")
        r_trigger = requests.post(f"http://localhost:8000/api/v1/analysis/{doc_id}/analyze", headers=headers)
        print(f"Status: {r_trigger.status_code}")
        print(f"Response: {json.dumps(r_trigger.json(), indent=2)}")

asyncio.run(reprocess())
