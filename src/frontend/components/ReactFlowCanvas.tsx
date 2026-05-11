import React, { useState, useCallback, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import ReactFlow, {
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Background,
  Controls,
  MarkerType,
  Handle,
  Position,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type EdgeMarker,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import { Maximize, Minimize } from 'react-feather';
import { GROUP_COLORS, NODE_TYPE_COLORS } from '../utils/constants';
import type { CanvasCommand, CanvasNodeData, CanvasEdge as StoredCanvasEdge } from '../types';

type CanvasNode = Node<CanvasNodeData>;
type CanvasEdge = Edge;

export interface CanvasState {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}

export interface ReactFlowCanvasHandle {
  getCanvasState: () => CanvasState;
  setCanvasState: (state: { nodes: CanvasNode[]; edges: StoredCanvasEdge[] }) => void;
}

function getLayoutedElements(nodes: CanvasNode[], edges: CanvasEdge[], direction = 'TB') {
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

interface CustomNodeProps {
  data: CanvasNodeData;
}

function CustomNode({ data }: CustomNodeProps) {
  const color = NODE_TYPE_COLORS[data.nodeType || ''] || GROUP_COLORS[data.group || ''] || GROUP_COLORS['other'];
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

interface ReactFlowCanvasProps {
  theme: string;
  sessionKey?: string;
}

const ReactFlowCanvas = forwardRef<ReactFlowCanvasHandle, ReactFlowCanvasProps>(function ReactFlowCanvas(
  { theme, sessionKey },
  ref
) {
  const [nodes, setNodes] = useState<CanvasNode[]>([]);
  const [edges, setEdges] = useState<CanvasEdge[]>([]);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const commandQueueRef = useRef<CanvasCommand[]>([]);
  const processingRef = useRef(false);
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

  const processCommand = useCallback(async (command: CanvasCommand) => {
    const cmd = command.cmd;
    const delay = 200;

    if (cmd === 'add_node') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setNodes((nds: CanvasNode[]) => {
        const exists = nds.find(n => n.id === command.id);
        if (exists) return nds;
        const newNode: CanvasNode = {
          id: command.id || '',
          type: 'customNode',
          position: {
            x: Math.random() * 400 + 100,
            y: Math.random() * 300 + 50,
          },
          data: {
            label: command.label || command.id || '',
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
          setNodes((current: CanvasNode[]) =>
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
      setEdges((eds: CanvasEdge[]) => {
        const exists = eds.find(
          e => e.source === command.source && e.target === command.target
        );
        if (exists) return eds;
        const newEdge: CanvasEdge = {
          id: `e-${command.source}-${command.target}`,
          source: command.source || '',
          target: command.target || '',
          label: command.label || '',
          type: 'smoothstep',
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: edgeMarkerColor } as EdgeMarker,
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
          setEdges((current: CanvasEdge[]) =>
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
  }, [setNodes, setEdges, edgeColor, edgeMarkerColor, labelColor, labelBgColor]);

  const enqueueCommand = useCallback((command: CanvasCommand) => {
    commandQueueRef.current.push(command);
    if (!processingRef.current) {
      processQueue();
    }
  }, []);

  const processQueue = useCallback(async () => {
    processingRef.current = true;
    while (commandQueueRef.current.length > 0) {
      const command = commandQueueRef.current.shift();
      if (command) {
        await processCommand(command);
      }
    }
    processingRef.current = false;
  }, [processCommand]);

  useEffect(() => {
    (window as unknown as Record<string, unknown>).__enqueueCanvasCommand = enqueueCommand;
    return () => {
      delete (window as unknown as Record<string, unknown>).__enqueueCanvasCommand;
    };
  }, [enqueueCommand]);

  useImperativeHandle(ref, () => ({
    getCanvasState: () => ({
      nodes: latestNodesRef.current,
      edges: latestEdgesRef.current,
    }),
    setCanvasState: (state: { nodes: CanvasNode[]; edges: StoredCanvasEdge[] }) => {
      setNodes(state.nodes);
      setEdges(state.edges as CanvasEdge[]);
    },
  }), []);

  useEffect(() => {
    setNodes([]);
    setEdges([]);
    commandQueueRef.current = [];
    processingRef.current = false;
  }, [sessionKey]);

  const onNodesChangeHandler = useCallback((changes: NodeChange[]) => {
    setNodes((nds: CanvasNode[]) => applyNodeChanges(changes, nds) as CanvasNode[]);
  }, [setNodes]);

  const onEdgesChangeHandler = useCallback((changes: EdgeChange[]) => {
    setEdges((eds: CanvasEdge[]) => applyEdgeChanges(changes, eds) as CanvasEdge[]);
  }, [setEdges]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  return (
    <div className={`rf-container ${isFullscreen ? 'rf-fullscreen' : ''}`}>
      <button
        className="rf-fullscreen-btn"
        onClick={toggleFullscreen}
        title={isFullscreen ? '退出全屏' : '全屏'}
      >
        {isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
      </button>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChangeHandler}
        onEdgesChange={onEdgesChangeHandler}
        onConnect={(connection: Connection) => {
          setEdges((eds: CanvasEdge[]) => addEdge({
            ...connection,
            type: 'smoothstep',
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed, color: '#888' } as EdgeMarker,
            style: { stroke: 'rgba(255,255,255,0.3)', strokeWidth: 1.5 },
          }, eds));
        }}
        nodeTypes={nodeTypes}
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
});

ReactFlowCanvas.displayName = 'ReactFlowCanvas';

export default ReactFlowCanvas;