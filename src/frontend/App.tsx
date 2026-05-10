import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNodesState, useEdgesState, type Node, type Edge } from 'reactflow';
import {
  Sun,
  Moon,
  Folder,
  ChevronDown,
  ChevronRight,
  Play,
  Square,
  AlertTriangle,
  BarChart2,
  FileText,
  Check,
  Save,
  RefreshCw,
} from 'react-feather';
import useWebSocket from './hooks/useWebSocket';
import DirectoryTree from './components/DirectoryTree';
import MemoryGraph from './components/MemoryGraph';
import ReactFlowCanvas from './components/ReactFlowCanvas';
import ProgressBar from './components/ProgressBar';
import CodeViewPanel from './components/CodeViewPanel';
import ConfigPanel from './components/ConfigPanel';
import WorkspaceTree from './components/WorkspaceTree';
import type {
  DirectoryNode,
  GraphNode,
  GraphEdge,
  MemoryNote,
  WorkspaceItem,
  CodeFileRef,
  WSMessage,
} from './types';

declare global {
  interface Window {
    electronAPI?: {
      getBackendConfig: () => Promise<{ port: number; token: string; ready: boolean }>;
      selectFolder: () => Promise<string | null>;
      readFile: (filePath: string) => Promise<{ success: boolean; content?: string; error?: string; size?: number }>;
    };
    showDirectoryPicker?: () => Promise<FileSystemDirectoryHandle>;
  }
}

export default function App() {
  const [directoryTree, setDirectoryTree] = useState<DirectoryNode | null>(null);
  const [currentPath, setCurrentPath] = useState('');
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [memoryNotes, setMemoryNotes] = useState<MemoryNote[]>([]);
  const [memoryDir, setMemoryDir] = useState('');
  const [selectedMemoryNote, setSelectedMemoryNote] = useState<MemoryNote | null>(null);
  const [memoryNoteContent, setMemoryNoteContent] = useState('');
  const [memoryNoteSaving, setMemoryNoteSaving] = useState(false);
  const [memoryNoteLoading, setMemoryNoteLoading] = useState(false);
  const [memoryNoteError, setMemoryNoteError] = useState('');
  const [memoryNoteSaved, setMemoryNoteSaved] = useState(false);
  const [showMemoryNotes, setShowMemoryNotes] = useState(false);
  const [workspaceTree, setWorkspaceTree] = useState<WorkspaceItem[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentTask, setCurrentTask] = useState('');
  const [completedFiles, setCompletedFiles] = useState(0);
  const [totalFiles, setTotalFiles] = useState(0);
  const [stopFlag, setStopFlag] = useState('');
  const [isSecondPass, setIsSecondPass] = useState(false);
  const [retrievalPath, setRetrievalPath] = useState<string[]>([]);
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem('visionwork2_theme');
      return saved || 'dark';
    } catch (e) {
      return 'dark';
    }
  });

  const [showConfig, setShowConfig] = useState(false);
  const [manualPath, setManualPath] = useState('d:\\总体\\工作\\在校工作经历\\VisionWork2\\workspace\\VisionWork2');
  const [profession, setProfession] = useState('软件工程师');
  const [apiUrl, setApiUrl] = useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('gpt-3.5-turbo');
  const [configSaved, setConfigSaved] = useState(false);

  const [canvasNodes, setCanvasNodes] = useNodesState([]);
  const [canvasEdges, setCanvasEdges] = useEdgesState([]);

  const [sidebarWidth, setSidebarWidth] = useState(340);
  const [memoryPanelWidth, setMemoryPanelWidth] = useState(340);
  const isDraggingRef = useRef<string | false>(false);

  const [codeViewNode, setCodeViewNode] = useState<Node | null>(null);
  const [codeFileList, setCodeFileList] = useState<CodeFileRef[]>([]);
  const [selectedCodeFile, setSelectedCodeFile] = useState<CodeFileRef | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileContentLoading, setFileContentLoading] = useState(false);
  const [fileContentError, setFileContentError] = useState('');
  const [highlightLines, setHighlightLines] = useState<[number, number] | null>(null);

  const setCanvasNodesWrapped = useCallback((updater: Node[] | ((nds: Node[]) => Node[])) => {
    if (typeof updater === 'function') {
      setCanvasNodes(updater);
    } else {
      setCanvasNodes(updater);
    }
  }, [setCanvasNodes]);

  const setCanvasEdgesWrapped = useCallback((updater: Edge[] | ((eds: Edge[]) => Edge[])) => {
    if (typeof updater === 'function') {
      setCanvasEdges(updater);
    } else {
      setCanvasEdges(updater);
    }
  }, [setCanvasEdges]);

  const messageHandlers = {
    onDirectoryTree: (msg: WSMessage) => {
      setDirectoryTree(msg.tree || null);
      setCurrentPath(msg.path || '');
      setError('');
    },
    onMemoryGraph: (msg: WSMessage) => {
      setGraphNodes(msg.nodes || []);
      setGraphEdges(msg.edges || []);
      if (msg.memory_dir) {
        setMemoryDir(msg.memory_dir);
        loadMemoryDir(msg.memory_dir);
      }
    },
    onProgress: (msg: WSMessage) => {
      setCurrentTask(msg.currentTask || '');
      setCompletedFiles(msg.completedFiles || 0);
      setTotalFiles(msg.totalFiles || 0);
    },
    onFirstPassComplete: () => {
      setCurrentTask('第一层阅读完成，正在进入第二层分析...');
      setIsSecondPass(true);
    },
    onAnalysisComplete: () => {
      setIsAnalyzing(false);
      setCurrentTask('分析完成');
      setIsSecondPass(false);
    },
    onMemoryPathUpdate: (msg: WSMessage) => {
      setRetrievalPath(msg.nodeIds || []);
    },
    onStopped: (msg: WSMessage) => {
      setIsAnalyzing(false);
      setCurrentTask(`已停止分析，已完成 ${msg.completedFiles || 0}/${msg.totalFiles || 0} 份文件`);
      setIsSecondPass(false);
    },
    onError: (msg: string | WSMessage) => {
      setError(typeof msg === 'string' ? msg : msg.message || '');
      setIsAnalyzing(false);
      setIsSecondPass(false);
    },
  };

  const { ws, connected, sendMessage, backendPortRef } = useWebSocket(messageHandlers);

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
      localStorage.setItem('visionwork2_theme', theme);
      document.body.className = theme === 'dark' ? 'theme-dark' : 'theme-light';
    } catch (e) {
      console.error('Failed to save theme:', e);
    }
  }, [theme]);

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

  const loadMemoryDir = async (dir: string) => {
    if (!dir) return;
    try {
      const port = backendPortRef.current;
      const token = new URLSearchParams(window.location.search).get('token') || '';
      const response = await fetch(`http://127.0.0.1:${port}/list-memory-dir?memory_dir=${encodeURIComponent(dir)}&token=${token}`);
      const data = await response.json();
      if (data.success) {
        setMemoryNotes(data.files);
      }
    } catch (e) {
      console.error('Failed to load memory directory:', e);
    }
  };

  const loadMemoryDirByPath = async () => {
    try {
      const port = backendPortRef.current;
      let token = '';
      if (window.electronAPI) {
        const config = await window.electronAPI.getBackendConfig();
        token = config.token;
      } else {
        token = new URLSearchParams(window.location.search).get('token') || 'dev-token';
      }
      const response = await fetch(`http://127.0.0.1:${port}/get-workspace-tree?token=${token}`);
      const data = await response.json();
      console.log('[Workspace] get-workspace-tree response:', data);
      if (data.success) {
        setMemoryDir(data.workspace_dir);
        setWorkspaceTree(data.tree);
      }
    } catch (e) {
      console.error('Failed to load workspace tree:', e);
    }
  };

  useEffect(() => {
    if (connected) {
      loadMemoryDirByPath();
    }
  }, [connected]);

  const scanDirectory = useCallback((folderPath: string) => {
    sendMessage({ type: 'scan_directory', path: folderPath });
  }, [sendMessage]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    let droppedPath = '';
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if ((file as unknown as { path?: string }).path) {
        droppedPath = (file as unknown as { path: string }).path;
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

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
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
    if (!connected || !currentPath) return;
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
    setIsSecondPass(false);
    setGraphNodes([]);
    setGraphEdges([]);
    setCanvasNodes([]);
    setCanvasEdges([]);
    setRetrievalPath([]);
    setCurrentTask('正在初始化...');
    setCompletedFiles(0);
    setTotalFiles(0);
    setError('');
    sendMessage({
      type: 'start_analysis',
      path: actualPath,
      profession,
      api_url: apiUrl,
      api_key: apiKey,
      model_name: modelName,
      stop_flag: newStopFlag,
    });
  }, [connected, currentPath, apiKey, manualPath, profession, apiUrl, modelName, sendMessage]);

  const stopAnalysis = useCallback(() => {
    if (!connected || !stopFlag) return;
    sendMessage({ type: 'stop_analysis', stop_flag: stopFlag });
    setCurrentTask('正在请求停止分析...');
  }, [connected, stopFlag, sendMessage]);

  const handleNodeDoubleClick = useCallback((node: Node) => {
    const codeRef = (node.data as Record<string, unknown>)?.codeRef as CodeFileRef[] | undefined;
    if (!codeRef || !Array.isArray(codeRef) || codeRef.length === 0) {
      setError('该节点没有关联的代码文件');
      setTimeout(() => setError(''), 3000);
      return;
    }
    const seen = new Set<string>();
    const files: CodeFileRef[] = [];
    codeRef.forEach(ref => {
      if (ref.file && !seen.has(ref.file)) {
        seen.add(ref.file);
        files.push({ file: ref.file, lines: ref.lines || null });
      }
    });
    setCodeViewNode(node);
    setCodeFileList(files);
    setSelectedCodeFile(null);
    setFileContent('');
    setFileContentError('');
    setHighlightLines(null);
  }, []);

  const loadFileContent = useCallback(async (fileRef: CodeFileRef) => {
    setFileContentLoading(true);
    setFileContentError('');
    setSelectedCodeFile(fileRef);
    setHighlightLines(fileRef.lines || null);
    try {
      if (window.electronAPI && window.electronAPI.readFile) {
        const result = await window.electronAPI.readFile(fileRef.file);
        if (result.success) {
          setFileContent(result.content || '');
        } else {
          setFileContentError(result.error || '');
          setFileContent('');
        }
      } else {
        const port = backendPortRef.current;
        const response = await fetch(`http://127.0.0.1:${port}/read-file?path=${encodeURIComponent(fileRef.file)}`);
        if (response.ok) {
          const data = await response.json();
          setFileContent(data.content);
        } else {
          setFileContentError('无法读取文件（非Electron环境）');
          setFileContent('');
        }
      }
    } catch (err) {
      setFileContentError(`读取文件失败: ${(err as Error).message}`);
      setFileContent('');
    } finally {
      setFileContentLoading(false);
    }
  }, []);

  const handleFileClick = useCallback((fileRef: CodeFileRef) => {
    loadFileContent(fileRef);
  }, [loadFileContent]);

  const handleBackToTree = useCallback(() => {
    setCodeViewNode(null);
    setCodeFileList([]);
    setSelectedCodeFile(null);
    setFileContent('');
    setFileContentError('');
    setHighlightLines(null);
  }, []);

  const handleMemoryNoteClick = async (note: WorkspaceItem) => {
    setSelectedMemoryNote(note as unknown as MemoryNote);
    setShowMemoryNotes(true);
    setMemoryNoteContent('');
    setMemoryNoteError('');
    setMemoryNoteLoading(true);
    try {
      const port = backendPortRef.current;
      const token = new URLSearchParams(window.location.search).get('token') || '';
      const response = await fetch(`http://127.0.0.1:${port}/read-file?path=${encodeURIComponent(note.path)}&token=${token}`);
      const data = await response.json();
      if (data.success) {
        setMemoryNoteContent(data.content);
      } else {
        setMemoryNoteError('无法读取文件内容');
      }
    } catch (e) {
      setMemoryNoteError('读取文件失败: ' + (e as Error).message);
    } finally {
      setMemoryNoteLoading(false);
    }
  };

  const handleSaveMemoryNote = async () => {
    if (!selectedMemoryNote || !selectedMemoryNote.path) return;
    setMemoryNoteSaving(true);
    try {
      const port = backendPortRef.current;
      const token = new URLSearchParams(window.location.search).get('token') || '';
      const response = await fetch(`http://127.0.0.1:${port}/save-file?token=${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedMemoryNote.path, content: memoryNoteContent }),
      });
      const data = await response.json();
      if (data.success) {
        setMemoryNoteSaved(true);
        setTimeout(() => setMemoryNoteSaved(false), 2000);
      } else {
        setMemoryNoteError('保存失败: ' + (data.detail || '未知错误'));
      }
    } catch (e) {
      setMemoryNoteError('保存失败: ' + (e as Error).message);
    } finally {
      setMemoryNoteSaving(false);
    }
  };

  const toggleDir = (path: string) => {
    setExpandedDirs(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const handleMouseMoveRef = useRef<((e: MouseEvent) => void) | null>(null);
  const handleMouseUpRef = useRef<(() => void) | null>(null);

  handleMouseMoveRef.current = (e: MouseEvent) => {
    if (!isDraggingRef.current) return;
    if (isDraggingRef.current === 'left') {
      const newWidth = Math.max(250, Math.min(500, e.clientX));
      setSidebarWidth(newWidth);
    } else if (isDraggingRef.current === 'right') {
      const newWidth = Math.max(250, Math.min(500, window.innerWidth - e.clientX));
      setMemoryPanelWidth(newWidth);
    }
  };

  handleMouseUpRef.current = () => {
    isDraggingRef.current = false;
    document.removeEventListener('mousemove', handleMouseMoveRef.current!);
    document.removeEventListener('mouseup', handleMouseUpRef.current!);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };

  const handleMouseDown = useCallback((panel: string) => {
    isDraggingRef.current = panel;
    document.addEventListener('mousemove', handleMouseMoveRef.current!);
    document.addEventListener('mouseup', handleMouseUpRef.current!);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>VisionWork2</h1>
        <div className="header-right">
          <button className="btn-theme-toggle" onClick={toggleTheme} title="切换主题">
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <div className={`status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '已连接' : '未连接'}
          </div>
        </div>
      </header>

      <div className="main-content" style={{ '--sidebar-width': sidebarWidth + 'px', '--memory-panel-width': memoryPanelWidth + 'px' } as React.CSSProperties}>
        <aside className="sidebar">
          <div className="sidebar-header">
            <h2>项目目录</h2>
            <button className="btn-select" onClick={handleSelectFolder}>
              <Folder size={16} />
              <span>选择文件夹</span>
            </button>
          </div>

          <div className="config-toggle" onClick={() => setShowConfig(!showConfig)}>
            <span className="config-toggle-icon">{showConfig ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
            <span>模型配置</span>
          </div>

          {showConfig && (
            <ConfigPanel
              profession={profession}
              setProfession={setProfession}
              apiUrl={apiUrl}
              setApiUrl={setApiUrl}
              apiKey={apiKey}
              setApiKey={setApiKey}
              modelName={modelName}
              setModelName={setModelName}
              isAnalyzing={isAnalyzing}
              configSaved={configSaved}
            />
          )}

          <div
            className={`drop-zone ${isDragging ? 'dragging' : ''} ${directoryTree ? 'has-tree' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {!directoryTree && !codeViewNode && (
              <div className="drop-placeholder">
                <Folder size={48} />
                <p className="drop-title">拖入项目文件夹</p>
                <p className="drop-hint">或将文件夹拖放到此处</p>
              </div>
            )}
          </div>

          {codeViewNode ? (
            <CodeViewPanel
              codeViewNode={codeViewNode}
              codeFileList={codeFileList}
              selectedCodeFile={selectedCodeFile}
              fileContent={fileContent}
              fileContentLoading={fileContentLoading}
              fileContentError={fileContentError}
              highlightLines={highlightLines}
              theme={theme}
              onBackToTree={handleBackToTree}
              onFileClick={handleFileClick}
              loadFileContent={loadFileContent}
            />
          ) : (
            <>
              {directoryTree && (
                <div className="tree-container">
                  <DirectoryTree node={directoryTree} />
                </div>
              )}
            </>
          )}

          {directoryTree && (
            <div className="analysis-actions">
              <ProgressBar
                currentTask={currentTask}
                completedFiles={completedFiles}
                totalFiles={totalFiles}
              />
              <div className="btn-group">
                {isAnalyzing ? (
                  <button className="btn-analyze btn-analyze-danger" onClick={stopAnalysis}>
                    <Square size={16} />
                    <span>停止分析</span>
                  </button>
                ) : (
                  <button className="btn-analyze btn-analyze-primary" onClick={startLLMAnalysis}>
                    <Play size={16} />
                    <span>开始分析</span>
                  </button>
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="error-message">
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
          )}
        </aside>

        <div
          className="resize-handle resize-handle-left"
          onMouseDown={() => handleMouseDown('left')}
        />

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
            <ReactFlowCanvas
              nodes={canvasNodes}
              setNodes={setCanvasNodesWrapped}
              edges={canvasEdges}
              setEdges={setCanvasEdgesWrapped}
              isSecondPass={isSecondPass}
              onNodeDoubleClick={handleNodeDoubleClick}
              theme={theme}
            />
          </div>
        </main>

        <div
          className="resize-handle resize-handle-right"
          onMouseDown={() => handleMouseDown('right')}
        />

        <aside className="memory-panel">
          {!showMemoryNotes ? (
            <div className="memory-panel-content">
              <div className="memory-panel-section">
                <div className="graph-header">
                  <span className="graph-title">记忆图谱</span>
                  <span className="graph-stats">
                    {graphNodes.length > 0
                      ? `${graphNodes.length} 个节点`
                      : '等待分析开始...'}
                  </span>
                </div>
                <div className="memory-graph-wrapper">
                  {graphNodes.length > 0 ? (
                    <MemoryGraph
                      nodes={graphNodes}
                      edges={graphEdges}
                      retrievalPath={retrievalPath}
                      theme={theme}
                      onNodeClick={handleMemoryNoteClick as unknown as (node: GraphNode) => void}
                    />
                  ) : (
                    <div className="memory-notes-empty">
                      <BarChart2 size={48} />
                      <p>暂无图谱</p>
                      <p className="empty-hint">选择项目文件夹并开始分析后，智能体会生成记忆图谱</p>
                    </div>
                  )}
                </div>
              </div>
              <div className="memory-panel-section memory-panel-section-tree">
                <div className="graph-header">
                  <span className="graph-title">工作区笔记</span>
                  <span className="graph-stats">
                    {workspaceTree.length > 0
                      ? `${(() => { let c = 0; for (const item of workspaceTree) { if (item.type === 'file') c++; else if (item.children) { for (const child of item.children) { if (child.type === 'file') c++; else if (child.children) c += child.children.filter(cc => cc.type === 'file').length; } } } return c; })()} 个笔记文件`
                      : '选择项目文件夹即可查看'}
                    <button className="btn-refresh-tree" onClick={loadMemoryDirByPath} title="刷新文件树">
                      <RefreshCw size={14} />
                    </button>
                  </span>
                </div>
                <WorkspaceTree
                  workspaceTree={workspaceTree}
                  expandedDirs={expandedDirs}
                  onToggleDir={toggleDir}
                  onNoteClick={handleMemoryNoteClick}
                />
              </div>
            </div>
          ) : (
            <div className="memory-note-editor">
              <div className="memory-note-header">
                <button className="btn-back" onClick={() => { setShowMemoryNotes(false); }}>
                  ← 返回
                </button>
                <span className="memory-note-title" title={selectedMemoryNote?.name}>
                  <FileText size={16} />
                  {' '}{selectedMemoryNote?.name}
                </span>
                <button
                  className="btn-save"
                  onClick={handleSaveMemoryNote}
                  disabled={memoryNoteSaving}
                >
                  {memoryNoteSaving ? '保存中...' : memoryNoteSaved ? <><Check size={14} /> 已保存</> : <><Save size={14} /> 保存</>}
                </button>
              </div>
              <div className="memory-note-body">
                {memoryNoteLoading ? (
                  <div className="memory-note-loading">加载中...</div>
                ) : memoryNoteError ? (
                  <div className="memory-note-error">{memoryNoteError}</div>
                ) : (
                  <textarea
                    className="memory-note-textarea"
                    value={memoryNoteContent}
                    onChange={(e) => setMemoryNoteContent(e.target.value)}
                    spellCheck={false}
                  />
                )}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
