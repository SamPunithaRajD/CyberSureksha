import json
import sys

# Set standard output to UTF-8 to handle special symbols on Windows console
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\ACER\.gemini\antigravity\brain\f1d3320a-4093-4c3c-b7df-568a6b2fb54d\.system_generated\logs\transcript.jsonl"
try:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    user_steps = []
    for line in lines:
        obj = json.loads(line)
        if obj.get('type') == 'USER_INPUT':
            user_steps.append(obj)
            
    print(f"Total user steps: {len(user_steps)}")
    # Print the last 20 user steps
    for step in user_steps[-20:]:
        print(f"=== User Step {step.get('step_index')} ===")
        print(step.get('content'))
except Exception as e:
    print("Error:", e)
