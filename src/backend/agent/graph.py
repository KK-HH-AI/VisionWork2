import json
import re
from typing import TypedDict, List, Optional, Callable, Awaitable
from ..tools.registry import tool_registry


class AgentState(TypedDict):
    user_message: str
    folder_path: Optional[str]
    tools_description: str
    tool_definitions: List[dict]
    scan_result: Optional[str]
    canvas_commands: List[dict]
    response_message: str


SendFunc = Callable[[dict], Awaitable[None]]


def build_initial_state(user_message: str, folder_path: Optional[str] = None) -> AgentState:
    return {
        "user_message": user_message,
        "folder_path": folder_path,
        "tools_description": tool_registry.tools_description,
        "tool_definitions": tool_registry.tool_definitions,
        "scan_result": None,
        "canvas_commands": [],
        "response_message": "",
    }


async def process_user_input(state: AgentState, send_func: Optional[SendFunc] = None) -> AgentState:
    user_message = state["user_message"]
    folder_path = state.get("folder_path")

    scan_pattern = re.compile(r"(?:请分析|扫描|scan|分析)\s*(?:文件夹)?[：:\s]*(.+)", re.IGNORECASE)
    match = scan_pattern.search(user_message)

    target_path = folder_path
    if match and not target_path:
        target_path = match.group(1).strip().strip('"').strip("'")

    if not target_path:
        state["response_message"] = "请提供要分析的文件夹路径，或点击输入框左侧的 + 按钮选择文件夹。"
        return state

    import os
    if not os.path.isdir(target_path):
        state["response_message"] = f"路径不存在或不是有效目录: {target_path}"
        return state

    scan_result_json = await tool_registry.execute_tool("scan_directory", {"folder_path": target_path})
    state["scan_result"] = scan_result_json

    try:
        tree = json.loads(scan_result_json)
    except json.JSONDecodeError:
        state["response_message"] = f"扫描目录失败，无法解析结果。"
        return state

    canvas_commands = _build_canvas_commands_from_tree(tree)
    state["canvas_commands"] = canvas_commands

    file_count = _count_files(tree)
    dir_count = _count_dirs(tree)
    state["response_message"] = (
        f"已扫描目录: {target_path}\n"
        f"发现 {dir_count} 个目录, {file_count} 个文件。"
    )

    if send_func:
        for cmd in canvas_commands:
            await send_func({
                "type": "canvas_command",
                "command": cmd,
            })

    return state


def _build_canvas_commands_from_tree(tree: dict) -> List[dict]:
    commands = []
    root_name = tree.get("name", "root")
    root_path = tree.get("path", "")

    commands.append({
        "cmd": "add_node",
        "id": f"dir-{_safe_id(root_path)}",
        "label": root_name,
        "type": "directory",
        "group": "directory",
        "description": root_path,
    })

    children = tree.get("children", [])
    for child in children[:20]:
        child_name = child.get("name", "")
        child_path = child.get("path", "")
        child_type = child.get("type", "file")
        node_id = f"{'dir' if child_type == 'directory' else 'file'}-{_safe_id(child_path)}"

        commands.append({
            "cmd": "add_node",
            "id": node_id,
            "label": child_name,
            "type": child_type,
            "group": child_type,
            "description": child_path,
        })

        commands.append({
            "cmd": "add_edge",
            "source": f"dir-{_safe_id(root_path)}",
            "target": node_id,
            "label": "包含",
        })

    commands.append({"cmd": "layout"})
    return commands


def _safe_id(path: str) -> str:
    import hashlib
    return hashlib.md5(path.encode()).hexdigest()[:12]


def _count_files(tree: dict) -> int:
    count = 0
    for child in tree.get("children", []):
        if child.get("type") == "file":
            count += 1
        elif child.get("type") == "directory":
            count += _count_files(child)
    return count


def _count_dirs(tree: dict) -> int:
    count = 0
    for child in tree.get("children", []):
        if child.get("type") == "directory":
            count += 1 + _count_dirs(child)
    return count