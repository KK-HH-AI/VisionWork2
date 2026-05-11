import os
import json

should_stop = {}


def _extract_json_objects(buffer):
    commands = []
    while True:
        start = buffer.find('{')
        if start == -1:
            break
        depth = 0
        in_string = False
        escape = False
        end = -1
        for i in range(start, len(buffer)):
            c = buffer[i]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if not in_string:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end == -1:
            break
        json_str = buffer[start:end + 1]
        try:
            cmd = json.loads(json_str)
            commands.append(cmd)
        except json.JSONDecodeError:
            pass
        buffer = buffer[end + 1:]
    return commands, buffer


def _create_search_memory_tool(memory_dir, retrieval_path, progress_queue):
    from langchain_core.tools import tool

    @tool
    def search_memory(query: str) -> str:
        """搜索项目记忆库中的代码分析笔记。传入关键词或问题，返回相关的笔记内容摘要。"""
        results = []
        visited_ids = []

        if not os.path.exists(memory_dir):
            return "记忆库目录不存在，请先完成第一层分析。"

        for filename in os.listdir(memory_dir):
            if not filename.endswith('.md'):
                continue
            filepath = os.path.join(memory_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            query_lower = query.lower()
            content_lower = content.lower()
            if query_lower in content_lower or any(
                keyword in content_lower
                for keyword in query_lower.split()
                if len(keyword) >= 2
            ):
                parts = filename.replace('.md', '').rsplit('_', 1)
                node_id = parts[-1] if len(parts) > 1 else filename.replace('.md', '')

                results.append({
                    "filename": filename,
                    "node_id": node_id,
                    "content": content[:600],
                })
                if node_id not in retrieval_path:
                    visited_ids.append(node_id)

        for nid in visited_ids:
            if nid not in retrieval_path:
                retrieval_path.append(nid)

        if visited_ids and progress_queue is not None:
            try:
                progress_queue.put_nowait({
                    "type": "memory_path_update",
                    "nodeIds": list(retrieval_path),
                })
            except Exception:
                pass

        if not results:
            return f"未在记忆库中找到与 '{query}' 直接相关的内容。可尝试使用文件名、模块名或功能关键词进行搜索。"

        output = f"找到 {len(results)} 条相关记忆：\n\n"
        for r in results:
            output += f"---\n### [{r['node_id']}] {r['filename']}\n{r['content']}\n"
        return output

    return search_memory