import React, { useEffect, useRef, useMemo } from 'react';
import * as d3 from 'd3';
import { GitBranch, Search } from 'react-feather';
import { GROUP_COLORS, COMMUNITY_LEVEL_COLORS, COMMUNITY_LEVEL_RADIUS, COMMUNITY_LEVEL_LABELS } from '../utils/constants';
import type { GraphNode, GraphEdge } from '../types';

interface MemoryGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  retrievalPath: string[];
  theme: string;
  onNodeClick?: (node: GraphNode) => void;
}

interface PathEdge {
  source: GraphNode;
  target: GraphNode;
  index: number;
}

const EDGE_STYLE = {
  community_hierarchy: { stroke: 'rgba(155, 89, 182, 0.4)', width: 2.5, dasharray: '6,3' },
  file_belongs: { stroke: 'rgba(150, 150, 150, 0.25)', width: 1, dasharray: '3,3' },
  default: { stroke: 'rgba(0,0,0,0.25)', width: 1.5, dasharray: '' },
};

function getEdgeStyle(edge: GraphEdge, theme: string) {
  const type = edge.type || '';
  if (type === 'community_hierarchy') return { ...EDGE_STYLE.community_hierarchy };
  if (type === 'file_belongs') return { ...EDGE_STYLE.file_belongs };
  return {
    stroke: theme === 'dark' ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)',
    width: 1.5,
    dasharray: '',
  };
}

function getNodeRadius(d: GraphNode): number {
  if (d.group === 'community' && d.level && COMMUNITY_LEVEL_RADIUS[d.level]) {
    return COMMUNITY_LEVEL_RADIUS[d.level];
  }
  return 10;
}

function getNodeColor(d: GraphNode, theme: string): string {
  if (d.group === 'community' && d.level && COMMUNITY_LEVEL_COLORS[d.level]) {
    return COMMUNITY_LEVEL_COLORS[d.level];
  }
  return GROUP_COLORS[d.group] || GROUP_COLORS['other'];
}

function getNodeLabel(d: GraphNode): string {
  const label = d.label || '';
  if (d.group === 'community' && d.level) {
    const levelLabel = COMMUNITY_LEVEL_LABELS[d.level] || d.level;
    return `${levelLabel}`;
  }
  if (d.path && d.path.endsWith('.md')) {
    const parts = d.path.split(/[\\/]/);
    return parts[parts.length - 1].replace(/\.md$/, '');
  }
  return label;
}

export default function MemoryGraph({ nodes, edges, retrievalPath, theme, onNodeClick }: MemoryGraphProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const prevNodeIdsRef = useRef<string>('');
  const pathGroupRef = useRef<{
    g: d3.Selection<SVGGElement, unknown, null, undefined>;
    nodes: GraphNode[];
    simulation: d3.Simulation<GraphNode, GraphEdge>;
    theme: string;
  } | null>(null);
  const pathTimerRef = useRef<d3.Timer | null>(null);
  const updatePathEdgesRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const currentIds = nodes.map(n => n.id).sort().join(',');
    if (currentIds === prevNodeIdsRef.current && prevNodeIdsRef.current !== '') {
      return;
    }
    prevNodeIdsRef.current = currentIds;

    const container = svgRef.current.parentElement;
    const width = container?.clientWidth || 300;
    const height = container?.clientHeight || 500;

    if (width === 0 || height === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('width', width).attr('height', height);

    const defs = svg.append('defs');

    defs.append('marker')
      .attr('id', 'arrowhead-path')
      .attr('viewBox', '0 0 10 7')
      .attr('refX', 10)
      .attr('refY', 3.5)
      .attr('markerWidth', 8)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('polygon')
      .attr('points', '0 0, 10 3.5, 0 7')
      .attr('fill', '#e94560');

    const g = svg.append('g');

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);

    const communityNodes = nodes.filter(n => n.group === 'community');
    const fileNodes = nodes.filter(n => n.group !== 'community');

    const nodeCount = nodes.length;
    const isLargeGraph = nodeCount > 50;

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(edges)
        .id((d: GraphNode) => d.id)
        .distance((e: GraphEdge) => {
          if (e.type === 'community_hierarchy') return isLargeGraph ? 80 : 60;
          if (e.type === 'file_belongs') return isLargeGraph ? 50 : 35;
          return isLargeGraph ? 35 : 25;
        })
        .strength((e: GraphEdge) => {
          if (e.type === 'community_hierarchy') return 0.6;
          if (e.type === 'file_belongs') return 0.3;
          return 0.5;
        })
      )
      .force('charge', d3.forceManyBody()
        .strength((d: d3.SimulationNodeDatum) => {
          const node = d as GraphNode;
          const base = isLargeGraph ? -800 : -400;
          if (node.group === 'community') {
            const levelNum = node.level ? parseInt(node.level.slice(1)) : 3;
            return base - (3 - levelNum) * 250;
          }
          return base;
        })
        .distanceMax(isLargeGraph ? 600 : 400)
      )
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide()
        .radius((d: d3.SimulationNodeDatum) => getNodeRadius(d as GraphNode) + (isLargeGraph ? 12 : 8))
        .strength(0.9)
      )
      .force('x', d3.forceX(width / 2).strength(0.03))
      .force('y', d3.forceY(height / 2).strength(0.03))
      .alphaDecay(isLargeGraph ? 0.005 : 0.015)
      .velocityDecay(0.3);

    simulationRef.current = simulation;

    const link = g.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', (d: GraphEdge) => getEdgeStyle(d, theme).stroke)
      .attr('stroke-width', (d: GraphEdge) => getEdgeStyle(d, theme).width)
      .attr('stroke-dasharray', (d: GraphEdge) => getEdgeStyle(d, theme).dasharray || null)
      .attr('opacity', 0.7);

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .style('cursor', (d: GraphNode) => {
        if (d.group === 'community' && d.has_summary && d.path) return 'pointer';
        if (d.path && d.path.endsWith('.md')) return 'pointer';
        return 'default';
      })
      .on('dblclick', (_event, d) => {
        if (onNodeClick && d.path) {
          onNodeClick(d);
        }
      })
      .call(
        d3.drag<SVGGElement, GraphNode>()
          .on('start', (event: d3.D3DragEvent<SVGGElement, GraphNode, GraphNode>, d: GraphNode) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event: d3.D3DragEvent<SVGGElement, GraphNode, GraphNode>, d: GraphNode) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event: d3.D3DragEvent<SVGGElement, GraphNode, GraphNode>, d: GraphNode) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }) as any
      );

    nodeGroup.append('circle')
      .attr('r', (d: GraphNode) => getNodeRadius(d))
      .attr('fill', (d: GraphNode) => getNodeColor(d, theme))
      .attr('stroke', (d: GraphNode) => {
        if (d.group === 'community') return 'rgba(255,255,255,0.5)';
        return theme === 'dark' ? '#fff' : 'rgba(0,0,0,0.45)';
      })
      .attr('stroke-width', (d: GraphNode) => d.group === 'community' ? 3 : 2.5)
      .attr('stroke-opacity', (d: GraphNode) => d.group === 'community' ? 0.8 : (theme === 'dark' ? 0.7 : 0.5))
      .attr('stroke-dasharray', (d: GraphNode) => {
        if (d.group === 'community' && d.has_summary) return '';
        if (d.group === 'community') return '4,2';
        return '';
      });

    nodeGroup.append('text')
      .text((d: GraphNode) => getNodeLabel(d))
      .attr('x', (d: GraphNode) => getNodeRadius(d) + 4)
      .attr('y', (d: GraphNode) => d.group === 'community' ? -2 : 4)
      .attr('fill', (d: GraphNode) => {
        if (d.group === 'community') return COMMUNITY_LEVEL_COLORS[d.level || 'C3'] || '#888';
        return theme === 'dark' ? '#d0d0d0' : '#374151';
      })
      .attr('font-size', (d: GraphNode) => d.group === 'community' ? '12px' : '11px')
      .attr('font-family', 'sans-serif')
      .attr('font-weight', (d: GraphNode) => d.group === 'community' ? '700' : '500');

    nodeGroup.append('title')
      .text((d: GraphNode) => {
        if (d.group === 'community') {
          const levelLabel = COMMUNITY_LEVEL_LABELS[d.level || ''] || d.level || '?';
          const summaryTag = d.has_summary ? ' [已摘要]' : ' [待摘要]';
          return `${levelLabel}${summaryTag}`;
        }
        return d.path || d.label;
      });

    const pathGroup = g.append('g').attr('class', 'retrieval-path-group');
    pathGroupRef.current = { g: pathGroup, nodes, simulation, theme };

    simulation.on('tick', () => {
      link
        .attr('x1', (d: GraphEdge) => (d.source as GraphNode).x || 0)
        .attr('y1', (d: GraphEdge) => (d.source as GraphNode).y || 0)
        .attr('x2', (d: GraphEdge) => (d.target as GraphNode).x || 0)
        .attr('y2', (d: GraphEdge) => (d.target as GraphNode).y || 0);

      nodeGroup.attr('transform', (d: GraphNode) => `translate(${d.x},${d.y})`);
    });

    simulation.on('end', () => {
      updatePathEdgesRef.current();
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, theme]);

  useEffect(() => {
    const container = svgRef.current?.parentElement;
    if (!container) return;

    const resizeObserver = new ResizeObserver(() => {
      const svg = d3.select(svgRef.current);
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w > 0 && h > 0) {
        svg.attr('width', w).attr('height', h);
        const sim = simulationRef.current;
        if (sim) {
          sim.force('center', d3.forceCenter(w / 2, h / 2));
          sim.alpha(0.1).restart();
        }
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    console.log('[MemoryGraph] retrievalPath changed:', retrievalPath);
    updatePathEdges();
  }, [retrievalPath]);

  function updatePathEdges() {
    if (!pathGroupRef.current) {
      console.log('[MemoryGraph] updatePathEdges: pathGroupRef is null, skipping');
      return;
    }
    const { g, nodes: currentNodes, simulation } = pathGroupRef.current;
    if (!g || currentNodes.length === 0) {
      console.log('[MemoryGraph] updatePathEdges: no g or no nodes, skipping');
      return;
    }

    if (pathTimerRef.current) {
      pathTimerRef.current.stop();
      pathTimerRef.current = null;
    }

    g.selectAll('*').remove();

    if (!retrievalPath || retrievalPath.length === 0) {
      console.log('[MemoryGraph] updatePathEdges: retrievalPath empty, cleared');
      return;
    }

    const nodeMap: Record<string, GraphNode> = {};
    currentNodes.forEach((n: GraphNode) => { nodeMap[n.id] = n; });

    const pathNodeIds = retrievalPath.filter(id => nodeMap[id]);
    console.log('[MemoryGraph] updatePathEdges: retrievalPath ids:', retrievalPath, 'matched nodes:', pathNodeIds);

    pathNodeIds.forEach((nodeId, index) => {
      const node = nodeMap[nodeId];
      const isCommunity = node.group === 'community';
      const isLatest = index === pathNodeIds.length - 1;

      const radius = getNodeRadius(node);
      const highlightColor = isCommunity ? COMMUNITY_LEVEL_COLORS[node.level || 'C3'] : '#e94560';

      g.append('circle')
        .attr('class', 'path-node-highlight')
        .attr('cx', node.x || 0)
        .attr('cy', node.y || 0)
        .attr('r', radius + 5)
        .attr('fill', 'none')
        .attr('stroke', highlightColor)
        .attr('stroke-width', isLatest ? 3 : 2)
        .attr('stroke-dasharray', isLatest ? 'none' : isCommunity ? '8,4' : '6,3')
        .attr('opacity', isLatest ? 1 : 0.7);

      g.append('text')
        .attr('class', 'path-node-label')
        .attr('x', (node.x || 0) + radius + 6)
        .attr('y', (node.y || 0) - radius - 2)
        .attr('fill', highlightColor)
        .attr('font-size', '9px')
        .attr('font-family', 'sans-serif')
        .attr('font-weight', isCommunity ? '600' : 'normal')
        .attr('opacity', 0.9)
        .text(`#${index + 1}`);
    });

    if (pathNodeIds.length < 2) return;

    const pathEdges: PathEdge[] = [];
    for (let i = 0; i < pathNodeIds.length - 1; i++) {
      const sourceNode = nodeMap[pathNodeIds[i]];
      const targetNode = nodeMap[pathNodeIds[i + 1]];
      if (sourceNode && targetNode) {
        pathEdges.push({
          source: sourceNode,
          target: targetNode,
          index: i,
        });
      }
    }

    const pathLines = g.selectAll<SVGGElement, PathEdge>('g')
      .data(pathEdges)
      .join('g')
      .attr('class', 'path-edge-group');

    const isCommunityEdge = (d: PathEdge) =>
      d.source.group === 'community' || d.target.group === 'community';

    pathLines.append('line')
      .attr('class', 'path-edge')
      .attr('x1', (d: PathEdge) => d.source.x || 0)
      .attr('y1', (d: PathEdge) => d.source.y || 0)
      .attr('x2', (d: PathEdge) => d.target.x || 0)
      .attr('y2', (d: PathEdge) => d.target.y || 0)
      .attr('stroke', (d: PathEdge) => {
        if (d.source.group === 'community' && d.source.level && COMMUNITY_LEVEL_COLORS[d.source.level]) {
          return COMMUNITY_LEVEL_COLORS[d.source.level];
        }
        return '#e94560';
      })
      .attr('stroke-width', (d: PathEdge) => isCommunityEdge(d) ? 2.5 : 2)
      .attr('stroke-dasharray', (d: PathEdge) => isCommunityEdge(d) ? '8,4,2,4' : '8,4')
      .attr('marker-end', 'url(#arrowhead-path)')
      .attr('opacity', 0.8);

    pathLines.append('circle')
      .attr('class', 'path-dot')
      .attr('r', (d: PathEdge) => isCommunityEdge(d) ? 4 : 3)
      .attr('fill', (d: PathEdge) => {
        if (d.source.group === 'community' && d.source.level && COMMUNITY_LEVEL_COLORS[d.source.level]) {
          return COMMUNITY_LEVEL_COLORS[d.source.level];
        }
        return '#ff6b8a';
      })
      .attr('opacity', 0);

    function animatePathDots() {
      const now = Date.now();
      const waveSpeed = 1200;
      const waveGap = 400;

      pathLines.selectAll<SVGCircleElement, PathEdge>('.path-dot')
        .attr('opacity', function(d: PathEdge) {
          const edgeStartTime = d.index * waveGap;
          if (now < edgeStartTime) return 0;
          return 0.9;
        })
        .attr('cx', function(d: PathEdge) {
          const edgeStartTime = d.index * waveGap;
          if (now < edgeStartTime) return d.source.x || 0;
          const t = ((now - edgeStartTime) / waveSpeed) % 1;
          return (d.source.x || 0) + ((d.target.x || 0) - (d.source.x || 0)) * t;
        })
        .attr('cy', function(d: PathEdge) {
          const edgeStartTime = d.index * waveGap;
          if (now < edgeStartTime) return d.source.y || 0;
          const t = ((now - edgeStartTime) / waveSpeed) % 1;
          return (d.source.y || 0) + ((d.target.y || 0) - (d.source.y || 0)) * t;
        });

      pathLines.selectAll<SVGLineElement, PathEdge>('.path-edge')
        .attr('opacity', function(d: PathEdge) {
          const edgeStartTime = d.index * waveGap;
          if (now < edgeStartTime) return 0.15;
          const progress = (now - edgeStartTime) / waveSpeed;
          if (progress > 1) return 0.8;
          return 0.15 + 0.65 * Math.min(progress, 1);
        });
    }

    pathTimerRef.current = d3.timer(animatePathDots);
  }

  updatePathEdgesRef.current = updatePathEdges;

  const retrievalNodes = useMemo(() => {
    if (!retrievalPath || retrievalPath.length === 0) return [];
    const nodeMap: Record<string, GraphNode> = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });
    return retrievalPath
      .filter(id => nodeMap[id])
      .map((id, idx) => {
        const node = nodeMap[id];
        const isCommunity = node.group === 'community';
        return {
          index: idx + 1,
          id,
          label: isCommunity ? COMMUNITY_LEVEL_LABELS[node.level || ''] || node.level : (nodeMap[id].label || id),
          path: nodeMap[id].path || '',
          isCommunity,
          level: node.level || '',
        };
      });
  }, [retrievalPath, nodes]);

  if (nodes.length === 0) {
    return (
      <div className="memory-graph-empty">
        <GitBranch size={24} />
        <p>暂无记忆文件</p>
        <p className="empty-hint">workspace 中没有 .md 记忆文件</p>
      </div>
    );
  }

  return (
    <div className="memory-graph-wrapper">
      <svg ref={svgRef} className="memory-graph-svg"></svg>
      {retrievalNodes.length > 0 && (
        <div className="memory-retrieval-list">
          <div className="memory-retrieval-list-header">
            <Search size={12} />
            <span>记忆检索路径</span>
            <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: '#e94560' }}>
              {retrievalNodes.length} 步
            </span>
          </div>
          {retrievalNodes.map((item) => (
            <div
              key={item.id}
              className={`memory-retrieval-item${item.isCommunity ? ' community-step' : ''}`}
              title={item.path || item.label || item.id}
            >
              <span
                className="memory-retrieval-index"
                style={item.isCommunity ? {
                  background: COMMUNITY_LEVEL_COLORS[item.level] || '#888',
                  color: '#fff',
                } : undefined}
              >
                #{item.index}
              </span>
              <span className="memory-retrieval-path">
                {item.label || item.id}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}