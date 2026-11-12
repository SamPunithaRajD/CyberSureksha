import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"c:\Users\ACER\Desktop\Cybersuraksha\backend\app\services\anomaly_detector.py"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx in range(150, min(len(lines), 230)):
    print(f"{idx+1}: {lines[idx]}", end="")
