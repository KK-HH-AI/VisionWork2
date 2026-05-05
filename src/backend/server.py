import sys
import os
import json
import argparse
import asyncio
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
