import json
import os
import hashlib
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..tools.registry import tool_registry
from ..core.config import WORKSPACE_ROOT
from ..utils.graph_utils import get_memory_dir


class AgentState(TypedDict):
    messages: List[BaseMessage]
    project_path: str
    plan: List[dict]
    current_step: int
    memory_dir: str
    canvas_nodes: list
    canvas_edges: list
    canvas_context: str
    memory_graph_nodes: list
    memory_graph_edges: list
    retrieval_path: list
    should_stop: bool
    api_url: str
    api_key: str
    model_name: str
    profession: str
    event_queue: Any
    plan_complete: bool


PLAN_SYSTEM_PROMPT = """你是一位{profession}，正在分析一个代码项目。你可以使用以下技能/工具：

{tools_description}

## 你的任务
根据用户的消息，制定一个执行计划。计划应该是一系列步骤，每个步骤调用一个工具来完成子任务。

## 推荐的分析流程
1. 首先使用 scan_directory 了解项目结构
2. 使用 read_file 读取关键文件的内容
3. 使用 analyze_module 对重要模块进行深度分析（会自动在画布上创建节点并保存笔记到记忆库）
4. 使用 draw_relation 的 add_node 操作在画布上手动创建节点（支持富内容 Markdown、图片 URL、自定义颜色）
5. 使用 draw_relation 的 add_edge 操作在画布上添加模块间的关联边
6. 使用 search_memory 在已分析的笔记中搜索特定内容
7. 使用 canvas_read 读取当前画布状态（节点和边），了解已有的流程图结构
8. 使用 draw_relation 的 update_node/update_edge/remove_node/remove_edge 操作来修改已有的流程图
9. 最后使用 final_answer 输出最终分析报告

## 当前画布状态
{canvas_context}

## 绘制复杂流程图指南
- 如果用户要求绘制复杂结构图（架构图、数据流图、类图等），可以使用 draw_relation 的 add_node 操作创建节点
- add_node 支持 rich_content 参数（Markdown 格式），可在节点内嵌入表格、列表、代码等富内容
- add_node 支持 image_url 参数，可在节点内显示图片
- add_node 支持 background_color 和 border_color 参数自定义节点颜色
- add_edge 支持 edge_color 参数自定义边的颜色
- 使用 update_edge 操作修改已有边的标签和颜色

## 修改流程图指南
- 如果用户要求修改已有的流程图，先使用 canvas_read 了解当前画布状态
- 使用 draw_relation 的 update_node 操作修改节点标签、类型、分组、富内容、图片、颜色
- 使用 draw_relation 的 update_edge 操作修改边的标签和颜色（需要 edge_id 参数，格式为 e-{{source}}-{{target}}）
- 使用 draw_relation 的 remove_node 操作删除节点（同时会删除相关边）
- 使用 draw_relation 的 remove_edge 操作删除边

## 输出格式
请严格按照以下JSON格式输出执行计划（只输出JSON，不要包含任何其他文字）：

{{
  "thought": "你的整体思考，简要说明你的分析策略",
  "plan": [
    {{
      "step_number": 1,
      "action": "工具名称",
      "args": {{"参数名": "参数值"}},
      "thought": "这一步的简短推理"
    }}
  ]
}}

注意：
- 计划步骤控制在3-10步之间
- 只输出JSON，不要包含```json```等标记
- analyze_module 需要提供 filepath, code_content, filename 参数
- draw_relation add_node 需要提供 node_id, label, node_type, group；可选 rich_content, image_url, background_color, border_color
- draw_relation add_edge 需要提供 source_id, target_id；可选 label, edge_color
- draw_relation update_node 需要提供 node_id 以及要修改的字段
- draw_relation update_edge 需要提供 edge_id（格式 e-{{source}}-{{target}}）以及要修改的字段
- draw_relation remove_node 需要提供 node_id
- draw_relation remove_edge 需要提供 source_id, target_id
- search_memory 需要提供 query 参数
- final_answer 需要提供 report 参数（Markdown格式的完整分析报告）
"""

OBSERVE_PROMPT = """你是一位{profession}，正在分析一个代码项目。

## 可用工具列表
{tools_description}

## 已执行的步骤和结果
{execution_summary}

## 当前状态
- 当前步骤: {current_step}
- 总步骤数: {total_steps}

## 你的任务
根据已执行步骤的结果，判断分析任务是否已经完成，或者是否需要调整计划。

重要：只能使用上面列出的工具，不要编造不存在的工具（如 list_files, ls, list_tools, dir 等）。

## 输出格式
请严格按照以下JSON格式输出（只输出JSON，不要包含任何其他文字）：

{{
  "status": "complete",
  "reflection": "你的反思，简要说明当前进展和下一步计划",
  "new_plan": []
}}

如果status是"continue"，new_plan中的每个步骤格式与初始计划相同：
{{
  "step_number": 1,
  "action": "工具名称",
  "args": {{"参数名": "参数值"}},
  "thought": "这一步的简短推理"
}}

注意：
- 如果已经获得了足够的项目信息，status应为"complete"
- 如果还需要更多信息，status应为"continue"并提供new_plan
- 只输出JSON，不要包含```json```等标记
"""


def _push_event(event_queue, event: dict):
    if event_queue is not None:
        try:
            if event.get("type") in ("memory_path_update", "memory_graph"):
                print(f"[graph.py] _push_event: type={event.get('type')}, nodeIds={event.get('nodeIds')}, nodes_count={len(event.get('nodes', []))}")
            event_queue.put_nowait(event)
        except Exception:
            pass


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None

    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _safe_id(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()[:12]


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
            "label": "contains",
        })

    commands.append({"cmd": "layout"})
    return commands


def plan_node(state: AgentState) -> AgentState:
    messages = state.get("messages", [])
    event_queue = state.get("event_queue")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if plan and current_step < len(plan):
        _push_event(event_queue, {
            "type": "thought",
            "message": "Continuing with existing plan..."
        })
        return state

    user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break

    if not user_message:
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "Unable to find user message."
        })
        state["plan"] = []
        state["plan_complete"] = True
        return state

    _push_event(event_queue, {
        "type": "thought",
        "message": "Analyzing your request, formulating execution plan..."
    })

    try:
        tools_desc = tool_registry.tools_description
        if not tools_desc:
            tools_desc = "- scan_directory: Scan directory structure"

        canvas_context = state.get("canvas_context", "")
        if not canvas_context:
            canvas_context = "当前画布为空，还没有任何节点或边。"

        system_prompt = PLAN_SYSTEM_PROMPT.format(
            profession=state.get("profession", "Software Engineer"),
            tools_description=tools_desc,
            canvas_context=canvas_context,
        )

        llm = ChatOpenAI(
            base_url=state["api_url"],
            api_key=state["api_key"],
            model=state["model_name"],
            temperature=0.3,
            max_tokens=2000,
            streaming=True,
        )

        full_content = ""
        for chunk in llm.stream([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User message: {user_message}\n\nProject path: {state.get('project_path', '')}\n\nPlease create an execution plan."),
        ]):
            chunk_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if chunk_content:
                full_content += chunk_content
                _push_event(event_queue, {
                    "type": "thought_chunk",
                    "message": chunk_content,
                })

        content = full_content
        plan_data = _extract_json(content)

        if plan_data and "plan" in plan_data:
            thought = plan_data.get("thought", "")
            plan = plan_data.get("plan", [])

            _push_event(event_queue, {
                "type": "thought",
                "message": thought,
            })

            _push_event(event_queue, {
                "type": "plan",
                "plan": plan,
            })

            state["plan"] = plan
            state["current_step"] = 0

            state["messages"] = list(messages) + [
                AIMessage(content=f"Execution plan created:\n{json.dumps(plan, ensure_ascii=False, indent=2)}")
            ]
        else:
            default_plan = [
                {
                    "step_number": 1,
                    "action": "scan_directory",
                    "args": {"folder_path": state.get("project_path", "")},
                    "thought": "First scan the project directory structure to understand file organization",
                }
            ]

            _push_event(event_queue, {
                "type": "thought",
                "message": "Using default plan: scan project directory first",
            })
            _push_event(event_queue, {
                "type": "plan",
                "plan": default_plan,
            })

            state["plan"] = default_plan
            state["current_step"] = 0

    except Exception as e:
        import traceback
        print(f"[graph.py] plan_node error: {type(e).__name__}: {e}")
        print(f"[graph.py] traceback: {traceback.format_exc()}")
        _push_event(event_queue, {
            "type": "error",
            "message": f"Planning failed: {type(e).__name__}: {str(e)}"
        })

        default_plan = [
            {
                "step_number": 1,
                "action": "scan_directory",
                "args": {"folder_path": state.get("project_path", "")},
                "thought": "Scan project directory structure",
            }
        ]
        state["plan"] = default_plan
        state["current_step"] = 0

    return state


def execute_node(state: AgentState) -> AgentState:
    plan = state.get("plan", [])
    event_queue = state.get("event_queue")
    project_path = state.get("project_path", "")

    if state.get("should_stop"):
        return state

    if not plan:
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "No executable plan."
        })
        return state

    current_step = state.get("current_step", 0)

    for i in range(current_step, len(plan)):
        if state.get("should_stop"):
            break

        step = plan[i]
        action = step.get("action", "")
        args = step.get("args", {})
        thought = step.get("thought", "")

        print(f"[graph.py] execute_node: step {i+1}/{len(plan)}, action={action}, args_keys={list(args.keys()) if args else 'none'}")

        _push_event(event_queue, {
            "type": "tool_call",
            "tool_name": action,
            "args": args,
            "thought": thought,
        })

        if "folder_path" not in args and project_path:
            args["folder_path"] = project_path

        context_tools = {"analyze_module", "search_memory", "read_file"}
        canvas_tools = {"canvas_read", "draw_relation"}
        if action in context_tools:
            if "api_url" not in args:
                args["api_url"] = state.get("api_url", "")
            if "api_key" not in args:
                args["api_key"] = state.get("api_key", "")
            if "model_name" not in args:
                args["model_name"] = state.get("model_name", "")
            if "profession" not in args:
                args["profession"] = state.get("profession", "Software Engineer")
            if "memory_dir" not in args:
                args["memory_dir"] = state.get("memory_dir", "")
            if "project_path" not in args:
                args["project_path"] = project_path
        if action in canvas_tools:
            if "canvas_nodes" not in args:
                args["canvas_nodes"] = state.get("canvas_nodes", [])
            if "canvas_edges" not in args:
                args["canvas_edges"] = state.get("canvas_edges", [])

        try:
            result_json = tool_registry.execute_tool_sync(action, args)

            result_preview = result_json[:300] if len(result_json) > 300 else result_json
            step["_result"] = result_json  # Full result for observe_node LLM

            _push_event(event_queue, {
                "type": "tool_result",
                "tool_name": action,
                "result": result_preview,
            })

            if action == "scan_directory":
                try:
                    tree = json.loads(result_json)
                    canvas_commands = _build_canvas_commands_from_tree(tree)
                    for cmd in canvas_commands:
                        _push_event(event_queue, {
                            "type": "canvas_command",
                            "command": cmd,
                        })
                except Exception:
                    pass

            try:
                result_data = json.loads(result_json)
                canvas_commands = result_data.get("canvas_commands", [])
                for cmd in canvas_commands:
                    _push_event(event_queue, {
                        "type": "canvas_command",
                        "command": cmd,
                    })
            except Exception:
                pass

            if action == "final_answer":
                try:
                    result_data = json.loads(result_json)
                    report = result_data.get("report", "")
                    if report:
                        _push_event(event_queue, {
                            "type": "chat_response",
                            "message": report,
                        })
                    state["plan_complete"] = True
                except Exception:
                    pass

            if action == "read_file":
                try:
                    filepath = args.get("filepath", "") or args.get("file_path", "")
                    if filepath and project_path:
                        node_id = hashlib.md5(os.path.relpath(filepath, project_path).encode()).hexdigest()[:12]
                        memory_dir = state.get("memory_dir", "")
                        if memory_dir and os.path.isdir(memory_dir):
                            import glob as glob_mod
                            pattern = os.path.join(memory_dir, f"*_{node_id}.md")
                            matches = glob_mod.glob(pattern)
                            if matches:
                                retrieval_path = list(state.get("retrieval_path", []))
                                if node_id not in retrieval_path:
                                    retrieval_path.append(node_id)
                                    state["retrieval_path"] = retrieval_path
                                    print(f"[graph.py] read_file: found memory note for {filepath}, pushing memory_path_update with nodeIds: {retrieval_path}")
                                    _push_event(event_queue, {
                                        "type": "memory_path_update",
                                        "nodeIds": list(retrieval_path),
                                    })
                except Exception:
                    pass

            if action == "analyze_module":
                try:
                    result_data = json.loads(result_json)
                    node_id = result_data.get("node_id", "")
                    filename = result_data.get("filename", "")
                    filepath = result_data.get("filepath", "")
                    note_path = result_data.get("note_path", "")
                    group = result_data.get("group", "other")

                    if node_id and note_path:
                        memory_nodes = list(state.get("memory_graph_nodes", []))
                        existing_ids = {n["id"] for n in memory_nodes}
                        if node_id not in existing_ids:
                            memory_nodes.append({
                                "id": node_id,
                                "label": filename,
                                "group": group,
                                "path": note_path,
                                "source_file": filepath,
                            })
                            state["memory_graph_nodes"] = memory_nodes

                        _push_event(event_queue, {
                            "type": "memory_graph",
                            "nodes": list(state["memory_graph_nodes"]),
                            "edges": list(state.get("memory_graph_edges", [])),
                            "memory_dir": state.get("memory_dir", ""),
                        })

                    if node_id:
                        retrieval_path = list(state.get("retrieval_path", []))
                        if node_id not in retrieval_path:
                            retrieval_path.append(node_id)
                            state["retrieval_path"] = retrieval_path
                            print(f"[graph.py] analyze_module: pushing memory_path_update with nodeIds: {retrieval_path}")
                            _push_event(event_queue, {
                                "type": "memory_path_update",
                                "nodeIds": list(retrieval_path),
                            })
                except Exception:
                    pass

            if action == "search_memory":
                try:
                    result_data = json.loads(result_json)
                    results = result_data.get("results", [])
                    if results:
                        retrieval_path = list(state.get("retrieval_path", []))
                        for r in results:
                            nid = r.get("node_id", "")
                            if nid and nid not in retrieval_path:
                                retrieval_path.append(nid)
                        state["retrieval_path"] = retrieval_path

                        print(f"[graph.py] search_memory: pushing memory_path_update with nodeIds: {retrieval_path}")
                        _push_event(event_queue, {
                            "type": "memory_path_update",
                            "nodeIds": list(retrieval_path),
                        })
                except Exception:
                    pass

            messages = list(state.get("messages", []))
            messages.append(AIMessage(content=f"Executed tool {action}: {thought}\nResult preview: {result_preview}"))
            state["messages"] = messages

        except Exception as e:
            print(f"[graph.py] execute_node: step {i+1}/{len(plan)} FAILED, action={action}, error={e}")
            _push_event(event_queue, {
                "type": "tool_result",
                "tool_name": action,
                "result": f"Execution failed: {str(e)}",
            })

        state["current_step"] = i + 1

    print(f"[graph.py] execute_node: completed, final current_step={state['current_step']}/{len(plan)}")
    return state


def observe_node(state: AgentState) -> AgentState:
    event_queue = state.get("event_queue")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if state.get("should_stop"):
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "Analysis stopped by user."
        })
        state["plan_complete"] = True
        return state

    # Loop protection: avoid infinite observe→execute→observe cycles
    observe_count = state.get("_observe_count", 0) + 1
    state["_observe_count"] = observe_count
    if observe_count > 3:
        print(f"[graph.py] observe_node: loop limit reached ({observe_count} iterations), forcing completion")
        state["plan_complete"] = True
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "Analysis complete.",
        })
        return state

    if current_step >= len(plan):
        if not plan:
            state["plan_complete"] = True
            _push_event(event_queue, {
                "type": "chat_response",
                "message": "I don't have enough information to proceed with the analysis. Please provide more details about what you'd like me to analyze.",
            })
            return state

        try:
            llm = ChatOpenAI(
                base_url=state["api_url"],
                api_key=state["api_key"],
                model=state["model_name"],
                temperature=0.3,
                max_tokens=1000,
                streaming=True,
            )

            execution_summary_parts = []
            for i, step in enumerate(plan):
                line = f"Step {i + 1}: {step.get('action', '')} - {step.get('thought', '')}"
                result = step.get("_result", "")
                if result:
                    truncated = result[:500] if len(result) > 500 else result
                    line += f" | Result: {truncated}"
                execution_summary_parts.append(line)
            execution_summary = "\n".join(execution_summary_parts)

            tools_desc = tool_registry.tools_description
            if not tools_desc:
                tools_desc = "- scan_directory: Scan directory structure\n- read_file: Read file content\n- analyze_module: Analyze a module\n- draw_relation: Draw flowchart\n- search_memory: Search memory notes\n- canvas_read: Read canvas state\n- final_answer: Output final report"

            observe_prompt = OBSERVE_PROMPT.format(
                profession=state.get("profession", "Software Engineer"),
                tools_description=tools_desc,
                execution_summary=execution_summary,
                current_step=current_step,
                total_steps=len(plan),
            )

            full_content = ""
            for chunk in llm.stream([
                SystemMessage(content=observe_prompt),
                HumanMessage(content="Please evaluate current progress and decide next step."),
            ]):
                chunk_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                if chunk_content:
                    full_content += chunk_content
                    _push_event(event_queue, {
                        "type": "thought_chunk",
                        "message": chunk_content,
                    })

            content = full_content
            observe_data = _extract_json(content)

            if observe_data:
                status = observe_data.get("status", "complete")
                reflection = observe_data.get("reflection", "")

                _push_event(event_queue, {
                    "type": "reflection",
                    "message": reflection,
                })

                if status == "complete":
                    state["plan_complete"] = True
                    _push_event(event_queue, {
                        "type": "chat_response",
                        "message": "Analysis complete.",
                    })
                else:
                    new_plan = observe_data.get("new_plan", [])
                    if new_plan:
                        # Detect plan similarity to prevent loop
                        old_actions = [s.get("action", "") for s in (plan or [])]
                        new_actions = [s.get("action", "") for s in new_plan]
                        if old_actions == new_actions:
                            print(f"[graph.py] observe_node: new plan identical to old plan, forcing completion")
                            state["plan_complete"] = True
                            _push_event(event_queue, {
                                "type": "chat_response",
                                "message": "Analysis complete.",
                            })
                        else:
                            state["plan"] = new_plan
                            state["current_step"] = 0
                            state["plan_complete"] = False
                            _push_event(event_queue, {
                                "type": "plan",
                                "plan": new_plan,
                            })
                    else:
                        state["plan_complete"] = True
                        _push_event(event_queue, {
                            "type": "chat_response",
                            "message": "Analysis complete.",
                        })
            else:
                state["plan_complete"] = True
                _push_event(event_queue, {
                    "type": "chat_response",
                    "message": "Analysis complete.",
                })

        except Exception as e:
            state["plan_complete"] = True
            _push_event(event_queue, {
                "type": "chat_response",
                "message": "Analysis complete.",
            })
    else:
        state["plan_complete"] = False

    return state


def should_continue(state: AgentState) -> str:
    if state.get("should_stop"):
        return "end"
    if state.get("plan_complete", False):
        return "end"
    if not state.get("plan"):
        return "end"
    # observe_node already created a valid plan; route directly to execute
    # (NOT to plan_node, which would overwrite with a fresh LLM call)
    return "execute"


def build_agent_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("observe", observe_node)

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "observe")
    workflow.add_conditional_edges(
        "observe",
        should_continue,
        {
            "execute": "execute",
            "end": END,
        }
    )

    return workflow.compile()


def build_initial_agent_state(
    user_message: str,
    project_path: str,
    api_url: str,
    api_key: str,
    model_name: str,
    profession: str = "Software Engineer",
    event_queue: Any = None,
    canvas_context: str = "",
    canvas_nodes: list = None,
    canvas_edges: list = None,
) -> AgentState:
    memory_dir = get_memory_dir(project_path, WORKSPACE_ROOT) if project_path else ""
    if memory_dir:
        os.makedirs(memory_dir, exist_ok=True)

    return {
        "messages": [HumanMessage(content=user_message)],
        "project_path": project_path,
        "plan": [],
        "current_step": 0,
        "memory_dir": memory_dir,
        "canvas_nodes": canvas_nodes or [],
        "canvas_edges": canvas_edges or [],
        "canvas_context": canvas_context,
        "memory_graph_nodes": [],
        "memory_graph_edges": [],
        "retrieval_path": [],
        "should_stop": False,
        "api_url": api_url,
        "api_key": api_key,
        "model_name": model_name,
        "profession": profession,
        "event_queue": event_queue,
        "plan_complete": False,
    }