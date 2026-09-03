import React, { useState } from 'react';

function formatCount(n) {
  if (!n) return null;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B views`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M views`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K views`;
  return `${n} views`;
}

function FormatOption({ format, selected, onSelect }) {
  const kindColors = {
    'video+audio': 'text-emerald-400',
    'video-only': 'text-blue-400',
    'audio-only': 'text-violet-400',
  };
  return (
    <button
      onClick={() => onSelect(format)}
      className={`w-full text-left rounded-xl px-4 py-3 border transition-all duration-200 ${
        selected
          ? 'border-indigo-500/50 bg-indigo-500/10 text-white'
          : 'border-white/5 bg-white/5 text-slate-300 hover:border-white/10 hover:bg-white/8 hover:text-white'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium truncate">{format.label}</span>
        {format.kind && (
          <span className={`text-xs shrink-0 ${kindColors[format.kind] || 'text-slate-400'}`}>
            {format.ext?.toUpperCase()}
          </span>
        )}
      </div>
    </button>
  );
}

export default function VideoInfoCard({ info, selectedFormat, onFormatChange, onDownload }) {
  const [imgError, setImgError] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [filterKind, setFilterKind] = useState('all');

  const filteredFormats = (info.formats || []).filter(f => {
    if (filterKind === 'all') return true;
    return f.kind === filterKind;
  });

  const handleDownload = async () => {
    setDownloading(true);
    await onDownload();
    setTimeout(() => setDownloading(false), 1000);
  };

  return (
    <div className="card p-5 fade-in-up">
      {/* Video metadata */}
      <div className="flex gap-4">
        {/* Thumbnail */}
        <div className="shrink-0 w-40 h-24 rounded-xl overflow-hidden bg-white/5 border border-white/10">
          {!imgError ? (
            <img
              src={info.thumbnail}
              alt={info.title}
              className="w-full h-full object-cover"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-slate-600">
              <svg className="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
                <path d="M23.5 6.19a3.02 3.02 0 0 0-2.12-2.14C19.45 3.5 12 3.5 12 3.5s-7.45 0-9.38.55A3.02 3.02 0 0 0 .5 6.19C0 8.13 0 12.19 0 12.19s0 4.07.5 6a3.02 3.02 0 0 0 2.12 2.14C4.55 20.88 12 20.88 12 20.88s7.45 0 9.38-.55a3.02 3.02 0 0 0 2.12-2.14c.5-1.94.5-6 .5-6s0-4.06-.5-6zM9.75 15.52V8.86l6.25 3.33-6.25 3.33z" />
              </svg>
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0 flex flex-col justify-between">
          <div>
            <h3 className="font-semibold text-white text-sm leading-snug line-clamp-2">{info.title}</h3>
            {info.uploader && (
              <p className="text-xs text-slate-500 mt-1">{info.uploader}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 mt-2">
            {info.duration && (
              <span className="badge-info">⏱ {info.duration}</span>
            )}
            {info.viewCount && (
              <span className="badge-info">👁 {formatCount(info.viewCount)}</span>
            )}
            {info.formats?.length && (
              <span className="badge-info">{info.formats.length} formats</span>
            )}
          </div>
        </div>
      </div>

      {/* Format filters */}
      <div className="flex gap-2 mt-5 mb-3">
        {['all', 'video+audio', 'video-only', 'audio-only'].map(k => (
          <button
            key={k}
            onClick={() => setFilterKind(k)}
            className={`rounded-lg px-3 py-1 text-xs font-medium transition-all duration-200 ${
              filterKind === k
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                : 'text-slate-500 hover:text-slate-300 border border-transparent hover:border-white/10'
            }`}
          >
            {k === 'all' ? 'All' : k === 'video+audio' ? '🎥 Combined' : k === 'video-only' ? '🎬 Video' : '🎵 Audio'}
          </button>
        ))}
      </div>

      {/* Format list — scrollable */}
      <div className="flex flex-col gap-2 max-h-52 overflow-y-auto pr-1">
        {filteredFormats.map(f => (
          <FormatOption
            key={f.id}
            format={f}
            selected={selectedFormat?.id === f.id}
            onSelect={onFormatChange}
          />
        ))}
        {filteredFormats.length === 0 && (
          <p className="text-sm text-slate-500 text-center py-4">No formats match this filter.</p>
        )}
      </div>

      {/* Download action */}
      <div className="flex items-center gap-3 mt-4 pt-4 border-t border-white/10">
        <div className="flex-1 min-w-0">
          {selectedFormat ? (
            <p className="text-xs text-slate-400 truncate">
              Selected: <span className="text-indigo-300">{selectedFormat.label}</span>
            </p>
          ) : (
            <p className="text-xs text-slate-500">Select a format above</p>
          )}
        </div>
        <button
          onClick={handleDownload}
          disabled={!selectedFormat || downloading}
          className="btn-primary"
        >
          {downloading ? (
            <>
              <svg className="w-4 h-4 spin-slow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" strokeLinecap="round" />
              </svg>
              Starting…
            </>
          ) : (
            <>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path d="M12 15V3m0 12-4-4m4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2 17l.621 2.485A2 2 0 0 0 4.561 21h14.878a2 2 0 0 0 1.94-1.515L22 17" strokeLinecap="round" />
              </svg>
              Download
            </>
          )}
        </button>
      </div>
    </div>
  );
}
