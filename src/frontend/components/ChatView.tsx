import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, FolderPlus, X, Folder, Settings, Square, ChevronDown, ChevronRight } from 'react-feather';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  subtype?: 'thinking' | 'response' | 'error';
}

interface ThinkingBlock {
  messages: ChatMessage[];
  startIndex: number;
}

interface ChatViewProps {
  connected: boolean;
  sendMessage: (message: unknown) => void;
  messages: ChatMessage[];
  onSelectFolder?: () => void;
  scanTag?: string | null;
  onClearScanTag?: () => void;
  onViewFileTree?: () => void;
  onOpenSkillManager?: () => void;
  isProcessing?: boolean;
  onStop?: () => void;
}

function buildThinkingBlocks(messages: ChatMessage[]): (ChatMessage | ThinkingBlock)[] {
  const result: (ChatMessage | ThinkingBlock)[] = [];
  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];
    if (msg.subtype === 'thinking') {
      const block: ThinkingBlock = { messages: [], startIndex: i };
      while (i < messages.length && messages[i].subtype === 'thinking') {
        block.messages.push(messages[i]);
        i++;
      }
      result.push(block);
    } else {
      result.push(msg);
      i++;
    }
  }
  return result;
}

export default function ChatView({
  connected,
  sendMessage,
  messages,
  onSelectFolder,
  scanTag,
  onClearScanTag,
  onViewFileTree,
  onOpenSkillManager,
  isProcessing,
  onStop,
}: ChatViewProps) {
  const [input, setInput] = useState('');
  const [expandedBlocks, setExpandedBlocks] = useState<Set<number>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || !connected || isProcessing) return;

    const msg: Record<string, unknown> = {
      type: 'chat_message',
      content: trimmed,
    };

    if (scanTag) {
      msg.path = scanTag;
    }

    sendMessage(msg);

    setInput('');
    inputRef.current?.focus();
  }, [input, connected, isProcessing, sendMessage, scanTag]);

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

  const toggleBlock = useCallback((blockIndex: number) => {
    setExpandedBlocks((prev) => {
      const next = new Set(prev);
      if (next.has(blockIndex)) {
        next.delete(blockIndex);
      } else {
        next.add(blockIndex);
      }
      return next;
    });
  }, []);

  const displayItems = buildThinkingBlocks(messages);

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <p>开始对话，探索你的代码库</p>
          </div>
        ) : (
          displayItems.map((item, idx) => {
            if ('messages' in item) {
              const block = item as ThinkingBlock;
              const isExpanded = expandedBlocks.has(idx);
              const lastMsg = block.messages[block.messages.length - 1];
              const preview = lastMsg ? lastMsg.content.substring(0, 80) : 'Thinking...';

              return (
                <div key={`block-${idx}`} className="thinking-block">
                  <div
                    className="thinking-block-header"
                    onClick={() => toggleBlock(idx)}
                  >
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span className="thinking-block-label">Thought</span>
                    <span className="thinking-block-preview">
                      {preview}{preview.length >= 80 ? '...' : ''}
                    </span>
                    <span className="thinking-block-count">{block.messages.length} steps</span>
                  </div>
                  {isExpanded && (
                    <div className="thinking-block-body">
                      {block.messages.map((msg) => (
                        <div key={msg.id} className="thinking-step">
                          <div className="thinking-step-content">{msg.content}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            }

            const msg = item as ChatMessage;
            return (
              <div key={msg.id} className={`chat-message ${msg.role}${msg.subtype === 'error' ? ' error' : ''}`}>
                <div className="chat-message-bubble">{msg.content}</div>
              </div>
            );
          })
        )}
        {isProcessing && (
          <div className="typing-indicator">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
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
          disabled={!connected || isProcessing}
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
        {isProcessing ? (
          <button
            className="btn-stop"
            onClick={onStop}
            title="停止"
          >
            <Square size={14} />
          </button>
        ) : (
          <button
            className="btn-send"
            onClick={handleSend}
            disabled={!connected || !input.trim()}
            title="发送"
          >
            <Send size={16} />
          </button>
        )}
        {onOpenSkillManager && (
          <button
            className="btn-settings"
            onClick={onOpenSkillManager}
            title="Skill 管理"
          >
            <Settings size={16} />
          </button>
        )}
      </div>
    </div>
  );
}