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
import { Maximize, Minimize, Plus, Trash2, Download, Upload, Grid, Check, X } from 'react-feather';
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
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [editNode, setEditNode] = useState<{ id: string; label: string; nodeType: string; group: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nodeCounterRef = useRef(0);

  const commandQueueRef = useRef<CanvasCommand[]>([]);
  const processingRef = useRef(false);
  const latestNodesRef = useRef(nodes);
  const latestEdgesRef = useRef(edges);
  const themeRef = useRef(theme);
  themeRef.current = theme;

  latestNodesRef.current = nodes;
  latestEdgesRef.current = edges;

  const edgeColor = theme === 'dark' ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.55)';
  const edgeMarkerColor = theme === 'dark' ? '#ccc' : '#333';
  const labelColor = theme === 'dark' ? '#ccc' : '#333';
  const labelBgColor = theme === 'dark' ? 'rgba(26, 26, 46, 0.85)' : 'rgba(255, 255, 255, 0.95)';

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
    } else if (cmd === 'update_node') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setNodes((nds: CanvasNode[]) =>
        nds.map((n) => {
          if (n.id !== command.id) return n;
          return {
            ...n,
            data: {
              ...n.data,
              label: command.label || n.data.label,
              nodeType: command.type || n.data.nodeType,
              group: command.group || n.data.group,
            },
          };
        })
      );
    } else if (cmd === 'remove_node') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setNodes((nds: CanvasNode[]) => nds.filter(n => n.id !== command.id));
      setEdges((eds: CanvasEdge[]) =>
        eds.filter(e => e.source !== command.id && e.target !== command.id)
      );
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
    } else if (cmd === 'remove_edge') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setEdges((eds: CanvasEdge[]) =>
        eds.filter(e => !(e.source === command.source && e.target === command.target))
      );
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

  useEffect(() => {
    if (nodes.length === 0 && edges.length === 0) return;
    setEdges((eds: CanvasEdge[]) =>
      eds.map((e) => ({
        ...e,
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeMarkerColor } as EdgeMarker,
        style: { ...e.style, stroke: edgeColor },
        labelStyle: { ...e.labelStyle, fill: labelColor },
        labelBgStyle: { ...e.labelBgStyle, fill: labelBgColor },
      }))
    );
  }, [theme, edgeColor, edgeMarkerColor, labelColor, labelBgColor]);

  const onNodesChangeHandler = useCallback((changes: NodeChange[]) => {
    setNodes((nds: CanvasNode[]) => {
      const updated = applyNodeChanges(changes, nds) as CanvasNode[];
      for (const change of changes) {
        if (change.type === 'select') {
          if (change.selected) {
            setSelectedNodes((prev) => {
              if (!prev.includes(change.id)) return [...prev, change.id];
              return prev;
            });
          } else {
            setSelectedNodes((prev) => prev.filter((id) => id !== change.id));
          }
        }
      }
      return updated;
    });
  }, [setNodes]);

  const onEdgesChangeHandler = useCallback((changes: EdgeChange[]) => {
    setEdges((eds: CanvasEdge[]) => applyEdgeChanges(changes, eds) as CanvasEdge[]);
  }, [setEdges]);

  const handleNodeDoubleClick = useCallback((_event: React.MouseEvent, node: CanvasNode) => {
    setEditNode({
      id: node.id,
      label: node.data.label || '',
      nodeType: node.data.nodeType || '',
      group: node.data.group || '',
    });
  }, []);

  const handleEditSave = useCallback(() => {
    if (!editNode) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === editNode.id
          ? {
              ...n,
              data: {
                ...n.data,
                label: editNode.label,
                nodeType: editNode.nodeType,
                group: editNode.group,
              },
            }
          : n
      )
    );
    setEditNode(null);
  }, [editNode]);

  const handleAddNode = useCallback(() => {
    nodeCounterRef.current += 1;
    const id = `user-node-${Date.now()}-${nodeCounterRef.current}`;
    const newNode: CanvasNode = {
      id,
      type: 'customNode',
      position: { x: Math.random() * 300 + 100, y: Math.random() * 200 + 50 },
      data: {
        label: `节点 ${nodeCounterRef.current}`,
        nodeType: 'module',
        group: 'other',
      },
    };
    setNodes((nds) => [...nds, newNode]);
  }, []);

  const handleDeleteSelected = useCallback(() => {
    if (selectedNodes.length === 0) return;
    const idsToRemove = new Set(selectedNodes);
    setNodes((nds) => nds.filter((n) => !idsToRemove.has(n.id)));
    setEdges((eds) => eds.filter((e) => !idsToRemove.has(e.source) && !idsToRemove.has(e.target)));
    setSelectedNodes([]);
  }, [selectedNodes]);

  const handleSaveCanvas = useCallback(() => {
    const state = {
      nodes: latestNodesRef.current,
      edges: latestEdgesRef.current,
    };
    const json = JSON.stringify(state, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flowchart-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const handleLoadCanvas = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileLoad = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const data = JSON.parse(evt.target?.result as string);
        if (data.nodes && Array.isArray(data.nodes)) {
          setNodes(data.nodes);
          setEdges(data.edges || []);
        }
      } catch (err) {
        console.error('Failed to parse flowchart file:', err);
      }
    };
    reader.readAsText(file);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const handleAutoLayout = useCallback(() => {
    const currentNodes = latestNodesRef.current;
    const currentEdges = latestEdgesRef.current;
    if (currentNodes.length === 0) return;
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(currentNodes, currentEdges);
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodes.length > 0) {
        if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return;
        handleDeleteSelected();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen, selectedNodes, handleDeleteSelected]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  return (
    <div className={`rf-container ${isFullscreen ? 'rf-fullscreen' : ''}`}>
      <div className="canvas-toolbar">
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          style={{ display: 'none' }}
          onChange={handleFileLoad}
        />
        <button className="canvas-toolbar-btn" onClick={handleAddNode} title="添加节点">
          <Plus size={14} />
        </button>
        <button
          className="canvas-toolbar-btn"
          onClick={handleDeleteSelected}
          disabled={selectedNodes.length === 0}
          title="删除选中节点 (Delete)"
        >
          <Trash2 size={14} />
        </button>
        <div className="canvas-toolbar-divider" />
        <button className="canvas-toolbar-btn" onClick={handleAutoLayout} title="自动布局">
          <Grid size={14} />
        </button>
        <div className="canvas-toolbar-divider" />
        <button className="canvas-toolbar-btn" onClick={handleSaveCanvas} title="导出 JSON">
          <Download size={14} />
        </button>
        <button className="canvas-toolbar-btn" onClick={handleLoadCanvas} title="导入 JSON">
          <Upload size={14} />
        </button>
        <div className="canvas-toolbar-divider" />
        <button
          className="canvas-toolbar-btn canvas-toolbar-fullscreen"
          onClick={toggleFullscreen}
          title={isFullscreen ? '退出全屏' : '全屏'}
        >
          {isFullscreen ? <Minimize size={14} /> : <Maximize size={14} />}
        </button>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChangeHandler}
        onEdgesChange={onEdgesChangeHandler}
        onNodeDoubleClick={handleNodeDoubleClick}
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

      {editNode && (
        <div className="canvas-edit-overlay" onClick={() => setEditNode(null)}>
          <div className="canvas-edit-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="canvas-edit-header">编辑节点</div>
            <div className="canvas-edit-field">
              <label>标签</label>
              <input
                type="text"
                value={editNode.label}
                onChange={(e) => setEditNode({ ...editNode, label: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Enter') handleEditSave(); if (e.key === 'Escape') setEditNode(null); }}
                autoFocus
              />
            </div>
            <div className="canvas-edit-field">
              <label>类型</label>
              <input
                type="text"
                value={editNode.nodeType}
                onChange={(e) => setEditNode({ ...editNode, nodeType: e.target.value })}
              />
            </div>
            <div className="canvas-edit-field">
              <label>分组</label>
              <input
                type="text"
                value={editNode.group}
                onChange={(e) => setEditNode({ ...editNode, group: e.target.value })}
              />
            </div>
            <div className="canvas-edit-actions">
              <button className="canvas-edit-btn cancel" onClick={() => setEditNode(null)}>
                <X size={14} /> 取消
              </button>
              <button className="canvas-edit-btn save" onClick={handleEditSave}>
                <Check size={14} /> 保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

ReactFlowCanvas.displayName = 'ReactFlowCanvas';

export default ReactFlowCanvas;