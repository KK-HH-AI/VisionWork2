import json
import os
from .base import BaseTool
from ..core.prompts import CANVAS_GENERATION_PROMPT


class GenerateCanvasTool(BaseTool):
    name = "generate_canvas"
    description = "在所有文件分析完成后，基于收集到的分析笔记，一次性批量生成完整的流程图（节点+边+布局）。这是绘制流程图的首选方式，效率远高于逐个节点创建。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "notes_summary": {
                "type": "string",
                "description": "所有已分析文件的笔记摘要，包含各文件的关键信息和实体。可通过 search_memory 收集或从执行历史中汇总。",
            },
            "user_intent": {
                "type": "string",
                "description": "用户的原始意图/指令，决定流程图的结构和重点方向。",
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
        },
        "required": ["notes_summary", "user_intent"],
    }

    async def execute(self, **kwargs) -> str:
        notes_summary = kwargs.get("notes_summary", "")
        user_intent = kwargs.get("user_intent", "")
        api_url = kwargs.get("api_url", "")
        api_key = kwargs.get("api_key", "")
        model_name = kwargs.get("model_name", "gpt-3.5-turbo")

        if not notes_summary:
            return json.dumps({"error": "notes_summary is required"}, ensure_ascii=False)
        if not user_intent:
            return json.dumps({"error": "user_intent is required"}, ensure_ascii=False)

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
                notes_summary=notes_summary[:12000],  # 截断超长摘要
            )

            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)

            # 从响应中提取 JSON 数组
            canvas_commands = self._extract_commands(response_text)

            if not canvas_commands:
                return json.dumps({
                    "error": "Failed to generate canvas commands from LLM response",
                    "raw_response": response_text[:500],
                }, ensure_ascii=False)

            return json.dumps({
                "canvas_commands": canvas_commands,
                "generated_count": len(canvas_commands),
            }, ensure_ascii=False)

        except Exception as e:
            print(f"[generate_canvas] Error: {type(e).__name__}: {e}")
            return json.dumps({"error": f"Canvas generation failed: {str(e)}"}, ensure_ascii=False)

    def _extract_commands(self, text: str) -> list:
        """从 LLM 返回文本中提取画布指令 JSON 数组"""
        if not text:
            return []

        text = text.strip()

        # 去掉代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 '[' 到最后一个 ']'
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