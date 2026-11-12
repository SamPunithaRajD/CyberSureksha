import os
import re

for root, dirs, files in os.walk('.'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            try:
                with open(p, 'r', encoding='utf-8') as file:
                    content = file.read()
                    if 'extract_text_from_pdf' in content or 'pdf_to_images' in content:
                        print(f"File: {p}")
                        for i, line in enumerate(content.split('\n')):
                            if 'extract_text_from_pdf' in line or 'pdf_to_images' in line:
                                print(f"  {i+1}: {line.strip()}")
            except Exception:
                pass
