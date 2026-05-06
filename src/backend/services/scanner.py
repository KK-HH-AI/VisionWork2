import os
from pathlib import Path
from ..core.config import IGNORE_DIRS, IGNORE_FILE_PATTERNS
from ..utils.file_utils import is_text_file
from ..utils.graph_utils import get_file_group


def build_directory_tree(root_path):
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")
    return _scan_directory(root)


def _scan_directory(path):
    node = {
        "name": path.name,
        "path": str(path),
        "type": "directory",
        "children": []
    }
    try:
        entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        for entry in entries:
            if entry.name.startswith('.'):
                continue
            if entry.is_dir():
                node["children"].append(_scan_directory(entry))
            else:
                node["children"].append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "file"
                })
    except PermissionError:
        node["children"].append({
            "name": "[Permission Denied]",
            "path": "",
            "type": "file"
        })
    return node


def collect_files(node, files_list=None):
    if files_list is None:
        files_list = []
    if node.get("type") == "file":
        files_list.append(node)
    for child in node.get("children", []):
        collect_files(child, files_list)
    return files_list


def build_file_queue(folder_path):
    tree = build_directory_tree(folder_path)
    all_files = collect_files(tree)
    queue = []
    for f in all_files:
        filepath = f["path"]
        if not os.path.isfile(filepath):
            continue
        filename = f["name"]
        if filename in IGNORE_FILE_PATTERNS:
            continue
        path_parts = Path(filepath).parts
        if any(part in IGNORE_DIRS for part in path_parts):
            continue
        if not is_text_file(filepath):
            continue
        queue.append({
            "name": filename,
            "path": filepath,
            "group": get_file_group(filename),
        })
    return queue


def build_dir_tree(base_path):
    if not os.path.exists(base_path):
        return []
    tree = []
    try:
        entries = sorted(os.listdir(base_path))
        for entry in entries:
            if entry.startswith('.'):
                continue
            full_path = os.path.join(base_path, entry)
            if os.path.isdir(full_path):
                children = build_dir_tree(full_path)
                tree.append({
                    "name": entry,
                    "path": full_path,
                    "type": "directory",
                    "children": children,
                })
            elif entry.endswith('.md'):
                tree.append({
                    "name": entry,
                    "path": full_path,
                    "type": "file",
                    "size": os.path.getsize(full_path),
                })
    except Exception:
        pass
    return tree
