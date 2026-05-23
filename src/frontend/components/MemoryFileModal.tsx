import React, { useState, useEffect, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { X, Save, FileText, Code, Eye } from 'react-feather';

interface MemoryFileModalProps {
  isOpen: boolean;
  filepath: string;
  filename: string;
  backendPort: number;
  onClose: () => void;
  onSaved?: () => void;
}

export default function MemoryFileModal({
  isOpen,
  filepath,
  filename,
  backendPort,
  onClose,
  onSaved,
}: MemoryFileModalProps) {
  const [content, setContent] = useState('');
  const [originalContent, setOriginalContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useState<'source' | 'preview'>('source');

  useEffect(() => {
    if (!isOpen || !filepath) return;

    setLoading(true);
    setError('');
    setSavedSuccess(false);

    const url = `http://127.0.0.1:${backendPort}/read-memory-file?filepath=${encodeURIComponent(filepath)}`;

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (data.success) {
          setContent(data.content || '');
          setOriginalContent(data.content || '');
        } else {
          setError(data.error || 'Failed to read file');
          setContent('');
          setOriginalContent('');
        }
      })
      .catch((err) => {
        setError(`Failed to load file: ${err.message}`);
        setContent('');
        setOriginalContent('');
      })
      .finally(() => setLoading(false));
  }, [isOpen, filepath, backendPort]);

  const handleSave = useCallback(() => {
    if (!filepath) return;

    setSaving(true);
    setSavedSuccess(false);
    setError('');

    fetch(`http://127.0.0.1:${backendPort}/save-memory-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filepath, content }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.success) {
          setOriginalContent(content);
          setSavedSuccess(true);
          setTimeout(() => setSavedSuccess(false), 2000);
          if (onSaved) onSaved();
        } else {
          setError(data.error || 'Failed to save file');
        }
      })
      .catch((err) => {
        setError(`Failed to save: ${err.message}`);
      })
      .finally(() => setSaving(false));
  }, [content, filepath, backendPort, onSaved]);

  const hasChanges = content !== originalContent;
  const isMarkdown = filename.endsWith('.md');

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (hasChanges) {
          handleSave();
        }
      }
    },
    [onClose, hasChanges, handleSave]
  );

  if (!isOpen) return null;

  return (
    <div className="memory-file-modal-overlay" onClick={onClose}>
      <div
        className="memory-file-modal"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="memory-file-modal-header">
          <div className="memory-file-modal-title">
            <FileText size={16} />
            <span>{filename}</span>
          </div>
          <div className="memory-file-modal-actions">
            {savedSuccess && <span className="memory-file-saved-hint">Saved</span>}
            {error && <span className="memory-file-error-hint">{error}</span>}
            {isMarkdown && (
              <button
                className="btn-icon memory-file-toggle-btn"
                onClick={() => setViewMode(viewMode === 'source' ? 'preview' : 'source')}
                title={viewMode === 'source' ? 'Preview Markdown' : 'Edit Source'}
              >
                {viewMode === 'source' ? <Eye size={16} /> : <Code size={16} />}
              </button>
            )}
            <button
              className="btn-icon memory-file-save-btn"
              onClick={handleSave}
              disabled={!hasChanges || saving}
              title="Save (Ctrl+S)"
            >
              <Save size={16} />
            </button>
            <button className="btn-icon" onClick={onClose} title="Close (Esc)">
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="memory-file-modal-body">
          {loading ? (
            <div className="memory-file-loading">Loading...</div>
          ) : viewMode === 'preview' && isMarkdown ? (
            <div className="memory-file-preview">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
          ) : (
            <Editor
              height="100%"
              language={isMarkdown ? 'markdown' : 'plaintext'}
              value={content}
              onChange={(value) => setContent(value || '')}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                lineNumbers: 'on',
                wordWrap: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 2,
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}