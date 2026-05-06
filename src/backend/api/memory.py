import os
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from ..services.scanner import build_dir_tree
from ..core.config import WORKSPACE_ROOT

router = APIRouter()


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
