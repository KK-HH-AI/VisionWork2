import os
import hashlib
from pathlib import Path


def generate_node_id(file_path, folder_path):
    rel_path = os.path.relpath(file_path, folder_path)
    return hashlib.md5(rel_path.encode()).hexdigest()[:12]


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


def get_project_name(folder_path):
    return Path(folder_path).name


def get_memory_dir(folder_path, workspace_root):
    project_name = get_project_name(folder_path)
    return os.path.join(workspace_root, project_name, 'memory')
