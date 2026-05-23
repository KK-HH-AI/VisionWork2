import json
from .base import BaseTool


class CanvasReadTool(BaseTool):
    name = "canvas_read"
    description = "读取当前画布的状态，获取所有节点和边的信息。用于了解当前流程图的结构，以便进行修改（增删改节点、修改边的标注等）。"
    parameters_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs) -> str:
        nodes = kwargs.get("canvas_nodes", [])
        edges = kwargs.get("canvas_edges", [])

        lines = []
        lines.append("## 当前画布状态\n")

        lines.append("### 节点列表")
        if nodes:
            for i, node in enumerate(nodes):
                node_id = node.get("id", f"unknown_{i}")
                node_data = node.get("data", {})
                label = node_data.get("label", node_id)
                node_type = node_data.get("nodeType", "") or node_data.get("group", "")
                type_str = f" [{node_type}]" if node_type else ""
                lines.append(f"- `{node_id}`: {label}{type_str}")
        else:
            lines.append("(空)")

        lines.append("\n### 边关系")
        if edges:
            for edge in edges:
                source = edge.get("source", "?")
                target = edge.get("target", "?")
                label = edge.get("label", "")
                label_str = f": {label}" if label else ""
                lines.append(f"- `{source}` → `{target}`{label_str}")
        else:
            lines.append("(空)")

        return json.dumps({"canvas_description": "\n".join(lines), "node_count": len(nodes), "edge_count": len(edges)}, ensure_ascii=False)