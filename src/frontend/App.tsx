import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Menu, Sidebar, Sun, Moon } from 'react-feather';
import useWebSocket from './hooks/useWebSocket';
import SessionSidebar from './components/SessionSidebar';
import RightPanel from './components/RightPanel';
import ChatView from './components/ChatView';
import ConfigPanel from './components/ConfigPanel';
import type { ChatMessage, WSMessage } from './types';

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
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const [profession, setProfession] = useState('软件工程师');
  const [apiUrl, setApiUrl] = useState('https://api.openai.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('gpt-3.5-turbo');
  const [configSaved, setConfigSaved] = useState(false);

  const [chatWidth, setChatWidth] = useState(45);
  const isDraggingCenterRef = useRef(false);

  const messageHandlers = {
    onChatResponse: (msg: WSMessage) => {
      setChatMessages((prev) => [
        ...prev,
        {
          id: nextMsgId(),
          role: 'assistant',
          content: msg.message || '',
          timestamp: Date.now(),
        },
      ]);
    },
    onError: (msg: string | WSMessage) => {
      const errorText = typeof msg === 'string' ? msg : msg.message || '';
      if (errorText) {
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: 'assistant',
            content: `错误: ${errorText}`,
            timestamp: Date.now(),
          },
        ]);
      }
    },
  };

  const { connected, sendMessage } = useWebSocket(messageHandlers);

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

  const handleSendMessage = useCallback(
    (message: unknown) => {
      const msg = message as { type: string; content: string };
      if (msg.type === 'chat_message') {
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: 'user',
            content: msg.content,
            timestamp: Date.now(),
          },
        ]);
      }
      sendMessage(message);
    },
    [sendMessage]
  );

  const handleNewSession = useCallback(() => {
    setChatMessages([]);
    setSessionSidebarOpen(false);
  }, []);

  const handleOpenConfig = useCallback(() => {
    setShowConfig(true);
    setSessionSidebarOpen(false);
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
      setChatWidth(Math.max(20, Math.min(80, pct)));
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
      />

      <RightPanel
        isOpen={rightPanelOpen}
        onClose={() => setRightPanelOpen(false)}
      />

      {showConfig && (
        <div className="config-modal-overlay" onClick={() => setShowConfig(false)}>
          <div className="config-modal" onClick={(e) => e.stopPropagation()}>
            <div className="config-modal-header">
              <h2>模型配置</h2>
              <button className="btn-icon" onClick={() => setShowConfig(false)}>✕</button>
            </div>
            <ConfigPanel
              profession={profession}
              setProfession={setProfession}
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

      <div className="main-center">
        <div className="chat-panel" style={{ width: `${chatWidth}%` }}>
          <ChatView
            connected={connected}
            sendMessage={handleSendMessage}
            messages={chatMessages}
          />
        </div>
        <div className="center-resize-handle" onMouseDown={handleCenterMouseDown} />
        <div className="canvas-panel" style={{ width: `${100 - chatWidth}%` }}>
          <div className="canvas-placeholder">
            <span>画布区域</span>
          </div>
        </div>
      </div>
    </div>
  );
}