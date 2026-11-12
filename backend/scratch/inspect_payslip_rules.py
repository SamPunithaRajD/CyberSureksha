import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"c:\Users\ACER\Desktop\Cybersuraksha\backend\app\services\anomaly_detector.py"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def detect_banking_validation_rules" in line or "payslip" in line.lower() and "def" in line:
        print(f"Match found at line {i+1}: {line.strip()}")
        # Print next 40 lines
        for j in range(i, min(len(lines), i + 60)):
            print(f"{j+1}: {lines[j]}", end="")
