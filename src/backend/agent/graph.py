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
4. 使用 draw_relation 在画布上添加模块间的关联边
5. 使用 search_memory 在已分析的笔记中搜索特定内容
6. 最后使用 final_answer 输出最终分析报告

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
- draw_relation 需要提供 source_id, target_id, label 参数
- search_memory 需要提供 query 参数
- final_answer 需要提供 report 参数（Markdown格式的完整分析报告）
"""

OBSERVE_PROMPT = """你是一位{profession}，正在分析一个代码项目。

## 已执行的步骤和结果
{execution_summary}

## 当前状态
- 当前步骤: {current_step}
- 总步骤数: {total_steps}

## 你的任务
根据已执行步骤的结果，判断分析任务是否已经完成，或者是否需要调整计划。

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

    tools_desc = tool_registry.tools_description
    if not tools_desc:
        tools_desc = "- scan_directory: Scan directory structure"

    system_prompt = PLAN_SYSTEM_PROMPT.format(
        profession=state.get("profession", "Software Engineer"),
        tools_description=tools_desc,
    )

    try:
        llm = ChatOpenAI(
            base_url=state["api_url"],
            api_key=state["api_key"],
            model=state["model_name"],
            temperature=0.3,
            max_tokens=2000,
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User message: {user_message}\n\nProject path: {state.get('project_path', '')}\n\nPlease create an execution plan."),
        ])

        content = response.content if hasattr(response, 'content') else str(response)
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
        _push_event(event_queue, {
            "type": "error",
            "message": f"Planning failed: {str(e)}"
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

        _push_event(event_queue, {
            "type": "tool_call",
            "tool_name": action,
            "args": args,
            "thought": thought,
        })

        if "folder_path" not in args and project_path:
            args["folder_path"] = project_path

        context_tools = {"analyze_module", "search_memory"}
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

        try:
            result_json = tool_registry.execute_tool_sync(action, args)

            result_preview = result_json[:500] if len(result_json) > 500 else result_json
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
                except Exception:
                    pass

            messages = list(state.get("messages", []))
            messages.append(AIMessage(content=f"Executed tool {action}: {thought}\nResult preview: {result_preview}"))
            state["messages"] = messages

        except Exception as e:
            _push_event(event_queue, {
                "type": "tool_result",
                "tool_name": action,
                "result": f"Execution failed: {str(e)}",
            })

        state["current_step"] = i + 1

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
            )

            execution_summary_parts = []
            for i, step in enumerate(plan):
                execution_summary_parts.append(
                    f"Step {i + 1}: {step.get('action', '')} - {step.get('thought', '')}"
                )
            execution_summary = "\n".join(execution_summary_parts)

            observe_prompt = OBSERVE_PROMPT.format(
                profession=state.get("profession", "Software Engineer"),
                execution_summary=execution_summary,
                current_step=current_step,
                total_steps=len(plan),
            )

            response = llm.invoke([
                SystemMessage(content=observe_prompt),
                HumanMessage(content="Please evaluate current progress and decide next step."),
            ])

            content = response.content if hasattr(response, 'content') else str(response)
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
    return "plan"


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
            "plan": "plan",
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
        "canvas_nodes": [],
        "canvas_edges": [],
        "should_stop": False,
        "api_url": api_url,
        "api_key": api_key,
        "model_name": model_name,
        "profession": profession,
        "event_queue": event_queue,
        "plan_complete": False,
    }