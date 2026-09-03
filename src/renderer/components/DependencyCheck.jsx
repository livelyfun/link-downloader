import React, { useState, useEffect } from 'react';

export default function DependencyCheck({ deps, onDepsUpdated }) {
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!window.electronAPI.onInstallProgress) return;
    const cleanup = window.electronAPI.onInstallProgress(({ percent }) => {
      setProgress(percent);
    });
    return cleanup;
  }, []);

  const handleAutoInstallYtDlp = async () => {
    setInstalling(true);
    setError(null);
    setProgress(0);

    const res = await window.electronAPI.installYtdlp();
    setInstalling(false);

    if (res.success) {
      if (onDepsUpdated) {
        const fresh = await window.electronAPI.checkDeps();
        onDepsUpdated(fresh);
      }
    } else {
      setError(res.error || 'Failed to auto-install yt-dlp');
    }
  };

  const issues = [];
  if (!deps.ytdlp) {
    issues.push({
      name: 'yt-dlp',
      canAutoInstall: true,
      fix: 'pip install yt-dlp   OR   sudo apt install yt-dlp',
    });
  }
  if (!deps.ffmpeg) {
    issues.push({
      name: 'ffmpeg',
      canAutoInstall: false,
      fix: 'sudo apt install ffmpeg',
    });
  }

  if (issues.length === 0) return null;

  return (
    <div className="mx-5 mb-1 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 flex gap-3 items-start fade-in-up">
      <svg className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="9" x2="12" y2="13" strokeLinecap="round" />
        <line x1="12" y1="17" x2="12.01" y2="17" strokeLinecap="round" />
      </svg>
      <div className="flex-1">
        <p className="text-sm font-semibold text-amber-300">Missing dependencies</p>
        <div className="flex flex-col gap-1.5 mt-1.5">
          {issues.map(({ name, canAutoInstall, fix }) => (
            <div key={name} className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-amber-200/80">
                <strong className="text-amber-300">{name}</strong> not found — run:{' '}
                <code className="font-mono bg-black/30 px-1.5 py-0.5 rounded text-amber-200">{fix}</code>
              </p>
              {name === 'yt-dlp' && canAutoInstall && (
                <button
                  onClick={handleAutoInstallYtDlp}
                  disabled={installing}
                  className="px-3 py-1 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 font-medium text-xs rounded-lg transition-all flex items-center gap-1.5"
                >
                  {installing ? (
                    <>
                      <svg className="w-3.5 h-3.5 spin-slow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4" strokeLinecap="round" />
                      </svg>
                      Installing ({progress}%)…
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                        <path d="M12 15V3m0 12-4-4m4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      ⚡ Auto-Install yt-dlp
                    </>
                  )}
                </button>
              )}
            </div>
          ))}
        </div>
        {error && (
          <p className="text-xs text-red-400 mt-2">{error}</p>
        )}
      </div>
    </div>
  );
}
