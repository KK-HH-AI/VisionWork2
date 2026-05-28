import json
import os
import logging
import re
from pathlib import Path
from .base import BaseTool
from ..core.prompts import CANVAS_GENERATION_PROMPT

logger = logging.getLogger(__name__)


class GenerateCanvasTool(BaseTool):
    name = "generate_canvas"
    description = "基于社区摘要或分析笔记，一次性批量生成完整的流程图（节点+边+布局）。优先使用向量检索获取最相关的社区摘要来生成更精准的流程图。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "notes_summary": {
                "type": "string",
                "description": "（可选，向后兼容）所有已分析文件的笔记摘要。如果提供则使用原逻辑；如果不提供则通过向量检索获取社区摘要。",
            },
            "user_intent": {
                "type": "string",
                "description": "用户的原始意图/指令，决定流程图的结构和重点方向。",
            },
            "community_level": {
                "type": "string",
                "description": "社区摘要层次：auto（自动选择）/ C0（全局） / C1 / C2 / C3（模块级）。默认为 auto。",
            },
            "api_url": {
                "type": "string",
                "description": "LLM API地址",
            },
            "api_key": {
                "type": "string",
                "description": "LLM API密钥",
            },
            "model_name": {
                "type": "string",
                "description": "LLM模型名称",
            },
            "memory_dir": {
                "type": "string",
                "description": "记忆目录路径",
            },
            "project_path": {
                "type": "string",
                "description": "项目根目录路径",
            },
        },
        "required": ["user_intent"],
    }

    async def execute(self, **kwargs) -> str:
        notes_summary = kwargs.get("notes_summary", "")
        user_intent = kwargs.get("user_intent", "")
        community_level = kwargs.get("community_level", "auto")
        memory_dir = kwargs.get("memory_dir", "")
        project_path = kwargs.get("project_path", "")
        api_url = kwargs.get("api_url", "")
        api_key = kwargs.get("api_key", "")
        model_name = kwargs.get("model_name", "gpt-3.5-turbo")

        if not user_intent:
            return json.dumps({"error": "user_intent is required"}, ensure_ascii=False)

        context = ""
        source_type = ""
        community_results = []
        warning = ""

        if notes_summary and notes_summary.strip():
            context = notes_summary
            source_type = "notes_summary"
        else:
            community_results = self._search_communities(
                user_intent=user_intent,
                memory_dir=memory_dir,
                project_path=project_path,
                community_level=community_level,
                k=5,
            )

            if community_results:
                context = self._build_community_context(community_results, max_tokens=8000)
                source_type = "community_summaries"
            else:
                if memory_dir and os.path.isdir(memory_dir):
                    context = self._gather_all_notes(memory_dir)
                    if context:
                        source_type = "all_notes_fallback"
                        warning = "No community summaries found, falling back to all notes traversal. Run generate_community_summaries first for better results."
                    else:
                        return json.dumps({
                            "error": "No notes or community summaries found. Please run analyze_module on key files first.",
                        }, ensure_ascii=False)
                else:
                    return json.dumps({
                        "error": f"memory_dir does not exist: {memory_dir}. Please analyze the project first.",
                    }, ensure_ascii=False)

        canvas_commands = self._generate_via_llm(
            user_intent=user_intent,
            context=context,
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
        )

        if not canvas_commands:
            return json.dumps({
                "error": "Failed to generate canvas commands from LLM response",
            }, ensure_ascii=False)

        if source_type == "community_summaries":
            canvas_commands = self._attach_community_metadata(canvas_commands, community_results)

        result = {
            "canvas_commands": canvas_commands,
            "generated_count": len(canvas_commands),
            "source_type": source_type,
        }

        if warning:
            result["warning"] = warning

        return json.dumps(result, ensure_ascii=False)

    def _search_communities(
        self, user_intent: str, memory_dir: str, project_path: str,
        community_level: str, k: int
    ) -> list:
        storage_path = ""
        if memory_dir and os.path.isdir(memory_dir):
            storage_path = os.path.dirname(memory_dir)
        elif project_path and os.path.isdir(project_path):
            storage_path = project_path

        if not storage_path:
            return []

        try:
            from .memory_vector_store import init_vector_store, query_vector_store, get_collection_count
        except Exception as e:
            logger.debug(f"[generate_canvas] Cannot import vector store: {e}")
            return []

        try:
            collection = init_vector_store(storage_path)
        except Exception as e:
            logger.debug(f"[generate_canvas] Vector store init failed: {e}")
            return []

        doc_count = get_collection_count(collection)
        if doc_count == 0:
            logger.debug(f"[generate_canvas] Vector store is empty")
            return []

        try:
            vector_results = query_vector_store(collection, user_intent, max(k * 2, 10), "community")
        except Exception as e:
            logger.warning(f"[generate_canvas] Vector query failed: {e}")
            return []

        if not vector_results:
            return []

        if community_level == "auto":
            community_level = self._determine_community_level(user_intent, vector_results)

        if community_level and community_level != "auto":
            filtered = [
                vr for vr in vector_results
                if vr.get("metadata", {}).get("level", "") == community_level
            ]
            if filtered:
                vector_results = filtered

        formatted = []
        for vr in vector_results[:k]:
            metadata = vr.get("metadata", {})
            result = {
                "score": vr.get("score", 0),
                "level": metadata.get("level", ""),
                "community_id": metadata.get("community_id", ""),
                "summary_path": metadata.get("summary_path", ""),
                "content": vr.get("content", ""),
            }

            summary_path = result.get("summary_path", "")
            if summary_path and os.path.isfile(summary_path):
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        result["content"] = f.read()
                except Exception:
                    pass
            elif not result.get("content"):
                continue

            formatted.append(result)

        logger.info(
            f"[generate_canvas] Retrieved {len(formatted)} community summaries "
            f"(level={community_level}) for intent: {user_intent[:50]}..."
        )
        return formatted

    def _determine_community_level(self, user_intent: str, vector_results: list) -> str:
        lower_intent = user_intent.lower()

        global_keywords = [
            "overall", "architecture", "overview", "整体架构", "全局", "总体", "概览",
            "entire", "whole", "complete", "full", "整个", "全部", "系统架构", "项目架构",
        ]
        module_keywords = [
            "module", "组件", "模块", "认证", "auth", "login", "database", "api",
            "function", "函数", "class", "类", "detail", "详细", "具体", "流程",
            "flow", "调用", "关系", "implement", "实现",
        ]

        has_global = any(kw in lower_intent for kw in global_keywords)
        has_module = any(kw in lower_intent for kw in module_keywords)

        if has_global:
            return "C0"

        if has_module:
            return "C2"

        available_levels = set()
        for vr in vector_results:
            level = vr.get("metadata", {}).get("level", "")
            if level:
                available_levels.add(level)

        if "C0" in available_levels:
            return "C0"
        if "C1" in available_levels:
            return "C1"
        if "C2" in available_levels:
            return "C2"

        return ""

    def _build_community_context(self, community_results: list, max_tokens: int = 8000) -> str:
        parts = []
        current_tokens = 0

        for cr in community_results:
            content = cr.get("content", "")
            if not content:
                continue

            level = cr.get("level", "")
            community_id = cr.get("community_id", "")
            header = f"## 社区摘要 ({level}, ID: {community_id})\n\n"
            chunk = header + content

            estimated_tokens = self._estimate_tokens(chunk)
            if current_tokens + estimated_tokens > max_tokens:
                remaining = max_tokens - current_tokens
                if remaining > 500:
                    truncate_chars = remaining * 4
                    chunk = chunk[:truncate_chars] + "\n...(truncated)"
                    parts.append(chunk)
                break

            parts.append(chunk)
            current_tokens += estimated_tokens

        context = "\n\n---\n\n".join(parts)
        logger.info(
            f"[generate_canvas] Built community context: {len(parts)} summaries, "
            f"~{current_tokens} tokens"
        )
        return context

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _gather_all_notes(self, memory_dir: str) -> str:
        if not memory_dir or not os.path.isdir(memory_dir):
            return ""

        parts = []
        total_tokens = 0
        max_tokens = 8000

        for root, dirs, files in os.walk(memory_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for filename in sorted(files):
                if not filename.endswith('.md'):
                    continue
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception:
                    continue

                if not content.strip():
                    continue

                chunk = f"## 文件: {filename}\n\n{content}"
                estimated = self._estimate_tokens(chunk)

                if total_tokens + estimated > max_tokens:
                    remaining = max_tokens - total_tokens
                    if remaining > 500:
                        chunk = chunk[:remaining * 4] + "\n...(truncated)"
                        parts.append(chunk)
                    break

                parts.append(chunk)
                total_tokens += estimated

        logger.info(
            f"[generate_canvas] Gathered {len(parts)} notes as fallback context (~{total_tokens} tokens)"
        )
        return "\n\n---\n\n".join(parts)

    def _generate_via_llm(
        self, user_intent: str, context: str,
        api_url: str, api_key: str, model_name: str
    ) -> list:
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                base_url=api_url,
                api_key=api_key,
                model=model_name,
                temperature=0.3,
                max_tokens=4000,
            )

            prompt = CANVAS_GENERATION_PROMPT.format(
                user_intent=user_intent,
                notes_summary=context[:12000],
            )

            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)

            canvas_commands = self._extract_commands(response_text)

            if not canvas_commands:
                logger.warning(
                    f"[generate_canvas] Failed to extract commands. "
                    f"Response preview: {response_text[:300]}"
                )

            return canvas_commands

        except Exception as e:
            logger.error(f"[generate_canvas] LLM generation error: {type(e).__name__}: {e}")
            return []

    def _attach_community_metadata(self, canvas_commands: list, community_results: list) -> list:
        community_ids = []
        community_levels = []
        for cr in community_results:
            cid = cr.get("community_id", "")
            level = cr.get("level", "")
            if cid:
                community_ids.append(cid)
            if level:
                community_levels.append(level)

        if not community_ids:
            return canvas_commands

        for cmd in canvas_commands:
            if cmd.get("cmd") == "add_node":
                if "data" not in cmd:
                    cmd["data"] = {}
                cmd["data"]["community_id"] = community_ids[0]
                cmd["data"]["community_ids"] = list(community_ids)
                cmd["data"]["community_level"] = community_levels[0] if community_levels else ""

        logger.info(
            f"[generate_canvas] Attached community metadata (ids={community_ids}) "
            f"to {sum(1 for c in canvas_commands if c.get('cmd') == 'add_node')} nodes"
        )
        return canvas_commands

    def _extract_commands(self, text: str) -> list:
        if not text:
            return []

        text = text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            pass

        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        return []