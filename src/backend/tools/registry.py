import os
import yaml
from typing import Dict, Any, List, Optional
from .base import BaseTool
from .scan import ScanDirectoryTool


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tools: Dict[str, BaseTool] = {}
        self._skill_descriptions: Dict[str, Dict[str, Any]] = {}
        self._load_skills()
        self._register_tools()

    def _load_skills(self):
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
        if not os.path.isdir(skills_dir):
            return

        for filename in os.listdir(skills_dir):
            if not filename.endswith((".yml", ".yaml")):
                continue
            filepath = os.path.join(skills_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f)
                if skill_data and "name" in skill_data:
                    self._skill_descriptions[skill_data["name"]] = skill_data
            except Exception:
                pass

    def _register_tools(self):
        tool_classes = [ScanDirectoryTool]
        for tool_cls in tool_classes:
            tool_instance = tool_cls()
            self._tools[tool_instance.name] = tool_instance

    @property
    def tool_definitions(self) -> List[Dict[str, Any]]:
        definitions = []
        for tool in self._tools.values():
            definitions.append(tool.to_tool_definition())
        return definitions

    @property
    def tools_description(self) -> str:
        lines = []
        for skill_name, skill_data in self._skill_descriptions.items():
            desc = skill_data.get("description", "")
            params = skill_data.get("parameters", {})
            param_desc = ", ".join(
                f"{k}({v.get('type', 'string')})" for k, v in params.items()
            )
            lines.append(f"- {skill_name}: {desc} 参数: {param_desc}")
        return "\n".join(lines)

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f'{{"error": "Unknown tool: {name}"}}'
        return await tool.execute(**args)


tool_registry = ToolRegistry()