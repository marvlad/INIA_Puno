# utils.py

import re
import shutil
import unicodedata
from pathlib import Path


def safe_filename(text):
    text = str(text).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^A-Za-z0-9_\-]", "", text)
    return text or "output"


def make_report_directory(report_root, name, cultivo):
    report_dir = Path(report_root).resolve() / f"{safe_filename(name)}_{safe_filename(cultivo)}"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def copy_file_to_dir(src, dst_dir):
    src = Path(src)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        print(f"WARNING: File not found: {src}")
        return None

    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst
