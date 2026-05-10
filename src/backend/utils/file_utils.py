import os
from pathlib import Path
from ..core.config import TEXT_EXTENSIONS, BINARY_EXTENSIONS, MAX_FILE_SIZE

# 快速判断一个文件是否属于“文本文件”，基于扩展名白名单/黑名单
def is_text_file(filepath):
    ext = Path(filepath).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True
    return False

# 安全地读取文本文件内容，具备大小截断和多编码兼容
def read_file_content(filepath, max_size=MAX_FILE_SIZE):
    # 用 os.path.getsize 获取文件字节大小
    file_size = os.path.getsize(filepath)
    if file_size > max_size:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_size)
        # 注意，这里是有文本截断的
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
