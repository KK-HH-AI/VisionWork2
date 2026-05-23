import json
import os
import hashlib
from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..tools.registry import tool_registry          # 工具注册表，统一管理可用工具
from ..core.config import WORKSPACE_ROOT            # 工作空间根路径
from ..utils.graph_utils import get_memory_dir      # 根据项目路径获取记忆存储目录

# ----------------------------------------------------------------------
# 定义代理的状态（AgentState）
# 这是整个图中流转的共享状态，每个节点都会读写它。
# ----------------------------------------------------------------------
class AgentState(TypedDict):
    messages: List[BaseMessage]          # 对话历史
    project_path: str                    # 被分析项目的根路径
    user_intent: str                     # 用户的原始指令，决定流程图绘制方向
    plan: List[dict]                     # 当前执行计划（多个步骤组成的列表）
    current_step: int                    # 当前执行到的步骤索引
    memory_dir: str                      # 记忆笔记存储目录
    canvas_nodes: list                   # 画布节点列表（前端可视化用）
    canvas_edges: list                   # 画布边列表
    canvas_context: str                  # 描述当前画布状态的文本，供LLM参考
    memory_graph_nodes: list             # 记忆图谱节点（记录分析过的模块）
    memory_graph_edges: list             # 记忆图谱边
    retrieval_path: list                 # 检索路径（最近一次搜索命中的节点ID列表）
    should_stop: bool                    # 外部触发停止标志
    api_url: str                         # LLM API 地址
    api_key: str                         # API 密钥
    model_name: str                      # 模型名称
    event_queue: Any                     # 事件队列，用于向前端推送实时消息
    plan_complete: bool                  # 整个计划是否已完成（用于结束条件）

# ----------------------------------------------------------------------
# 系统提示词模板
# PLAN_SYSTEM_PROMPT: 用于生成初始执行计划
# OBSERVE_PROMPT:     用于在执行完所有步骤后进行反思，判断是否继续
# ----------------------------------------------------------------------
PLAN_SYSTEM_PROMPT = """你是一个智能流程图绘制助手。你的任务是根据用户的指令，阅读和分析项目文件，理解项目结构和内容，然后在画布上绘制出用户想要的流程图。

## 项目范围限制
你只能分析 project_path 指定的目录及其子目录中的文件和文件夹。不要读取或扫描 project_path 范围之外的任何内容。project_path 在用户消息中已明确指出。

## 可用工具
{tools_description}

## 推荐工作流程（两阶段）

### 第一阶段：收集信息（必须包含 analyze_module）
1. 使用 scan_directory 了解项目整体结构（folder_path 必须使用 project_path）
2. 使用 read_file 读取用户关注的关键文件（代码、文档、配置、数据等）
3. **必须**使用 analyze_module 对重要文件进行深度分析，生成笔记保存到记忆库（记忆图谱依赖这些笔记）
4. 如需要，使用 search_memory 搜索已分析笔记中的特定内容

### 第二阶段：批量生成流程图
5. 使用 generate_canvas 一次性批量生成完整的流程图（节点+边+布局）
   - notes_summary: 汇总所有 analyze_module 的分析笔记
   - user_intent: 用户的原始指令
   - 这是效率最高的方式，LLM会在充分了解项目内容后一次性规划整个流程图

### 收尾
6. 使用 final_answer 输出最终分析报告

## 画布微调工具（批量生成后如需微调）
- canvas_read: 读取当前画布状态
- draw_relation add_node/update_node/remove_node: 增删改节点
- draw_relation add_edge/update_edge/remove_edge: 增删改边

## 当前画布状态
{canvas_context}

## 输出格式
请严格按照以下JSON格式输出执行计划（只输出JSON，不要包含任何其他文字）：

{{
  "thought": "你的整体思考，简要说明你打算如何理解用户的意图并绘制流程图",
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
- 所有文件路径必须在 project_path 范围之内
- 第一阶段先收集信息，第二阶段用 generate_canvas 批量生成流程图
- analyze_module 需要提供 filepath, code_content, filename，且必须调用（记忆图谱依赖它）
- generate_canvas 需要提供 notes_summary（汇总所有 analyze_module 的分析笔记）和 user_intent（用户原始指令）
- final_answer 需要提供 report 参数（Markdown格式的完整分析报告）
"""
OBSERVE_PROMPT = """你是一个智能流程图绘制助手。根据用户指令和已执行步骤的结果，判断分析任务是否已经完成。

## 可用工具列表
{tools_description}

## 已执行的步骤和结果
{execution_summary}

## 当前状态
- 当前步骤: {current_step}
- 总步骤数: {total_steps}

## 你的任务
根据已执行步骤的结果，判断分析任务是否已经完成，或者是否需要调整计划继续执行。

重要：只能使用上面列出的工具，不要编造不存在的工具。

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
- 如果已经完成了信息收集和流程图绘制，status应为"complete"
- 如果还需要补充分析或调整流程图，status应为"continue"并提供new_plan
- 只输出JSON，不要包含```json```等标记
"""

# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------
def _push_event(event_queue, event: dict):
    """
    安全地向事件队列推送一个事件。
    事件队列用于通知前端（如 websocket）当前代理的行为。
    """
    if event_queue is not None:
        try:
            if event.get("type") in ("memory_path_update", "memory_graph"):
                print(f"[graph.py] _push_event: type={event.get('type')}, "
                      f"nodeIds={event.get('nodeIds')}, nodes_count={len(event.get('nodes', []))}")
            event_queue.put_nowait(event)
        except Exception:
            pass

def _extract_json(text: str) -> Optional[dict]:
    """
    从LLM返回的文本中提取JSON对象。
    支持纯JSON、```json```包裹、文本中任意位置的JSON对象。
    """
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
    """对路径字符串做 MD5 哈希，取前12位作为短ID。"""
    return hashlib.md5(path.encode()).hexdigest()[:12]

def _build_canvas_commands_from_tree(tree: dict) -> List[dict]:
    """将 scan_directory 返回的目录树结构转换为画布命令列表。"""
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

# ----------------------------------------------------------------------
# 图节点函数
# ----------------------------------------------------------------------
def plan_node(state: AgentState) -> AgentState:
    """计划节点：根据用户消息和当前画布状态，调用LLM生成执行计划。"""
    messages = state.get("messages", [])
    event_queue = state.get("event_queue")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if plan and current_step < len(plan):
        _push_event(event_queue, {
            "type": "thought",
            "message": "继续执行现有计划..."
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
            "message": "无法找到用户消息。"
        })
        state["plan"] = []
        state["plan_complete"] = True
        return state

    # 保存用户意图供后续阶段使用
    state["user_intent"] = user_message

    _push_event(event_queue, {
        "type": "thought",
        "message": "正在理解你的指令，制定执行计划..."
    })

    try:
        tools_desc = tool_registry.tools_description
        if not tools_desc:
            tools_desc = "- scan_directory: 扫描目录结构"

        canvas_context = state.get("canvas_context", "")
        if not canvas_context:
            canvas_context = "当前画布为空，还没有任何节点或边。"

        system_prompt = PLAN_SYSTEM_PROMPT.format(
            tools_description=tools_desc,
            canvas_context=canvas_context,
        )

        llm = ChatOpenAI(
            base_url=state["api_url"],
            api_key=state["api_key"],
            model=state["model_name"],
            temperature=0.3,
            max_tokens=2000,
            streaming=False,  # 不流式输出JSON计划，避免前端显示原始JSON
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"用户指令: {user_message}\n\n"
                                 f"项目路径: {state.get('project_path', '')}\n\n"
                                 f"请制定执行计划。"),
        ])
        full_content = response.content if hasattr(response, 'content') else str(response)

        plan_data = _extract_json(full_content)

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
                AIMessage(content=f"执行计划已创建:\n{json.dumps(plan, ensure_ascii=False, indent=2)}")
            ]
        else:
            default_plan = [
                {
                    "step_number": 1,
                    "action": "scan_directory",
                    "args": {"folder_path": state.get("project_path", "")},
                    "thought": "先扫描项目目录结构，了解文件组织",
                }
            ]
            _push_event(event_queue, {
                "type": "thought",
                "message": "使用默认计划：先扫描项目目录",
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
            "message": f"计划制定失败: {type(e).__name__}: {str(e)}"
        })
        default_plan = [
            {
                "step_number": 1,
                "action": "scan_directory",
                "args": {"folder_path": state.get("project_path", "")},
                "thought": "扫描项目目录结构",
            }
        ]
        state["plan"] = default_plan
        state["current_step"] = 0

    return state

def execute_node(state: AgentState) -> AgentState:
    """执行节点：按顺序执行计划中的每个步骤（工具调用）。"""
    plan = state.get("plan", [])
    event_queue = state.get("event_queue")
    project_path = state.get("project_path", "")

    if state.get("should_stop"):
        return state

    if not plan:
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "没有可执行的计划。"
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

        print(f"[graph.py] execute_node: step {i+1}/{len(plan)}, action={action}, "
              f"args_keys={list(args.keys()) if args else 'none'}")

        _push_event(event_queue, {
            "type": "tool_call",
            "tool_name": action,
            "args": args,
            "thought": thought,
        })

        # 自动补充通用参数
        if "folder_path" not in args and project_path:
            args["folder_path"] = project_path

        # 需要上下文信息的工具
        context_tools = {"analyze_module", "search_memory", "read_file", "generate_canvas"}
        canvas_tools = {"canvas_read", "draw_relation"}
        if action in context_tools:
            for key in ("api_url", "api_key", "model_name", "memory_dir", "project_path"):
                if key not in args:
                    args[key] = state.get(key, "")
        if action in canvas_tools:
            for key in ("canvas_nodes", "canvas_edges"):
                if key not in args:
                    args[key] = state.get(key, [])

        # generate_canvas 自动补充 user_intent
        if action == "generate_canvas":
            if "user_intent" not in args:
                args["user_intent"] = state.get("user_intent", "")

        try:
            result_json = tool_registry.execute_tool_sync(action, args)

            result_preview = result_json[:300] if len(result_json) > 300 else result_json
            step["_result"] = result_json

            _push_event(event_queue, {
                "type": "tool_result",
                "tool_name": action,
                "result": result_preview,
            })

            # ---- 对特定工具的结果进行后处理 ----

            # 1. scan_directory：将目录树转换为画布命令
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

            # 2. 通用画布命令提取
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

            # 3. generate_canvas：推送批量生成的画布命令 + 统计信息
            if action == "generate_canvas":
                try:
                    result_data = json.loads(result_json)
                    generated_count = result_data.get("generated_count", 0)
                    if generated_count > 0:
                        _push_event(event_queue, {
                            "type": "chat_response",
                            "message": f"已批量生成 {generated_count} 条画布指令，流程图已更新。",
                        })
                except Exception:
                    pass

            # 4. final_answer：提取最终报告推送给前端
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

                    # 推送所有已分析节点到检索路径，让记忆图谱高亮显示全部分析过的文件
                    memory_nodes = state.get("memory_graph_nodes", [])
                    if memory_nodes:
                        all_ids = [n["id"] for n in memory_nodes]
                        _push_event(event_queue, {
                            "type": "memory_path_update",
                            "nodeIds": all_ids,
                        })
                except Exception:
                    pass

            # 5. read_file 笔记检测
            if action == "read_file":
                try:
                    filepath = args.get("filepath", "") or args.get("file_path", "")
                    if filepath and project_path:
                        node_id = hashlib.md5(
                            os.path.relpath(filepath, project_path).encode()
                        ).hexdigest()[:12]
                        memory_dir = state.get("memory_dir", "")
                        if memory_dir and os.path.isdir(memory_dir):
                            import glob as glob_mod
                            pattern = os.path.join(memory_dir, f"*_{node_id}.md")
                            matches = glob_mod.glob(pattern)
                except Exception:
                    pass

            # 6. analyze_module：更新记忆图谱
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

                except Exception:
                    pass

            # 7. search_memory：更新检索路径
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

            # 更新对话历史
            messages = list(state.get("messages", []))
            messages.append(
                AIMessage(content=f"已执行工具 {action}: {thought}\n结果预览: {result_preview}")
            )
            state["messages"] = messages

        except Exception as e:
            print(f"[graph.py] execute_node: step {i+1}/{len(plan)} FAILED, action={action}, error={e}")
            _push_event(event_queue, {
                "type": "tool_result",
                "tool_name": action,
                "result": f"执行失败: {str(e)}",
            })

        state["current_step"] = i + 1

    print(f"[graph.py] execute_node: 完成, final current_step={state['current_step']}/{len(plan)}")
    return state

def observe_node(state: AgentState) -> AgentState:
    """观察/反思节点：评估进展是否满足用户需求，决定继续或结束。"""
    event_queue = state.get("event_queue")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if state.get("should_stop"):
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "用户已停止分析。"
        })
        state["plan_complete"] = True
        return state

    observe_count = state.get("_observe_count", 0) + 1
    state["_observe_count"] = observe_count
    if observe_count > 5:
        print(f"[graph.py] observe_node: 循环次数达到上限 ({observe_count})，强制结束")
        state["plan_complete"] = True
        _push_event(event_queue, {
            "type": "chat_response",
            "message": "分析已自动完成。如需进一步分析，请发送新的指令。",
        })
        return state

    if current_step >= len(plan):
        if not plan:
            state["plan_complete"] = True
            _push_event(event_queue, {
                "type": "chat_response",
                "message": "信息不足，无法继续分析。请提供更详细的指令。",
            })
            return state

        try:
            llm = ChatOpenAI(
                base_url=state["api_url"],
                api_key=state["api_key"],
                model=state["model_name"],
                temperature=0.3,
                max_tokens=1000,
                streaming=False,  # 不流式输出JSON，避免前端显示原始JSON
            )

            execution_summary_parts = []
            for i, step in enumerate(plan):
                line = f"步骤 {i + 1}: {step.get('action', '')} - {step.get('thought', '')}"
                result = step.get("_result", "")
                if result:
                    truncated = result[:500] if len(result) > 500 else result
                    line += f" | 结果: {truncated}"
                execution_summary_parts.append(line)
            execution_summary = "\n".join(execution_summary_parts)

            tools_desc = tool_registry.tools_description
            if not tools_desc:
                tools_desc = (
                    "- scan_directory: 扫描目录结构\n"
                    "- read_file: 读取文件内容\n"
                    "- analyze_module: 分析文件\n"
                    "- generate_canvas: 批量生成流程图\n"
                    "- draw_relation: 手动操作流程图\n"
                    "- search_memory: 搜索记忆笔记\n"
                    "- canvas_read: 读取画布状态\n"
                    "- final_answer: 输出最终报告"
                )

            observe_prompt = OBSERVE_PROMPT.format(
                tools_description=tools_desc,
                execution_summary=execution_summary,
                current_step=current_step,
                total_steps=len(plan),
            )

            response = llm.invoke([
                SystemMessage(content=observe_prompt),
                HumanMessage(content="请评估当前进展并决定下一步。"),
            ])
            full_content = response.content if hasattr(response, 'content') else str(response)

            observe_data = _extract_json(full_content)

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
                        "message": "分析完成。",
                    })
                else:
                    new_plan = observe_data.get("new_plan", [])
                    if new_plan:
                        old_actions = [s.get("action", "") for s in (plan or [])]
                        new_actions = [s.get("action", "") for s in new_plan]
                        if old_actions == new_actions:
                            print(f"[graph.py] observe_node: 新计划与旧计划相同，强制结束")
                            state["plan_complete"] = True
                            _push_event(event_queue, {
                                "type": "chat_response",
                                "message": "分析完成。",
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
                            "message": "分析完成。",
                        })
            else:
                state["plan_complete"] = True
                _push_event(event_queue, {
                    "type": "chat_response",
                    "message": "分析完成。",
                })

        except Exception as e:
            state["plan_complete"] = True
            _push_event(event_queue, {
                "type": "chat_response",
                "message": "分析完成。",
            })
    else:
        state["plan_complete"] = False

    return state

# ----------------------------------------------------------------------
# 条件边函数
# ----------------------------------------------------------------------
def should_continue(state: AgentState) -> str:
    if state.get("should_stop"):
        return "end"
    if state.get("plan_complete", False):
        return "end"
    if not state.get("plan"):
        return "end"
    return "execute"

# ----------------------------------------------------------------------
# 构建代理图
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# 初始化代理状态的工厂函数
# ----------------------------------------------------------------------
def build_initial_agent_state(
    user_message: str,
    project_path: str,
    api_url: str,
    api_key: str,
    model_name: str,
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
        "user_intent": user_message,
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
        "event_queue": event_queue,
        "plan_complete": False,
    }