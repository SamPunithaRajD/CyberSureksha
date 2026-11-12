import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"c:\Users\ACER\Desktop\Cybersuraksha\frontend\src\App.jsx"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "notify" in line.lower() or "notification" in line.lower():
        print(f"App.jsx:{idx+1}: {line.strip()}")
