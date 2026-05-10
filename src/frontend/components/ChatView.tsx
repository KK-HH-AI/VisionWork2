import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send } from 'react-feather';

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
}

export default function ChatView({ connected, sendMessage, messages }: ChatViewProps) {
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
      <div className="chat-input-area">
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