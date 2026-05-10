import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, FolderPlus, X, Folder } from 'react-feather';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

interface ChatViewProps {
  connected: boolean;
  sendMessage: (message: unknown) => void;
  messages: ChatMessage[];
  onSelectFolder?: () => void;
  scanTag?: string | null;
  onClearScanTag?: () => void;
  onViewFileTree?: () => void;
}

export default function ChatView({
  connected,
  sendMessage,
  messages,
  onSelectFolder,
  scanTag,
  onClearScanTag,
  onViewFileTree,
}: ChatViewProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || !connected) return;

    sendMessage({
      type: 'chat_message',
      content: trimmed,
    });

    setInput('');
    inputRef.current?.focus();
  }, [input, connected, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleSelectFolder = useCallback(() => {
    if (onSelectFolder) {
      onSelectFolder();
    }
  }, [onSelectFolder]);

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <p>开始对话，探索你的代码库</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`chat-message ${msg.role}`}>
              <div className="chat-message-bubble">{msg.content}</div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      {scanTag && (
        <div className="scan-tag-bar">
          <div className="scan-tag">
            <Folder size={14} />
            <span className="scan-tag-path" title={scanTag}>{scanTag}</span>
            {onViewFileTree && (
              <button className="btn-scan-action" onClick={onViewFileTree} title="查看文件树">
                查看文件树
              </button>
            )}
            {onClearScanTag && (
              <button className="btn-scan-close" onClick={onClearScanTag} title="清除">
                <X size={14} />
              </button>
            )}
          </div>
        </div>
      )}
      <div className="chat-input-area">
        <button
          className="btn-folder-select"
          onClick={handleSelectFolder}
          disabled={!connected}
          title="选择文件夹"
        >
          <FolderPlus size={18} />
        </button>
        <textarea
          ref={inputRef}
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息..."
          rows={1}
          disabled={!connected}
        />
        <button
          className="btn-send"
          onClick={handleSend}
          disabled={!connected || !input.trim()}
          title="发送"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}