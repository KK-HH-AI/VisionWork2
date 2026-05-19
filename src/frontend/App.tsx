import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Menu, Sidebar, Sun, Moon } from 'react-feather';
import useWebSocket from './hooks/useWebSocket';
import SessionSidebar from './components/SessionSidebar';
import RightPanel from './components/RightPanel';
import ChatView from './components/ChatView';
import ReactFlowCanvas from './components/ReactFlowCanvas';
import type { ReactFlowCanvasHandle } from './components/ReactFlowCanvas';
import MemoryGraph from './components/MemoryGraph';
import MemoryFileModal from './components/MemoryFileModal';
import ConfigPanel from './components/ConfigPanel';
import SkillManager from './components/SkillManager';
import type { ChatMessage, WSMessage, SessionData, CanvasEdge as StoredCanvasEdge, GraphNode, GraphEdge } from './types';
import {
  loadSessions,
  loadCurrentSessionId,
  createSession,
  updateSession,
  deleteSession,
  switchToSession,
  ensureCurrentSession,
} from './utils/sessionStore';

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

let msgIdCounter = 0;
function nextMsgId(): string {
  msgIdCounter += 1;
  return `msg_${Date.now()}_${msgIdCounter}`;
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem('visionwork2_theme');
      return saved || 'dark';
    } catch (e) {
      return 'dark';
    }
  });

  const [sessionSidebarOpen, setSessionSidebarOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [showSkillManager, setShowSkillManager] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [scanTag, setScanTag] = useState<string | null>(null);
  const [rightPanelInitialTab, setRightPanelInitialTab] = useState<'notes' | 'files' | undefined>(undefined);
  const [memoryFileModalOpen, setMemoryFileModalOpen] = useState(false);
  const [memoryFileModalPath, setMemoryFileModalPath] = useState('');
  const [memoryFileModalName, setMemoryFileModalName] = useState('');

  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [retrievalPath, setRetrievalPath] = useState<string[]>([]);

  const [apiUrl, setApiUrl] = useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('gpt-3.5-turbo');
  const [configSaved, setConfigSaved] = useState(false);

  const [sessions, setSessions] = useState<SessionData[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const canvasRef = useRef<ReactFlowCanvasHandle>(null);

  const [chatWidth, setChatWidth] = useState(40);
  const [canvasWidth, setCanvasWidth] = useState(35);
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [rightPanelWidth, setRightPanelWidth] = useState(300);
  const isDraggingCenterRef = useRef(false);
  const isDraggingCanvasMemRef = useRef(false);
  const isDraggingSidebarRef = useRef(false);
  const isDraggingRightPanelRef = useRef(false);
  const streamingMsgIdRef = useRef<string | null>(null);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentCompleted, setAgentCompleted] = useState(false);

  const messageHandlers = {
    onChatResponse: (msg: WSMessage) => {
      setIsProcessing(false);
      streamingMsgIdRef.current = null;
      setAgentRunning(false);
      setAgentCompleted(true);
      setTimeout(() => setAgentCompleted(false), 3000);
      setChatMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: 'assistant',
          content: msg.message || '',
          timestamp: Date.now(),
          subtype: 'response',
        },
      ]);
    },
    onThought: (msg: WSMessage) => {
      streamingMsgIdRef.current = null;
      setChatMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: 'assistant',
          content: msg.message || '',
          timestamp: Date.now(),
          subtype: 'thinking',
        },
      ]);
    },
    onThoughtChunk: (msg: WSMessage) => {
      const chunkContent = msg.message || '';
      setChatMessages((prev) => {
        if (streamingMsgIdRef.current) {
          return prev.map((m) =>
            m.id === streamingMsgIdRef.current
              ? { ...m, content: m.content + chunkContent }
              : m
          );
        }
        const newId = nextMsgId();
        streamingMsgIdRef.current = newId;
        return [
          ...prev,
          {
            id: newId,
            role: 'assistant',
            content: chunkContent,
            timestamp: Date.now(),
            subtype: 'thinking',
          },
        ];
      });
    },
    onPlan: (msg: WSMessage) => {
      streamingMsgIdRef.current = null;
      const plan = msg.plan;
      if (plan && plan.length > 0) {
        const planText = plan
          .map((step) => `${step.step_number}. ${step.action} - ${step.thought}`)
          .join('\n');
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: 'assistant',
            content: planText,
            timestamp: Date.now(),
            subtype: 'thinking',
          },
        ]);
      }
    },
    onToolCall: (msg: WSMessage) => {
      streamingMsgIdRef.current = null;
      setChatMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: 'assistant',
          content: `${msg.tool_name || ''}: ${msg.thought || ''}`,
          timestamp: Date.now(),
          subtype: 'thinking',
        },
      ]);
    },
    onToolResult: (msg: WSMessage) => {
      streamingMsgIdRef.current = null;
      const resultPreview = typeof msg.result === 'string'
        ? msg.result.substring(0, 200)
        : '';
      setChatMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: 'assistant',
          content: resultPreview,
          timestamp: Date.now(),
          subtype: 'thinking',
        },
      ]);
    },
    onReflection: (msg: WSMessage) => {
      streamingMsgIdRef.current = null;
      setChatMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: 'assistant',
          content: msg.message || '',
          timestamp: Date.now(),
          subtype: 'thinking',
        },
      ]);
    },
    onError: (msg: string | WSMessage) => {
      setIsProcessing(false);
      streamingMsgIdRef.current = null;
      const errorText = typeof msg === 'string' ? msg : msg.message || '';
      if (errorText) {
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: 'assistant',
            content: errorText,
            timestamp: Date.now(),
            subtype: 'error',
          },
        ]);
      }
    },
    onStopped: () => {
      setIsProcessing(false);
      streamingMsgIdRef.current = null;
      setAgentRunning(false);
      setAgentCompleted(true);
      setTimeout(() => setAgentCompleted(false), 3000);
    },
    onMemoryGraph: (msg: WSMessage) => {
      const newNodes: GraphNode[] = msg.nodes || [];
      setGraphNodes((prev) => {
        const existingIds = new Set(prev.map((n) => n.id));
        const merged = [...prev];
        for (const n of newNodes) {
          if (!existingIds.has(n.id)) {
            merged.push(n);
            existingIds.add(n.id);
          }
        }
        return merged;
      });
      setGraphEdges(msg.edges || []);
    },
    onMemoryPathUpdate: (msg: WSMessage) => {
      console.log('[App] onMemoryPathUpdate received:', msg.nodeIds);
      setRetrievalPath(msg.nodeIds || []);
    },
  };

  const { connected, sendMessage, backendPortRef } = useWebSocket(messageHandlers);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('visionwork2_config');
      if (saved) {
        const config = JSON.parse(saved);
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
      const savedSessions = loadSessions();
      setSessions(savedSessions);
      const savedId = loadCurrentSessionId();
      if (savedId && savedSessions.find((s) => s.id === savedId)) {
        setCurrentSessionId(savedId);
        const session = savedSessions.find((s) => s.id === savedId);
        if (session) {
          setChatMessages(session.messages || []);
        }
      } else {
        const newSession = ensureCurrentSession();
        setCurrentSessionId(newSession.id);
        setSessions(loadSessions());
      }
    } catch (e) {
      console.error('Failed to initialize sessions:', e);
      const newSession = createSession();
      setCurrentSessionId(newSession.id);
      setSessions(loadSessions());
    }
  }, []);

  useEffect(() => {
    if (connected && backendPortRef.current > 0) {
      fetch(`http://127.0.0.1:${backendPortRef.current}/get-memory-graph-nodes`)
        .then(r => r.json())
        .then(data => {
          if (data.success && data.nodes) {
            setGraphNodes(data.nodes);
          }
        })
        .catch(err => console.error('Failed to fetch memory graph nodes:', err));
    }
  }, [connected]);

  const saveCurrentSession = useCallback(() => {
    if (!currentSessionId) return;
    const canvasState = canvasRef.current?.getCanvasState();
    updateSession(currentSessionId, {
      messages: chatMessages,
      canvasNodes: canvasState?.nodes || [],
      canvasEdges: (canvasState?.edges || []) as unknown as StoredCanvasEdge[],
    });
    setSessions(loadSessions());
  }, [currentSessionId, chatMessages]);

  useEffect(() => {
    if (!currentSessionId) return;
    const timer = setInterval(() => {
      saveCurrentSession();
    }, 3000);
    return () => clearInterval(timer);
  }, [currentSessionId, saveCurrentSession]);

  useEffect(() => {
    if (!currentSessionId) return;
    const canvasState = canvasRef.current?.getCanvasState();
    updateSession(currentSessionId, {
      messages: chatMessages,
      canvasNodes: canvasState?.nodes || [],
      canvasEdges: (canvasState?.edges || []) as unknown as StoredCanvasEdge[],
    });
  }, [chatMessages, currentSessionId]);

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
      const configData = { apiUrl, apiKey, modelName };
      localStorage.setItem('visionwork2_config', JSON.stringify(configData));
      setConfigSaved(true);
      setTimeout(() => setConfigSaved(false), 2000);
    } catch (e) {
      console.error('Failed to save config:', e);
    }
  }, [apiUrl, apiKey, modelName]);

  useEffect(() => {
    if (connected && apiUrl && apiKey) {
      sendMessage({
        type: 'set_config',
        api_url: apiUrl,
        api_key: apiKey,
        model_name: modelName,
      });
    }
  }, [connected, apiUrl, apiKey, modelName, sendMessage]);

  const handleSendMessage = useCallback(
    (message: unknown) => {
      const msg = message as { type: string; content: string; path?: string; files?: string[] };
      if (msg.type === 'chat_message') {
        setIsProcessing(true);
        setAgentRunning(true);
        setAgentCompleted(false);
        streamingMsgIdRef.current = null;
        const projectPath = msg.path || scanTag;
        let displayContent = msg.content;
        if (projectPath) {
          displayContent = `📁 **${projectPath}**\n\n${msg.content}`;
        }
        if (msg.files && msg.files.length > 0) {
          const fileNames = msg.files.map((f: string) => {
            const parts = f.replace(/\\/g, '/').split('/');
            return parts[parts.length - 1];
          }).join(', ');
          displayContent = `📎 ${fileNames}\n\n${displayContent}`;
        }
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: 'user',
            content: displayContent,
            timestamp: Date.now(),
          },
        ]);
        const payload: Record<string, unknown> = {
          type: 'chat_message',
          content: msg.content,
          api_url: apiUrl,
          api_key: apiKey,
          model_name: modelName,
        };
        if (msg.path || scanTag) {
          payload.path = msg.path || scanTag;
        }

        const canvasState = canvasRef.current?.getCanvasState();
        if (canvasState && (canvasState.nodes.length > 0 || canvasState.edges.length > 0)) {
          const lines: string[] = [];
          lines.push('节点:');
          for (const node of canvasState.nodes) {
            const label = node.data?.label || node.id;
            const nodeType = node.data?.nodeType || '';
            const typeStr = nodeType ? ` [${nodeType}]` : '';
            lines.push(`  - ${node.id}: ${label}${typeStr}`);
          }
          lines.push('边:');
          for (const edge of canvasState.edges) {
            const label = edge.label ? ` (${edge.label})` : '';
            lines.push(`  - ${edge.source} -> ${edge.target}${label}`);
          }
          payload.canvas_context = lines.join('\n');
          payload.canvas_nodes = canvasState.nodes.map((n) => ({
            id: n.id,
            data: n.data,
          }));
          payload.canvas_edges = canvasState.edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label || '',
          }));
        }

        sendMessage(payload);
      } else {
        sendMessage(message);
      }
    },
    [sendMessage, apiUrl, apiKey, modelName, scanTag]
  );

  const handleStop = useCallback(() => {
    sendMessage({ type: 'stop_agent' });
    setIsProcessing(false);
  }, [sendMessage]);

  const handleNewSession = useCallback(() => {
    saveCurrentSession();
    const newSession = createSession();
    setCurrentSessionId(newSession.id);
    setChatMessages([]);
    setScanTag(null);
    setSessions(loadSessions());
    setSessionSidebarOpen(false);
  }, [saveCurrentSession]);

  const handleSelectSession = useCallback((id: string) => {
    if (id === currentSessionId) {
      setSessionSidebarOpen(false);
      return;
    }
    saveCurrentSession();
    const session = switchToSession(id);
    if (session) {
      setCurrentSessionId(session.id);
      setChatMessages(session.messages);
      setScanTag(session.projectPath || null);
      setTimeout(() => {
        canvasRef.current?.setCanvasState({
          nodes: session.canvasNodes || [],
          edges: session.canvasEdges || [],
        });
      }, 100);
    }
    setSessions(loadSessions());
    setSessionSidebarOpen(false);
  }, [currentSessionId, saveCurrentSession]);

  const handleDeleteSession = useCallback((id: string) => {
    deleteSession(id);
    const remaining = loadSessions();
    setSessions(remaining);
    if (id === currentSessionId) {
      if (remaining.length > 0) {
        const first = remaining[0];
        switchToSession(first.id);
        setCurrentSessionId(first.id);
        setChatMessages(first.messages);
        setScanTag(first.projectPath || null);
        setTimeout(() => {
          canvasRef.current?.setCanvasState({
            nodes: first.canvasNodes || [],
            edges: first.canvasEdges || [],
          });
        }, 100);
      } else {
        const newSession = createSession();
        setCurrentSessionId(newSession.id);
        setChatMessages([]);
        setScanTag(null);
        setSessions(loadSessions());
      }
    }
  }, [currentSessionId]);

  const handleSelectFolder = useCallback(async () => {
    try {
      let folderPath: string | null = null;

      if (window.electronAPI) {
        folderPath = await window.electronAPI.selectFolder();
      } else if (window.showDirectoryPicker) {
        const handle = await window.showDirectoryPicker();
        folderPath = handle.name;
      } else {
        const input = document.createElement('input');
        input.type = 'file';
        input.webkitdirectory = true;
        folderPath = await new Promise<string | null>((resolve) => {
          input.onchange = () => {
            const files = input.files;
            if (files && files.length > 0) {
              const firstFile = files[0];
              const relativePath = firstFile.webkitRelativePath || firstFile.name;
              resolve(relativePath.split('/')[0] || relativePath);
            } else {
              resolve(null);
            }
          };
          input.click();
        });
      }

      if (folderPath) {
        setScanTag(folderPath);
      }
    } catch (err) {
      console.error('Failed to select folder:', err);
    }
  }, []);

  const handleClearScanTag = useCallback(() => {
    setScanTag(null);
  }, []);

  const handleViewFileTree = useCallback(() => {
    setRightPanelInitialTab('files');
    setRightPanelOpen(true);
  }, []);

  const handleOpenConfig = useCallback(() => {
    setShowConfig(true);
    setSessionSidebarOpen(false);
  }, []);

  const handleOpenSkillManager = useCallback(() => {
    setShowSkillManager(true);
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const handleCenterMouseDown = useCallback(() => {
    isDraggingCenterRef.current = true;
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingCenterRef.current) return;
      const container = document.querySelector('.main-center');
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      const maxChat = 100 - canvasWidth - 10;
      setChatWidth(Math.max(15, Math.min(maxChat, pct)));
    };
    const handleMouseUp = () => {
      isDraggingCenterRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [canvasWidth]);

  const handleCanvasMemMouseDown = useCallback(() => {
    isDraggingCanvasMemRef.current = true;
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingCanvasMemRef.current) return;
      const container = document.querySelector('.main-center');
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      const minCanvas = 15;
      const maxCanvas = 100 - chatWidth - 10;
      setCanvasWidth(Math.max(minCanvas, Math.min(maxCanvas, pct - chatWidth)));
    };
    const handleMouseUp = () => {
      isDraggingCanvasMemRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [chatWidth]);

  const handleSidebarResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingSidebarRef.current = true;
    const startX = e.clientX;
    const startWidth = sidebarWidth;
    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDraggingSidebarRef.current) return;
      const delta = ev.clientX - startX;
      setSidebarWidth(Math.max(200, Math.min(500, startWidth + delta)));
    };
    const handleMouseUp = () => {
      isDraggingSidebarRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [sidebarWidth]);

  const handleRightPanelResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRightPanelRef.current = true;
    const startX = e.clientX;
    const startWidth = rightPanelWidth;
    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDraggingRightPanelRef.current) return;
      const delta = startX - ev.clientX;
      setRightPanelWidth(Math.max(200, Math.min(800, startWidth + delta)));
    };
    const handleMouseUp = () => {
      isDraggingRightPanelRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [rightPanelWidth]);

  const handleMemoryGraphNodeClick = useCallback((node: GraphNode) => {
    if (node.path && node.path.endsWith('.md')) {
      const parts = node.path.replace(/\\/g, '/').split('/');
      const filename = parts[parts.length - 1];
      setMemoryFileModalPath(node.path);
      setMemoryFileModalName(filename);
      setMemoryFileModalOpen(true);
    }
  }, []);

  return (
    <div className="app-container">
      <div className="top-bar">
        <div className="top-bar-left">
          <button
            className="btn-icon"
            onClick={() => setSessionSidebarOpen(!sessionSidebarOpen)}
            title="会话"
          >
            <Menu size={20} />
          </button>
          <span className="top-bar-title">VisionWork2</span>
        </div>
        <div className="top-bar-right">
          <div className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <button className="btn-icon" onClick={toggleTheme} title="切换主题">
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button
            className="btn-icon"
            onClick={() => setRightPanelOpen(!rightPanelOpen)}
            title="面板"
          >
            <Sidebar size={20} />
          </button>
        </div>
      </div>

      <SessionSidebar
        isOpen={sessionSidebarOpen}
        onClose={() => setSessionSidebarOpen(false)}
        onNewSession={handleNewSession}
        onOpenConfig={handleOpenConfig}
        width={sidebarWidth}
        onResizeStart={handleSidebarResizeStart}
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />

      <RightPanel
        isOpen={rightPanelOpen}
        onClose={() => setRightPanelOpen(false)}
        scanTag={scanTag}
        backendPort={backendPortRef.current}
        initialTab={rightPanelInitialTab}
        width={rightPanelWidth}
        onResizeStart={handleRightPanelResizeStart}
      />

      {showConfig && (
        <div className="config-modal-overlay" onClick={() => setShowConfig(false)}>
          <div className="config-modal" onClick={(e) => e.stopPropagation()}>
            <div className="config-modal-header">
              <h2>模型配置</h2>
              <button className="btn-icon" onClick={() => setShowConfig(false)}>✕</button>
            </div>
            <ConfigPanel
              apiUrl={apiUrl}
              setApiUrl={setApiUrl}
              apiKey={apiKey}
              setApiKey={setApiKey}
              modelName={modelName}
              setModelName={setModelName}
              isAnalyzing={false}
              configSaved={configSaved}
            />
          </div>
        </div>
      )}

      <SkillManager
        isOpen={showSkillManager}
        onClose={() => setShowSkillManager(false)}
        backendPort={backendPortRef.current}
      />

      <div className="main-center">
        <div className="chat-panel" style={{ width: `${chatWidth}%` }}>
          <ChatView
            connected={connected}
            sendMessage={handleSendMessage}
            messages={chatMessages}
            onSelectFolder={handleSelectFolder}
            scanTag={scanTag}
            onClearScanTag={handleClearScanTag}
            onViewFileTree={handleViewFileTree}
            onOpenSkillManager={handleOpenSkillManager}
            isProcessing={isProcessing}
            onStop={handleStop}
            agentRunning={agentRunning}
            agentCompleted={agentCompleted}
          />
        </div>
        <div className="center-resize-handle" onMouseDown={handleCenterMouseDown} />
        <div className="canvas-panel" style={{ width: `${canvasWidth}%` }}>
          <ReactFlowCanvas ref={canvasRef} theme={theme} sessionKey={currentSessionId || undefined} />
        </div>
        <div className="canvas-memory-resize-handle" onMouseDown={handleCanvasMemMouseDown} />
        <div className="memory-graph-panel" style={{ width: `${100 - chatWidth - canvasWidth}%` }}>
          <MemoryGraph
            key={`mg-${graphNodes.map(n => n.id).sort().join(',')}`}
            nodes={graphNodes}
            edges={graphEdges}
            retrievalPath={retrievalPath}
            theme={theme}
            onNodeClick={handleMemoryGraphNodeClick}
          />
        </div>
      </div>

      <MemoryFileModal
        isOpen={memoryFileModalOpen}
        filepath={memoryFileModalPath}
        filename={memoryFileModalName}
        backendPort={backendPortRef.current}
        onClose={() => setMemoryFileModalOpen(false)}
      />
    </div>
  );
}