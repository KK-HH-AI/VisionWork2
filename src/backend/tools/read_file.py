import json
from .base import BaseTool
from ..utils.file_utils import read_file_content


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取指定文件的源代码内容，返回内容摘要（截断大文件）。用于了解单个文件的代码实现。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "要读取的文件的绝对路径",
            }
        },
        "required": ["filepath"],
    }

    async def execute(self, **kwargs) -> str:
        filepath = kwargs.get("filepath", "")
        if not filepath:
            return json.dumps({"error": "filepath is required"}, ensure_ascii=False)

        import os
        if not os.path.isfile(filepath):
            return json.dumps({"error": f"File not found: {filepath}"}, ensure_ascii=False)

        content = read_file_content(filepath)
        if content is None:
            return json.dumps({"error": f"Cannot read file (possibly binary): {filepath}"}, ensure_ascii=False)

        filename = os.path.basename(filepath)
        preview = content[:2000] if len(content) > 2000 else content
        truncated = len(content) > 2000

        return json.dumps({
            "filename": filename,
            "filepath": filepath,
            "content": preview,
            "total_length": len(content),
            "truncated": truncated,
        }, ensure_ascii=False)