import json
import os
import time
import logging
from collections import Counter
from pathlib import Path
from .base import BaseTool

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

try:
    import community as community_louvain
    HAS_LOUVAIN = True
except ImportError:
    HAS_LOUVAIN = False


class BuildProjectGraphTool(BaseTool):
    name = "build_project_graph"
    description = "读取项目中所有_entities.json文件，构建全局知识图谱，进行层次社区检测，并将图谱和社区归属保存到workspace/<项目>/graph/下。"
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
            "max_layers": {
                "type": "integer",
                "description": "最大社区层次深度，默认4（C0-C3）",
            },
            "resolution": {
                "type": "number",
                "description": "社区检测分辨率参数，默认1.0（值越小社区越大）",
            },
        },
        "required": ["project_path"],
    }

    async def execute(self, **kwargs) -> str:
        start_time = time.time()
        project_path = kwargs.get("project_path", "")
        workspace_root = kwargs.get("workspace_root", "")
        max_layers = kwargs.get("max_layers", 4)
        resolution = kwargs.get("resolution", 1.0)

        if not project_path:
            return json.dumps({"error": "project_path is required"}, ensure_ascii=False)

        if not os.path.isdir(project_path):
            return json.dumps({"error": f"project_path does not exist: {project_path}"}, ensure_ascii=False)

        if not HAS_NETWORKX:
            return json.dumps({"error": "networkx is not installed. Run: pip install networkx"}, ensure_ascii=False)

        if not HAS_LOUVAIN:
            return json.dumps({"error": "python-louvain is not installed. Run: pip install python-louvain"}, ensure_ascii=False)

        project_name = Path(project_path).name

        if not workspace_root:
            from ..core.config import WORKSPACE_ROOT
            workspace_root = WORKSPACE_ROOT

        memory_dir = os.path.join(workspace_root, project_name, "memory")
        graph_dir = os.path.join(workspace_root, project_name, "graph")

        if not os.path.isdir(memory_dir):
            return json.dumps({
                "error": f"Memory directory not found: {memory_dir}. Run analysis first.",
                "project": project_name,
                "memory_dir": memory_dir,
            }, ensure_ascii=False)

        try:
            all_entities, all_relations = self._load_all_entities(memory_dir)
            logger.info(f"[build_project_graph] Loaded {len(all_entities)} raw entities and {len(all_relations)} raw relations")

            merged_entities = self._merge_entities(all_entities)
            merged_relations = self._merge_relations(all_relations)
            logger.info(f"[build_project_graph] After merge: {len(merged_entities)} entities, {len(merged_relations)} relations")

            if len(merged_entities) == 0:
                return json.dumps({
                    "error": "No entities found in memory directory. Run analysis first.",
                    "project": project_name,
                    "memory_dir": memory_dir,
                }, ensure_ascii=False)

            G = self._build_graph(merged_entities, merged_relations)
            logger.info(f"[build_project_graph] Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

            communities = self._hierarchical_community_detection(
                G, max_layers=max_layers, resolution=resolution
            )

            community_tree = self._build_community_tree(G, communities)

            graph_data = {
                "project": project_name,
                "node_count": G.number_of_nodes(),
                "edge_count": G.number_of_edges(),
                "nodes": [],
                "edges": [],
            }

            for node_id in G.nodes():
                entity = G.nodes[node_id].get("entity", {})
                graph_data["nodes"].append({
                    "id": node_id,
                    "name": entity.get("name", node_id),
                    "type": entity.get("type", "unknown"),
                    "file": entity.get("file", ""),
                    "line_start": entity.get("line_start", 0),
                    "line_end": entity.get("line_end", 0),
                    "description": entity.get("description", ""),
                })

            for source, target, edge_data in G.edges(data=True):
                graph_data["edges"].append({
                    "source": source,
                    "target": target,
                    "type": edge_data.get("type", "unknown"),
                    "description": edge_data.get("description", ""),
                })

            communities_data = {
                "project": project_name,
                "layers": max_layers,
                "node_count": G.number_of_nodes(),
                "community_count_per_layer": {
                    f"C{i}": len(set(communities.get(f"C{i}", {}).values()))
                    for i in range(max_layers)
                },
                "nodes": [],
            }

            for node_id in G.nodes():
                node_communities = {}
                for layer in range(max_layers):
                    layer_key = f"C{layer}"
                    node_communities[layer_key] = communities.get(layer_key, {}).get(node_id, -1)

                communities_data["nodes"].append({
                    "id": node_id,
                    "communities": node_communities,
                })

            os.makedirs(graph_dir, exist_ok=True)

            graph_path = os.path.join(graph_dir, "graph.json")
            with open(graph_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)

            communities_path = os.path.join(graph_dir, "communities.json")
            with open(communities_path, "w", encoding="utf-8") as f:
                json.dump(communities_data, f, ensure_ascii=False, indent=2)

            if community_tree:
                community_tree_path = os.path.join(graph_dir, "community_tree.json")
                with open(community_tree_path, "w", encoding="utf-8") as f:
                    json.dump(community_tree, f, ensure_ascii=False, indent=2)

            elapsed = time.time() - start_time
            logger.info(
                f"[build_project_graph] Completed in {elapsed:.2f}s: "
                f"{len(merged_entities)} entities -> {G.number_of_nodes()} nodes, "
                f"{len(merged_relations)} relations -> {G.number_of_edges()} edges"
            )

            return json.dumps({
                "project": project_name,
                "graph_path": graph_path,
                "communities_path": communities_path,
                "node_count": G.number_of_nodes(),
                "edge_count": G.number_of_edges(),
                "community_counts": {
                    f"C{i}": len(set(communities.get(f"C{i}", {}).values()))
                    for i in range(max_layers)
                },
                "elapsed_seconds": round(elapsed, 2),
            }, ensure_ascii=False)

        except Exception as e:
            import traceback
            logger.error(f"[build_project_graph] Error: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            return json.dumps({
                "error": f"{type(e).__name__}: {str(e)}",
                "project": project_name,
            }, ensure_ascii=False)

    def _load_all_entities(self, memory_dir):
        all_entities = []
        all_relations = []

        for root, dirs, files in os.walk(memory_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for filename in files:
                if not filename.endswith("_entities.json"):
                    continue
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    entities = data.get("entities", [])
                    relations = data.get("relations", [])

                    for e in entities:
                        e["_source_file"] = filepath
                        all_entities.append(e)

                    for r in relations:
                        r["_source_file"] = filepath
                        all_relations.append(r)

                except Exception as e:
                    logger.warning(f"[build_project_graph] Failed to load {filepath}: {e}")

        return all_entities, all_relations

    def _merge_entities(self, entities):
        entity_map = {}

        for e in entities:
            eid = e.get("id", "")
            if not eid:
                continue

            name = e.get("name", "")
            file = e.get("file", "")
            composite_key = eid if eid else f"{name}|{file}"

            if composite_key not in entity_map:
                entity_map[composite_key] = {
                    "id": eid,
                    "name": name,
                    "type": e.get("type", "unknown"),
                    "file": file,
                    "line_start": e.get("line_start", 0),
                    "line_end": e.get("line_end", 0),
                    "description": e.get("description", ""),
                    "count": 1,
                    "descriptions": [e.get("description", "")] if e.get("description") else [],
                }
            else:
                existing = entity_map[composite_key]
                existing["count"] += 1
                desc = e.get("description", "")
                if desc:
                    existing["descriptions"].append(desc)

        for key, info in entity_map.items():
            if info["descriptions"]:
                desc_counter = Counter(info["descriptions"])
                info["description"] = desc_counter.most_common(1)[0][0]
            del info["descriptions"]
            del info["count"]

        return list(entity_map.values())

    def _merge_relations(self, relations):
        seen = set()
        merged = []

        for r in relations:
            source = r.get("source_id", "")
            target = r.get("target_id", "")
            rtype = r.get("type", "unknown")
            key = (source, target, rtype)

            if key not in seen:
                seen.add(key)
                merged.append({
                    "source_id": source,
                    "target_id": target,
                    "type": rtype,
                    "description": r.get("description", ""),
                })

        return merged

    def _build_graph(self, entities, relations):
        G = nx.Graph()

        entity_ids = set()
        for e in entities:
            node_id = e["id"]
            entity_ids.add(node_id)
            G.add_node(node_id, entity={
                "name": e["name"],
                "type": e["type"],
                "file": e["file"],
                "line_start": e["line_start"],
                "line_end": e["line_end"],
                "description": e["description"],
            })

        for r in relations:
            source = r["source_id"]
            target = r["target_id"]
            if source in entity_ids and target in entity_ids and source != target:
                G.add_edge(source, target, type=r["type"], description=r.get("description", ""))

        return G

    def _hierarchical_community_detection(self, G, max_layers=4, resolution=1.0):
        communities = {}
        for layer in range(max_layers):
            communities[f"C{layer}"] = {}

        if G.number_of_nodes() == 0:
            return communities

        all_nodes = list(G.nodes())
        for node in all_nodes:
            communities["C0"][node] = 0

        if max_layers <= 1:
            return communities

        try:
            partition = community_louvain.best_partition(G, resolution=resolution, random_state=42)
        except Exception as e:
            logger.warning(f"[build_project_graph] Louvain partition failed: {e}, using connected components")
            partition = {}
            for comp_id, comp_nodes in enumerate(nx.connected_components(G)):
                for node in comp_nodes:
                    partition[node] = comp_id

        for node, comm_id in partition.items():
            communities["C1"][node] = comm_id

        if max_layers <= 2:
            return communities

        comm_to_nodes = {}
        for node, comm_id in partition.items():
            comm_to_nodes.setdefault(comm_id, []).append(node)

        layer2_global_counter = 0
        for comm_id, comm_nodes in comm_to_nodes.items():
            if len(comm_nodes) < 3:
                for node in comm_nodes:
                    communities["C2"][node] = 0
                layer2_global_counter += 1
                continue

            subgraph = G.subgraph(comm_nodes).copy()

            if subgraph.number_of_edges() == 0:
                for node in comm_nodes:
                    communities["C2"][node] = 0
                layer2_global_counter += 1
                continue

            try:
                sub_partition = community_louvain.best_partition(
                    subgraph, resolution=resolution, random_state=42
                )
            except Exception:
                for node in comm_nodes:
                    communities["C2"][node] = 0
                layer2_global_counter += 1
                continue

            local_to_global = {}
            for node, local_id in sub_partition.items():
                if local_id not in local_to_global:
                    local_to_global[local_id] = layer2_global_counter
                    layer2_global_counter += 1
                communities["C2"][node] = local_to_global[local_id]

        if max_layers <= 3:
            return communities

        c2_to_nodes = {}
        for node, c2_id in communities["C2"].items():
            c2_to_nodes.setdefault(c2_id, []).append(node)

        layer3_global_counter = 0
        for c2_id, c2_nodes in c2_to_nodes.items():
            if len(c2_nodes) < 3:
                for node in c2_nodes:
                    communities["C3"][node] = 0
                layer3_global_counter += 1
                continue

            subgraph = G.subgraph(c2_nodes).copy()

            if subgraph.number_of_edges() == 0:
                for node in c2_nodes:
                    communities["C3"][node] = 0
                layer3_global_counter += 1
                continue

            try:
                sub_partition = community_louvain.best_partition(
                    subgraph, resolution=resolution, random_state=42
                )
            except Exception:
                for node in c2_nodes:
                    communities["C3"][node] = 0
                layer3_global_counter += 1
                continue

            local_to_global = {}
            for node, local_id in sub_partition.items():
                if local_id not in local_to_global:
                    local_to_global[local_id] = layer3_global_counter
                    layer3_global_counter += 1
                communities["C3"][node] = local_to_global[local_id]

        return communities

    def _build_community_tree(self, G, communities):
        if not communities:
            return None

        tree = {"name": "root", "layer": "C0", "community_id": 0, "node_count": G.number_of_nodes(), "children": []}

        c1_groups = {}
        for node, cid in communities.get("C1", {}).items():
            c1_groups.setdefault(cid, []).append(node)

        for c1_id, c1_nodes in sorted(c1_groups.items()):
            c1_child = {
                "layer": "C1",
                "community_id": c1_id,
                "node_count": len(c1_nodes),
                "sample_nodes": c1_nodes[:5],
                "children": [],
            }

            if "C2" in communities:
                c2_groups = {}
                for node in c1_nodes:
                    c2_id = communities["C2"].get(node, -1)
                    c2_groups.setdefault(c2_id, []).append(node)

                for c2_id, c2_nodes in sorted(c2_groups.items()):
                    c2_child = {
                        "layer": "C2",
                        "community_id": c2_id,
                        "node_count": len(c2_nodes),
                        "sample_nodes": c2_nodes[:5],
                    }
                    c1_child["children"].append(c2_child)

            tree["children"].append(c1_child)

        return tree