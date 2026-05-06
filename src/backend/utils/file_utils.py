import os
from pathlib import Path
from ..core.config import TEXT_EXTENSIONS, BINARY_EXTENSIONS, MAX_FILE_SIZE


def is_text_file(filepath):
    ext = Path(filepath).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True
    return False


def read_file_content(filepath, max_size=MAX_FILE_SIZE):
    file_size = os.path.getsize(filepath)
    if file_size > max_size:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_size)
        return content + f"\n\n... (文件过大，已截断，原始大小: {file_size} bytes)"
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='gbk') as f:
                return f.read()
        except Exception:
            return None
