import json
from .base import BaseTool
from ..memory.vector_store import get_vector_store


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "通过向量语义搜索在已分析的笔记中查找相关内容。传入问题或关键词，返回最相关的笔记片段及出处。"
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

        if not memory_dir:
            return json.dumps({"error": "memory_dir is required for vector search"}, ensure_ascii=False)

        try:
            vector_store = get_vector_store(memory_dir)
            results = vector_store.search(query, k=k)

            if not results:
                return json.dumps({
                    "query": query,
                    "results": [],
                    "message": f"No relevant notes found for query: '{query}'",
                }, ensure_ascii=False)

            formatted_results = []
            for r in results:
                formatted_results.append({
                    "node_id": r.get("node_id", ""),
                    "filename": r.get("filename", ""),
                    "filepath": r.get("filepath", ""),
                    "content_preview": r.get("content", "")[:500],
                    "score": r.get("score", 0),
                })

            return json.dumps({
                "query": query,
                "total_found": len(results),
                "results": formatted_results,
            }, ensure_ascii=False)

        except Exception as e:
            return json.dumps({
                "error": f"Vector search failed: {str(e)}",
                "query": query,
            }, ensure_ascii=False)