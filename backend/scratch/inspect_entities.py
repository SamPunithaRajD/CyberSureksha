with open('app/services/anomaly_detector.py', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if i+1 >= 730 and i+1 <= 950:
        if 'entities' in line:
            print(f"{i+1}: {line.strip()}")
