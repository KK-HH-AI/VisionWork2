import os
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from ..utils.file_utils import read_file_content
from ..services.scanner import build_directory_tree

router = APIRouter()


@router.get("/read-file")
async def read_file(path: str = Query(...)):
    """
    读取指定路径的文件内容。

    输入:
        path (str): 查询参数，表示要读取的文件路径。

    输出:
        JSONResponse: 包含以下字段的JSON响应:
            - success (bool): 是否成功。
            - content (str): 文件内容（如果成功）。
            - size (int): 文件大小（字节数）。

    中间过程:
        1. 检查文件路径是否存在，不存在则抛出404异常。
        2. 检查路径是否指向文件，不是文件则抛出400异常。
        3. 获取文件大小，若超过5MB则抛出413异常。
        4. 调用 read_file_content 尝试读取文件内容（自动处理编码）。
        5. 若内容读取失败（返回None），抛出415异常。
        6. 返回包含文件内容和大小的成功响应。
    """
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
    """
    将内容保存到指定路径的文件。

    输入:
        request (dict): 请求体字典，必须包含以下键:
            - path (str): 要保存的文件路径。
            - content (str): 要写入的文件内容。

    输出:
        JSONResponse: 包含以下字段的JSON响应:
            - success (bool): 是否成功。
            - message (str): 操作结果描述。

    中间过程:
        1. 从请求字典中提取 path 和 content。
        2. 若缺少 path 或 content 为 None，抛出400异常。
        3. 获取文件所在目录，若目录不存在则递归创建（os.makedirs）。
        4. 以 UTF-8 编码打开文件并写入内容。
        5. 返回保存成功的响应。
    """
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
    """
    扫描指定目录，构建目录树结构。

    输入:
        path (str): 查询参数，表示要扫描的目录路径。

    输出:
        JSONResponse: 包含以下字段的JSON响应:
            - success (bool): 是否成功。
            - tree (dict): 由 build_directory_tree 返回的目录树结构。

    中间过程:
        1. 检查路径是否存在，不存在则抛出404异常。
        2. 检查路径是否为目录，不是目录则抛出400异常。
        3. 调用 build_directory_tree 函数生成目录树（递归遍历子目录和文件）。
        4. 返回包含目录树的成功响应。
    """
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