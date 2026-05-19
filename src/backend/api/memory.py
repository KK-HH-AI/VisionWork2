import os
import re
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from ..services.scanner import build_dir_tree
from ..core.config import WORKSPACE_ROOT

router = APIRouter()


def _extract_node_id_from_filename(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    parts = stem.rsplit('_', 1)
    if len(parts) == 2 and re.match(r'^[0-9a-f]{12}$', parts[1]):
        return parts[1]
    return stem


def _get_group_from_path(filepath: str, workspace_root: str) -> str:
    rel = os.path.relpath(filepath, workspace_root)
    parts = rel.replace('\\', '/').split('/')
    if len(parts) >= 2:
        return parts[0]
    return 'other'


@router.get("/get-memory-graph-nodes")
async def get_memory_graph_nodes():
    try:
        workspace_dir = WORKSPACE_ROOT
        nodes = []
        seen_ids = set()

        if not os.path.exists(workspace_dir):
            return JSONResponse({"success": True, "nodes": []})

        for root, dirs, files in os.walk(workspace_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'node_modules']
            for filename in files:
                if not filename.endswith('.md'):
                    continue
                filepath = os.path.join(root, filename)
                node_id = _extract_node_id_from_filename(filename)
                if node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                group = _get_group_from_path(filepath, workspace_dir)
                label = os.path.splitext(filename)[0]
                nodes.append({
                    "id": node_id,
                    "label": label,
                    "group": group,
                    "path": filepath,
                })

        return JSONResponse({"success": True, "nodes": nodes})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list-memory-dir")
async def list_memory_dir(memory_dir: str = Query(...)):
    try:
        if not os.path.exists(memory_dir):
            return JSONResponse({"success": True, "files": []})
        files = []
        for filename in sorted(os.listdir(memory_dir)):
            filepath = os.path.join(memory_dir, filename)
            if os.path.isfile(filepath):
                files.append({
                    "name": filename,
                    "path": filepath,
                    "size": os.path.getsize(filepath),
                })
        return JSONResponse({"success": True, "files": files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-memory-dir")
async def get_memory_dir(folder_path: str = Query(...)):
    try:
        from ..utils.graph_utils import get_memory_dir as _get_memory_dir
        memory_dir = _get_memory_dir(folder_path, WORKSPACE_ROOT)
        if not os.path.exists(memory_dir):
            return JSONResponse({"success": True, "memory_dir": memory_dir, "files": []})
        files = []
        for filename in sorted(os.listdir(memory_dir)):
            filepath = os.path.join(memory_dir, filename)
            if os.path.isfile(filepath):
                files.append({
                    "name": filename,
                    "path": filepath,
                    "size": os.path.getsize(filepath),
                })
        return JSONResponse({"success": True, "memory_dir": memory_dir, "files": files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-workspace-tree")
async def get_workspace_tree():
    try:
        workspace_dir = WORKSPACE_ROOT
        if not os.path.exists(workspace_dir):
            return JSONResponse({"success": True, "workspace_dir": workspace_dir, "tree": []})
        tree = build_dir_tree(workspace_dir)
        return JSONResponse({"success": True, "workspace_dir": workspace_dir, "tree": tree})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
