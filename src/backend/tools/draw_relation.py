import json
from .base import BaseTool


class DrawRelationTool(BaseTool):
    name = "draw_relation"
    description = "在画布上操作流程图：添加模块关联边、修改节点属性、删除节点、删除边。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型：add_edge（添加边）、update_node（修改节点）、remove_node（删除节点）、remove_edge（删除边）。默认为 add_edge。",
                "enum": ["add_edge", "update_node", "remove_node", "remove_edge"],
            },
            "source_id": {
                "type": "string",
                "description": "源节点ID（add_edge、remove_edge 时必填）",
            },
            "target_id": {
                "type": "string",
                "description": "目标节点ID（add_edge、remove_edge 时必填）",
            },
            "label": {
                "type": "string",
                "description": "关系描述/节点新标签（add_edge、update_node 时使用）",
            },
            "node_id": {
                "type": "string",
                "description": "节点ID（update_node、remove_node 时必填）",
            },
            "new_label": {
                "type": "string",
                "description": "节点的新标签（update_node 时使用）",
            },
            "new_type": {
                "type": "string",
                "description": "节点的新类型（update_node 时使用），如 module、function、class",
            },
            "new_group": {
                "type": "string",
                "description": "节点的新分组（update_node 时使用），如 backend、frontend、utils",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> str:
        operation = kwargs.get("operation", "add_edge")

        if operation == "add_edge":
            return await self._add_edge(kwargs)
        elif operation == "update_node":
            return await self._update_node(kwargs)
        elif operation == "remove_node":
            return await self._remove_node(kwargs)
        elif operation == "remove_edge":
            return await self._remove_edge(kwargs)
        else:
            return json.dumps({"error": f"Unknown operation: {operation}"}, ensure_ascii=False)

    async def _add_edge(self, kwargs: dict) -> str:
        source_id = kwargs.get("source_id", "")
        target_id = kwargs.get("target_id", "")
        label = kwargs.get("label", "")

        if not source_id or not target_id:
            return json.dumps({"error": "source_id and target_id are required for add_edge"}, ensure_ascii=False)

        return json.dumps({
            "source_id": source_id,
            "target_id": target_id,
            "label": label,
            "canvas_commands": [{
                "cmd": "add_edge",
                "source": source_id,
                "target": target_id,
                "label": label,
            }],
        }, ensure_ascii=False)

    async def _update_node(self, kwargs: dict) -> str:
        node_id = kwargs.get("node_id", "")
        new_label = kwargs.get("new_label", "") or kwargs.get("label", "")
        new_type = kwargs.get("new_type", "")
        new_group = kwargs.get("new_group", "")

        if not node_id:
            return json.dumps({"error": "node_id is required for update_node"}, ensure_ascii=False)

        changes = []
        if new_label:
            changes.append(f"label → {new_label}")
        if new_type:
            changes.append(f"type → {new_type}")
        if new_group:
            changes.append(f"group → {new_group}")

        return json.dumps({
            "node_id": node_id,
            "changes": ", ".join(changes) if changes else "no changes",
            "canvas_commands": [{
                "cmd": "update_node",
                "id": node_id,
                "label": new_label,
                "type": new_type,
                "group": new_group,
            }],
        }, ensure_ascii=False)

    async def _remove_node(self, kwargs: dict) -> str:
        node_id = kwargs.get("node_id", "")

        if not node_id:
            return json.dumps({"error": "node_id is required for remove_node"}, ensure_ascii=False)

        return json.dumps({
            "node_id": node_id,
            "canvas_commands": [{
                "cmd": "remove_node",
                "id": node_id,
            }],
        }, ensure_ascii=False)

    async def _remove_edge(self, kwargs: dict) -> str:
        source_id = kwargs.get("source_id", "")
        target_id = kwargs.get("target_id", "")

        if not source_id or not target_id:
            return json.dumps({"error": "source_id and target_id are required for remove_edge"}, ensure_ascii=False)

        return json.dumps({
            "source_id": source_id,
            "target_id": target_id,
            "canvas_commands": [{
                "cmd": "remove_edge",
                "source": source_id,
                "target": target_id,
            }],
        }, ensure_ascii=False)