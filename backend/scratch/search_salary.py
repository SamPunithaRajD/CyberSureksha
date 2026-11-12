import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = r"c:\Users\ACER\Desktop\Cybersuraksha\backend\app\services"
for root, dirs, files in os.walk(path):
    for f in files:
        if f.endswith(".py"):
            filepath = os.path.join(root, f)
            with open(filepath, "r", encoding="utf-8") as file:
                lines = file.readlines()
            for idx, line in enumerate(lines):
                if "salary" in line.lower():
                    print(f"{f}:{idx+1}: {line.strip()}")
