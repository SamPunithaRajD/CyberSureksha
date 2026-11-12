with open('logs/docushield_2026-05-28.log', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "cannot access local variable 'entities'" in line:
        print("MATCH:", line)
        for j in range(max(0, i-10), min(len(lines), i+15)):
            print(f"{j}: {lines[j]}", end='')
