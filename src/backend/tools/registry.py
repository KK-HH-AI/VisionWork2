# 文件：tool_registry.py
# 职责：管理所有工具（技能）的注册、描述生成、配置过滤和执行
# 采用单例模式，确保全局唯一

import os
import yaml
import json
from typing import Dict, Any, List, Optional

# 引入工具基类和各个具体工具
from .base import BaseTool
from .scan import ScanDirectoryTool
from .read_file import ReadFileTool
from .analyze_module import AnalyzeModuleTool
from .draw_relation import DrawRelationTool
from .search_memory import SearchMemoryTool
from .final_answer import FinalAnswerTool
from .canvas_read import CanvasReadTool
from .generate_canvas import GenerateCanvasTool
from .build_project_graph import BuildProjectGraphTool


class ToolRegistry:
    """
    工具注册中心（单例模式）：
    - 加载技能描述文件（YAML）用于生成工具说明
    - 注册全部可用工具实例
    - 根据 skills_config.json 决定哪些工具启用
    - 提供同步/异步执行接口
    """
    _instance: Optional["ToolRegistry"] = None  # 单例存储

    def __new__(cls) -> "ToolRegistry":
        # 保证整个进程只有一个 ToolRegistry 实例
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False  # 标记是否已完成初始化
        return cls._instance

    def __init__(self):
        # 由于是单例，只初始化一次
        if self._initialized:
            return
        self._initialized = True

        self._tools: Dict[str, BaseTool] = {}                     # 工具名 -> 工具实例
        self._skill_descriptions: Dict[str, Dict[str, Any]] = {}  # 技能名称 -> 技能描述数据（从YAML读取）
        self._load_skills()        # 加载所有 skills/*.yml 文件，提取技能描述
        self._register_tools()    # 注册所有内置工具实例

    def _load_skills(self):
        """
        从 skills 目录加载所有 .yml/.yaml 文件，解析后存入 _skill_descriptions。
        每个 YAML 应包含 name、description、parameters 等字段，
        用于后续生成面向 LLM 的工具描述文本。
        """
        # 定位 skills 目录（当前文件的上两级目录中的 skills 文件夹）
        skills_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills"
        )
        if not os.path.isdir(skills_dir):
            return  # 目录不存在则跳过

        for filename in os.listdir(skills_dir):
            if not filename.endswith((".yml", ".yaml")):
                continue
            filepath = os.path.join(skills_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f)
                # 只保存包含 name 字段的有效技能描述
                if skill_data and "name" in skill_data:
                    self._skill_descriptions[skill_data["name"]] = skill_data
            except Exception:
                pass  # 文件格式错误则忽略

    def _register_tools(self):
        """
        实例化所有硬编码的工具类，并存入 _tools 字典。
        工具名称由实例的 name 属性决定。
        """
        tool_classes = [
            ScanDirectoryTool,
            ReadFileTool,
            AnalyzeModuleTool,
            DrawRelationTool,
            SearchMemoryTool,
            FinalAnswerTool,
            CanvasReadTool,
            GenerateCanvasTool,
            BuildProjectGraphTool,
        ]
        for tool_cls in tool_classes:
            tool_instance = tool_cls()            # 创建工具实例
            self._tools[tool_instance.name] = tool_instance # 工具实例列表

    @property
    def tool_definitions(self) -> List[Dict[str, Any]]:
        """
        生成所有“已启用”工具的定义列表（LLM 函数调用格式）。
        会读取 skills_config.json 中的 enabled 字段做过滤，
        默认 enabled 为 True。
        """
        definitions = []
        skills_config = self._load_skills_config()  # 加载启用/禁用配置
        for tool in self._tools.values():
            # 检查该工具是否在配置中被禁用
            enabled = skills_config.get(tool.name, {}).get("enabled", True)
            if enabled:
                definitions.append(tool.to_tool_definition())
        return definitions

    @property
    def tools_description(self) -> str:
        """
        生成用于 Prompt 的纯文本工具描述。
        从 _skill_descriptions 中读取描述和参数信息，
        同样受 skills_config 中的 enabled 控制。
        """
        lines = []
        skills_config = self._load_skills_config()
        for skill_name, skill_data in self._skill_descriptions.items():
            enabled = skills_config.get(skill_name, {}).get("enabled", True)
            if not enabled:
                continue
            desc = skill_data.get("description", "")
            params = skill_data.get("parameters", {})
            # 构造参数描述字符串：name(type), age(integer)
            param_desc = ", ".join(
                f"{k}({v.get('type', 'string')})" for k, v in params.items()
            )
            lines.append(f"- {skill_name}: {desc} 参数: {param_desc}")
        return "\n".join(lines)

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """
        异步执行工具（在已有的异步上下文中使用）。
        步骤：
        1. 查找工具实例
        2. 检查是否启用
        3. 调用 tool.execute(**args)
        """
        tool = self._tools.get(name)
        if not tool:
            return f'{{"error": "Unknown tool: {name}"}}'

        skills_config = self._load_skills_config()
        enabled = skills_config.get(name, {}).get("enabled", True)
        if not enabled:
            return f'{{"error": "Tool {name} is disabled"}}'

        return await tool.execute(**args)

    def execute_tool_sync(self, name: str, args: Dict[str, Any]) -> str:
        """
        同步执行工具（可能被同步代码或嵌套事件循环环境调用）。
        处理策略：
        - 若当前没有运行的事件循环，直接用 asyncio.run() 执行
        - 若已有事件循环正在运行（如 Jupyter notebook 或某些框架），
          则在新线程中运行异步任务，避免嵌套循环冲突
        """
        tool = self._tools.get(name)
        if not tool:
            return f'{{"error": "Unknown tool: {name}"}}'

        skills_config = self._load_skills_config()
        enabled = skills_config.get(name, {}).get("enabled", True)
        if not enabled:
            return f'{{"error": "Tool {name} is disabled"}}'

        import asyncio
        import traceback
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已有运行中的循环，通过线程池在新线程中执行异步代码，防止冲突
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_tool_async, tool, args)
                    return future.result(timeout=30)  # 最长等待 30 秒
            else:
                # 没有运行中的循环，直接在该线程内创建临时事件循环并运行
                return asyncio.run(tool.execute(**args))
        except RuntimeError:
            # 在某些环境下 get_event_loop 可能抛出 RuntimeError（例如无当前循环），
            # 此时也采用 asyncio.run()
            return asyncio.run(tool.execute(**args))
        except Exception as e:
            # 捕获并记录所有执行异常，以 JSON 错误信息返回
            print(f"[registry] Tool execution error for '{name}': {type(e).__name__}: {e}")
            print(f"[registry] Args: {args}")
            print(f"[registry] Traceback: {traceback.format_exc()}")
            return json.dumps({"error": f"{type(e).__name__}: {str(e)}"}, ensure_ascii=False)

    @staticmethod
    def _run_tool_async(tool, args: Dict[str, Any]) -> str:
        """
        静态辅助方法：在新线程中运行工具的异步 execute 方法。
        主要用于 execute_tool_sync 中的线程池调度。
        """
        import asyncio
        return asyncio.run(tool.execute(**args))

    def _load_skills_config(self) -> Dict[str, Any]:
        """
        加载 skills/skills_config.json 配置文件。
        文件格式示例：
        {
            "scan_directory": { "enabled": true },
            "draw_relation": { "enabled": false }
        }
        若文件不存在或解析失败，返回空字典（默认全部启用）。
        """
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "skills_config.json"
        )
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass  # 解析错误则忽略，返回空配置
        return {}


# 模块级单例：供外部直接 import 使用
tool_registry = ToolRegistry()