import json
from .base import BaseTool


class DrawRelationTool(BaseTool):
    name = "draw_relation"
    description = "在画布上操作流程图：添加节点（支持富内容、图片、颜色）、添加关系边、修改节点属性、修改边属性、删除节点、删除边。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型：add_node（添加节点）、add_edge（添加边）、update_node（修改节点）、update_edge（修改边）、remove_node（删除节点）、remove_edge（删除边）。默认为 add_edge。",
                "enum": ["add_node", "add_edge", "update_node", "update_edge", "remove_node", "remove_edge"],
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
                "description": "节点标签/边的关系描述（add_node、add_edge、update_node 时使用）",
            },
            "node_id": {
                "type": "string",
                "description": "节点ID（add_node、update_node、remove_node 时必填）",
            },
            "node_type": {
                "type": "string",
                "description": "节点类型（add_node 时使用），如 module、function、class、data、service、component",
            },
            "group": {
                "type": "string",
                "description": "节点分组（add_node 时使用），如 backend、frontend、utils、python、javascript",
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
            "rich_content": {
                "type": "string",
                "description": "节点内的富内容，Markdown 格式（add_node、update_node 时使用）。支持表格、列表、代码等。",
            },
            "image_url": {
                "type": "string",
                "description": "节点内显示的图片 URL（add_node、update_node 时使用）",
            },
            "background_color": {
                "type": "string",
                "description": "节点背景颜色，如 #1a1a2e（add_node、update_node 时使用）",
            },
            "border_color": {
                "type": "string",
                "description": "节点边框颜色，如 #4B8BBE（add_node、update_node 时使用）",
            },
            "edge_color": {
                "type": "string",
                "description": "边的颜色，如 #e94560（add_edge、update_edge 时使用）",
            },
            "edge_id": {
                "type": "string",
                "description": "边的ID（update_edge 时必填，格式为 e-{source}-{target}）",
            },
            "description": {
                "type": "string",
                "description": "节点描述文本（add_node 时使用）",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> str:
        operation = kwargs.get("operation", "add_edge")

        if operation == "add_node":
            return await self._add_node(kwargs)
        elif operation == "add_edge":
            return await self._add_edge(kwargs)
        elif operation == "update_node":
            return await self._update_node(kwargs)
        elif operation == "update_edge":
            return await self._update_edge(kwargs)
        elif operation == "remove_node":
            return await self._remove_node(kwargs)
        elif operation == "remove_edge":
            return await self._remove_edge(kwargs)
        else:
            return json.dumps({"error": f"Unknown operation: {operation}"}, ensure_ascii=False)

    async def _add_node(self, kwargs: dict) -> str:
        node_id = kwargs.get("node_id", "")
        label = kwargs.get("label", "")
        node_type = kwargs.get("node_type", "module")
        group = kwargs.get("group", "other")
        description = kwargs.get("description", "")
        rich_content = kwargs.get("rich_content", "")
        image_url = kwargs.get("image_url", "")
        background_color = kwargs.get("background_color", "")
        border_color = kwargs.get("border_color", "")

        if not node_id:
            return json.dumps({"error": "node_id is required for add_node"}, ensure_ascii=False)

        cmd = {
            "cmd": "add_node",
            "id": node_id,
            "label": label or node_id,
            "type": node_type,
            "group": group,
            "description": description,
            "richContent": rich_content,
            "imageUrl": image_url,
            "backgroundColor": background_color,
            "borderColor": border_color,
        }

        return json.dumps({
            "node_id": node_id,
            "label": label,
            "type": node_type,
            "group": group,
            "canvas_commands": [cmd],
        }, ensure_ascii=False)

    async def _add_edge(self, kwargs: dict) -> str:
        source_id = kwargs.get("source_id", "") or kwargs.get("source", "")
        target_id = kwargs.get("target_id", "") or kwargs.get("target", "")
        label = kwargs.get("label", "")
        edge_color = kwargs.get("edge_color", "")

        if not source_id or not target_id:
            return json.dumps({"error": "source_id and target_id are required for add_edge"}, ensure_ascii=False)

        cmd = {
            "cmd": "add_edge",
            "source": source_id,
            "target": target_id,
            "label": label,
        }
        if edge_color:
            cmd["edgeColor"] = edge_color

        return json.dumps({
            "source_id": source_id,
            "target_id": target_id,
            "label": label,
            "canvas_commands": [cmd],
        }, ensure_ascii=False)

    async def _update_node(self, kwargs: dict) -> str:
        node_id = kwargs.get("node_id", "")
        new_label = kwargs.get("new_label", "") or kwargs.get("label", "")
        new_type = kwargs.get("new_type", "")
        new_group = kwargs.get("new_group", "")
        rich_content = kwargs.get("rich_content", "")
        image_url = kwargs.get("image_url", "")
        background_color = kwargs.get("background_color", "")
        border_color = kwargs.get("border_color", "")

        if not node_id:
            return json.dumps({"error": "node_id is required for update_node"}, ensure_ascii=False)

        changes = []
        cmd: dict = {"cmd": "update_node", "id": node_id}

        if new_label:
            changes.append(f"label → {new_label}")
            cmd["label"] = new_label
        if new_type:
            changes.append(f"type → {new_type}")
            cmd["type"] = new_type
        if new_group:
            changes.append(f"group → {new_group}")
            cmd["group"] = new_group
        if rich_content:
            changes.append("rich_content updated")
            cmd["richContent"] = rich_content
        if image_url:
            changes.append("image_url updated")
            cmd["imageUrl"] = image_url
        if background_color:
            changes.append("background_color updated")
            cmd["backgroundColor"] = background_color
        if border_color:
            changes.append("border_color updated")
            cmd["borderColor"] = border_color

        return json.dumps({
            "node_id": node_id,
            "changes": ", ".join(changes) if changes else "no changes",
            "canvas_commands": [cmd],
        }, ensure_ascii=False)

    async def _update_edge(self, kwargs: dict) -> str:
        edge_id = kwargs.get("edge_id", "")
        label = kwargs.get("label", "")
        edge_color = kwargs.get("edge_color", "")

        if not edge_id:
            return json.dumps({"error": "edge_id is required for update_edge (format: e-{source}-{target})"}, ensure_ascii=False)

        changes = []
        cmd: dict = {"cmd": "update_edge", "id": edge_id}

        if label:
            changes.append(f"label → {label}")
            cmd["label"] = label
        if edge_color:
            changes.append(f"color → {edge_color}")
            cmd["edgeColor"] = edge_color

        return json.dumps({
            "edge_id": edge_id,
            "changes": ", ".join(changes) if changes else "no changes",
            "canvas_commands": [cmd],
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
        source_id = kwargs.get("source_id", "") or kwargs.get("source", "")
        target_id = kwargs.get("target_id", "") or kwargs.get("target", "")

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