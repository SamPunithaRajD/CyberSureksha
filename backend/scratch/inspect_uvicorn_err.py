import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"c:\Users\ACER\Desktop\Cybersuraksha\backend\uvicorn_err.txt"
if os.path.exists(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        print(f"Total lines in uvicorn_err.txt: {len(lines)}")
        print("--- LAST 50 LINES OF UVICORN ERRORS ---")
        for line in lines[-50:]:
            print(line.strip())
    except Exception as e:
        print("Error:", e)
else:
    print("uvicorn_err.txt does not exist")
