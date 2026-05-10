import React from 'react';
import { Plus, Settings } from 'react-feather';

interface SessionSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewSession: () => void;
  onOpenConfig: () => void;
}

export default function SessionSidebar({
  isOpen,
  onClose,
  onNewSession,
  onOpenConfig,
}: SessionSidebarProps) {
  return (
    <>
      {isOpen && (
        <div className="session-sidebar-overlay" onClick={onClose} />
      )}
      <div className={`session-sidebar ${isOpen ? 'open' : ''}`}>
        <div className="session-sidebar-header">
          <h2>会话</h2>
          <button className="btn-new-session" onClick={onNewSession} title="新建会话">
            <Plus size={18} />
          </button>
        </div>
        <div className="session-list">
          <div className="session-list-empty">暂无会话</div>
        </div>
        <div className="session-sidebar-footer">
          <button className="btn-config" onClick={onOpenConfig} title="配置">
            <Settings size={16} />
            <span>配置</span>
          </button>
        </div>
      </div>
    </>
  );
}