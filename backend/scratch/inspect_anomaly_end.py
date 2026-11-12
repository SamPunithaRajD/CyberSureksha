import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"c:\Users\ACER\Desktop\Cybersuraksha\backend\app\services\anomaly_detector.py"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

total_lines = len(lines)
print(f"Total lines: {total_lines}")
for idx in range(total_lines - 120, total_lines):
    print(f"{idx+1}: {lines[idx]}", end="")
