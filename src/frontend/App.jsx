import React, { useState, useEffect, useCallback, useRef } from 'react';
import * as d3 from 'd3';

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
  'other': '#9E9E9E'
};

function MemoryGraph({ nodes, edges }) {
  const svgRef = useRef(null);
  const simulationRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const container = svgRef.current.parentElement;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

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
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30))
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
      .attr('r', 8)
      .attr('fill', d => GROUP_COLORS[d.group] || GROUP_COLORS['other'])
      .attr('stroke', 'rgba(255,255,255,0.3)')
      .attr('stroke-width', 1.5);

    nodeGroup.append('text')
      .text(d => d.label)
      .attr('x', 12)
      .attr('y', 4)
      .attr('fill', '#c0c0c0')
      .attr('font-size', '11px')
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
          if (message.type === 'directory_tree') {
            setDirectoryTree(message.tree);
            setCurrentPath(message.path);
            setError('');
          } else if (message.type === 'memory_graph') {
            setGraphNodes(message.nodes);
            setGraphEdges(message.edges || []);
          } else if (message.type === 'analysis_complete') {
            setIsAnalyzing(false);
            setAnalysisComplete(true);
          } else if (message.type === 'error') {
            setError(message.message);
            setIsAnalyzing(false);
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
      try {
        const dirHandle = await window.showDirectoryPicker();
        const tree = await readDirectoryHandle(dirHandle);
        setDirectoryTree(tree);
        setCurrentPath(dirHandle.name);
        setError('');
      } catch (err) {
        if (err.name !== 'AbortError') {
          setError(`读取文件夹失败: ${err.message}`);
        }
      }
    }
  }, [scanDirectory]);

  const simulateAnalysis = useCallback(() => {
    if (ws && connected && currentPath) {
      setIsAnalyzing(true);
      setAnalysisComplete(false);
      setGraphNodes([]);
      setGraphEdges([]);
      ws.send(JSON.stringify({
        type: 'simulate_analysis',
        path: currentPath
      }));
    }
  }, [ws, connected, currentPath]);

  async function readDirectoryHandle(dirHandle) {
    const node = {
      name: dirHandle.name,
      path: dirHandle.name,
      type: 'directory',
      children: []
    };

    const entries = [];
    for await (const entry of dirHandle.values()) {
      entries.push(entry);
    }

    entries.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'directory' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

    for (const entry of entries) {
      if (entry.kind === 'directory') {
        node.children.push(await readDirectoryHandle(entry));
      } else {
        node.children.push({
          name: entry.name,
          path: `${dirHandle.name}/${entry.name}`,
          type: 'file'
        });
      }
    }

    return node;
  }

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
              <button
                className="btn-analyze"
                onClick={simulateAnalysis}
                disabled={isAnalyzing}
              >
                <span className="btn-icon">{isAnalyzing ? '⏳' : '🔬'}</span>
                <span>{isAnalyzing ? '分析中...' : '模拟分析'}</span>
              </button>
            </div>
          )}

          {error && (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              <span>{error}</span>
            </div>
          )}
        </aside>

        <main className="content-area">
          {graphNodes.length > 0 ? (
            <div className="graph-container">
              <div className="graph-header">
                <span className="graph-title">记忆图谱</span>
                <span className="graph-stats">
                  {graphNodes.length} 个节点
                  {analysisComplete && ' · 分析完成'}
                </span>
              </div>
              <MemoryGraph nodes={graphNodes} edges={graphEdges} />
            </div>
          ) : (
            <div className="placeholder-content">
              <h2>欢迎使用 VisionWork2</h2>
              <p>请从左侧导入项目文件夹开始分析</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
