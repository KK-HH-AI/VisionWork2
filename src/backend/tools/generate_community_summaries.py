import json
import os
import time
import logging
from pathlib import Path
from collections import defaultdict
from .base import BaseTool

logger = logging.getLogger(__name__)

COMMUNITY_SUMMARY_SYSTEM_PROMPT = """你是一个软件架构分析专家。你的任务是根据提供的社区实体信息和关系，为这个社区生成一个结构化的自然语言摘要。

## 要求
请按以下Markdown格式生成摘要：

## 标题
用一个概括性名称作为标题（如"用户认证模块"、"数据访问层"、"前端UI组件"等）

## 概述
用2-5句话描述这个模块/子系统的核心功能和职责。

## 关键实体
列举最重要的3-5个实体及其作用：
- **实体名** (类型): 作用描述

## 与其他社区的关系
如果社区摘要中提到了与其他社区的关系信息，请在此描述跨社区依赖或协作关系。

注意：
- 只输出Markdown格式的摘要，不要包含任何前缀说明
- 摘要应该在200-500 token之间
- 使用中文描述
- 保持准确，不要编造不存在的关系
"""

COMMUNITY_SUMMARY_C0_PROMPT = """你是一个软件架构分析专家。你的任务是根据提供的项目全局信息和各子社区摘要，为整个项目生成一个高度概括的架构摘要。

## 要求
请按以下Markdown格式生成摘要：

## 标题
项目整体架构概览

## 概述
用3-5句话高度概括整个项目的架构、核心流程和主要组件。

## 关键子系统
列举最重要的3-5个子系统及其职责：
- **子系统名**: 职责描述

## 架构特点
简述项目的整体架构模式和技术特点

注意：
- 只输出Markdown格式的摘要，不要包含任何前缀说明
- 摘要应该在500 token以内
- 使用中文描述
- 保持准确，基于已有信息，不要编造
"""


class GenerateCommunitySummariesTool(BaseTool):
    name = "generate_community_summaries"
    description = "对每个检测到的社区调用LLM生成自然语言描述摘要，保存为community_<level>_<id>.md，并更新communities.json包含summary_path字段。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "项目根目录路径",
            },
            "workspace_root": {
                "type": "string",
                "description": "workspace根目录路径",
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
        },
        "required": ["project_path"],
    }

    async def execute(self, **kwargs) -> str:
        start_time = time.time()
        project_path = kwargs.get("project_path", "")
        workspace_root = kwargs.get("workspace_root", "")
        api_url = kwargs.get("api_url", "")
        api_key = kwargs.get("api_key", "")
        model_name = kwargs.get("model_name", "qwen-plus")

        if not project_path:
            return json.dumps({"error": "project_path is required"}, ensure_ascii=False)

        if not os.path.isdir(project_path):
            return json.dumps({"error": f"project_path does not exist: {project_path}"}, ensure_ascii=False)

        project_name = Path(project_path).name

        if not workspace_root:
            from ..core.config import WORKSPACE_ROOT
            workspace_root = WORKSPACE_ROOT

        graph_dir = os.path.join(workspace_root, project_name, "graph")
        communities_dir = os.path.join(workspace_root, project_name, "communities")

        graph_path = os.path.join(graph_dir, "graph.json")
        communities_path = os.path.join(graph_dir, "communities.json")

        if not os.path.isfile(graph_path):
            return json.dumps({
                "error": f"graph.json not found: {graph_path}. Run build_project_graph first.",
                "project": project_name,
            }, ensure_ascii=False)

        if not os.path.isfile(communities_path):
            return json.dumps({
                "error": f"communities.json not found: {communities_path}. Run build_project_graph first.",
                "project": project_name,
            }, ensure_ascii=False)

        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            with open(communities_path, "r", encoding="utf-8") as f:
                communities_data = json.load(f)

            nodes_index = {n["id"]: n for n in graph_data.get("nodes", [])}
            edges = graph_data.get("edges", [])

            source_target_map = defaultdict(list)
            for edge in edges:
                source_target_map[edge["source"]].append(edge)
                source_target_map[edge["target"]].append(edge)

            layers_count = communities_data.get("layers", 4)
            community_nodes = self._build_community_node_map(communities_data, layers_count)

            llm = None
            if api_url and api_key:
                try:
                    from langchain_openai import ChatOpenAI
                    llm = ChatOpenAI(
                        base_url=api_url,
                        api_key=api_key,
                        model=model_name,
                        temperature=0.3,
                        max_tokens=800,
                    )
                except Exception as e:
                    logger.warning(f"[generate_community_summaries] LLM init failed: {e}")

            os.makedirs(communities_dir, exist_ok=True)

            all_sub_summaries = {}
            summary_count = 0

            for layer in range(layers_count - 1, -1, -1):
                layer_key = f"C{layer}"
                comm_map = community_nodes.get(layer_key, {})

                for comm_id, node_ids in sorted(comm_map.items()):
                    if layer == 0:
                        summary_path = self._generate_c0_summary(
                            node_ids=node_ids,
                            nodes_index=nodes_index,
                            edges=edges,
                            source_target_map=source_target_map,
                            communities_dir=communities_dir,
                            llm=llm,
                            sub_summaries=all_sub_summaries,
                        )
                    else:
                        summary_path = self._generate_community_summary(
                            comm_id=comm_id,
                            layer_key=layer_key,
                            node_ids=node_ids,
                            nodes_index=nodes_index,
                            edges=edges,
                            source_target_map=source_target_map,
                            communities_dir=communities_dir,
                            llm=llm,
                            sub_summaries=all_sub_summaries if layer < layers_count - 1 else None,
                        )

                    if summary_path:
                        all_sub_summaries[f"{layer_key}_{comm_id}"] = summary_path
                        summary_count += 1

            communities_data = self._update_communities_with_summaries(
                communities_data, communities_dir, layers_count, community_nodes
            )

            with open(communities_path, "w", encoding="utf-8") as f:
                json.dump(communities_data, f, ensure_ascii=False, indent=2)

            elapsed = time.time() - start_time
            logger.info(
                f"[generate_community_summaries] Completed in {elapsed:.2f}s: "
                f"{summary_count} community summaries generated"
            )

            return json.dumps({
                "project": project_name,
                "communities_dir": communities_dir,
                "summary_count": summary_count,
                "elapsed_seconds": round(elapsed, 2),
            }, ensure_ascii=False)

        except Exception as e:
            import traceback
            logger.error(f"[generate_community_summaries] Error: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            return json.dumps({
                "error": f"{type(e).__name__}: {str(e)}",
                "project": project_name,
            }, ensure_ascii=False)

    def _build_community_node_map(self, communities_data, layers_count):
        community_nodes = {}
        for layer in range(layers_count):
            community_nodes[f"C{layer}"] = defaultdict(list)

        for node_info in communities_data.get("nodes", []):
            node_id = node_info["id"]
            for layer_key, comm_id in node_info.get("communities", {}).items():
                if layer_key in community_nodes:
                    community_nodes[layer_key][comm_id].append(node_id)

        return community_nodes

    def _generate_community_summary(
        self, comm_id, layer_key, node_ids, nodes_index,
        edges, source_target_map, communities_dir, llm, sub_summaries
    ):
        summary_filename = f"community_{layer_key}_{comm_id}.md"
        summary_path = os.path.join(communities_dir, summary_filename)

        entities_info = []
        for node_id in node_ids:
            if node_id in nodes_index:
                node = nodes_index[node_id]
                entities_info.append({
                    "name": node.get("name", node_id),
                    "type": node.get("type", "unknown"),
                    "description": node.get("description", ""),
                })

        internal_edges = []
        node_set = set(node_ids)
        cross_edges = []

        for edge in edges:
            s = edge["source"]
            t = edge["target"]
            if s in node_set and t in node_set:
                internal_edges.append(edge)
            elif (s in node_set) != (t in node_set):
                cross_edges.append(edge)

        internal_edges_sorted = sorted(
            internal_edges,
            key=lambda e: (1 if e.get("description") else 0),
            reverse=True
        )[:10]

        cross_edges_sorted = sorted(
            cross_edges,
            key=lambda e: (1 if e.get("description") else 0),
            reverse=True
        )[:10]

        entities_text = "\n".join(
            f"- [{e['type']}] {e['name']}: {e.get('description', '无描述')}"
            for e in entities_info[:50]
        ) if entities_info else "(无实体)"

        internal_text = "\n".join(
            f"- {e.get('source', '?')} --[{e.get('type', '?')}]--> {e.get('target', '?')}: {e.get('description', '')}"
            for e in internal_edges_sorted
        ) if internal_edges_sorted else "(无内部关系)"

        cross_text = "\n".join(
            f"- {e.get('source', '?')} --[{e.get('type', '?')}]--> {e.get('target', '?')}: {e.get('description', '')}"
            for e in cross_edges_sorted
        ) if cross_edges_sorted else "(无跨社区关系)"

        sub_summary_text = ""
        if sub_summaries:
            relevant = []
            for key, path in sub_summaries.items():
                if os.path.isfile(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                        relevant.append(f"## 子社区 {key}\n{content[:500]}")
                    except Exception:
                        pass
            if relevant:
                sub_summary_text = "\n\n".join(relevant)

        prompt = f"""请为以下社区生成一个结构化的摘要。

## 社区信息
- 层级: {layer_key}
- 社区ID: {comm_id}
- 实体数量: {len(node_ids)}

## 社区内实体
{entities_text}

## 社区内部关键关系 (Top 10)
{internal_text}

## 跨社区关系
{cross_text}"""

        if sub_summary_text:
            prompt += f"""

## 子社区摘要（供参考）
{sub_summary_text}"""

        summary_content = self._call_llm(llm, prompt)
        if not summary_content:
            summary_content = self._generate_template_summary(
                comm_id, layer_key, entities_info, internal_edges_sorted, cross_edges_sorted
            )

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_content)

        logger.info(f"[generate_community_summaries] Generated summary: {summary_filename}")
        return summary_path

    def _generate_c0_summary(
        self, node_ids, nodes_index, edges, source_target_map,
        communities_dir, llm, sub_summaries
    ):
        summary_filename = "community_C0_0.md"
        summary_path = os.path.join(communities_dir, summary_filename)

        entities_info = []
        for node_id in node_ids:
            if node_id in nodes_index:
                node = nodes_index[node_id]
                entities_info.append({
                    "name": node.get("name", node_id),
                    "type": node.get("type", "unknown"),
                    "description": node.get("description", ""),
                })

        top_entities = sorted(
            entities_info,
            key=lambda e: len(e.get("description", "")),
            reverse=True
        )[:30]

        entities_text = "\n".join(
            f"- [{e['type']}] {e['name']}: {e.get('description', '无描述')}"
            for e in top_entities
        ) if top_entities else "(无实体)"

        top_edges = sorted(
            edges,
            key=lambda e: (1 if e.get("description") else 0),
            reverse=True
        )[:20]

        edges_text = "\n".join(
            f"- {e.get('source', '?')} --[{e.get('type', '?')}]--> {e.get('target', '?')}: {e.get('description', '')}"
            for e in top_edges
        ) if top_edges else "(无关系)"

        sub_summary_text = ""
        if sub_summaries:
            relevant = []
            for key, path in list(sub_summaries.items())[:10]:
                if os.path.isfile(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                        relevant.append(f"## 子社区 {key}\n{content[:400]}")
                    except Exception:
                        pass
            if relevant:
                sub_summary_text = "\n\n".join(relevant)

        prompt = f"""请为整个项目生成一个高度概括的架构摘要。

## 项目统计
- 总实体数: {len(node_ids)}
- 总关系数: {len(edges)}

## 核心实体（按描述丰富度排序Top 30）
{entities_text}

## 关键关系（Top 20）
{edges_text}"""

        if sub_summary_text:
            prompt += f"""

## 子社区摘要（供参考）
{sub_summary_text}"""

        summary_content = self._call_c0_llm(llm, prompt)
        if not summary_content:
            summary_content = f"# 项目整体架构概览\n\n该项目包含 {len(node_ids)} 个实体和 {len(edges)} 个关系。\n\n"

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_content)

        logger.info(f"[generate_community_summaries] Generated C0 summary: {summary_filename}")

    def _call_llm(self, llm, prompt):
        if llm is None:
            return None

        try:
            full_prompt = COMMUNITY_SUMMARY_SYSTEM_PROMPT + "\n\n" + prompt
            response = llm.invoke(full_prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            return content.strip()
        except Exception as e:
            logger.warning(f"[generate_community_summaries] LLM call failed: {e}")
            return None

    def _call_c0_llm(self, llm, prompt):
        if llm is None:
            return None

        try:
            full_prompt = COMMUNITY_SUMMARY_C0_PROMPT + "\n\n" + prompt
            response = llm.invoke(full_prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            return content.strip()
        except Exception as e:
            logger.warning(f"[generate_community_summaries] C0 LLM call failed: {e}")
            return None

    def _generate_template_summary(self, comm_id, layer_key, entities_info, internal_edges, cross_edges):
        entity_types = {}
        for e in entities_info[:20]:
            t = e.get("type", "unknown")
            entity_types[t] = entity_types.get(t, 0) + 1

        type_summary = "、".join(f"{cnt}个{v}" for v, cnt in sorted(entity_types.items(), key=lambda x: -x[1])[:5])

        top_names = [e["name"] for e in entities_info[:5]]

        lines = [
            f"# 社区 {layer_key}-{comm_id}",
            "",
            "## 概述",
            "",
            f"该社区包含 {len(entities_info)} 个实体，类型分布: {type_summary}。",
            f"核心实体包括: {', '.join(top_names)}。",
            "",
            "## 关键实体",
            "",
        ]

        for e in entities_info[:5]:
            lines.append(f"- **{e['name']}** ({e['type']}): {e.get('description', '无描述')}")

        if internal_edges:
            lines.append("")
            lines.append("## 社区内部关键关系")
            lines.append("")
            for e in internal_edges[:5]:
                lines.append(f"- `{e.get('source', '?')}` --[{e.get('type', '?')}]--> `{e.get('target', '?')}`: {e.get('description', '')}")

        if cross_edges:
            lines.append("")
            lines.append("## 跨社区关系")
            lines.append("")
            for e in cross_edges[:5]:
                lines.append(f"- `{e.get('source', '?')}` --[{e.get('type', '?')}]--> `{e.get('target', '?')}`: {e.get('description', '')}")

        return "\n".join(lines)

    def _update_communities_with_summaries(self, communities_data, communities_dir, layers_count, community_nodes):
        summary_list = []

        for layer in range(layers_count):
            layer_key = f"C{layer}"
            comm_map = community_nodes.get(layer_key, {})

            for comm_id in comm_map.keys():
                summary_filename = f"community_{layer_key}_{comm_id}.md"
                summary_path = os.path.join(communities_dir, summary_filename)
                if os.path.isfile(summary_path):
                    summary_list.append({
                        "layer": layer_key,
                        "community_id": comm_id,
                        "node_count": len(comm_map[comm_id]),
                        "summary_path": summary_path,
                        "summary_filename": summary_filename,
                    })

        communities_data["community_summaries"] = summary_list
        return communities_data