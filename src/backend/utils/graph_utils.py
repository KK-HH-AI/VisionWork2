import os
import hashlib
from pathlib import Path

# 为文件生成一个固定长度的唯一 ID
def generate_node_id(file_path, folder_path):
    rel_path = os.path.relpath(file_path, folder_path)
    return hashlib.md5(rel_path.encode()).hexdigest()[:12]

# 根据文件扩展名，将文件归入一个“文件组”（类别标签）
def get_file_group(filename):
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    groups = {
        'py': 'python', 'js': 'javascript', 'jsx': 'react', 'ts': 'typescript',
        'tsx': 'react', 'java': 'java', 'cpp': 'cpp', 'c': 'c', 'h': 'c',
        'html': 'web', 'css': 'web', 'scss': 'web', 'less': 'web',
        'json': 'config', 'yaml': 'config', 'yml': 'config', 'xml': 'config',
        'md': 'doc', 'txt': 'doc', 'csv': 'data',
        'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image', 'svg': 'image',
    }
    return groups.get(ext, 'other')

# 获取项目（根文件夹）的名称，即路径的最后一个组成部分，例如：/home/user/my_project → my_project。
def get_project_name(folder_path):
    return Path(folder_path).name

# 构建一个“记忆目录”的路径，返回值：<workspace_root>/<项目名>/memory
def get_memory_dir(folder_path, workspace_root):
    project_name = get_project_name(folder_path)
    return os.path.join(workspace_root, project_name, 'memory')
