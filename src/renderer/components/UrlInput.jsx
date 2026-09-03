import React, { useState, useRef } from 'react';

const YT_URL_RE = /^https?:\/\/(www\.)?(youtube\.com\/(watch\?.*v=|shorts\/|embed\/)|youtu\.be\/).+/i;

export default function UrlInput({ onInfoFetched }) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setUrl(text.trim());
      setError(null);
    } catch {
      // Ignore clipboard errors
    }
  };

  const handleFetch = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
      setError('Please paste a YouTube URL first.');
      return;
    }
    if (!YT_URL_RE.test(trimmed)) {
      setError('That doesn\'t look like a YouTube URL. Try: https://www.youtube.com/watch?v=...');
      return;
    }

    setLoading(true);
    setError(null);

    const result = await window.electronAPI.fetchInfo(trimmed);

    setLoading(false);

    if (result.success) {
      onInfoFetched(result.data);
    } else {
      setError(result.error || 'Failed to fetch video info.');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleFetch();
  };

  const handleClear = () => {
    setUrl('');
    setError(null);
    onInfoFetched(null);
    inputRef.current?.focus();
  };

  return (
    <div className="card p-5 flex flex-col gap-4 fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-5 h-5 text-indigo-400">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.45 3.5 12 3.5 12 3.5s-7.45 0-9.38.55A3.02 3.02 0 0 0 .5 6.19C0 8.13 0 12.19 0 12.19s0 4.07.5 6a3.02 3.02 0 0 0 2.12 2.14C4.55 20.88 12 20.88 12 20.88s7.45 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14c.5-1.94.5-6 .5-6s0-4.06-.5-6zM9.75 15.52V8.86l6.25 3.33-6.25 3.33z" />
          </svg>
        </div>
        <h2 className="text-sm font-semibold text-white">Paste YouTube URL</h2>
      </div>

      {/* Input row */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="url"
            value={url}
            onChange={(e) => { setUrl(e.target.value); setError(null); }}
            onKeyDown={handleKeyDown}
            placeholder="https://www.youtube.com/watch?v=..."
            className="input-field pr-10"
            disabled={loading}
            spellCheck={false}
          />
          {url && (
            <button
              onClick={handleClear}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
              title="Clear"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </div>

        <button onClick={handlePaste} className="btn-ghost shrink-0" title="Paste from clipboard">
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" strokeLinecap="round" />
            <rect x="9" y="3" width="6" height="4" rx="1" />
          </svg>
          Paste
        </button>

        <button
          onClick={handleFetch}
          disabled={loading || !url.trim()}
          className="btn-primary shrink-0"
        >
          {loading ? (
            <>
              <svg className="w-4 h-4 spin-slow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" strokeLinecap="round" />
              </svg>
              Fetching…
            </>
          ) : (
            <>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" strokeLinecap="round" />
              </svg>
              Fetch Info
            </>
          )}
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 fade-in-up">
          <svg className="w-4 h-4 text-red-400 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" strokeLinecap="round" />
          </svg>
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}
    </div>
  );
}
