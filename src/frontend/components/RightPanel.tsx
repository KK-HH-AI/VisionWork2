import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Folder, X, Save, Edit3 } from 'react-feather';
import DirectoryTree from './DirectoryTree';
import WorkspaceTree from './WorkspaceTree';
import type { DirectoryNode, WorkspaceItem } from '../types';

interface RightPanelProps {
  isOpen: boolean;
  onClose: () => void;
  scanTag: string | null;
  backendPort: number;
  initialTab?: 'notes' | 'files';
  width: number;
  onResizeStart: (e: React.MouseEvent) => void;
}

type TabType = 'notes' | 'files';

export default function RightPanel({ isOpen, onClose, scanTag, backendPort, initialTab, width, onResizeStart }: RightPanelProps) {
  const [activeTab, setActiveTab] = useState<TabType>(initialTab || 'notes');
  const [directoryTree, setDirectoryTree] = useState<DirectoryNode | null>(null);
  const [dirTreeLoading, setDirTreeLoading] = useState(false);
  const [workspaceTree, setWorkspaceTree] = useState<WorkspaceItem[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  const [selectedNote, setSelectedNote] = useState<WorkspaceItem | null>(null);
  const [noteContent, setNoteContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  useEffect(() => {
    if (isOpen && scanTag) {
      fetchDirectoryTree(scanTag);
    }
  }, [isOpen, scanTag]);

  useEffect(() => {
    if (isOpen) {
      fetchWorkspaceTree();
    }
  }, [isOpen]);

  const fetchDirectoryTree = useCallback(async (folderPath: string) => {
    setDirTreeLoading(true);
    try {
      const url = `http://127.0.0.1:${backendPort}/scan-directory?path=${encodeURIComponent(folderPath)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.success && data.tree) {
        setDirectoryTree(data.tree);
      }
    } catch (err) {
      console.error('Failed to fetch directory tree:', err);
    } finally {
      setDirTreeLoading(false);
    }
  }, [backendPort]);

  const fetchWorkspaceTree = useCallback(async () => {
    try {
      const url = `http://127.0.0.1:${backendPort}/get-workspace-tree`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.success && data.tree) {
        setWorkspaceTree(data.tree);
      }
    } catch (err) {
      console.error('Failed to fetch workspace tree:', err);
    }
  }, [backendPort]);

  const handleToggleDir = useCallback((path: string) => {
    setExpandedDirs((prev) => ({ ...prev, [path]: !prev[path] }));
  }, []);

  const handleNoteClick = useCallback(async (item: WorkspaceItem) => {
    setSelectedNote(item);
    setIsEditing(false);
    setNoteLoading(true);
    try {
      const url = `http://127.0.0.1:${backendPort}/read-file?path=${encodeURIComponent(item.path)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.success) {
        setNoteContent(data.content || '');
      }
    } catch (err) {
      console.error('Failed to read note:', err);
    } finally {
      setNoteLoading(false);
    }
  }, [backendPort]);

  const handleStartEdit = useCallback(() => {
    setEditContent(noteContent);
    setIsEditing(true);
  }, [noteContent]);

  const handleSaveNote = useCallback(async () => {
    if (!selectedNote) return;
    try {
      const url = `http://127.0.0.1:${backendPort}/save-file`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedNote.path, content: editContent }),
      });
      const data = await res.json();
      if (data.success) {
        setNoteContent(editContent);
        setIsEditing(false);
      }
    } catch (err) {
      console.error('Failed to save note:', err);
    }
  }, [backendPort, selectedNote, editContent]);

  const handleCancelEdit = useCallback(() => {
    setIsEditing(false);
    setEditContent('');
  }, []);

  const handleBackToTree = useCallback(() => {
    setSelectedNote(null);
    setIsEditing(false);
    setNoteContent('');
  }, []);

  return (
    <>
      {isOpen && (
        <div className="right-panel-overlay" onClick={onClose} />
      )}
      <div className={`right-panel ${isOpen ? 'open' : ''}`} style={{ width: `${width}px` }}>
        <div
          className="panel-resize-handle"
          onMouseDown={onResizeStart}
        />
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
            <div className="right-panel-notes">
              {selectedNote ? (
                <div className="note-viewer">
                  <div className="note-viewer-header">
                    <button className="btn-icon" onClick={handleBackToTree} title="返回">
                      <X size={16} />
                    </button>
                    <span className="note-viewer-title" title={selectedNote.name}>{selectedNote.name}</span>
                    {!isEditing ? (
                      <button className="btn-icon" onClick={handleStartEdit} title="编辑">
                        <Edit3 size={14} />
                      </button>
                    ) : (
                      <>
                        <button className="btn-icon" onClick={handleSaveNote} title="保存">
                          <Save size={14} />
                        </button>
                        <button className="btn-icon" onClick={handleCancelEdit} title="取消">
                          <X size={14} />
                        </button>
                      </>
                    )}
                  </div>
                  <div className="note-viewer-body">
                    {noteLoading ? (
                      <div className="right-panel-empty">
                        <p>加载中...</p>
                      </div>
                    ) : isEditing ? (
                      <textarea
                        className="note-editor"
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                      />
                    ) : (
                      <pre className="note-content">{noteContent}</pre>
                    )}
                  </div>
                </div>
              ) : workspaceTree.length > 0 ? (
                <WorkspaceTree
                  workspaceTree={workspaceTree}
                  expandedDirs={expandedDirs}
                  onToggleDir={handleToggleDir}
                  onNoteClick={handleNoteClick}
                />
              ) : (
                <div className="right-panel-empty">
                  <FileText size={32} />
                  <p>暂无记忆笔记</p>
                </div>
              )}
            </div>
          )}
          {activeTab === 'files' && (
            <div className="right-panel-files">
              {dirTreeLoading ? (
                <div className="right-panel-empty">
                  <p>加载中...</p>
                </div>
              ) : directoryTree ? (
                <DirectoryTree node={directoryTree} />
              ) : scanTag ? (
                <div className="right-panel-empty">
                  <Folder size={32} />
                  <p>无法加载文件树</p>
                </div>
              ) : (
                <div className="right-panel-empty">
                  <Folder size={32} />
                  <p>请先选择要分析的文件夹</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}