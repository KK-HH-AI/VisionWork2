import json
import os
import re
import logging
from .base import BaseTool

logger = logging.getLogger(__name__)


def _extract_node_id_from_filename(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    parts = stem.rsplit('_', 1)
    if len(parts) == 2 and re.match(r'^[0-9a-f]{12}$', parts[1]):
        return parts[1]
    return stem


def _keyword_search(memory_dir: str, query: str, k: int) -> list:
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
                "score": float(total_score),
                "source_type": "note",
            })

    scored_results.sort(key=lambda r: -r["score"])
    return scored_results[:k]


def _try_vector_search(memory_dir: str, query: str, k: int, search_type: str) -> list:
    storage_path = os.path.dirname(memory_dir) if memory_dir else ""
    if not storage_path:
        return []

    try:
        from .memory_vector_store import init_vector_store, query_vector_store, get_collection_count
    except Exception as e:
        logger.debug(f"[search_memory] Cannot import vector store module: {e}")
        return []

    try:
        collection = init_vector_store(storage_path)
    except Exception as e:
        logger.debug(f"[search_memory] Vector store init failed: {e}")
        return []

    doc_count = get_collection_count(collection)
    if doc_count == 0:
        logger.debug(f"[search_memory] Vector store is empty, falling back to keyword search")
        return []

    try:
        vector_results = query_vector_store(collection, query, k, search_type)
    except Exception as e:
        logger.warning(f"[search_memory] Vector query failed: {e}, falling back to keyword search")
        return []

    if not vector_results:
        logger.debug(f"[search_memory] Vector search returned no results")
        return []

    formatted_results = []
    for vr in vector_results:
        metadata = vr.get("metadata", {})
        source_type = metadata.get("source_type", "note")
        result = {
            "score": vr.get("score", 0),
            "source_type": source_type,
        }

        if source_type == "note":
            filepath = metadata.get("filepath", "")
            filename = metadata.get("filename", "")
            node_id = _extract_node_id_from_filename(filename)
            result["node_id"] = node_id
            result["filename"] = filename
            result["filepath"] = filepath

            content_preview = vr.get("content", "")
            if content_preview and len(content_preview) > 500:
                content_preview = content_preview[:500] + "..."
            result["content_preview"] = content_preview

        elif source_type == "community":
            summary_path = metadata.get("summary_path", "")
            level = metadata.get("level", "")
            community_id = metadata.get("community_id", "")
            result["summary_path"] = summary_path
            result["level"] = level
            result["community_id"] = community_id

            content_preview = vr.get("content", "")
            if content_preview and len(content_preview) > 500:
                content_preview = content_preview[:500] + "..."
            result["content_preview"] = content_preview

        formatted_results.append(result)

    return formatted_results


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "通过向量语义搜索在已分析的笔记中查找相关内容。传入问题或关键词，返回最相关的笔记片段及出处。优先使用向量语义搜索，无法使用向量库时自动降级为关键词搜索。"
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
            "search_type": {
                "type": "string",
                "description": "搜索类型：note（仅笔记）、community（仅社区摘要）、all（全部），默认all",
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
        search_type = kwargs.get("search_type", "all")
        memory_dir = kwargs.get("memory_dir", "")

        if not query:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)

        used_vector = False
        results = []

        if memory_dir and os.path.isdir(memory_dir):
            vector_results = _try_vector_search(memory_dir, query, k, search_type)
            if vector_results:
                results = vector_results
                used_vector = True
                logger.info(
                    f"[search_memory] Vector search returned {len(results)} results "
                    f"for query '{query[:50]}...' (type={search_type})"
                )

        if not used_vector:
            if memory_dir and os.path.isdir(memory_dir):
                logger.info(
                    f"[search_memory] Falling back to keyword search for query '{query[:50]}...'"
                )
                results = _keyword_search(memory_dir, query, k)
            else:
                return json.dumps({
                    "query": query,
                    "results": [],
                    "message": f"记忆目录不存在或为空: {memory_dir}",
                }, ensure_ascii=False)

        if not results:
            return json.dumps({
                "query": query,
                "results": [],
                "message": f"No relevant results found for query: '{query}'",
                "search_method": "vector" if used_vector else "keyword",
            }, ensure_ascii=False)

        return json.dumps({
            "query": query,
            "total_found": len(results),
            "results": results,
            "search_method": "vector" if used_vector else "keyword",
        }, ensure_ascii=False)