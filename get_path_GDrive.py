import re
import os

def find_and_open_su(su_number: int, folder_path: str) -> None:
    range_pattern = re.compile(r'SU\s*(\d+)\s*(?:-\s*(\d+))?', re.IGNORECASE)
    
    matches = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if not filename.endswith('.pdf'):
                continue
    
            m = range_pattern.search(filename)
            if not m:
                continue

            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else start

            if start <= su_number <= end:
                matches.append(os.path.join(root, filename))
    
    if matches:
        print(f"Found {len(matches)} file(s) for SU{su_number:04d}:\n")
        for f in matches:
            print(f"  Full path : {f}")          # ← full absolute path
            print(f"  Relative  : {os.path.relpath(f, folder_path)}")
            print()
        print("Opening all...")
        for f in matches:
            os.startfile(f)
    else:
        print(f"No file found for SU{su_number:04d}")


# --- Usage ---
folder = r"G:\My Drive\your_folder"

su_input = int(input("Enter SU number: "))
find_and_open_su(su_input, folder)
~                                  
