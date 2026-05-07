import React from 'react';

interface ProgressBarProps {
  currentTask: string;
  completedFiles: number;
  totalFiles: number;
}

export default function ProgressBar({ currentTask, completedFiles, totalFiles }: ProgressBarProps) {
  const percent = totalFiles > 0 ? Math.round((completedFiles / totalFiles) * 100) : 0;

  return (
    <div className="progress-container">
      <div className="progress-header">
        <span className="progress-task">{currentTask || '准备中...'}</span>
        <span className="progress-count">{completedFiles}/{totalFiles}</span>
      </div>
      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
