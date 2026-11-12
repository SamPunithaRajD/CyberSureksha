import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.docushield
    
    doc_id = "6a1b1158faa484afc5cc0628"
    analysis = await db.analyses.find_one({'document_id': doc_id})
    if not analysis:
        print("Analysis not found")
        return
        
    ocr_result = analysis.get("ocr_result", {})
    pages = ocr_result.get("extraction", {}).get("pages", [])
    print(f"Total pages in OCR results: {len(pages)}")
    
    for page in pages:
        p_num = page.get("page_num")
        if p_num == 4:
            print("--- PAGE 4 BLOCKS ---")
            blocks = page.get("blocks", [])
            for idx, b in enumerate(blocks):
                print(f"[{idx}] Text: '{b.get('text')}' | BBox: {b.get('bbox')}")

if __name__ == '__main__':
    asyncio.run(main())
