import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"c:\Users\ACER\Desktop\Cybersuraksha\backend\logs\docushield_2026-05-30.log"
try:
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print(f"Total log lines: {len(lines)}")
    
    # Check for warnings, errors, or exceptions
    print("--- RECENT WARNINGS & ERRORS ---")
    for idx, line in enumerate(lines):
        if "warning" in line.lower() or "error" in line.lower() or "exception" in line.lower() or "traceback" in line.lower():
            # Print matching line and up to 3 subsequent lines if it is a traceback
            print(f"[{idx+1}] {line.strip()}")
            if "traceback" in line.lower() or "exception" in line.lower():
                for j in range(idx+1, min(len(lines), idx+6)):
                    print(f"    {lines[j].strip()}")
except Exception as e:
    print("Error:", e)
