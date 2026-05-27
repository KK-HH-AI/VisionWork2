import React, { useState, useCallback, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import ReactFlow, {
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Background,
  BackgroundVariant,
  Controls,
  SelectionMode,
  MarkerType,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeTypes,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type EdgeMarker,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { NodeResizer } from '@reactflow/node-resizer';
import '@reactflow/node-resizer/dist/style.css';
import dagre from 'dagre';
import { toPng, toJpeg } from 'html-to-image';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Maximize, Minimize, Plus, Trash2, Download, Upload, Grid, Check, X, Image, Edit3 } from 'react-feather';
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

  dagreGraph.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    const hasRichContent = node.data.richContent || node.data.imageUrl;
    const w = hasRichContent ? 280 : 180;
    const h = hasRichContent ? 180 : 60;
    dagreGraph.setNode(node.id, { width: w, height: h });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const hasRichContent = node.data.richContent || node.data.imageUrl;
    const w = hasRichContent ? 280 : 180;
    const h = hasRichContent ? 180 : 60;
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - w / 2,
        y: nodeWithPosition.y - h / 2,
      },
      style: {
        ...node.style,
        width: w,
        height: h,
        opacity: 1,
        transition: 'opacity 0.2s ease-in',
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

/* ========== CustomNode with rich content support ========== */
function CustomNode({ id, data, selected }: { id: string; data: CanvasNodeData; selected?: boolean }) {
  const borderColor = data.borderColor || NODE_TYPE_COLORS[data.nodeType || ''] || GROUP_COLORS[data.group || ''] || GROUP_COLORS['other'];
  const bgColor = data.backgroundColor || undefined;
  const headerColor = data.borderColor || borderColor;
  const hasRichContent = !!(data.richContent || data.imageUrl);

  return (
    <>
      <NodeResizer
        nodeId={id}
        minWidth={hasRichContent ? 200 : 120}
        minHeight={50}
        isVisible={selected}
        lineStyle={{ borderColor: 'rgba(255,255,255,0.4)' }}
        handleStyle={{ width: 8, height: 8, backgroundColor: '#4B8BBE', border: '1px solid #fff' }}
      />
      <div
        className={`rf-custom-node ${hasRichContent ? 'rf-custom-node-rich' : ''}`}
        style={{
          borderColor,
          backgroundColor: bgColor,
          width: '100%',
          height: '100%',
        }}
      >
        <Handle type="target" position={Position.Top} className="rf-handle" />
        <div className="rf-node-header" style={{ backgroundColor: headerColor }}>
          <span className="rf-node-type">{data.nodeType || data.group || 'module'}</span>
        </div>
        <div className="rf-node-body">
          <span className="rf-node-label">{data.label}</span>
          {data.imageUrl && (
            <div className="rf-node-image-wrap">
              <img src={data.imageUrl} alt={data.label} className="rf-node-image" />
            </div>
          )}
          {data.richContent && (
            <div className="rf-node-rich-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {data.richContent.length > 500 ? data.richContent.substring(0, 500) + '...' : data.richContent}
              </ReactMarkdown>
            </div>
          )}
        </div>
        <Handle type="source" position={Position.Bottom} className="rf-handle" />
      </div>
    </>
  );
}

const nodeTypes: NodeTypes = { customNode: CustomNode };

/* ========== Edge Edit State ========== */
interface EditEdgeState {
  id: string;
  source: string;
  target: string;
  label: string;
  strokeColor: string;
}

/* ========== Node Edit State ========== */
interface EditNodeState {
  id: string;
  label: string;
  nodeType: string;
  group: string;
  richContent: string;
  imageUrl: string;
  backgroundColor: string;
  borderColor: string;
}

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
  const [editNode, setEditNode] = useState<EditNodeState | null>(null);
  const [editEdge, setEditEdge] = useState<EditEdgeState | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nodeCounterRef = useRef(0);
  const flowRef = useRef<HTMLDivElement>(null);

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

  /* ========== Command Processing ========== */
  const processCommand = useCallback(async (command: CanvasCommand) => {
    const cmd = command.cmd;
    const delay = 200;

    if (cmd === 'add_node') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setNodes((nds: CanvasNode[]) => {
        const exists = nds.find(n => n.id === command.id);
        if (exists) {
          return nds.map(n => {
            if (n.id !== command.id) return n;
            return {
              ...n,
              data: {
                ...n.data,
                label: command.label || n.data.label,
                nodeType: command.type || n.data.nodeType,
                group: command.group || n.data.group,
                description: command.description || n.data.description,
                richContent: command.richContent || n.data.richContent,
                imageUrl: command.imageUrl || n.data.imageUrl,
                backgroundColor: command.backgroundColor || n.data.backgroundColor,
                borderColor: command.borderColor || n.data.borderColor,
              },
            };
          });
        }
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
            richContent: command.richContent || '',
            imageUrl: command.imageUrl || '',
            backgroundColor: command.backgroundColor || '',
            borderColor: command.borderColor || '',
          },
          style: {
            width: (command.richContent || command.imageUrl) ? 280 : 180,
            height: (command.richContent || command.imageUrl) ? 180 : 60,
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
              richContent: command.richContent !== undefined ? command.richContent : n.data.richContent,
              imageUrl: command.imageUrl !== undefined ? command.imageUrl : n.data.imageUrl,
              backgroundColor: command.backgroundColor !== undefined ? command.backgroundColor : n.data.backgroundColor,
              borderColor: command.borderColor !== undefined ? command.borderColor : n.data.borderColor,
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
        if (exists) {
          return eds.map(e => {
            if (e.source === command.source && e.target === command.target) {
              const newStroke = command.edgeColor || (e.style as React.CSSProperties)?.stroke;
              return {
                ...e,
                label: command.label || e.label,
                style: { ...((e.style || {}) as React.CSSProperties), stroke: newStroke },
                markerEnd: {
                  ...((e.markerEnd as EdgeMarker) || { type: MarkerType.ArrowClosed }),
                  color: newStroke || (e.markerEnd as EdgeMarker)?.color || edgeMarkerColor,
                } as EdgeMarker,
              };
            }
            return e;
          });
        }
        const newEdge: CanvasEdge = {
          id: `e-${command.source}-${command.target}`,
          source: command.source || '',
          target: command.target || '',
          label: command.label || '',
          type: 'smoothstep',
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: command.edgeColor || edgeMarkerColor } as EdgeMarker,
          style: {
            stroke: command.edgeColor || edgeColor,
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
                ? { ...e, style: { ...((e.style || {}) as React.CSSProperties), opacity: 1 } }
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
    } else if (cmd === 'update_edge') {
      await new Promise(resolve => setTimeout(resolve, delay));
      setEdges((eds: CanvasEdge[]) =>
        eds.map((e) => {
          if (e.id !== command.id) return e;
          return {
            ...e,
            label: (command.label !== undefined ? command.label : e.label) as string,
            style: { ...((e.style || {}) as React.CSSProperties), stroke: command.edgeColor || (e.style as React.CSSProperties)?.stroke },
            markerEnd: {
              ...((e.markerEnd as EdgeMarker) || { type: MarkerType.ArrowClosed, color: edgeMarkerColor }),
              color: command.edgeColor || (e.markerEnd as EdgeMarker)?.color || edgeMarkerColor,
            } as EdgeMarker,
          };
        })
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
        markerEnd: {
          ...((e.markerEnd as EdgeMarker) || { type: MarkerType.ArrowClosed, color: edgeMarkerColor }),
          color: (e.style as React.CSSProperties)?.stroke as string || edgeMarkerColor,
        } as EdgeMarker,
        style: { ...((e.style || {}) as React.CSSProperties) },
        labelStyle: { ...(e.labelStyle as React.CSSProperties || {}), fill: labelColor },
        labelBgStyle: { ...(e.labelBgStyle as React.CSSProperties || {}), fill: labelBgColor },
      }))
    );
  }, [theme, edgeColor, edgeMarkerColor, labelColor, labelBgColor]);

  /* ========== Node Change / Delete Handlers ========== */
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

  /* ========== Node Double-Click -> Rich Edit Dialog ========== */
  const handleNodeDoubleClick = useCallback((_event: React.MouseEvent, node: CanvasNode) => {
    setEditNode({
      id: node.id,
      label: node.data.label || '',
      nodeType: node.data.nodeType || '',
      group: node.data.group || '',
      richContent: node.data.richContent || '',
      imageUrl: node.data.imageUrl || '',
      backgroundColor: node.data.backgroundColor || '',
      borderColor: node.data.borderColor || '',
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
                richContent: editNode.richContent,
                imageUrl: editNode.imageUrl,
                backgroundColor: editNode.backgroundColor,
                borderColor: editNode.borderColor,
              },
            }
          : n
      )
    );
    setEditNode(null);
  }, [editNode]);

  /* ========== Edge Double-Click -> Edit Edge Label & Color ========== */
  const handleEdgeDoubleClick = useCallback((_event: React.MouseEvent, edge: CanvasEdge) => {
    setEditEdge({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: (edge.label as string) || '',
      strokeColor: (edge.style?.stroke as string) || '',
    });
  }, []);

  const handleEdgeEditSave = useCallback(() => {
    if (!editEdge) return;
    setEdges((eds) =>
      eds.map((e) =>
        e.id === editEdge.id
          ? {
              ...e,
              label: editEdge.label as string,
              style: { ...((e.style || {}) as React.CSSProperties), stroke: editEdge.strokeColor || (e.style as React.CSSProperties)?.stroke },
              markerEnd: {
                ...((e.markerEnd as EdgeMarker) || { type: MarkerType.ArrowClosed }),
                color: editEdge.strokeColor || (e.markerEnd as EdgeMarker)?.color || '#888',
              } as EdgeMarker,
            }
          : e
      )
    );
    setEditEdge(null);
  }, [editEdge]);

  /* ========== Connect -> Add Edge (no auto-edit) ========== */
  const handleConnect = useCallback((connection: Connection) => {
    const id = `e-${connection.source}-${connection.target}`;
    setEdges((eds: CanvasEdge[]) => {
      const exists = eds.find(
        e => e.source === connection.source && e.target === connection.target
      );
      if (exists) return eds;
      return addEdge({
        ...connection,
        id,
        type: 'smoothstep',
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#888' } as EdgeMarker,
        style: { stroke: 'rgba(255,255,255,0.3)', strokeWidth: 1.5 },
      }, eds);
    });
  }, []);

  /* ========== Add / Delete Nodes ========== */
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
      style: { width: 180, height: 60 },
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

  /* ========== JSON Import / Export ========== */
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

  /* ========== Image Export (PNG / JPG) ========== */
  const handleExportPng = useCallback(() => {
    const el = flowRef.current?.querySelector('.react-flow__viewport') as HTMLElement;
    if (!el) return;
    toPng(el, { backgroundColor: theme === 'dark' ? '#111' : '#f5f5f5', pixelRatio: 2 })
      .then((dataUrl) => {
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `flowchart-${Date.now()}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      })
      .catch((err) => console.error('Failed to export PNG:', err));
  }, [theme]);

  const handleExportJpg = useCallback(() => {
    const el = flowRef.current?.querySelector('.react-flow__viewport') as HTMLElement;
    if (!el) return;
    toJpeg(el, { backgroundColor: theme === 'dark' ? '#111' : '#f5f5f5', quality: 0.95, pixelRatio: 2 })
      .then((dataUrl) => {
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `flowchart-${Date.now()}.jpg`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      })
      .catch((err) => console.error('Failed to export JPG:', err));
  }, [theme]);

  /* ========== Auto Layout ========== */
  const handleAutoLayout = useCallback(() => {
    const currentNodes = latestNodesRef.current;
    const currentEdges = latestEdgesRef.current;
    if (currentNodes.length === 0) return;
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(currentNodes, currentEdges);
    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, []);

  /* ========== Keyboard Shortcuts ========== */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (editNode) { setEditNode(null); return; }
        if (editEdge) { setEditEdge(null); return; }
        if (isFullscreen) { setIsFullscreen(false); }
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodes.length > 0) {
        if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return;
        handleDeleteSelected();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen, selectedNodes, handleDeleteSelected, editNode, editEdge]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  /* ========== Render ========== */
  return (
    <div className={`rf-container ${isFullscreen ? 'rf-fullscreen' : ''}`} ref={flowRef}>
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
        <button className="canvas-toolbar-btn" onClick={handleExportPng} title="导出 PNG">
          <Image size={14} />
        </button>
        <button className="canvas-toolbar-btn" onClick={handleExportJpg} title="导出 JPG" style={{ fontSize: '11px', fontWeight: 700, lineHeight: '28px' }}>
          JPG
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
        onEdgeDoubleClick={handleEdgeDoubleClick}
        onConnect={handleConnect}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={4}
        selectionOnDrag
        panOnDrag={[1]}
        selectionMode={SelectionMode.Partial}
        selectNodesOnDrag={true}
        defaultEdgeOptions={{
          type: 'smoothstep',
          animated: false,
          style: { stroke: 'rgba(255,255,255,0.2)', strokeWidth: 1 },
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} color={theme === 'dark' ? '#888' : '#aaa'} gap={16} size={2} />
        <Controls className="rf-controls" />
      </ReactFlow>

      {/* ===== Node Edit Dialog ===== */}
      {editNode && (
        <div className="canvas-edit-overlay" onClick={() => setEditNode(null)}>
          <div className="canvas-edit-dialog canvas-edit-dialog-wide" onClick={(e) => e.stopPropagation()}>
            <div className="canvas-edit-header">编辑节点</div>
            <div className="canvas-edit-scroll">
              <div className="canvas-edit-field">
                <label>标签</label>
                <textarea
                  value={editNode.label}
                  onChange={(e) => setEditNode({ ...editNode, label: e.target.value })}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleEditSave(); } if (e.key === 'Escape') setEditNode(null); }}
                  rows={2}
                  autoFocus
                />
              </div>
              <div className="canvas-edit-row">
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
              </div>
              <div className="canvas-edit-row">
                <div className="canvas-edit-field">
                  <label>边框颜色</label>
                  <div className="canvas-color-picker-wrap">
                    <input
                      type="color"
                      value={editNode.borderColor || '#4B8BBE'}
                      onChange={(e) => setEditNode({ ...editNode, borderColor: e.target.value })}
                    />
                    <input
                      type="text"
                      value={editNode.borderColor}
                      onChange={(e) => setEditNode({ ...editNode, borderColor: e.target.value })}
                      placeholder="#4B8BBE"
                    />
                  </div>
                </div>
                <div className="canvas-edit-field">
                  <label>背景颜色</label>
                  <div className="canvas-color-picker-wrap">
                    <input
                      type="color"
                      value={editNode.backgroundColor || '#1a1a2e'}
                      onChange={(e) => setEditNode({ ...editNode, backgroundColor: e.target.value })}
                    />
                    <input
                      type="text"
                      value={editNode.backgroundColor}
                      onChange={(e) => setEditNode({ ...editNode, backgroundColor: e.target.value })}
                      placeholder="留空为默认"
                    />
                  </div>
                </div>
              </div>
              <div className="canvas-edit-field">
                <label>图片链接</label>
                <input
                  type="text"
                  value={editNode.imageUrl}
                  onChange={(e) => setEditNode({ ...editNode, imageUrl: e.target.value })}
                  placeholder="https://example.com/image.png"
                />
              </div>
              <div className="canvas-edit-field">
                <label>富内容 (Markdown)</label>
                <textarea
                  value={editNode.richContent}
                  onChange={(e) => setEditNode({ ...editNode, richContent: e.target.value })}
                  placeholder="支持 Markdown：表格、列表、代码等"
                  rows={6}
                />
              </div>
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

      {/* ===== Edge Edit Dialog ===== */}
      {editEdge && (
        <div className="canvas-edit-overlay" onClick={() => setEditEdge(null)}>
          <div className="canvas-edit-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="canvas-edit-header">
              <Edit3 size={14} />
              <span>编辑边</span>
            </div>
            <div className="canvas-edit-field">
              <label>标注</label>
              <input
                type="text"
                value={editEdge.label}
                onChange={(e) => setEditEdge({ ...editEdge, label: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Enter') { handleEdgeEditSave(); } if (e.key === 'Escape') setEditEdge(null); }}
                placeholder="调用 / 依赖 / 数据流..."
                autoFocus
              />
            </div>
            <div className="canvas-edit-field">
              <label>边颜色</label>
              <div className="canvas-color-picker-wrap">
                <input
                  type="color"
                  value={editEdge.strokeColor || '#888888'}
                  onChange={(e) => setEditEdge({ ...editEdge, strokeColor: e.target.value })}
                />
                <input
                  type="text"
                  value={editEdge.strokeColor}
                  onChange={(e) => setEditEdge({ ...editEdge, strokeColor: e.target.value })}
                  placeholder="#888888"
                />
              </div>
            </div>
            <div className="canvas-edit-actions">
              <button className="canvas-edit-btn cancel" onClick={() => setEditEdge(null)}>
                <X size={14} /> 取消
              </button>
              <button className="canvas-edit-btn save" onClick={handleEdgeEditSave}>
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