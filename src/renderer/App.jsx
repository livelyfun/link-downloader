import React, { useState, useEffect, useCallback } from 'react';
import UrlInput from './components/UrlInput.jsx';
import VideoInfoCard from './components/VideoInfoCard.jsx';
import DownloadProgress from './components/DownloadProgress.jsx';
import HistoryList from './components/HistoryList.jsx';
import Settings from './components/Settings.jsx';
import DependencyCheck from './components/DependencyCheck.jsx';

const TABS = ['Download', 'History', 'Settings'];

export default function App() {
  const [activeTab, setActiveTab] = useState('Download');
  const [deps, setDeps] = useState(null);
  const [config, setConfig] = useState(null);

  // Video info state
  const [videoInfo, setVideoInfo] = useState(null);
  const [selectedFormat, setSelectedFormat] = useState(null);

  // Download tracking
  const [downloads, setDownloads] = useState({});

  // Check dependencies on mount
  useEffect(() => {
    window.electronAPI.checkDeps().then(setDeps);
    window.electronAPI.getConfig().then(setConfig);
  }, []);

  // Subscribe to download events from main process
  useEffect(() => {
    const removeProgress = window.electronAPI.onDownloadProgress((data) => {
      setDownloads(prev => ({
        ...prev,
        [data.downloadId]: {
          ...prev[data.downloadId],
          ...data,
        },
      }));
    });

    const removeComplete = window.electronAPI.onDownloadComplete((data) => {
      setDownloads(prev => ({
        ...prev,
        [data.downloadId]: {
          ...prev[data.downloadId],
          ...data,
          percent: 100,
        },
      }));
    });

    const removeError = window.electronAPI.onDownloadError((data) => {
      setDownloads(prev => ({
        ...prev,
        [data.downloadId]: {
          ...prev[data.downloadId],
          ...data,
        },
      }));
    });

    return () => {
      removeProgress();
      removeComplete();
      removeError();
    };
  }, []);

  const handleInfoFetched = useCallback((info) => {
    setVideoInfo(info);
    if (info?.formats?.length > 0) {
      setSelectedFormat(info.formats[0]);
    }
  }, []);

  const handleDownload = useCallback(async () => {
    if (!videoInfo || !selectedFormat) return;
    const result = await window.electronAPI.startDownload({
      url: videoInfo.url,
      formatId: selectedFormat.id,
      title: videoInfo.title,
    });
    if (result?.downloadId) {
      setDownloads(prev => ({
        ...prev,
        [result.downloadId]: {
          downloadId: result.downloadId,
          title: videoInfo.title,
          status: 'in-progress',
          percent: 0,
        },
      }));
    }
  }, [videoInfo, selectedFormat]);

  const handleConfigSave = useCallback(async (newConfig) => {
    const saved = await window.electronAPI.saveConfig(newConfig);
    setConfig(saved);
  }, []);

  const activeDownloads = Object.values(downloads);

  return (
    <div className="flex flex-col h-screen bg-[#0f0f13] text-slate-200 select-none">
      {/* Title bar drag region */}
      <div className="flex items-center px-5 pt-4 pb-2 gap-4" style={{ WebkitAppRegion: 'drag' }}>
        {/* App logo + name */}
        <div className="flex items-center gap-2.5" style={{ WebkitAppRegion: 'no-drag' }}>
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-black text-sm shadow-lg shadow-indigo-500/30">
            YT
          </div>
          <span className="font-bold text-white text-sm tracking-tight">YT Downloader</span>
        </div>

        {/* Tabs */}
        <nav className="flex gap-1 ml-4" style={{ WebkitAppRegion: 'no-drag' }}>
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                activeTab === tab
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>

        {/* Active download indicator */}
        {activeDownloads.filter(d => d.status === 'in-progress').length > 0 && (
          <div className="ml-auto flex items-center gap-2" style={{ WebkitAppRegion: 'no-drag' }}>
            <span className="inline-flex items-center gap-1.5 text-xs text-indigo-300">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
              {activeDownloads.filter(d => d.status === 'in-progress').length} downloading
            </span>
          </div>
        )}
      </div>

      {/* Dependency warning banner with auto-installer */}
      {deps && (!deps.ytdlp || !deps.ffmpeg) && (
        <DependencyCheck deps={deps} onDepsUpdated={setDeps} />
      )}

      {/* Main content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'Download' && (
          <div className="h-full flex flex-col gap-4 px-5 py-4 overflow-y-auto">
            <UrlInput onInfoFetched={handleInfoFetched} />

            {videoInfo && (
              <VideoInfoCard
                info={videoInfo}
                selectedFormat={selectedFormat}
                onFormatChange={setSelectedFormat}
                onDownload={handleDownload}
              />
            )}

            {/* Active downloads in the Download tab */}
            {activeDownloads.length > 0 && (
              <div className="flex flex-col gap-3">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Downloads</h3>
                {activeDownloads.map(dl => (
                  <DownloadProgress
                    key={dl.downloadId}
                    download={dl}
                    onCancel={() => window.electronAPI.cancelDownload(dl.downloadId)}
                    onShowFile={() => window.electronAPI.showItemInFolder(dl.filePath)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'History' && (
          <div className="h-full overflow-y-auto px-5 py-4">
            <HistoryList />
          </div>
        )}

        {activeTab === 'Settings' && config && (
          <div className="h-full overflow-y-auto px-5 py-4">
            <Settings config={config} onSave={handleConfigSave} />
          </div>
        )}
      </div>
    </div>
  );
}
