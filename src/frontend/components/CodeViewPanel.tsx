import React, { useEffect } from 'react';
import { MapPin } from 'react-feather';
import Editor from '@monaco-editor/react';
import { getFileIcon } from '../utils/fileIcons';
import { getMonacoLanguage } from '../utils/monacoLanguages';
import type { CodeFileRef } from '../types';

interface CodeViewPanelProps {
  codeViewNode: { data?: { label?: string } } | null;
  codeFileList: CodeFileRef[];
  selectedCodeFile: CodeFileRef | null;
  fileContent: string;
  fileContentLoading: boolean;
  fileContentError: string;
  highlightLines: [number, number] | null;
  theme: string;
  onBackToTree: () => void;
  onFileClick: (fileRef: CodeFileRef) => void;
  loadFileContent: (fileRef: CodeFileRef) => void;
}

export default function CodeViewPanel({
  codeViewNode,
  codeFileList,
  selectedCodeFile,
  fileContent,
  fileContentLoading,
  fileContentError,
  highlightLines,
  theme,
  onBackToTree,
  onFileClick,
  loadFileContent,
}: CodeViewPanelProps) {
  useEffect(() => {
    if (codeViewNode && codeFileList.length > 0 && !selectedCodeFile) {
      loadFileContent(codeFileList[0]);
    }
  }, [codeViewNode, codeFileList]);

  return (
    <div className="code-view-panel">
      <div className="code-view-header">
        <button className="btn-back-tree" onClick={onBackToTree}>
          <span>← 返回目录树</span>
        </button>
        <span className="code-view-title" title={codeViewNode?.data?.label}>
          <MapPin size={14} /> {codeViewNode?.data?.label}
        </span>
      </div>
      <div className="code-file-list">
        <div className="code-file-list-title">
          相关文件 ({codeFileList.length})
        </div>
        {codeFileList.map((fileRef, idx) => (
          <div
            key={idx}
            className={`code-file-item ${selectedCodeFile === fileRef ? 'active' : ''}`}
            onClick={() => onFileClick(fileRef)}
          >
            <span className="code-file-icon">{getFileIcon(fileRef.file.split(/[/\\]/).pop() || '')}</span>
            <span className="code-file-name" title={fileRef.file}>
              {fileRef.file.split(/[/\\]/).pop()}
            </span>
            {fileRef.lines && (
              <span className="code-file-lines">L{fileRef.lines[0]}-L{fileRef.lines[1]}</span>
            )}
          </div>
        ))}
      </div>
      <div className="code-editor-container">
        {fileContentLoading ? (
          <div className="code-editor-loading">加载中...</div>
        ) : fileContentError ? (
          <div className="code-editor-error">{fileContentError}</div>
        ) : fileContent ? (
          <Editor
            key={selectedCodeFile ? selectedCodeFile.file : 'empty'}
            height="100%"
            language={selectedCodeFile ? getMonacoLanguage(selectedCodeFile.file) : 'plaintext'}
            value={fileContent}
            theme={theme === 'dark' ? 'vs-dark' : 'vs'}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              automaticLayout: true,
            }}
            onMount={(editor, monaco) => {
              if (highlightLines && highlightLines.length === 2) {
                const [startLine, endLine] = highlightLines;
                editor.revealLineInCenter(startLine);
                editor.setSelection(
                  new monaco.Selection(startLine, 1, endLine, 1)
                );
                const range = new monaco.Range(startLine, 1, endLine, Number.MAX_SAFE_INTEGER);
                const decoration = {
                  range,
                  options: {
                    isWholeLine: true,
                    className: 'highlighted-line',
                    glyphMarginClassName: 'highlighted-line-glyph',
                  },
                };
                editor.deltaDecorations([], [decoration]);
              }
            }}
          />
        ) : (
          <div className="code-editor-placeholder">
            选择一个文件以查看代码
          </div>
        )}
      </div>
    </div>
  );
}
