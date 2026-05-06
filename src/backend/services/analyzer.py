import os
import json
import queue
import asyncio
import threading
from pathlib import Path
from typing import TypedDict, List

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from ..core.config import WORKSPACE_ROOT
from ..core.prompts import ANALYSIS_PROMPT, SECOND_PASS_PROMPT
from ..utils.file_utils import read_file_content
from ..utils.graph_utils import generate_node_id, get_memory_dir
from ..services.scanner import build_file_queue

should_stop = {}


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
    stop_flag: str
    retrieval_path: List[str]


def index_files_node(state: AnalysisState) -> AnalysisState:
    folder_path = state["folder_path"]
    file_queue = build_file_queue(folder_path)
    memory_dir = get_memory_dir(folder_path, WORKSPACE_ROOT)
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

    code_content = read_file_content(filepath)
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

    node_id = generate_node_id(filepath, folder_path)

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
