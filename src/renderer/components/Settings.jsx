import React, { useState } from 'react';

export default function Settings({ config, onSave }) {
  const [form, setForm] = useState({ ...config });
  const [saved, setSaved] = useState(false);

  const handleChange = (key, value) => {
    setForm(prev => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    await onSave(form);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const handleOpenFolder = () => {
    window.electronAPI.openFolder(form.downloadFolder);
  };

  return (
    <div className="flex flex-col gap-6 max-w-lg">
      <h2 className="text-sm font-semibold text-white">Settings</h2>

      {/* Download folder */}
      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Storage</h3>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-slate-300">Download Folder</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={form.downloadFolder || ''}
              onChange={e => handleChange('downloadFolder', e.target.value)}
              className="input-field flex-1 font-mono text-xs"
              placeholder="/home/user/Downloads/yt-downloads"
            />
            <button onClick={handleOpenFolder} className="btn-ghost shrink-0" title="Open folder">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
          <p className="text-xs text-slate-600">The folder where all downloaded files will be saved.</p>
        </div>
      </div>

      {/* Format preferences */}
      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Format Preferences</h3>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-slate-300">Default Format</label>
          <select
            value={form.defaultFormat || 'bestvideo+bestaudio/best'}
            onChange={e => handleChange('defaultFormat', e.target.value)}
            className="select-field"
          >
            <option value="bestvideo+bestaudio/best">Best Quality (auto)</option>
            <option value="bestvideo[height<=1080]+bestaudio/best[height<=1080]">Up to 1080p</option>
            <option value="bestvideo[height<=720]+bestaudio/best[height<=720]">Up to 720p</option>
            <option value="bestvideo[height<=480]+bestaudio/best[height<=480]">Up to 480p</option>
            <option value="bestaudio/best">Audio Only (best)</option>
          </select>
        </div>

        {/* Auto-convert to MP3 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-slate-300">Auto-convert audio to MP3</p>
            <p className="text-xs text-slate-600 mt-0.5">Requires ffmpeg to be installed.</p>
          </div>
          <button
            onClick={() => handleChange('autoConvertMp3', !form.autoConvertMp3)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-300 focus:outline-none ${
              form.autoConvertMp3 ? 'bg-indigo-600' : 'bg-white/10'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-300 ${
                form.autoConvertMp3 ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button onClick={handleSave} className="btn-primary">
          {saved ? (
            <>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path d="m20 6-11 11-5-5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Saved!
            </>
          ) : (
            <>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M17 21v-8H7v8M7 3v5h8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Save Settings
            </>
          )}
        </button>
        <button
          onClick={() => { setForm({ ...config }); setSaved(false); }}
          className="btn-ghost"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
