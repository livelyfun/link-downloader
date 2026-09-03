import React, { useState, useEffect } from 'react';

function HistoryItem({ item, onShowFile, onOpenFolder }) {
  const statusColor = {
    completed: 'badge-success',
    failed: 'badge-error',
    cancelled: 'badge-warn',
    'in-progress': 'badge-info',
  };

  const formattedDate = item.completedAt || item.startedAt
    ? new Date(item.completedAt || item.startedAt).toLocaleString()
    : '—';

  return (
    <div className="card p-4 flex items-center gap-4">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white truncate" title={item.title}>{item.title}</p>
        <p className="text-xs text-slate-600 mt-0.5">{formattedDate}</p>
        {item.filePath && (
          <p className="text-xs text-slate-500 truncate mt-0.5" title={item.filePath}>{item.filePath}</p>
        )}
        {item.error && (
          <p className="text-xs text-red-400 mt-0.5 truncate">{item.error}</p>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span className={statusColor[item.status] || 'badge-info'}>{item.status}</span>
        {item.status === 'completed' && (
          <button
            onClick={() => onShowFile(item.filePath)}
            className="btn-ghost py-1 px-2.5 text-xs"
          >
            Show File
          </button>
        )}
      </div>
    </div>
  );
}

export default function HistoryList() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    const h = await window.electronAPI.getHistory();
    setHistory([...(h || [])].reverse()); // newest first
    setLoading(false);
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleClear = async () => {
    if (!confirm('Clear all download history?')) return;
    await window.electronAPI.clearHistory();
    setHistory([]);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Download History</h2>
        <div className="flex gap-2">
          <button onClick={refresh} className="btn-ghost py-1.5 px-3 text-xs">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3 3v5h5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Refresh
          </button>
          {history.length > 0 && (
            <button onClick={handleClear} className="btn-danger py-1.5 px-3 text-xs">
              Clear All
            </button>
          )}
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {[1,2,3].map(i => (
            <div key={i} className="rounded-2xl h-16 skeleton" />
          ))}
        </div>
      ) : history.length === 0 ? (
        <div className="card p-12 flex flex-col items-center gap-3 text-center">
          <svg className="w-10 h-10 text-slate-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <p className="text-sm text-slate-500">No downloads yet.</p>
          <p className="text-xs text-slate-600">Your download history will appear here.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {history.map(item => (
            <HistoryItem
              key={item.id}
              item={item}
              onShowFile={(fp) => window.electronAPI.showItemInFolder(fp)}
              onOpenFolder={(folder) => window.electronAPI.openFolder(folder)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
