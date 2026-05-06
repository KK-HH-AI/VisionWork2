import sys
import os
import json
import argparse
import asyncio
import hashlib
import threading
import queue
from pathlib import Path
from typing import TypedDict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from fastapi.responses import JSONResponse
import uvicorn

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = []
valid_token = None
should_stop = {}

WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'workspace')

TEXT_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
    '.html', '.css', '.scss', '.less', '.json', '.yaml', '.yml', '.xml',
    '.md', '.txt', '.csv', '.sh', '.bat', '.ps1', '.sql', '.r', '.rb',
    '.go', '.rs', '.swift', '.kt', '.scala', '.php', '.lua', '.pl',
    '.toml', '.ini', '.cfg', '.env', '.gitignore', '.dockerfile',
    '.vue', '.svelte', '.astro', '.graphql', '.proto',
}

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.bmp', '.webp',
    '.mp3', '.wav', '.mp4', '.avi', '.mov', '.webm',
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.exe', '.dll', '.so', '.dylib', '.bin',
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    '.pyc', '.pyo', '.class', '.o', '.obj',
}

MAX_FILE_SIZE = 200 * 1024


class AnalysisState(TypedDict):
    folder_path: str
    profession: str
    api_url: str
    api_key: str
    model_name: str
    file_queue: List[dict]
    processed: List[dict]
    graph_nodes: List[dict]
    graph_edges: List[dict]
    current_index: int
    total_files: int
    memory_dir: str
    progress_queue: object
    retrieval_path: List[str]


@app.get("/read-file")
async def read_file(path: str = Query(...)):
    try:
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="文件不存在")
        if not os.path.isfile(path):
            raise HTTPException(status_code=400, detail="路径不是文件")
        file_size = os.path.getsize(path)
        if file_size > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件过大（超过5MB）")
        content = _read_file_content(path)
        if content is None:
            raise HTTPException(status_code=415, detail="无法读取文件编码")
        return JSONResponse({"success": True, "content": content, "size": file_size})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save-file")
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


@app.get("/list-memory-dir")
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


@app.get("/get-memory-dir")
async def get_memory_dir(folder_path: str = Query(...)):
    try:
        memory_dir = _get_memory_dir(folder_path)
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if token != valid_token:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    websocket.max_size = 10 * 1024 * 1024
    active_connections.append(websocket)

    analysis_task = None
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

            elif message.get("type") == "start_analysis":
                folder_path = message.get("path")
                profession = message.get("profession", "软件工程师")
                api_url = message.get("api_url", "")
                api_key = message.get("api_key", "")
                model_name = message.get("model_name", "gpt-3.5-turbo")
                stop_flag = message.get("stop_flag", "")

                if not folder_path:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No path provided"
                    })
                    continue

                if not api_url or not api_key:
                    await websocket.send_json({
                        "type": "error",
                        "message": "API URL and API Key are required"
                    })
                    continue

                print(f"[Backend] Starting analysis task with stop_flag: {stop_flag}")
                analysis_task = asyncio.create_task(
                    run_llm_analysis(
                        websocket, folder_path, profession,
                        api_url, api_key, model_name, stop_flag
                    )
                )

            elif message.get("type") == "stop_analysis":
                stop_flag = message.get("stop_flag", "")
                print(f"[Backend] Received stop_analysis request, stop_flag: {stop_flag}")
                if stop_flag:
                    should_stop[stop_flag] = True
                    print(f"[Backend] Set should_stop[{stop_flag}] = True")
                    print(f"[Backend] Current should_stop dict: {should_stop}")
                    await websocket.send_json({
                        "type": "stopped"
                    })
                else:
                    print(f"[Backend] ERROR: No stop_flag in stop_analysis request")
                    await websocket.send_json({
                        "type": "error",
                        "message": "No stop_flag provided"
                    })

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if analysis_task and not analysis_task.done():
            analysis_task.cancel()
        if websocket in active_connections:
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


def _is_text_file(filepath):
    ext = Path(filepath).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True
    return False


def _read_file_content(filepath, max_size=MAX_FILE_SIZE):
    file_size = os.path.getsize(filepath)
    if file_size > max_size:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_size)
        return content + f"\n\n... (文件过大，已截断，原始大小: {file_size} bytes)"
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='gbk') as f:
                return f.read()
        except Exception:
            return None


ANALYSIS_PROMPT = """你是一位{profession}。请分析以下代码文件，并生成结构化的分析笔记。

文件名：{filename}
文件路径：{filepath}

代码内容：
```
{code_content}
```

请按以下结构生成分析笔记（使用Markdown格式）：

## 模块概述
简要描述该文件/模块的整体功能和职责。

## 核心组件
列出关键的函数、类、接口及其作用。

## 依赖关系
分析该模块依赖的其他模块或外部库。

## 注意事项
指出代码中值得关注的设计模式、潜在问题或改进建议。
"""

SECOND_PASS_PROMPT = """你是一位{profession}。请基于以下代码项目的分析笔记，生成一个分析图指令序列。

## 项目笔记摘要
{notes_summary}

## 要求
请生成一个JSON数组，每个元素是一个画布指令。严格按照以下格式输出，只输出JSON数组，不要包含任何其他文字、解释或markdown标记。

支持的指令类型：

1. add_node: 添加节点
   {{"cmd": "add_node", "id": "唯一ID(英文)", "label": "节点标签(中文)", "type": "节点类型", "group": "分组", "description": "简要描述", "codeRef": [{{"file": "文件路径", "lines": [起始行, 结束行]}}]}}
   type可选值: module, function, class, data, config, interface, service, component
   group可选值: python, javascript, react, typescript, java, cpp, c, web, config, doc, data, image, other
   codeRef为可选字段，列出该节点关联的源代码文件及其行号范围。如果从笔记中能确定具体文件，请填写相对路径；如果不确定，可省略此字段。

2. add_edge: 添加连线
   {{"cmd": "add_edge", "source": "源节点ID", "target": "目标节点ID", "label": "关系描述(中文)"}}

3. layout: 自动布局
   {{"cmd": "layout", "algorithm": "dagre"}}

请根据你的职业视角({profession})，生成有意义的分析图：
- 后端开发工程师：生成模块调用关系图，展示各模块之间的依赖和调用关系
- 前端开发工程师：生成组件树和状态流转图
- 产品经理：生成功能结构图，展示功能模块的层次关系
- 架构师：生成系统架构图，展示系统分层和组件关系
- 数据分析师：生成数据流图，展示数据处理流程

注意：
- 节点数量控制在10-25个之间，选择最重要的模块/组件
- 边要体现模块间的真实关系（调用、依赖、数据流等）
- 最后一条指令必须是 layout
- 只输出JSON数组，不要包含```json```等标记"""


IGNORE_DIRS = {
    'node_modules', '.git', '__pycache__', 'dist', 'dist-electron',
    '.venv', 'venv', 'workspace', '.vite', 'build', 'target',
    '.next', '.nuxt', 'coverage', '.tox', '.eggs',
}

IGNORE_FILE_PATTERNS = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'poetry.lock', 'Pipfile.lock',
}


def _build_file_queue(folder_path):
    tree = build_directory_tree(folder_path)
    all_files = _collect_files(tree)
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
        if not _is_text_file(filepath):
            continue
        queue.append({
            "name": filename,
            "path": filepath,
            "group": _get_file_group(filename),
        })
    return queue


def index_files_node(state: AnalysisState) -> AnalysisState:
    folder_path = state["folder_path"]
    file_queue = _build_file_queue(folder_path)
    memory_dir = _get_memory_dir(folder_path)
    os.makedirs(memory_dir, exist_ok=True)

    state["file_queue"] = file_queue
    state["total_files"] = len(file_queue)
    state["current_index"] = 0
    state["processed"] = []
    state["graph_nodes"] = []
    state["graph_edges"] = []
    state["memory_dir"] = memory_dir
    state["retrieval_path"] = []

    progress_queue = state.get("progress_queue")
    if progress_queue is not None:
        try:
            progress_queue.put_nowait({
                "type": "progress",
                "currentTask": f"扫描完成，共发现 {len(file_queue)} 个文件，即将开始分析...",
                "completedFiles": 0,
                "totalFiles": len(file_queue),
            })
        except Exception:
            pass

    return state


def first_pass_reader_node(state: AnalysisState) -> AnalysisState:
    file_queue = state["file_queue"]
    current_index = state["current_index"]
    folder_path = state["folder_path"]
    memory_dir = state["memory_dir"]
    progress_queue = state.get("progress_queue")
    stop_flag = state.get("stop_flag")

    print(f"[Reader] Processing file {current_index + 1}/{len(file_queue)}, stop_flag: {stop_flag}, should_stop value: {should_stop.get(stop_flag, False) if stop_flag else 'N/A'}")

    if current_index >= len(file_queue):
        return state

    if stop_flag and should_stop.get(stop_flag, False):
        print(f"[Reader] STOPPED at index {current_index} due to stop_flag")
        if progress_queue is not None:
            try:
                progress_queue.put_nowait({
                    "type": "stopped",
                    "completedFiles": current_index,
                    "totalFiles": state["total_files"],
                })
            except Exception:
                pass
        return state

    file_info = file_queue[current_index]
    filename = file_info["name"]
    filepath = file_info["path"]
    group = file_info["group"]

    if progress_queue is not None:
        try:
            progress_queue.put_nowait({
                "type": "progress",
                "currentTask": f"接下来开始分析第 {current_index + 1} 份文件：{filename}",
                "completedFiles": current_index,
                "totalFiles": state["total_files"],
            })
        except Exception:
            pass

    code_content = _read_file_content(filepath)
    if code_content is None:
        state["current_index"] = current_index + 1
        if progress_queue is not None:
            try:
                progress_queue.put_nowait({
                    "type": "progress",
                    "currentTask": f"跳过二进制文件 {filename}",
                    "completedFiles": current_index + 1,
                    "totalFiles": state["total_files"],
                })
            except Exception:
                pass
        return state

    node_id = _generate_node_id(filepath, folder_path)

    try:
        llm = ChatOpenAI(
            base_url=state["api_url"],
            api_key=state["api_key"],
            model=state["model_name"],
            temperature=0.3,
            max_tokens=2000,
        )

        prompt = ANALYSIS_PROMPT.format(
            profession=state["profession"],
            filename=filename,
            filepath=filepath,
            code_content=code_content,
        )

        response = llm.invoke(prompt)
        note_content = response.content

        if stop_flag and should_stop.get(stop_flag, False):
            if progress_queue is not None:
                try:
                    progress_queue.put_nowait({
                        "type": "stopped",
                        "completedFiles": current_index + 1,
                        "totalFiles": state["total_files"],
                    })
                except Exception:
                    pass
            state["current_index"] = current_index + 1
            return state

    except Exception as e:
        note_content = f"# {filename}\n\n分析失败: {str(e)}\n\n- 类型: {group}\n"

    if stop_flag and should_stop.get(stop_flag, False):
        if progress_queue is not None:
            try:
                progress_queue.put_nowait({
                    "type": "stopped",
                    "completedFiles": current_index + 1,
                    "totalFiles": state["total_files"],
                })
            except Exception:
                pass
        state["current_index"] = current_index + 1
        return state

    note_filename = f"{Path(filename).stem}_{node_id}.md"
    note_path = os.path.join(memory_dir, note_filename)
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(note_content)

    processed_entry = {
        "filename": filename,
        "filepath": filepath,
        "node_id": node_id,
        "group": group,
        "note_path": note_path,
    }
    state["processed"].append(processed_entry)

    graph_node = {
        "id": node_id,
        "label": note_filename,
        "group": group,
        "path": note_path,
        "source_file": filepath,
    }
    state["graph_nodes"].append(graph_node)

    state["current_index"] = current_index + 1

    if progress_queue is not None:
        try:
            if state["current_index"] < state["total_files"]:
                progress_queue.put_nowait({
                    "type": "progress",
                    "currentTask": f"第 {state['current_index']} 份文件已经分析好了，接下来开始第 {state['current_index'] + 1} 份：{file_queue[state['current_index']]['name']}",
                    "completedFiles": state["current_index"],
                    "totalFiles": state["total_files"],
                })
            else:
                progress_queue.put_nowait({
                    "type": "progress",
                    "currentTask": f"第 {state['current_index']} 份文件已经分析好了",
                    "completedFiles": state["current_index"],
                    "totalFiles": state["total_files"],
                })
                progress_queue.put_nowait({
                    "type": "first_pass_complete",
                    "total_files": state["total_files"],
                    "memory_dir": state["memory_dir"],
                })
            progress_queue.put_nowait({
                "type": "memory_graph",
                "nodes": list(state["graph_nodes"]),
                "edges": list(state["graph_edges"]),
                "memory_dir": state["memory_dir"],
            })
        except Exception:
            pass

    return state


def _extract_json_objects(buffer):
    commands = []
    while True:
        start = buffer.find('{')
        if start == -1:
            break

        depth = 0
        in_string = False
        escape = False
        end = -1

        for i in range(start, len(buffer)):
            c = buffer[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if not in_string:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

        if end == -1:
            break

        json_str = buffer[start:end + 1]
        try:
            cmd = json.loads(json_str)
            commands.append(cmd)
        except json.JSONDecodeError:
            pass

        buffer = buffer[end + 1:]

    return commands, buffer


def _create_search_memory_tool(memory_dir, retrieval_path, progress_queue):
    @tool
    def search_memory(query: str) -> str:
        """搜索项目记忆库中的代码分析笔记。传入关键词或问题，返回相关的笔记内容摘要。"""
        results = []
        visited_ids = []

        if not os.path.exists(memory_dir):
            return "记忆库目录不存在，请先完成第一层分析。"

        for filename in os.listdir(memory_dir):
            if not filename.endswith('.md'):
                continue
            filepath = os.path.join(memory_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            query_lower = query.lower()
            content_lower = content.lower()
            if query_lower in content_lower or any(
                keyword in content_lower
                for keyword in query_lower.split()
                if len(keyword) >= 2
            ):
                parts = filename.replace('.md', '').rsplit('_', 1)
                node_id = parts[-1] if len(parts) > 1 else filename.replace('.md', '')

                results.append({
                    "filename": filename,
                    "node_id": node_id,
                    "content": content[:600],
                })
                if node_id not in retrieval_path:
                    visited_ids.append(node_id)

        for nid in visited_ids:
            if nid not in retrieval_path:
                retrieval_path.append(nid)

        if visited_ids and progress_queue is not None:
            try:
                progress_queue.put_nowait({
                    "type": "memory_path_update",
                    "nodeIds": list(retrieval_path),
                })
            except Exception:
                pass

        if not results:
            return f"未在记忆库中找到与 '{query}' 直接相关的内容。可尝试使用文件名、模块名或功能关键词进行搜索。"

        output = f"找到 {len(results)} 条相关记忆：\n\n"
        for r in results:
            output += f"---\n### [{r['node_id']}] {r['filename']}\n{r['content']}\n"
        return output

    return search_memory


def second_pass_reader_node(state: AnalysisState) -> AnalysisState:
    processed = state["processed"]
    progress_queue = state.get("progress_queue")
    stop_flag = state.get("stop_flag")
    memory_dir = state.get("memory_dir", "")
    retrieval_path = state.get("retrieval_path", [])

    if stop_flag and should_stop.get(stop_flag, False):
        if progress_queue is not None:
            try:
                progress_queue.put_nowait({"type": "second_pass_complete"})
            except Exception:
                pass
        return state

    if progress_queue is not None:
        try:
            progress_queue.put_nowait({
                "type": "progress",
                "currentTask": "第二层阅读：智能体正在检索记忆并生成分析图...",
                "completedFiles": state["total_files"],
                "totalFiles": state["total_files"],
            })
        except Exception:
            pass

    notes_summary_parts = []
    for entry in processed:
        note_path = entry.get("note_path", "")
        if note_path and os.path.exists(note_path):
            try:
                with open(note_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                summary = content[:800] if len(content) > 800 else content
                notes_summary_parts.append(f"### {entry['filename']}\n{summary}")
            except Exception:
                notes_summary_parts.append(f"### {entry['filename']}\n(无法读取笔记)")

    notes_summary = "\n\n".join(notes_summary_parts)
    if len(notes_summary) > 8000:
        notes_summary = notes_summary[:8000] + "\n\n...(笔记已截断)"

    prompt = SECOND_PASS_PROMPT.format(
        profession=state["profession"],
        notes_summary=notes_summary,
    )

    try:
        llm = ChatOpenAI(
            base_url=state["api_url"],
            api_key=state["api_key"],
            model=state["model_name"],
            temperature=0.5,
            max_tokens=4000,
        )

        search_memory_tool = _create_search_memory_tool(
            memory_dir, retrieval_path, progress_queue
        )

        llm_with_tools = llm.bind_tools([search_memory_tool])

        system_msg = SystemMessage(content=f"""你是一位{state['profession']}，正在分析一个代码项目。

你可以使用 search_memory 工具来搜索项目的记忆库（包含各代码文件的LLM分析笔记），以获取更详细的模块信息。

当你对项目有了足够的理解后，请生成分析图指令序列（JSON数组格式）。

注意：
- 在生成分析图之前，建议先用 search_memory 搜索关键模块的信息
- 每次搜索后你会获得相关笔记，帮助你更好地理解模块间的关系
- 如果笔记中明确提到了源代码文件路径，请在节点的 codeRef 字段中标注，方便用户反向定位代码
- 最终输出必须是纯JSON数组，不要包含markdown标记""")

        human_msg = HumanMessage(content=prompt)

        messages = [system_msg, human_msg]
        max_tool_rounds = 8
        tool_round = 0

        while tool_round < max_tool_rounds:
            if stop_flag and should_stop.get(stop_flag, False):
                break

            response = llm_with_tools.invoke(messages)
            messages.append(response)

            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("args", {})
                    tool_call_id = tool_call.get("id", "")

                    if progress_queue is not None:
                        try:
                            progress_queue.put_nowait({
                                "type": "progress",
                                "currentTask": f"智能体正在检索记忆: {tool_args.get('query', '')[:50]}...",
                                "completedFiles": state["total_files"],
                                "totalFiles": state["total_files"],
                            })
                        except Exception:
                            pass

                    if tool_name == "search_memory":
                        result = search_memory_tool.invoke(tool_args)
                    else:
                        result = f"未知工具: {tool_name}"

                    messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call_id
                    ))

                tool_round += 1
                continue

            content = response.content if hasattr(response, 'content') else str(response)
            commands, _ = _extract_json_objects(content)

            for cmd in commands:
                if progress_queue is not None:
                    try:
                        progress_queue.put_nowait({
                            "type": "canvas_command",
                            "command": cmd,
                        })
                    except Exception:
                        pass

            if not commands and content.strip():
                commands, _ = _extract_json_objects("[" + content)
                for cmd in commands:
                    if progress_queue is not None:
                        try:
                            progress_queue.put_nowait({
                                "type": "canvas_command",
                                "command": cmd,
                            })
                        except Exception:
                            pass

            break

        state["retrieval_path"] = retrieval_path

    except Exception as e:
        if progress_queue is not None:
            try:
                progress_queue.put_nowait({
                    "type": "error",
                    "message": f"第二层阅读失败: {str(e)}"
                })
            except Exception:
                pass

    if progress_queue is not None:
        try:
            progress_queue.put_nowait({
                "type": "second_pass_complete",
            })
        except Exception:
            pass

    return state


def should_continue(state: AnalysisState) -> str:
    stop_flag = state.get("stop_flag")
    stop_val = should_stop.get(stop_flag, False) if stop_flag else False
    print(f"[Continue] stop_flag={stop_flag}, should_stop={stop_val}, current_index={state['current_index']}, total={len(state['file_queue'])}")
    if stop_flag and stop_val:
        print(f"[Continue] STOPPING due to stop_flag")
        return "end"
    if state["current_index"] >= len(state["file_queue"]):
        print(f"[Continue] SECOND_PASS - all files processed, moving to second pass")
        return "second_pass"
    print(f"[Continue] CONTINUE to next file")
    return "continue"


def build_analysis_graph():
    workflow = StateGraph(AnalysisState)

    workflow.add_node("index_files", index_files_node)
    workflow.add_node("first_pass_reader", first_pass_reader_node)
    workflow.add_node("second_pass_reader", second_pass_reader_node)

    workflow.set_entry_point("index_files")
    workflow.add_edge("index_files", "first_pass_reader")
    workflow.add_conditional_edges(
        "first_pass_reader",
        should_continue,
        {
            "continue": "first_pass_reader",
            "second_pass": "second_pass_reader",
            "end": END,
        }
    )
    workflow.add_edge("second_pass_reader", END)

    return workflow.compile()


async def run_llm_analysis(websocket, folder_path, profession, api_url, api_key, model_name, stop_flag=""):
    progress_queue = queue.Queue()
    if stop_flag:
        should_stop[stop_flag] = False

    initial_state: AnalysisState = {
        "folder_path": folder_path,
        "profession": profession,
        "api_url": api_url,
        "api_key": api_key,
        "model_name": model_name,
        "file_queue": [],
        "processed": [],
        "graph_nodes": [],
        "graph_edges": [],
        "current_index": 0,
        "total_files": 0,
        "memory_dir": "",
        "progress_queue": progress_queue,
        "stop_flag": stop_flag,
        "retrieval_path": [],
    }

    graph = build_analysis_graph()

    def run_graph():
        try:
            result = graph.invoke(initial_state)
            if stop_flag and should_stop.get(stop_flag, False):
                progress_queue.put({
                    "type": "stopped",
                    "completed_files": result.get("current_index", 0),
                    "total_files": result.get("total_files", 0),
                })
        except Exception as e:
            progress_queue.put({"type": "error", "message": str(e)})

    graph_thread = threading.Thread(target=run_graph, daemon=True)
    graph_thread.start()

    try:
        while True:
            try:
                msg = progress_queue.get_nowait()
            except queue.Empty:
                if not graph_thread.is_alive():
                    try:
                        msg = progress_queue.get_nowait()
                    except queue.Empty:
                        break
                await asyncio.sleep(0.05)
                continue

            msg_type = msg.get("type")

            if msg_type == "first_pass_complete":
                try:
                    await websocket.send_json({
                        "type": "first_pass_complete",
                        "total_files": msg.get("total_files", 0),
                        "memory_dir": msg.get("memory_dir", ""),
                    })
                except RuntimeError:
                    pass
            elif msg_type == "second_pass_complete":
                try:
                    await websocket.send_json({
                        "type": "analysis_complete",
                    })
                except RuntimeError:
                    pass
                break
            elif msg_type == "stopped":
                try:
                    await websocket.send_json({
                        "type": "stopped",
                        "completedFiles": msg.get("completed_files", 0),
                        "totalFiles": msg.get("total_files", 0),
                    })
                except RuntimeError:
                    pass
                break
            elif msg_type == "error":
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": msg.get("message", "Unknown error")
                    })
                except RuntimeError:
                    pass
                break
            try:
                await websocket.send_json(msg)
            except RuntimeError:
                break
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except RuntimeError:
            pass


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
