import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"c:\Users\ACER\Desktop\Cybersuraksha\frontend\src\App.jsx"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "usequery(" in line.lower():
        print(f"App.jsx:{idx+1}: {line.strip()}")
        # Print next 3 lines
        for j in range(idx+1, min(len(lines), idx+4)):
            print(f"    {lines[j].strip()}")
