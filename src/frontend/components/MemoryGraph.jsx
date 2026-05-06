import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { GROUP_COLORS } from '../utils/constants';

export default function MemoryGraph({ nodes, edges, retrievalPath, theme, onNodeClick }) {
  const svgRef = useRef(null);
  const simulationRef = useRef(null);
  const pathGroupRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const container = svgRef.current.parentElement;
    const width = container.clientWidth || 300;
    const height = container.clientHeight || 500;

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

    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);

    const simulation = d3.forceSimulation(nodes)
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(25))
      .alphaDecay(0.02);

    simulationRef.current = simulation;

    const link = g.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', theme === 'dark' ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)')
      .attr('stroke-width', 1.5);

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        if (onNodeClick && d.path) {
          onNodeClick(d);
        }
      })
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );

    nodeGroup.append('circle')
      .attr('r', 7)
      .attr('fill', d => GROUP_COLORS[d.group] || GROUP_COLORS['other'])
      .attr('stroke', theme === 'dark' ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)')
      .attr('stroke-width', 1.5);

    nodeGroup.append('text')
      .text(d => {
        const label = d.label || '';
        if (d.path && d.path.endsWith('.md')) {
          const parts = d.path.split(/[\\/]/);
          const filename = parts[parts.length - 1];
          return filename.replace(/\.md$/, '');
        }
        return label;
      })
      .attr('x', 10)
      .attr('y', 3)
      .attr('fill', theme === 'dark' ? '#c0c0c0' : '#495057')
      .attr('font-size', '10px')
      .attr('font-family', 'sans-serif');

    const pathGroup = g.append('g').attr('class', 'retrieval-path-group');
    pathGroupRef.current = { g: pathGroup, nodes, simulation, theme };

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`);

      updatePathEdges();
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, theme]);

  useEffect(() => {
    updatePathEdges();
  }, [retrievalPath]);

  function updatePathEdges() {
    if (!pathGroupRef.current) return;
    const { g, nodes, simulation } = pathGroupRef.current;
    if (!g || nodes.length === 0) return;

    g.selectAll('*').remove();

    if (!retrievalPath || retrievalPath.length < 2) return;

    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });

    const pathEdges = [];
    for (let i = 0; i < retrievalPath.length - 1; i++) {
      const sourceId = retrievalPath[i];
      const targetId = retrievalPath[i + 1];
      const sourceNode = nodeMap[sourceId];
      const targetNode = nodeMap[targetId];
      if (sourceNode && targetNode) {
        pathEdges.push({
          source: sourceNode,
          target: targetNode,
          index: i,
        });
      }
    }

    const pathLines = g.selectAll('g')
      .data(pathEdges)
      .join('g')
      .attr('class', 'path-edge-group');

    pathLines.append('line')
      .attr('class', 'path-edge')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)
      .attr('stroke', '#e94560')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '8,4')
      .attr('marker-end', 'url(#arrowhead-path)')
      .attr('opacity', 0.8);

    pathLines.append('circle')
      .attr('class', 'path-dot')
      .attr('r', 3)
      .attr('fill', '#ff6b8a')
      .attr('opacity', 0.9);

    function animatePathDots() {
      pathLines.selectAll('.path-dot')
        .attr('cx', function(d) {
          const t = (Date.now() / 1500 + d.index * 0.3) % 1;
          return d.source.x + (d.target.x - d.source.x) * t;
        })
        .attr('cy', function(d) {
          const t = (Date.now() / 1500 + d.index * 0.3) % 1;
          return d.source.y + (d.target.y - d.source.y) * t;
        });
    }

    d3.timer(animatePathDots);
  }

  return (
    <svg ref={svgRef} className="memory-graph-svg"></svg>
  );
}
