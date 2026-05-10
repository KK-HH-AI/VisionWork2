export interface DirectoryNode {
  name: string;
  path: string;
  type: 'directory' | 'file';
  children?: DirectoryNode[];
}

export interface GraphNode {
  id: string;
  label: string;
  group: string;
  path?: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
}

export interface MemoryNote {
  name: string;
  path: string;
}

export interface WorkspaceItem {
  name: string;
  path: string;
  type: 'directory' | 'file';
  children?: WorkspaceItem[];
}

export interface CodeFileRef {
  file: string;
  lines?: [number, number] | null;
}

export interface CanvasNodeData {
  label: string;
  nodeType?: string;
  group?: string;
  description?: string;
  codeRef?: CodeFileRef[] | null;
}

export interface CanvasNode {
  id: string;
  type?: string;
  position: { x: number; y: number };
  data: CanvasNodeData;
  style?: React.CSSProperties;
}

export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  type?: string;
  animated?: boolean;
  markerEnd?: { type: string; color: string };
  style?: React.CSSProperties;
  labelStyle?: React.CSSProperties;
  labelBgStyle?: React.CSSProperties;
}

export interface CanvasCommand {
  cmd: 'add_node' | 'add_edge' | 'layout';
  id?: string;
  label?: string;
  type?: string;
  group?: string;
  description?: string;
  codeRef?: CodeFileRef[] | null;
  source?: string;
  target?: string;
}

export interface WSMessage {
  type: string;
  tree?: DirectoryNode;
  path?: string;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  memory_dir?: string;
  currentTask?: string;
  completedFiles?: number;
  totalFiles?: number;
  nodeIds?: string[];
  message?: string;
  command?: CanvasCommand;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export interface MessageHandlers {
  onDirectoryTree?: (msg: WSMessage) => void;
  onMemoryGraph?: (msg: WSMessage) => void;
  onProgress?: (msg: WSMessage) => void;
  onFirstPassComplete?: (msg: WSMessage) => void;
  onAnalysisComplete?: (msg: WSMessage) => void;
  onMemoryPathUpdate?: (msg: WSMessage) => void;
  onStopped?: (msg: WSMessage) => void;
  onError?: (msg: string | WSMessage) => void;
  onChatResponse?: (msg: WSMessage) => void;
}
