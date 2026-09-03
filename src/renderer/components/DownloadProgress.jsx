import React from 'react';

export default function DownloadProgress({ download, onCancel, onShowFile }) {
  const { downloadId, title, percent = 0, speed, eta, status, filePath, error, size } = download;

  const isActive = status === 'in-progress';
  const isComplete = status === 'completed';
  const isFailed = status === 'failed' || status === 'cancelled';

  const statusColors = {
    'in-progress': 'badge-info',
    completed: 'badge-success',
    failed: 'badge-error',
    cancelled: 'badge-warn',
  };

  const statusLabels = {
    'in-progress': 'Downloading',
    completed: 'Complete',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };

  return (
    <div className={`card p-4 fade-in-up ${isActive ? 'glow-active' : ''}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-white truncate">{title || 'Downloading…'}</p>
          {error && (
            <p className="text-xs text-red-400 mt-0.5 line-clamp-2">{error}</p>
          )}
          {isActive && (
            <div className="flex gap-3 mt-1">
              {speed && <span className="text-xs text-slate-500">⚡ {speed}</span>}
              {eta && eta !== '00:00' && <span className="text-xs text-slate-500">⏱ ETA {eta}</span>}
              {size && <span className="text-xs text-slate-500">📦 {size}</span>}
            </div>
          )}
          {isComplete && filePath && (
            <p className="text-xs text-emerald-500 mt-0.5 truncate" title={filePath}>{filePath}</p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={statusColors[status] || 'badge-info'}>
            {statusLabels[status] || status}
          </span>
          {isActive && (
            <button onClick={onCancel} className="btn-danger py-1 px-2.5 text-xs">
              Cancel
            </button>
          )}
          {isComplete && (
            <button onClick={onShowFile} className="btn-ghost py-1 px-2.5 text-xs">
              Show File
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{
            width: `${Math.min(100, Math.max(0, percent))}%`,
            background: isFailed
              ? '#ef4444'
              : isComplete
              ? 'linear-gradient(90deg, #10b981, #34d399)'
              : 'linear-gradient(90deg, #6366f1, #8b5cf6, #a78bfa)',
          }}
        />
      </div>

      <div className="flex justify-between items-center mt-1.5">
        <span className="text-xs text-slate-600 font-mono">
          {isActive ? `${percent.toFixed(1)}%` : isComplete ? '100%' : '—'}
        </span>
        {isActive && (
          <span className="text-xs text-slate-600 font-mono">{percent.toFixed(1)}%</span>
        )}
      </div>
    </div>
  );
}
