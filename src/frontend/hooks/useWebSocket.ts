import { useState, useEffect, useCallback, useRef } from 'react';
import { flushSync } from 'react-dom';
import type { MessageHandlers, WSMessage } from '../types';

declare global {
  interface Window {
    electronAPI?: {
      getBackendConfig: () => Promise<{ port: number; token: string; ready: boolean }>;
      selectFolder: () => Promise<string | null>;
      readFile: (filePath: string) => Promise<{ success: boolean; content?: string; error?: string; size?: number }>;
    };
    __enqueueCanvasCommand?: (command: unknown) => void;
  }
}

export default function useWebSocket(onMessageHandlers: MessageHandlers) {
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const backendPortRef = useRef(8765);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    async function connect() {
      try {
        let port: number;
        let token: string;

        if (window.electronAPI) {
          const config = await window.electronAPI.getBackendConfig();
          port = config.port;
          token = config.token;
        } else {
          port = 8765;
          token = 'dev-token';
        }

        backendPortRef.current = port;

        const wsUrl = `ws://127.0.0.1:${port}/ws?token=${token}`;
        const websocket = new WebSocket(wsUrl);

        websocket.onopen = () => {
          setConnected(true);
          if (onMessageHandlers.onError) onMessageHandlers.onError('');
        };

        websocket.onclose = () => {
          setConnected(false);
        };

        websocket.onmessage = (event) => {
          const message: WSMessage = JSON.parse(event.data);
          console.log('[WS] Received message:', message.type, message);

          if (message.type === 'directory_tree') {
            flushSync(() => {
              if (onMessageHandlers.onDirectoryTree) onMessageHandlers.onDirectoryTree(message);
            });
          } else if (message.type === 'memory_graph') {
            flushSync(() => {
              if (onMessageHandlers.onMemoryGraph) onMessageHandlers.onMemoryGraph(message);
            });
          } else if (message.type === 'canvas_command') {
            const cmd = message.command;
            if (cmd && cmd.cmd) {
              console.log('[Canvas] Enqueue command:', cmd.cmd, cmd.id || cmd.source || '');
              if (window.__enqueueCanvasCommand) {
                window.__enqueueCanvasCommand(cmd);
              } else {
                console.warn('[Canvas] __enqueueCanvasCommand not ready, command dropped:', cmd.cmd);
              }
            }
          } else if (message.type === 'progress') {
            flushSync(() => {
              if (onMessageHandlers.onProgress) onMessageHandlers.onProgress(message);
            });
          } else if (message.type === 'first_pass_complete') {
            flushSync(() => {
              if (onMessageHandlers.onFirstPassComplete) onMessageHandlers.onFirstPassComplete(message);
            });
          } else if (message.type === 'analysis_complete') {
            flushSync(() => {
              if (onMessageHandlers.onAnalysisComplete) onMessageHandlers.onAnalysisComplete(message);
            });
          } else if (message.type === 'memory_path_update') {
            flushSync(() => {
              if (onMessageHandlers.onMemoryPathUpdate) onMessageHandlers.onMemoryPathUpdate(message);
            });
          } else if (message.type === 'stopped') {
            flushSync(() => {
              if (onMessageHandlers.onStopped) onMessageHandlers.onStopped(message);
            });
          } else if (message.type === 'error') {
            flushSync(() => {
              if (onMessageHandlers.onError) onMessageHandlers.onError(message.message || '');
            });
          } else if (message.type === 'chat_response') {
            flushSync(() => {
              if (onMessageHandlers.onChatResponse) onMessageHandlers.onChatResponse(message);
            });
          } else if (message.type === 'pong') {
          }
        };

        websocket.onerror = () => {
          if (onMessageHandlers.onError) onMessageHandlers.onError('WebSocket connection failed');
          setConnected(false);
        };

        setWs(websocket);
        wsRef.current = websocket;
      } catch (err) {
        if (onMessageHandlers.onError) onMessageHandlers.onError(`Connection failed: ${(err as Error).message}`);
      }
    }

    connect();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const sendMessage = useCallback((message: unknown) => {
    if (wsRef.current && connected) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, [connected]);

  return { ws, connected, sendMessage, backendPortRef };
}
