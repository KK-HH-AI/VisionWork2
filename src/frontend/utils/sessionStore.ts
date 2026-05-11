import type { SessionData, ChatMessage, CanvasNode, CanvasEdge } from '../types';

const SESSIONS_KEY = 'visionwork2_sessions';
const CURRENT_SESSION_KEY = 'visionwork2_current_session_id';

function generateId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

export function loadSessions(): SessionData[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SessionData[];
    if (!Array.isArray(parsed)) return [];
    return parsed.map((s) => ({
      ...s,
      messages: s.messages || [],
      canvasNodes: s.canvasNodes || [],
      canvasEdges: s.canvasEdges || [],
    }));
  } catch {
    return [];
  }
}

function saveSessions(sessions: SessionData[]): void {
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  } catch (e) {
    console.error('Failed to save sessions:', e);
  }
}

export function loadCurrentSessionId(): string | null {
  try {
    return localStorage.getItem(CURRENT_SESSION_KEY);
  } catch {
    return null;
  }
}

function saveCurrentSessionId(id: string | null): void {
  try {
    if (id) {
      localStorage.setItem(CURRENT_SESSION_KEY, id);
    } else {
      localStorage.removeItem(CURRENT_SESSION_KEY);
    }
  } catch (e) {
    console.error('Failed to save current session id:', e);
  }
}

export function createSession(title?: string): SessionData {
  const session: SessionData = {
    id: generateId(),
    title: title || '新会话',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
    canvasNodes: [],
    canvasEdges: [],
  };
  const sessions = loadSessions();
  sessions.unshift(session);
  saveSessions(sessions);
  saveCurrentSessionId(session.id);
  return session;
}

export function updateSession(
  id: string,
  updates: {
    title?: string;
    projectPath?: string;
    messages?: ChatMessage[];
    canvasNodes?: CanvasNode[];
    canvasEdges?: CanvasEdge[];
  }
): SessionData | null {
  const sessions = loadSessions();
  const index = sessions.findIndex((s) => s.id === id);
  if (index === -1) return null;

  const session = sessions[index];
  if (updates.title !== undefined) session.title = updates.title;
  if (updates.projectPath !== undefined) session.projectPath = updates.projectPath;
  if (updates.messages !== undefined) session.messages = updates.messages;
  if (updates.canvasNodes !== undefined) session.canvasNodes = updates.canvasNodes;
  if (updates.canvasEdges !== undefined) session.canvasEdges = updates.canvasEdges;
  session.updatedAt = Date.now();

  sessions[index] = session;
  saveSessions(sessions);
  return session;
}

export function getSession(id: string): SessionData | null {
  const sessions = loadSessions();
  return sessions.find((s) => s.id === id) || null;
}

export function deleteSession(id: string): void {
  const sessions = loadSessions().filter((s) => s.id !== id);
  saveSessions(sessions);
  const currentId = loadCurrentSessionId();
  if (currentId === id) {
    const newCurrent = sessions.length > 0 ? sessions[0].id : null;
    saveCurrentSessionId(newCurrent);
  }
}

export function switchToSession(id: string): SessionData | null {
  const session = getSession(id);
  if (session) {
    saveCurrentSessionId(id);
  }
  return session;
}

export function getCurrentSession(): SessionData | null {
  const currentId = loadCurrentSessionId();
  if (!currentId) return null;
  return getSession(currentId);
}

export function ensureCurrentSession(): SessionData {
  const current = getCurrentSession();
  if (current) return current;
  return createSession();
}