import sys
import os
import json
import argparse
import asyncio
import hashlib
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = []
valid_token = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if token != valid_token:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    websocket.max_size = 10 * 1024 * 1024  # 10MB
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "scan_directory":
                folder_path = message.get("path")
                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided"
                    })
                    continue

                try:
                    tree = build_directory_tree(folder_path)
                    await websocket.send_json({
                        "type": "directory_tree",
                        "path": folder_path,
                        "tree": tree
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })

            elif message.get("type") == "simulate_analysis":
                folder_path = message.get("path")
                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided"
                    })
                    continue

                try:
                    await run_simulated_analysis(websocket, folder_path)
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        active_connections.remove(websocket)


def build_directory_tree(root_path: str) -> dict:
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")

    return _scan_directory(root)


def _scan_directory(path: Path) -> dict:
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


WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'workspace')


def _collect_files(node, files_list=None):
    if files_list is None:
        files_list = []
    if node.get("type") == "file":
        files_list.append(node)
    for child in node.get("children", []):
        _collect_files(child, files_list)
    return files_list


def _get_project_name(folder_path):
    return Path(folder_path).name


def _get_memory_dir(folder_path):
    project_name = _get_project_name(folder_path)
    return os.path.join(WORKSPACE_ROOT, project_name, 'memory')


def _generate_node_id(file_path, folder_path):
    rel_path = os.path.relpath(file_path, folder_path)
    return hashlib.md5(rel_path.encode()).hexdigest()[:12]


def _get_file_group(filename):
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


async def run_simulated_analysis(websocket, folder_path):
    memory_dir = _get_memory_dir(folder_path)
    os.makedirs(memory_dir, exist_ok=True)

    test_files = [
        {"name": "server.py", "group": "python"},
        {"name": "App.jsx", "group": "react"},
        {"name": "main.js", "group": "javascript"},
        {"name": "styles.css", "group": "web"},
        {"name": "config.json", "group": "config"},
        {"name": "README.md", "group": "doc"},
        {"name": "utils.ts", "group": "typescript"},
        {"name": "index.html", "group": "web"},
        {"name": "data.csv", "group": "data"},
        {"name": "logo.png", "group": "image"},
        {"name": "main.cpp", "group": "cpp"},
        {"name": "notes.txt", "group": "doc"},
    ]

    nodes = []
    batch_size = 2
    for i, file_info in enumerate(test_files):
        filename = file_info["name"]
        group = file_info["group"]
        node_id = hashlib.md5(filename.encode()).hexdigest()[:12]

        note_filename = f"{Path(filename).stem}_{node_id}.md"
        note_path = os.path.join(memory_dir, note_filename)
        note_content = f"# {filename}\n\n这是文件 {filename} 的模拟摘要。\n\n- 类型: {group}\n"
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(note_content)

        nodes.append({
            "id": node_id,
            "label": filename,
            "group": group,
            "path": f"{folder_path}/{filename}"
        })

        if (i + 1) % batch_size == 0 or (i + 1) == len(test_files):
            try:
                await websocket.send_json({
                    "type": "memory_graph",
                    "nodes": list(nodes),
                    "edges": []
                })
            except RuntimeError:
                return

        await asyncio.sleep(0.3)

    try:
        await websocket.send_json({
            "type": "analysis_complete",
            "total_files": len(test_files),
            "memory_dir": memory_dir
        })
    except RuntimeError:
        pass


def main():
    global valid_token
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, required=True)
    args = parser.parse_args()

    valid_token = args.token
    print(f"Backend starting on port {args.port}", flush=True)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
