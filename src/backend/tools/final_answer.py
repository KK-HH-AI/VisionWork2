import json
from .base import BaseTool


class FinalAnswerTool(BaseTool):
    name = "final_answer"
    description = "输出最终分析报告文本。在所有分析步骤完成后，生成一份结构化的总结报告。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "report": {
                "type": "string",
                "description": "最终分析报告内容（Markdown格式）",
            },
        },
        "required": ["report"],
    }

    async def execute(self, **kwargs) -> str:
        report = kwargs.get("report", "")

        if not report:
            return json.dumps({"error": "report is required"}, ensure_ascii=False)

        return json.dumps({
            "report": report,
            "status": "final_answer",
        }, ensure_ascii=False)