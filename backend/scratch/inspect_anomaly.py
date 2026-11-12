with open('app/services/anomaly_detector.py', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "def process" in line or "entities" in line:
        print(f"{i+1}: {line.strip()}")
