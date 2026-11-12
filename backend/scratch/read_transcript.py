import json

path = r"C:\Users\ACER\.gemini\antigravity\brain\f1d3320a-4093-4c3c-b7df-568a6b2fb54d\.system_generated\logs\transcript.jsonl"
try:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print(f"Total lines in transcript: {len(lines)}")
    # Print the last 10 lines
    for i in range(max(0, len(lines) - 10), len(lines)):
        obj = json.loads(lines[i])
        print(f"--- Step {obj.get('step_index')} (Source: {obj.get('source')}, Type: {obj.get('type')}) ---")
        content = obj.get('content', '')
        if isinstance(content, str):
            print(content[:500])
        else:
            print(str(content)[:500])
except Exception as e:
    print("Error:", e)
