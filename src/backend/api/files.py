import os
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from ..utils.file_utils import read_file_content
from ..services.scanner import build_directory_tree

router = APIRouter()


@router.get("/read-file")
async def read_file(path: str = Query(...)):
    try:
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="文件不存在")
        if not os.path.isfile(path):
            raise HTTPException(status_code=400, detail="路径不是文件")
        file_size = os.path.getsize(path)
        if file_size > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件过大（超过5MB）")
        content = read_file_content(path)
        if content is None:
            raise HTTPException(status_code=415, detail="无法读取文件编码")
        return JSONResponse({"success": True, "content": content, "size": file_size})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-file")
async def save_file(request: dict):
    try:
        path = request.get("path")
        content = request.get("content")
        if not path:
            raise HTTPException(status_code=400, detail="缺少文件路径")
        if content is None:
            raise HTTPException(status_code=400, detail="缺少文件内容")
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return JSONResponse({"success": True, "message": "文件保存成功"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-directory")
async def scan_directory(path: str = Query(...)):
    try:
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="路径不存在")
        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail="路径不是目录")
        tree = build_directory_tree(path)
        return JSONResponse({"success": True, "tree": tree})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
