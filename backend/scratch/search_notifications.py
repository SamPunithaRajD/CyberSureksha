import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = r"c:\Users\ACER\Desktop\Cybersuraksha"
for root, dirs, files in os.walk(path):
    # Skip node_modules, dist, .gemini, etc.
    if any(p in root for p in ["node_modules", "dist", ".gemini"]):
        continue
    for f in files:
        if f.endswith((".py", ".jsx", ".js")):
            filepath = os.path.join(root, f)
            with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
                content = file.read()
            if "notify" in content.lower() or "notification" in content.lower():
                print(f"Match in {f} ({filepath})")
