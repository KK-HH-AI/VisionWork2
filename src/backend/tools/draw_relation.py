import json
from .base import BaseTool


class DrawRelationTool(BaseTool):
    name = "draw_relation"
    description = "根据分析结果，在画布上添加模块之间的关联边（调用、依赖、数据流等关系）。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "source_id": {
                "type": "string",
                "description": "源节点ID",
            },
            "target_id": {
                "type": "string",
                "description": "目标节点ID",
            },
            "label": {
                "type": "string",
                "description": "关系描述（中文），如'调用'、'依赖'、'数据流'",
            },
        },
        "required": ["source_id", "target_id", "label"],
    }

    async def execute(self, **kwargs) -> str:
        source_id = kwargs.get("source_id", "")
        target_id = kwargs.get("target_id", "")
        label = kwargs.get("label", "")

        if not source_id or not target_id:
            return json.dumps({"error": "source_id and target_id are required"}, ensure_ascii=False)

        canvas_commands = [
            {
                "cmd": "add_edge",
                "source": source_id,
                "target": target_id,
                "label": label,
            }
        ]

        return json.dumps({
            "source_id": source_id,
            "target_id": target_id,
            "label": label,
            "canvas_commands": canvas_commands,
        }, ensure_ascii=False)