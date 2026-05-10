import json
from .base import BaseTool
from ..services.scanner import build_directory_tree


class ScanDirectoryTool(BaseTool):
    name = "scan_directory"
    description = "扫描指定目录结构，返回完整的目录树JSON。用于了解项目文件组织、发现代码文件、构建项目地图。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "folder_path": {
                "type": "string",
                "description": "要扫描的目录的绝对路径",
            }
        },
        "required": ["folder_path"],
    }

    async def execute(self, **kwargs) -> str:
        folder_path = kwargs.get("folder_path", "")
        if not folder_path:
            return json.dumps({"error": "folder_path is required"}, ensure_ascii=False)

        tree = build_directory_tree(folder_path)
        return json.dumps(tree, ensure_ascii=False)