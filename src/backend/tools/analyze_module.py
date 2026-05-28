import json
import os
import hashlib
import logging
import time
from pathlib import Path
from .base import BaseTool
from ..core.prompts import (
    GENERAL_ANALYSIS_PROMPT,
    ENTITY_DESCRIPTION_PROMPT,
    FALLBACK_EXTRACTION_PROMPT,
    FALLBACK_NOTE_PROMPT,
)
from ..utils.graph_utils import generate_node_id, get_file_group

logger = logging.getLogger(__name__)


class AnalyzeModuleTool(BaseTool):
    name = "analyze_module"
    description = "接收一个文件路径和内容，调用LLM分析该文件（代码/文档/配置/数据等），生成Markdown笔记保存到记忆目录，返回笔记路径和关键摘要。同时在画布上创建模块节点。"
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
        start_time = time.time()
        filepath = kwargs.get("filepath", "")
        code_content = kwargs.get("code_content", "")
        filename = kwargs.get("filename", os.path.basename(filepath) if filepath else "")
        api_url = kwargs.get("api_url", "")
        api_key = kwargs.get("api_key", "")
        model_name = kwargs.get("model_name", "qwen-plus")
        memory_dir = kwargs.get("memory_dir", "")
        project_path = kwargs.get("project_path", "")

        if not filepath or not code_content:
            return json.dumps({"error": "filepath and code_content are required"}, ensure_ascii=False)

        node_id = generate_node_id(filepath, project_path) if project_path else hashlib.md5(filepath.encode()).hexdigest()[:12]
        group = get_file_group(filename)

        note_content = ""
        entities_data = {"entities": [], "relations": []}
        used_fallback = False

        try:
            from .code_parser import parse_code_entities, _get_language_from_filename

            language = _get_language_from_filename(filename)

            if language:
                logger.info(f"[analyze_module] File '{filename}' detected as '{language}', using hybrid path")
                parse_result = parse_code_entities(code_content, language)

                if parse_result is not None:
                    entities = parse_result.get('entities', [])
                    relations = parse_result.get('relations', [])

                    for e in entities:
                        e['file'] = filename
                        e['id'] = f"{filename}:{e['id']}"

                    for r in relations:
                        r['source_id'] = f"{filename}:{r['source_id']}"
                        if r['target_id'] and not r['target_id'].startswith(filename):
                            if not any(c in r['target_id'] for c in './'):
                                pass

                    entities = await _generate_descriptions(
                        entities, code_content, api_url, api_key, model_name
                    )

                    note_content = await _generate_note_from_entities(
                        entities, relations, filename, filepath,
                        api_url, api_key, model_name
                    )

                    entities_data = {
                        "entities": entities,
                        "relations": relations,
                    }

                    logger.info(
                        f"[analyze_module] Hybrid path completed: {len(entities)} entities, "
                        f"{len(relations)} relations for '{filename}'"
                    )
                else:
                    logger.info(f"[analyze_module] Static parsing failed for '{filename}', falling back to LLM")
                    entities_data, note_content = await _fallback_llm_extraction(
                        code_content, filename, filepath, api_url, api_key, model_name
                    )
                    used_fallback = True
            else:
                logger.info(f"[analyze_module] Unsupported language for '{filename}', using LLM fallback")
                entities_data, note_content = await _fallback_llm_extraction(
                    code_content, filename, filepath, api_url, api_key, model_name
                )
                used_fallback = True

        except Exception as e:
            logger.warning(f"[analyze_module] Hybrid path exception: {type(e).__name__}: {e}, falling back to LLM")
            try:
                entities_data, note_content = await _fallback_llm_extraction(
                    code_content, filename, filepath, api_url, api_key, model_name
                )
                used_fallback = True
            except Exception as fallback_error:
                logger.error(f"[analyze_module] Fallback also failed: {fallback_error}")
                note_content = f"# {filename}\n\n分析失败: {str(fallback_error)}\n\n- 类型: {group}\n"
                entities_data = {"entities": [], "relations": []}

        if not note_content:
            note_content = f"# {filename}\n\n- 类型: {group}\n"

        note_filename = f"{Path(filename).stem}_{node_id}.md"
        note_path = ""
        entities_path = ""
        if memory_dir:
            os.makedirs(memory_dir, exist_ok=True)
            note_path = os.path.join(memory_dir, note_filename)
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(note_content)

            entities_filename = f"{Path(filename).stem}_{node_id}_entities.json"
            entities_path = os.path.join(memory_dir, entities_filename)
            with open(entities_path, 'w', encoding='utf-8') as f:
                json.dump(entities_data, f, ensure_ascii=False, indent=2)

            try:
                from .memory_vector_store import init_vector_store, add_notes
                storage_path = os.path.dirname(memory_dir)
                collection = init_vector_store(storage_path)
                add_notes(collection, [{
                    "content": note_content,
                    "filepath": filepath,
                    "filename": filename,
                }])
            except Exception as e:
                logger.warning(f"[analyze_module] Vector store update failed: {type(e).__name__}: {e}")

        summary = note_content[:300] if len(note_content) > 300 else note_content

        elapsed = time.time() - start_time
        logger.info(
            f"[analyze_module] Completed '{filename}' in {elapsed:.2f}s "
            f"(fallback={used_fallback}, entities={len(entities_data.get('entities', []))})"
        )

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
            "entities_path": entities_path,
            "summary": summary,
            "group": group,
            "canvas_commands": canvas_commands,
            "entity_count": len(entities_data.get("entities", [])),
            "relation_count": len(entities_data.get("relations", [])),
            "used_fallback": used_fallback,
            "elapsed_seconds": round(elapsed, 2),
        }, ensure_ascii=False)


async def _generate_descriptions(entities, code_content, api_url, api_key, model_name):
    if not api_url or not api_key:
        return entities

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            base_url=api_url,
            api_key=api_key,
            model=model_name,
            temperature=0,
            max_tokens=256,
        )

        lines = code_content.split('\n')

        for entity in entities:
            if entity.get('description'):
                continue

            line_start = entity.get('line_start', 1)
            line_end = entity.get('line_end', line_start)
            context_start = max(0, line_start - 3)
            context_end = min(len(lines), line_end + 3)
            snippet = '\n'.join(lines[context_start:context_end])

            if len(snippet) > 2000:
                snippet = snippet[:2000]

            prompt = ENTITY_DESCRIPTION_PROMPT.format(
                type=entity.get('type', 'unknown'),
                name=entity.get('name', 'unknown'),
                code_snippet=snippet,
            )

            try:
                response = llm.invoke(prompt)
                description = response.content if hasattr(response, 'content') else str(response)
                description = description.strip()[:100]
                entity['description'] = description
            except Exception as e:
                logger.debug(f"Description generation failed for {entity['name']}: {e}")
                entity['description'] = ''

    except Exception as e:
        logger.warning(f"Description generation disabled: {e}")

    return entities


async def _generate_note_from_entities(entities, relations, filename, filepath, api_url, api_key, model_name):
    if not api_url or not api_key:
        return _generate_template_note(entities, relations, filename, filepath)

    try:
        from langchain_openai import ChatOpenAI

        entity_lines = []
        for e in entities[:30]:
            desc = e.get('description', '')
            entity_lines.append(f"- [{e.get('type', '?')}] {e.get('name', '?')}: {desc}")

        entities_summary = '\n'.join(entity_lines) if entity_lines else '(无实体)'

        relation_lines = []
        for r in relations[:30]:
            relation_lines.append(f"- {r.get('source_id', '?')} --[{r.get('type', '?')}]--> {r.get('target_id', '?')}")
        relations_summary = '\n'.join(relation_lines) if relation_lines else '(无关系)'

        prompt = FALLBACK_NOTE_PROMPT.format(
            filename=filename,
            filepath=filepath,
            entities_summary=entities_summary + '\n\n## 关系列表\n' + relations_summary,
        )

        llm = ChatOpenAI(
            base_url=api_url,
            api_key=api_key,
            model=model_name,
            temperature=0.3,
            max_tokens=2000,
        )

        response = llm.invoke(prompt)
        return response.content if hasattr(response, 'content') else str(response)

    except Exception as e:
        logger.warning(f"Note generation via LLM failed: {e}")
        return _generate_template_note(entities, relations, filename, filepath)


def _generate_template_note(entities, relations, filename, filepath):
    lines = [
        f"# {filename}",
        f"",
        f"## 文件概述",
        f"",
        f"路径: {filepath}",
        f"",
        f"## 关键实体",
        f"",
    ]

    for e in entities:
        name = e.get('name', '?')
        etype = e.get('type', '?')
        desc = e.get('description', '')
        lines.append(f"- **[{etype}]** `{name}` {desc}")

    if relations:
        lines.append("")
        lines.append("## 关系")
        lines.append("")
        for r in relations:
            lines.append(f"- `{r.get('source_id', '?')}` → `{r.get('target_id', '?')}` ({r.get('type', '?')})")

    return '\n'.join(lines)


async def _fallback_llm_extraction(code_content, filename, filepath, api_url, api_key, model_name):
    entities_data = {"entities": [], "relations": []}
    note_content = ""

    if not api_url or not api_key:
        note_content = f"# {filename}\n\nLLM不可用，无法进行降级分析。\n"
        return entities_data, note_content

    try:
        from langchain_openai import ChatOpenAI

        content_for_llm = code_content
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(code_content)
            if len(tokens) > 6000:
                logger.info(f"[analyze_module] File '{filename}' has {len(tokens)} tokens, chunking for fallback")
                chunks = _chunk_content(code_content, tokens, enc)
                all_entities = []
                all_relations = []
                seen_entity_ids = set()

                for i, chunk in enumerate(chunks):
                    chunk_result, _ = await _extract_entities_via_llm(
                        chunk, filename, filepath, api_url, api_key, model_name
                    )
                    for e in chunk_result.get('entities', []):
                        eid = e.get('id', '')
                        if eid not in seen_entity_ids:
                            seen_entity_ids.add(eid)
                            all_entities.append(e)
                    for r in chunk_result.get('relations', []):
                        key = (r.get('source_id'), r.get('target_id'), r.get('type'))
                        all_relations.append(r)

                entities_data = {"entities": all_entities, "relations": all_relations}
                note_content = await _generate_note_from_entities(
                    all_entities, all_relations, filename, filepath, api_url, api_key, model_name
                )
                return entities_data, note_content
        except ImportError:
            logger.debug("tiktoken not available, using raw content truncation")
            content_for_llm = code_content[:12000]

        entities_data, note_content = await _extract_entities_via_llm(
            content_for_llm, filename, filepath, api_url, api_key, model_name
        )
        return entities_data, note_content

    except Exception as e:
        logger.error(f"[analyze_module] Fallback LLM extraction failed: {e}")
        return {"entities": [], "relations": []}, f"# {filename}\n\n降级分析失败: {str(e)}\n"


async def _extract_entities_via_llm(content, filename, filepath, api_url, api_key, model_name):
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        base_url=api_url,
        api_key=api_key,
        model=model_name,
        temperature=0.3,
        max_tokens=4000,
    )

    prompt = FALLBACK_EXTRACTION_PROMPT.format(
        filename=filename,
        filepath=filepath,
        content=content,
    )

    response = llm.invoke(prompt)
    response_text = response.content if hasattr(response, 'content') else str(response)
    response_text = response_text.strip()

    if response_text.startswith('```'):
        lines = response_text.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        response_text = '\n'.join(lines)

    try:
        data = json.loads(response_text)
        entities = data.get('entities', [])
        relations = data.get('relations', [])
    except json.JSONDecodeError:
        logger.warning("Fallback LLM response was not valid JSON, returning empty")
        entities = []
        relations = []

    entities_data = {"entities": entities, "relations": relations}
    note_content = await _generate_note_from_entities(
        entities, relations, filename, filepath, api_url, api_key, model_name
    )

    return entities_data, note_content


def _chunk_content(code_content, tokens, enc, max_tokens=6000, overlap=200):
    chunks = []
    i = 0
    while i < len(tokens):
        end = min(i + max_tokens, len(tokens))
        chunk_tokens = tokens[i:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text)
        if end >= len(tokens):
            break
        i = end - overlap

    return chunks