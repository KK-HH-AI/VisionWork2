import json
import os
import re
from .base import BaseTool


def _extract_node_id_from_filename(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    parts = stem.rsplit('_', 1)
    if len(parts) == 2 and re.match(r'^[0-9a-f]{12}$', parts[1]):
        return parts[1]
    return stem


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "在已分析的记忆笔记（.md文件）中搜索相关内容。传入关键词或问题，返回匹配的笔记片段及出处。基于文件内容文本搜索，不依赖向量数据库。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，可以是问题、关键词或概念描述",
            },
            "k": {
                "type": "integer",
                "description": "返回结果数量，默认5",
            },
            "memory_dir": {
                "type": "string",
                "description": "记忆目录路径",
            },
        },
        "required": ["query"],
    }

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        k = kwargs.get("k", 5)
        memory_dir = kwargs.get("memory_dir", "")

        if not query:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)

        if not memory_dir or not os.path.isdir(memory_dir):
            return json.dumps({
                "query": query,
                "results": [],
                "message": f"记忆目录不存在或为空: {memory_dir}",
            }, ensure_ascii=False)

        try:
            keywords = [kw.lower() for kw in query.lower().split() if len(kw) >= 2]
            if not keywords:
                keywords = [query.lower()]

            scored_results = []

            for root, dirs, files in os.walk(memory_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'node_modules']
                for filename in files:
                    if not filename.endswith('.md'):
                        continue
                    filepath = os.path.join(root, filename)

                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except Exception:
                        continue

                    if not content.strip():
                        continue

                    content_lower = content.lower()
                    match_count = 0
                    for kw in keywords:
                        if kw in content_lower:
                            match_count += content_lower.count(kw)

                    if match_count == 0:
                        continue

                    title_score = 0
                    filename_lower = filename.lower()
                    for kw in keywords:
                        if kw in filename_lower:
                            title_score += 3

                    total_score = match_count + title_score

                    node_id = _extract_node_id_from_filename(filename)

                    first_match_idx = min(
                        content_lower.find(kw)
                        for kw in keywords
                        if kw in content_lower
                    )

                    preview_start = max(0, first_match_idx - 100)
                    preview = content[preview_start:preview_start + 500]
                    if preview_start > 0:
                        preview = "..." + preview
                    if preview_start + 500 < len(content):
                        preview = preview + "..."

                    scored_results.append({
                        "node_id": node_id,
                        "filename": filename,
                        "filepath": filepath,
                        "content_preview": preview,
                        "score": total_score,
                    })

            scored_results.sort(key=lambda r: -r["score"])
            scored_results = scored_results[:k]

            if not scored_results:
                return json.dumps({
                    "query": query,
                    "results": [],
                    "message": f"No relevant notes found for query: '{query}'",
                }, ensure_ascii=False)

            return json.dumps({
                "query": query,
                "total_found": len(scored_results),
                "results": scored_results,
            }, ensure_ascii=False)

        except Exception as e:
            return json.dumps({
                "error": f"Search failed: {str(e)}",
                "query": query,
            }, ensure_ascii=False)