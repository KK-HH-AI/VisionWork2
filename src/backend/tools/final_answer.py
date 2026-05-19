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
            report = ("I've completed the analysis. If you have a specific project or file you'd like me to "
                      "analyze, please provide the path and what you'd like to know about it.")

        return json.dumps({
            "report": report,
            "status": "final_answer",
        }, ensure_ascii=False)