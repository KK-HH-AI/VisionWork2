import React from 'react';

export default function WorkspaceTree({
  workspaceTree,
  expandedDirs,
  onToggleDir,
  onNoteClick,
}) {
  const countFiles = (items) => {
    let count = 0;
    for (const item of items) {
      if (item.type === 'file') {
        count++;
      } else if (item.children) {
        count += countFiles(item.children);
      }
    }
    return count;
  };

  const renderTree = (items, depth = 0) => {
    return items.map((item) => {
      if (item.type === 'directory') {
        const isExpanded = expandedDirs[item.path];
        return (
          <div key={item.path} className="tree-item">
            <div
              className="tree-item-header tree-dir"
              onClick={() => onToggleDir(item.path)}
            >
              <span className="tree-icon">{isExpanded ? '📂' : '📁'}</span>
              <span className="tree-name">{item.name}</span>
            </div>
            {isExpanded && item.children && item.children.length > 0 && (
              <div className="tree-children">
                {renderTree(item.children, depth + 1)}
              </div>
            )}
          </div>
        );
      } else {
        return (
          <div
            key={item.path}
            className="tree-item tree-file"
            onClick={() => onNoteClick(item)}
          >
            <span className="tree-icon">📝</span>
            <span className="tree-name" title={item.name}>{item.name}</span>
          </div>
        );
      }
    });
  };

  return (
    <div className="workspace-tree-container">
      {renderTree(workspaceTree)}
    </div>
  );
}
