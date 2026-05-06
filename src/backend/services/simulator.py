import os
import json
import hashlib
import asyncio
from pathlib import Path
from ..core.config import WORKSPACE_ROOT
from ..utils.graph_utils import get_memory_dir


async def run_simulated_analysis(websocket, folder_path):
    memory_dir = get_memory_dir(folder_path, WORKSPACE_ROOT)
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
                    "edges": [],
                    "memory_dir": memory_dir,
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

    node_ids = [n["id"] for n in nodes]
    if len(node_ids) >= 4:
        simulated_paths = [
            node_ids[:3],
            node_ids[:5],
            node_ids[:7],
            node_ids[:9],
        ]
        for path in simulated_paths:
            await asyncio.sleep(0.8)
            try:
                await websocket.send_json({
                    "type": "memory_path_update",
                    "nodeIds": path,
                })
            except RuntimeError:
                return
