import React, { useState, useEffect, useCallback } from 'react';

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

function App() {
  const [ws, setWs] = useState(null);
  const [connected, setConnected] = useState(false);
  const [directoryTree, setDirectoryTree] = useState(null);
  const [currentPath, setCurrentPath] = useState('');
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);

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
          } else if (message.type === 'error') {
            setError(message.message);
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

          {error && (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              <span>{error}</span>
            </div>
          )}
        </aside>

        <main className="content-area">
          <div className="placeholder-content">
            <h2>欢迎使用 VisionWork2</h2>
            <p>请从左侧导入项目文件夹开始分析</p>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
