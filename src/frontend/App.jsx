import React, { useState, useEffect, useCallback, useRef } from 'react';
import { flushSync } from 'react-dom';
import * as d3 from 'd3';
import ReactFlow, {
  useNodesState,
  useEdgesState,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';

const FILE_ICONS = {
  'js': '📜', 'jsx': '⚛️', 'ts': '📘', 'tsx': '⚛️',
  'py': '🐍', 'java': '☕', 'cpp': '⚙️', 'c': '⚙️', 'h': '⚙️',
  'html': '🌐', 'css': '🎨', 'scss': '🎨', 'less': '🎨',
  'json': '📋', 'xml': '📋', 'yaml': '📋', 'yml': '📋',
  'md': '📝', 'txt': '📄', 'csv': '📊',
  'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️', 'svg': '🖼️',
  'default': '📄'
};

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  return FILE_ICONS[ext] || FILE_ICONS['default'];
}

function DirectoryTree({ node, depth = 0 }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isDirectory = node.type === 'directory';

  const toggle = () => {
    if (isDirectory) {
      setExpanded(!expanded);
    }
  };

  return (
    <div>
      <div
        className="tree-item"
        style={{ paddingLeft: `${depth * 16}px` }}
        onClick={toggle}
      >
        <span className="tree-icon">
          {isDirectory ? (expanded ? '📂' : '📁') : getFileIcon(node.name)}
        </span>
        <span className="tree-name">{node.name}</span>
      </div>
      {isDirectory && expanded && node.children && (
        <div className="tree-children">
          {node.children.map((child, idx) => (
            <DirectoryTree key={child.path || idx} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

const GROUP_COLORS = {
  'python': '#4B8BBE',
  'javascript': '#F0DB4F',
  'react': '#61DAFB',
  'typescript': '#3178C6',
  'java': '#ED8B00',
  'cpp': '#659AD2',
  'c': '#555555',
  'web': '#E34F26',
  'config': '#6C6C6C',
  'doc': '#8E8E8E',
  'data': '#4CAF50',
  'image': '#9C27B0',
  'module': '#4B8BBE',
  'function': '#E34F26',
  'class': '#ED8B00',
  'interface': '#61DAFB',
  'service': '#4CAF50',
  'component': '#9C27B0',
  'other': '#9E9E9E'
};

const NODE_TYPE_COLORS = {
  'module': '#4B8BBE',
  'function': '#E34F26',
  'class': '#ED8B00',
  'data': '#4CAF50',
  'config': '#6C6C6C',
  'interface': '#61DAFB',
  'service': '#4CAF50',
  'component': '#9C27B0',
};

function MemoryGraph({ nodes, edges }) {
  const svgRef = useRef(null);
  const simulationRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const container = svgRef.current.parentElement;
    const width = container.clientWidth || 300;
    const height = container.clientHeight || 500;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('width', width).attr('height', height);

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
      .attr('stroke', 'rgba(255,255,255,0.15)')
      .attr('stroke-width', 1);

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
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
      .attr('stroke', 'rgba(255,255,255,0.3)')
      .attr('stroke-width', 1.5);

    nodeGroup.append('text')
      .text(d => d.label)
      .attr('x', 10)
      .attr('y', 3)
      .attr('fill', '#c0c0c0')
      .attr('font-size', '10px')
      .attr('font-family', 'sans-serif');

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, edges]);

  return (
    <svg ref={svgRef} className="memory-graph-svg"></svg>
  );
}

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
      <div className="rf-node-header" style={{ backgroundColor: color }}>
        <span className="rf-node-type">{data.nodeType || data.group || 'module'}</span>
      </div>
      <div className="rf-node-body">
        <span className="rf-node-label">{data.label}</span>
      </div>
    </div>
  );
}

const nodeTypes = { customNode: CustomNode };

function ReactFlowCanvas({ nodes, setNodes, edges, setEdges, isSecondPass }) {
  const commandQueueRef = useRef([]);
  const processingRef = useRef(false);
  const reactFlowInstanceRef = useRef(null);
  const latestNodesRef = useRef(nodes);
  const latestEdgesRef = useRef(edges);

  latestNodesRef.current = nodes;
  latestEdgesRef.current = edges;

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
          markerEnd: { type: MarkerType.ArrowClosed, color: '#888' },
          style: {
            stroke: 'rgba(255,255,255,0.3)',
            strokeWidth: 1.5,
            opacity: 0,
            transition: 'opacity 0.2s ease-in',
          },
          labelStyle: { fill: '#aaa', fontSize: 10 },
          labelBgStyle: { fill: 'rgba(26, 26, 46, 0.8)' },
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
        <Background color="rgba(255,255,255,0.05)" gap={20} />
        <Controls className="rf-controls" />
        <MiniMap
          nodeColor={(node) => {
            const color = NODE_TYPE_COLORS[node.data?.nodeType] || GROUP_COLORS[node.data?.group] || '#9E9E9E';
            return color;
          }}
          maskColor="rgba(0,0,0,0.6)"
          style={{ backgroundColor: 'rgba(26, 26, 46, 0.9)' }}
        />
      </ReactFlow>
    </div>
  );
}

function ProgressBar({ currentTask, completedFiles, totalFiles, isAnalyzing }) {
  const percent = totalFiles > 0 ? Math.round((completedFiles / totalFiles) * 100) : 0;

  return (
    <div className="progress-container">
      <div className="progress-header">
        <span className="progress-task">{currentTask || '准备中...'}</span>
        <span className="progress-count">{completedFiles}/{totalFiles}</span>
      </div>
      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

function App() {
  const [ws, setWs] = useState(null);
  const [connected, setConnected] = useState(false);
  const [directoryTree, setDirectoryTree] = useState(null);
  const [currentPath, setCurrentPath] = useState('');
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [graphNodes, setGraphNodes] = useState([]);
  const [graphEdges, setGraphEdges] = useState([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [currentTask, setCurrentTask] = useState('');
  const [completedFiles, setCompletedFiles] = useState(0);
  const [totalFiles, setTotalFiles] = useState(0);
  const [stopFlag, setStopFlag] = useState('');
  const [isSecondPass, setIsSecondPass] = useState(false);

  const [showConfig, setShowConfig] = useState(false);
  const [manualPath, setManualPath] = useState('d:\\总体\\工作\\在校工作经历\\VisionWork2\\workspace\\VisionWork2');
  const [profession, setProfession] = useState('软件工程师');
  const [apiUrl, setApiUrl] = useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('gpt-3.5-turbo');
  const [configSaved, setConfigSaved] = useState(false);

  const [canvasNodes, setCanvasNodes] = useNodesState([]);
  const [canvasEdges, setCanvasEdges] = useEdgesState([]);

  const setCanvasNodesWrapped = useCallback((updater) => {
    if (typeof updater === 'function') {
      setCanvasNodes(updater);
    } else {
      setCanvasNodes(updater);
    }
  }, [setCanvasNodes]);

  const setCanvasEdgesWrapped = useCallback((updater) => {
    if (typeof updater === 'function') {
      setCanvasEdges(updater);
    } else {
      setCanvasEdges(updater);
    }
  }, [setCanvasEdges]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('visionwork2_config');
      if (saved) {
        const config = JSON.parse(saved);
        if (config.profession) setProfession(config.profession);
        if (config.apiUrl) setApiUrl(config.apiUrl);
        if (config.apiKey) setApiKey(config.apiKey);
        if (config.modelName) setModelName(config.modelName);
      }
    } catch (e) {
      console.error('Failed to load config:', e);
    }
  }, []);

  useEffect(() => {
    try {
      const configData = { profession, apiUrl, apiKey, modelName };
      localStorage.setItem('visionwork2_config', JSON.stringify(configData));
      setConfigSaved(true);
      setTimeout(() => setConfigSaved(false), 2000);
    } catch (e) {
      console.error('Failed to save config:', e);
    }
  }, [profession, apiUrl, apiKey, modelName]);

  useEffect(() => {
    async function connect() {
      try {
        let port, token;

        if (window.electronAPI) {
          const config = await window.electronAPI.getBackendConfig();
          port = config.port;
          token = config.token;
        } else {
          port = 8765;
          token = 'dev-token';
        }

        const wsUrl = `ws://127.0.0.1:${port}/ws?token=${token}`;
        const websocket = new WebSocket(wsUrl);

        websocket.onopen = () => {
          setConnected(true);
          setError('');
        };

        websocket.onclose = () => {
          setConnected(false);
        };

        websocket.onmessage = (event) => {
          const message = JSON.parse(event.data);
          console.log('[WS] Received message:', message.type, message);

          if (message.type === 'directory_tree') {
            flushSync(() => {
              setDirectoryTree(message.tree);
              setCurrentPath(message.path);
              setError('');
            });
          } else if (message.type === 'memory_graph') {
            flushSync(() => {
              setGraphNodes(message.nodes || []);
              setGraphEdges(message.edges || []);
            });
          } else if (message.type === 'canvas_command') {
            const cmd = message.command;
            if (cmd && cmd.cmd) {
              console.log('[Canvas] Enqueue command:', cmd.cmd, cmd.id || cmd.source || '');
              if (window.__enqueueCanvasCommand) {
                window.__enqueueCanvasCommand(cmd);
              } else {
                console.warn('[Canvas] __enqueueCanvasCommand not ready, command dropped:', cmd.cmd);
              }
            }
          } else if (message.type === 'progress') {
            flushSync(() => {
              setCurrentTask(message.currentTask || '');
              setCompletedFiles(message.completedFiles || 0);
              setTotalFiles(message.totalFiles || 0);
            });
          } else if (message.type === 'first_pass_complete') {
            flushSync(() => {
              setCurrentTask('第一层阅读完成，正在进入第二层分析...');
              setIsSecondPass(true);
            });
          } else if (message.type === 'analysis_complete') {
            flushSync(() => {
              setIsAnalyzing(false);
              setAnalysisComplete(true);
              setCurrentTask('分析完成');
              setIsSecondPass(false);
            });
          } else if (message.type === 'stopped') {
            flushSync(() => {
              setIsAnalyzing(false);
              setCurrentTask(`已停止分析，已完成 ${message.completedFiles || 0}/${message.totalFiles || 0} 份文件`);
              setIsSecondPass(false);
            });
          } else if (message.type === 'error') {
            flushSync(() => {
              setError(message.message);
              setIsAnalyzing(false);
              setIsSecondPass(false);
            });
          } else if (message.type === 'pong') {
          }
        };

        websocket.onerror = () => {
          setError('WebSocket connection failed');
          setConnected(false);
        };

        setWs(websocket);
      } catch (err) {
        setError(`Connection failed: ${err.message}`);
      }
    }

    connect();

    return () => {
      if (ws) ws.close();
    };
  }, []);

  const scanDirectory = useCallback((folderPath) => {
    if (ws && connected) {
      ws.send(JSON.stringify({
        type: 'scan_directory',
        path: folderPath
      }));
    }
  }, [ws, connected]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);

    let droppedPath = '';

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.path) {
        droppedPath = file.path;
      }
    }

    if (!droppedPath && e.dataTransfer.getData) {
      droppedPath = e.dataTransfer.getData('text/uri-list') || '';
      if (droppedPath.startsWith('file://')) {
        droppedPath = decodeURIComponent(droppedPath.replace('file:///', '').replace(/\//g, '\\'));
      }
    }

    if (droppedPath) {
      scanDirectory(droppedPath);
    }
  }, [scanDirectory]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleSelectFolder = useCallback(async () => {
    if (window.electronAPI && window.electronAPI.selectFolder) {
      const folderPath = await window.electronAPI.selectFolder();
      if (folderPath) {
        scanDirectory(folderPath);
      }
    } else if (window.showDirectoryPicker) {
      if (!manualPath.trim()) {
        setError('请先在上方输入文件夹完整路径');
        return;
      }
      scanDirectory(manualPath);
    }
  }, [scanDirectory, manualPath]);

  const startLLMAnalysis = useCallback(() => {
    if (ws && connected && currentPath) {
      if (!apiKey.trim()) {
        setError('请输入 API Key');
        return;
      }
      const actualPath = window.electronAPI ? currentPath : manualPath;
      if (!actualPath.trim()) {
        setError('请设置文件夹路径');
        return;
      }
      const newStopFlag = `stop_${Date.now()}`;
      setStopFlag(newStopFlag);
      setIsAnalyzing(true);
      setAnalysisComplete(false);
      setIsSecondPass(false);
      setGraphNodes([]);
      setGraphEdges([]);
      setCanvasNodes([]);
      setCanvasEdges([]);
      setCurrentTask('正在初始化...');
      setCompletedFiles(0);
      setTotalFiles(0);
      setError('');
      ws.send(JSON.stringify({
        type: 'start_analysis',
        path: actualPath,
        profession: profession,
        api_url: apiUrl,
        api_key: apiKey,
        model_name: modelName,
        stop_flag: newStopFlag,
      }));
    }
  }, [ws, connected, currentPath, profession, apiUrl, apiKey, modelName, manualPath]);

  const stopAnalysis = useCallback(() => {
    if (ws && connected && stopFlag) {
      ws.send(JSON.stringify({
        type: 'stop_analysis',
        stop_flag: stopFlag,
      }));
      setCurrentTask('正在请求停止分析...');
    } else {
      setError('无法发送停止命令，请检查连接状态');
    }
  }, [ws, connected, stopFlag]);

  const simulateAnalysis = useCallback(() => {
    if (ws && connected && currentPath) {
      setIsAnalyzing(true);
      setAnalysisComplete(false);
      setIsSecondPass(false);
      setGraphNodes([]);
      setGraphEdges([]);
      setCanvasNodes([]);
      setCanvasEdges([]);
      ws.send(JSON.stringify({
        type: 'simulate_analysis',
        path: currentPath
      }));
    }
  }, [ws, connected, currentPath]);

  return (
    <div className="app-container">
      <header className="header">
        <h1>VisionWork2</h1>
        <div className={`status ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '已连接' : '未连接'}
        </div>
      </header>

      <div className="main-content">
        <aside className="sidebar">
          <div className="sidebar-header">
            <h2>项目目录</h2>
            <button className="btn-select" onClick={handleSelectFolder}>
              <span className="btn-icon">📂</span>
              <span>选择文件夹</span>
            </button>
          </div>

          <div className="config-toggle" onClick={() => setShowConfig(!showConfig)}>
            <span className="config-toggle-icon">{showConfig ? '▼' : '▶'}</span>
            <span>模型配置</span>
          </div>

          {showConfig && (
            <div className="config-panel">
              <div className="config-field">
                <label>职业角色</label>
                <input
                  type="text"
                  value={profession}
                  onChange={(e) => setProfession(e.target.value)}
                  placeholder="例如：Python后端工程师"
                  disabled={isAnalyzing}
                />
              </div>
              <div className="config-field">
                <label>API 地址</label>
                <input
                  type="text"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                  disabled={isAnalyzing}
                />
              </div>
              <div className="config-field">
                <label>API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  disabled={isAnalyzing}
                />
              </div>
              <div className="config-field">
                <label>模型名称</label>
                <input
                  type="text"
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  placeholder="gpt-3.5-turbo"
                  disabled={isAnalyzing}
                />
              </div>
              {configSaved && (
                <div className="config-saved-hint">✅ 配置已自动保存</div>
              )}
            </div>
          )}

          {currentPath && (
            <div className="current-path">
              <span className="path-icon">📍</span>
              <span className="path-text" title={currentPath}>{currentPath}</span>
            </div>
          )}

          <div
            className={`drop-zone ${isDragging ? 'dragging' : ''} ${directoryTree ? 'has-tree' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {!directoryTree && (
              <div className="drop-placeholder">
                <div className="drop-icon">📂</div>
                <p className="drop-title">拖入项目文件夹</p>
                <p className="drop-hint">或将文件夹拖放到此处</p>
              </div>
            )}
          </div>

          {directoryTree && (
            <div className="tree-container">
              <DirectoryTree node={directoryTree} />
            </div>
          )}

          {directoryTree && (
            <div className="analysis-actions">
              <ProgressBar
                currentTask={currentTask}
                completedFiles={completedFiles}
                totalFiles={totalFiles}
                isAnalyzing={isAnalyzing}
              />

              <div className="btn-group">
                {isAnalyzing ? (
                  <button
                    className="btn-analyze btn-analyze-danger"
                    onClick={stopAnalysis}
                  >
                    <span className="btn-icon">⛔</span>
                    <span>停止分析</span>
                  </button>
                ) : (
                  <>
                    <button
                      className="btn-analyze btn-analyze-primary"
                      onClick={startLLMAnalysis}
                      disabled={!apiKey.trim()}
                    >
                      <span className="btn-icon">🚀</span>
                      <span>开始分析</span>
                    </button>
                    <button
                      className="btn-analyze btn-analyze-secondary"
                      onClick={simulateAnalysis}
                      disabled={isAnalyzing}
                    >
                      <span className="btn-icon">🔬</span>
                      <span>模拟分析</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              <span>{error}</span>
            </div>
          )}
        </aside>

        <main className="canvas-area">
          <div className="graph-container">
            <div className="graph-header">
              <span className="graph-title">
                {isSecondPass ? '第二层分析 · 流式画布' : '分析画布'}
              </span>
              <span className="graph-stats">
                {canvasNodes.length > 0
                  ? `${canvasNodes.length} 个节点 · ${canvasEdges.length} 条连线`
                  : '等待分析开始...'}
                {isSecondPass && ' · 流式渲染中...'}
              </span>
            </div>
            <ReactFlowProvider>
              <ReactFlowCanvas
                nodes={canvasNodes}
                setNodes={setCanvasNodesWrapped}
                edges={canvasEdges}
                setEdges={setCanvasEdgesWrapped}
                isSecondPass={isSecondPass}
              />
            </ReactFlowProvider>
          </div>
        </main>

        <aside className="memory-panel">
          <div className="graph-container">
            <div className="graph-header">
              <span className="graph-title">记忆图谱</span>
              <span className="graph-stats">
                {graphNodes.length > 0
                  ? `${graphNodes.length} 个节点${analysisComplete ? ' · 分析完成' : ''}`
                  : '等待分析开始...'}
              </span>
            </div>
            <MemoryGraph nodes={graphNodes} edges={graphEdges} />
          </div>
        </aside>
      </div>
    </div>
  );
}

export default App;
