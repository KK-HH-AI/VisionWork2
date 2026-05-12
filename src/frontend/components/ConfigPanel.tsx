import React from 'react';
import { Check } from 'react-feather';

interface ConfigPanelProps {
  apiUrl: string;
  setApiUrl: (value: string) => void;
  apiKey: string;
  setApiKey: (value: string) => void;
  modelName: string;
  setModelName: (value: string) => void;
  isAnalyzing: boolean;
  configSaved: boolean;
}

export default function ConfigPanel({
  apiUrl, setApiUrl,
  apiKey, setApiKey,
  modelName, setModelName,
  isAnalyzing, configSaved
}: ConfigPanelProps) {
  return (
    <div className="config-panel">
      <div className="config-field">
        <label>API 地址</label>
        <input
          type="text"
          value={apiUrl}
          onChange={(e) => setApiUrl(e.target.value)}
          placeholder="https://api.openai.com/v1"
          disabled={isAnalyzing}
        />
      </div>
      <div className="config-field">
        <label>API Key</label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-..."
          disabled={isAnalyzing}
        />
      </div>
      <div className="config-field">
        <label>模型名称</label>
        <input
          type="text"
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          placeholder="gpt-3.5-turbo"
          disabled={isAnalyzing}
        />
      </div>
      {configSaved && (
        <div className="config-saved-hint"><Check size={14} /> 配置已自动保存</div>
      )}
    </div>
  );
}
