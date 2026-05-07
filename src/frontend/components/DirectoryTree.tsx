import React, { useState } from 'react';
import { getFileIcon } from '../utils/fileIcons';
import type { DirectoryNode } from '../types';

interface DirectoryTreeProps {
  node: DirectoryNode;
  depth?: number;
}

export default function DirectoryTree({ node, depth = 0 }: DirectoryTreeProps) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isDirectory = node.type === 'directory';

  const toggle = () => {
    if (isDirectory) {
      setExpanded(!expanded);
    }
  };

  return (
    <div>
      <div
        className="tree-item"
        style={{ paddingLeft: `${depth * 16}px` }}
        onClick={toggle}
      >
        <span className="tree-icon">
          {isDirectory ? (expanded ? '📂' : '📁') : getFileIcon(node.name)}
        </span>
        <span className="tree-name">{node.name}</span>
      </div>
      {isDirectory && expanded && node.children && (
        <div className="tree-children">
          {node.children.map((child, idx) => (
            <DirectoryTree key={child.path || idx} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
