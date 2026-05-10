import React, { useState } from 'react';
import { FileText, Folder } from 'react-feather';

interface RightPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabType = 'notes' | 'files';

export default function RightPanel({ isOpen, onClose }: RightPanelProps) {
  const [activeTab, setActiveTab] = useState<TabType>('notes');

  return (
    <>
      {isOpen && (
        <div className="right-panel-overlay" onClick={onClose} />
      )}
      <div className={`right-panel ${isOpen ? 'open' : ''}`}>
        <div className="right-panel-tabs">
          <button
            className={`right-panel-tab ${activeTab === 'notes' ? 'active' : ''}`}
            onClick={() => setActiveTab('notes')}
          >
            <FileText size={14} />
            <span>记忆笔记</span>
          </button>
          <button
            className={`right-panel-tab ${activeTab === 'files' ? 'active' : ''}`}
            onClick={() => setActiveTab('files')}
          >
            <Folder size={14} />
            <span>文件树</span>
          </button>
        </div>
        <div className="right-panel-content">
          {activeTab === 'notes' && (
            <div className="right-panel-empty">
              <FileText size={32} />
              <p>暂无记忆笔记</p>
            </div>
          )}
          {activeTab === 'files' && (
            <div className="right-panel-empty">
              <Folder size={32} />
              <p>暂无文件树</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}