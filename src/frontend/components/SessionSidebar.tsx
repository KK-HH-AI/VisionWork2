import React from 'react';
import { Plus, Settings, MessageSquare, Trash2 } from 'react-feather';
import type { SessionData } from '../types';

interface SessionSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewSession: () => void;
  onOpenConfig: () => void;
  width: number;
  onResizeStart: (e: React.MouseEvent) => void;
  sessions: SessionData[];
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return '刚刚';
  if (diffMins < 60) return `${diffMins}分钟前`;
  if (diffHours < 24) return `${diffHours}小时前`;
  if (diffDays < 7) return `${diffDays}天前`;

  const month = date.getMonth() + 1;
  const day = date.getDate();
  return `${month}/${day}`;
}

export default function SessionSidebar({
  isOpen,
  onClose,
  onNewSession,
  onOpenConfig,
  width,
  onResizeStart,
  sessions,
  currentSessionId,
  onSelectSession,
  onDeleteSession,
}: SessionSidebarProps) {
  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    onDeleteSession(id);
  };

  return (
    <>
      {isOpen && (
        <div className="session-sidebar-overlay" onClick={onClose} />
      )}
      <div
        className={`session-sidebar ${isOpen ? 'open' : ''}`}
        style={{ width: `${width}px` }}
      >
        <div className="session-sidebar-header">
          <h2>会话</h2>
          <button className="btn-new-session" onClick={onNewSession} title="新建会话">
            <Plus size={18} />
          </button>
        </div>
        <div className="session-list">
          {sessions.length === 0 ? (
            <div className="session-list-empty">暂无会话</div>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
                onClick={() => onSelectSession(session.id)}
              >
                <div className="session-item-icon">
                  <MessageSquare size={16} />
                </div>
                <div className="session-item-content">
                  <div className="session-item-title">{session.title}</div>
                  <div className="session-item-meta">
                    <span className="session-item-time">{formatTime(session.updatedAt)}</span>
                    <span className="session-item-count">{session.messages.length} 条消息</span>
                  </div>
                </div>
                <button
                  className="session-item-delete"
                  onClick={(e) => handleDelete(e, session.id)}
                  title="删除会话"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
        <div className="session-sidebar-footer">
          <button className="btn-config" onClick={onOpenConfig} title="配置">
            <Settings size={16} />
            <span>配置</span>
          </button>
        </div>
        <div
          className="sidebar-resize-handle"
          onMouseDown={onResizeStart}
        />
      </div>
    </>
  );
}