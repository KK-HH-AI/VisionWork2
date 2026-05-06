import React, { useState, useEffect, useCallback, useRef } from 'react';
import ReactFlow, {
  useNodesState,
  useEdgesState,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Background,
  Controls,
  MarkerType,
  ReactFlowProvider,
  Handle,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { GROUP_COLORS, NODE_TYPE_COLORS } from '../utils/constants';

function getLayoutedElements(nodes, edges, direction = 'TB') {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 180;
  const nodeHeight = 60;

  dagreGraph.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
      style: {
        ...node.style,
        opacity: 1,
        transition: 'opacity 0.2s ease-in',
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

function CustomNode({ data }) {
  const color = NODE_TYPE_COLORS[data.nodeType] || GROUP_COLORS[data.group] || GROUP_COLORS['other'];
  return (
    <div className="rf-custom-node" style={{ borderColor: color }}>
      <Handle type="target" position={Position.Top} className="rf-handle" />
      <div className="rf-node-header" style={{ backgroundColor: color }}>
        <span className="rf-node-type">{data.nodeType || data.group || 'module'}</span>
      </div>
      <div className="rf-node-body">
        <span className="rf-node-label">{data.label}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="rf-handle" />
    </div>
  );
}

const nodeTypes = { customNode: CustomNode };

export default function ReactFlowCanvas({ nodes, setNodes, edges, setEdges, isSecondPass, onNodeDoubleClick, theme }) {
  const commandQueueRef = useRef([]);
  const processingRef = useRef(false);
  const reactFlowInstanceRef = useRef(null);
  const latestNodesRef = useRef(nodes);
  const latestEdgesRef = useRef(edges);
  const themeRef = useRef(theme);
  themeRef.current = theme;

  latestNodesRef.current = nodes;
  latestEdgesRef.current = edges;

  const edgeColor = theme === 'dark' ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.25)';
  const edgeMarkerColor = theme === 'dark' ? '#aaa' : '#555';
  const labelColor = theme === 'dark' ? '#aaa' : '#555';
  const labelBgColor = theme === 'dark' ? 'rgba(26, 26, 46, 0.8)' : 'rgba(255, 255, 255, 0.9)';

  const processCommand = useCallback(async (command) => {
    const cmd = command.cmd;
    const delay = 200;
    console.log('[ReactFlowCanvas] Processing command:', cmd, JSON.stringify(command).substring(0, 120));

    if (cmd === 'add_node') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setNodes((nds) => {
        const exists = nds.find(n => n.id === command.id);
        if (exists) return nds;
        const newNode = {
          id: command.id,
          type: 'customNode',
          position: {
            x: Math.random() * 400 + 100,
            y: Math.random() * 300 + 50,
          },
          data: {
            label: command.label || command.id,
            nodeType: command.type || 'module',
            group: command.group || 'other',
            description: command.description || '',
            codeRef: command.codeRef || null,
          },
          style: {
            opacity: 0,
            transition: 'opacity 0.2s ease-in',
          },
        };
        setTimeout(() => {
          setNodes((current) =>
            current.map((n) =>
              n.id === command.id
                ? { ...n, style: { ...n.style, opacity: 1 } }
                : n
            )
          );
        }, 50);
        return [...nds, newNode];
      });
    } else if (cmd === 'add_edge') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setEdges((eds) => {
        const exists = eds.find(
          e => e.source === command.source && e.target === command.target
        );
        if (exists) return eds;
        const newEdge = {
          id: `e-${command.source}-${command.target}`,
          source: command.source,
          target: command.target,
          label: command.label || '',
          type: 'smoothstep',
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: edgeMarkerColor },
          style: {
            stroke: edgeColor,
            strokeWidth: 1.5,
            opacity: 0,
            transition: 'opacity 0.2s ease-in',
          },
          labelStyle: { fill: labelColor, fontSize: 10 },
          labelBgStyle: { fill: labelBgColor },
        };
        setTimeout(() => {
          setEdges((current) =>
            current.map((e) =>
              e.id === newEdge.id
                ? { ...e, style: { ...e.style, opacity: 1 } }
                : e
            )
          );
        }, 50);
        return [...eds, newEdge];
      });
    } else if (cmd === 'layout') {
      await new Promise(resolve => setTimeout(resolve, 300));
      const currentNodes = latestNodesRef.current;
      const currentEdges = latestEdgesRef.current;
      if (currentNodes.length === 0) return;
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(currentNodes, currentEdges);
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
    }
  }, [setNodes, setEdges]);

  const enqueueCommand = useCallback((command) => {
    commandQueueRef.current.push(command);
    if (!processingRef.current) {
      processQueue();
    }
  }, []);

  const processQueue = useCallback(async () => {
    processingRef.current = true;
    while (commandQueueRef.current.length > 0) {
      const command = commandQueueRef.current.shift();
      await processCommand(command);
    }
    processingRef.current = false;
  }, [processCommand]);

  useEffect(() => {
    window.__enqueueCanvasCommand = enqueueCommand;
    return () => {
      delete window.__enqueueCanvasCommand;
    };
  }, [enqueueCommand]);

  const onInit = useCallback((instance) => {
    reactFlowInstanceRef.current = instance;
  }, []);

  const onNodesChangeHandler = useCallback((changes) => {
    setNodes((nds) => applyNodeChanges(changes, nds));
  }, [setNodes]);

  const onEdgesChangeHandler = useCallback((changes) => {
    setEdges((eds) => applyEdgeChanges(changes, eds));
  }, [setEdges]);

  return (
    <div className="rf-container">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChangeHandler}
        onEdgesChange={onEdgesChangeHandler}
        onNodeDoubleClick={(event, node) => {
          if (onNodeDoubleClick) {
            onNodeDoubleClick(node);
          }
        }}
        onConnect={(connection) => {
          setEdges((eds) => addEdge({
            ...connection,
            type: 'smoothstep',
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed, color: '#888' },
            style: { stroke: 'rgba(255,255,255,0.3)', strokeWidth: 1.5 },
          }, eds));
        }}
        nodeTypes={nodeTypes}
        onInit={onInit}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={4}
        defaultEdgeOptions={{
          type: 'smoothstep',
          animated: false,
          style: { stroke: 'rgba(255,255,255,0.2)', strokeWidth: 1 },
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color={theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'} gap={20} />
        <Controls className="rf-controls" />
      </ReactFlow>
    </div>
  );
}
