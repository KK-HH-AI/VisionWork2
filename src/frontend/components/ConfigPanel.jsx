import React from 'react';

export default function ConfigPanel({
  profession, setProfession,
  apiUrl, setApiUrl,
  apiKey, setApiKey,
  modelName, setModelName,
  isAnalyzing, configSaved
}) {
  return (
    <div className="config-panel">
      <div className="config-field">
        <label>职业角色</label>
        <input
          type="text"
          value={profession}
          onChange={(e) => setProfession(e.target.value)}
          placeholder="例如：Python后端工程师"
          disabled={isAnalyzing}
        />
      </div>
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
        <div className="config-saved-hint">✅ 配置已自动保存</div>
      )}
    </div>
  );
}
