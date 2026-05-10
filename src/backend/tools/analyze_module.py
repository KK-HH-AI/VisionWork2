import json
import os
import hashlib
from pathlib import Path
from .base import BaseTool
from ..core.prompts import ANALYSIS_PROMPT
from ..utils.graph_utils import generate_node_id, get_file_group
from ..memory.vector_store import get_vector_store


class AnalyzeModuleTool(BaseTool):
    name = "analyze_module"
    description = "接收一个文件路径和内容，调用LLM分析该模块，生成Markdown笔记保存到记忆目录，返回笔记路径和关键摘要。同时在画布上创建模块节点。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "要分析的文件的绝对路径",
            },
            "code_content": {
                "type": "string",
                "description": "文件内容（可通过read_file获取）",
            },
            "filename": {
                "type": "string",
                "description": "文件名",
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
            "profession": {
                "type": "string",
                "description": "分析者职业视角",
            },
            "memory_dir": {
                "type": "string",
                "description": "记忆目录路径",
            },
            "project_path": {
                "type": "string",
                "description": "项目根路径",
            },
        },
        "required": ["filepath", "code_content", "filename"],
    }

    async def execute(self, **kwargs) -> str:
        filepath = kwargs.get("filepath", "")
        code_content = kwargs.get("code_content", "")
        filename = kwargs.get("filename", os.path.basename(filepath) if filepath else "")
        api_url = kwargs.get("api_url", "")
        api_key = kwargs.get("api_key", "")
        model_name = kwargs.get("model_name", "gpt-3.5-turbo")
        profession = kwargs.get("profession", "Software Engineer")
        memory_dir = kwargs.get("memory_dir", "")
        project_path = kwargs.get("project_path", "")

        if not filepath or not code_content:
            return json.dumps({"error": "filepath and code_content are required"}, ensure_ascii=False)

        node_id = generate_node_id(filepath, project_path) if project_path else hashlib.md5(filepath.encode()).hexdigest()[:12]
        group = get_file_group(filename)

        note_content = ""
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                base_url=api_url,
                api_key=api_key,
                model=model_name,
                temperature=0.3,
                max_tokens=2000,
            )

            prompt = ANALYSIS_PROMPT.format(
                profession=profession,
                filename=filename,
                filepath=filepath,
                code_content=code_content[:8000],
            )

            response = llm.invoke(prompt)
            note_content = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            note_content = f"# {filename}\n\n分析失败: {str(e)}\n\n- 类型: {group}\n"

        note_filename = f"{Path(filename).stem}_{node_id}.md"
        note_path = ""
        if memory_dir:
            os.makedirs(memory_dir, exist_ok=True)
            note_path = os.path.join(memory_dir, note_filename)
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(note_content)

            try:
                vector_store = get_vector_store(memory_dir)
                vector_store.add_notes([{
                    "id": node_id,
                    "content": note_content,
                    "filepath": filepath,
                    "filename": filename,
                    "note_path": note_path,
                    "node_id": node_id,
                }])
            except Exception:
                pass

        summary = note_content[:300] if len(note_content) > 300 else note_content

        canvas_commands = [
            {
                "cmd": "add_node",
                "id": node_id,
                "label": filename,
                "type": "module",
                "group": group,
                "description": summary,
                "codeRef": [{"file": filepath, "lines": [1, code_content.count(chr(10)) + 1]}],
            }
        ]

        return json.dumps({
            "node_id": node_id,
            "filename": filename,
            "filepath": filepath,
            "note_path": note_path,
            "summary": summary,
            "group": group,
            "canvas_commands": canvas_commands,
        }, ensure_ascii=False)