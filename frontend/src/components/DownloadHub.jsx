import React, { useState, useEffect, useRef } from 'react';
import { Download, Pause, Play, Trash2, HardDrive, CheckCircle2, PlayCircle, X } from 'lucide-react';
import { 
  subscribeDownloads, 
  startOrResumePersistentDownload, 
  pausePersistentDownload, 
  deleteDownloadRecord, 
  assembleAndTriggerSave,
  getStreamBlobUrl
} from '../utils/persistentDownloader';
import { triggerHaptic } from '../lib/telegram';

export default function DownloadHub({ isOpen: externalIsOpen, setIsOpen: setExternalIsOpen, showTrigger = false }) {
  const [downloads, setDownloads] = useState([]);
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  
  const isOpen = externalIsOpen !== undefined ? externalIsOpen : internalIsOpen;
  const setIsOpen = setExternalIsOpen || setInternalIsOpen;

  useEffect(() => {
    const unsubscribe = subscribeDownloads((records) => {
      const sorted = (records || []).sort((a, b) => {
        const timeA = a.createdAt || a.addedAt || a.updatedAt || 0;
        const timeB = b.createdAt || b.addedAt || b.updatedAt || 0;
        return timeB - timeA;
      });
      setDownloads(sorted);
    });
    return () => unsubscribe();
  }, []);

  const activeDownloads = downloads.filter(d => d.status === 'downloading');
  const activeCount = downloads.filter(d => d.status === 'downloading' || d.status === 'paused' || d.status === 'paused_network_loss').length;

  const [deleteConfirmRecord, setDeleteConfirmRecord] = useState(null);

  const handlePause = async (id) => {
    triggerHaptic('impact', 'light');
    await pausePersistentDownload(id, 'paused');
  };

  const handleResume = async (rec) => {
    triggerHaptic('impact', 'medium');
    await startOrResumePersistentDownload(rec.movie, rec.urls);
  };

  const handleDeleteRequest = (rec) => {
    triggerHaptic('impact', 'medium');
    setDeleteConfirmRecord(rec);
  };

  const confirmDeleteAction = async () => {
    if (!deleteConfirmRecord) return;
    const targetId = deleteConfirmRecord.id;
    setDeleteConfirmRecord(null);
    triggerHaptic('impact', 'heavy');
    await deleteDownloadRecord(targetId);
  };

  const handleSaveToDevice = async (rec) => {
    triggerHaptic('notification', 'success');
    await assembleAndTriggerSave(rec.id, rec.fileName, rec.movie?.mime_type || 'video/mp4');
  };

  const handleWatchPreview = async (rec) => {
    triggerHaptic('impact', 'medium');
    const blobUrl = await getStreamBlobUrl(rec.id, rec.movie?.mime_type || 'video/mp4');
    if (blobUrl) {
      window.open(blobUrl, '_blank');
    }
  };

  return (
    <>
      {/* Optional Trigger Button (for desktop header embedded trigger) */}
      {showTrigger && (
        <button
          onClick={() => {
            triggerHaptic('impact', 'light');
            setIsOpen(!isOpen);
          }}
          className={`relative p-2 sm:p-2.5 rounded-xl border transition flex items-center gap-2 cursor-pointer ${
            activeDownloads.length > 0 
              ? 'bg-gradient-to-r from-red-600/20 via-rose-600/20 to-red-500/20 border-red-500/50 text-red-400 shadow-lg shadow-red-600/20 animate-pulse' 
              : 'bg-zinc-900 border-zinc-800 text-zinc-300 hover:text-white hover:border-zinc-700'
          }`}
          title="Downloads"
        >
          <Download className="w-4 h-4 text-emerald-400" />
          <span className="hidden sm:inline text-xs font-bold">Downloads</span>
          
          {activeCount > 0 && (
            <span className="absolute -top-1.5 -right-1.5 bg-red-600 text-white font-extrabold text-[10px] w-5 h-5 rounded-full flex items-center justify-center border-2 border-zinc-950 shadow-md">
              {activeCount}
            </span>
          )}
        </button>
      )}

      {/* Slide-over Glassmorphic Download Modal Drawer */}
      {isOpen && (
        <div 
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 z-50 flex items-center justify-center sm:items-start sm:justify-end p-3 sm:p-6 sm:pt-20 bg-black/80 backdrop-blur-md animate-fadeIn"
        >
          <div 
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm sm:w-96 rounded-2xl border border-white/10 p-4 sm:p-5 shadow-[0_25px_60px_rgba(0,0,0,0.95)] bg-zinc-950/95 backdrop-blur-2xl space-y-4 max-h-[85vh] flex flex-col relative"
          >
            
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-800/90 pb-3">
              <div className="flex items-center space-x-2">
                <div className="p-1.5 rounded-lg bg-red-500/10 text-red-500 border border-red-500/20">
                  <Download className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white">Download Hub</h4>
                  <p className="text-[10px] text-zinc-400 font-medium">Persistent Background Engine</p>
                </div>
              </div>
              <button 
                onClick={() => setIsOpen(false)}
                className="text-zinc-400 hover:text-white p-1.5 rounded-lg hover:bg-zinc-900 transition cursor-pointer border border-zinc-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Download List */}
            {downloads.length === 0 ? (
              <div className="py-12 text-center space-y-2.5">
                <div className="w-12 h-12 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto text-zinc-600">
                  <Download className="w-6 h-6" />
                </div>
                <p className="text-xs text-zinc-300 font-bold">No active downloads</p>
                <p className="text-[11px] text-zinc-500 max-w-xs mx-auto">
                  Movies you download will appear here with auto-resume support.
                </p>
              </div>
            ) : (
              <div className="space-y-3 overflow-y-auto pr-1 flex-1 no-scrollbar">
                {downloads.map((rec) => {
                  const isDownloading = rec.status === 'downloading';
                  const isCompleted = rec.status === 'completed';
                  const isPausedNetwork = rec.status === 'paused_network_loss';

                  return (
                    <div key={rec.id} className="bg-zinc-900/90 border border-zinc-800/90 rounded-xl p-3.5 space-y-3 shadow-inner">
                      
                      {/* Title & Status */}
                      <div className="flex items-start space-x-3">
                        <div className="w-10 h-12 rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden shrink-0">
                          <img 
                            src={rec.movie?.poster_url || "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=300&q=80"} 
                            alt={rec.fileName} 
                            className="w-full h-full object-cover" 
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h5 className="text-xs font-bold text-white truncate">{rec.fileName}</h5>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                              isCompleted ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                              isDownloading ? 'bg-red-500/10 text-red-400 border border-red-500/20 animate-pulse' :
                              isPausedNetwork ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                              'bg-zinc-800 text-zinc-400'
                            }`}>
                              {isCompleted ? 'Ready' : isDownloading ? 'Downloading' : isPausedNetwork ? 'Offline' : 'Paused'}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Progress Bar */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-zinc-400 font-medium">
                            {isCompleted ? 'Download Complete' : isDownloading ? 'Downloading...' : 'Paused'}
                          </span>
                          <span className="font-extrabold text-white font-mono">{rec.percentage}%</span>
                        </div>

                        <div className="w-full bg-zinc-950 rounded-full h-2 overflow-hidden border border-zinc-800">
                          <div 
                            className={`h-full rounded-full transition-all duration-300 ${
                              isCompleted ? 'bg-emerald-500' : 'bg-gradient-to-r from-red-600 to-rose-500'
                            }`}
                            style={{ width: `${rec.percentage}%` }}
                          />
                        </div>
                      </div>

                      {/* Controls Row */}
                      <div className="flex items-center justify-between pt-1 border-t border-zinc-800/80 text-xs">
                        
                        {/* Left: Stream Online Button if available */}
                        {rec.streamReady && !isCompleted ? (
                          <button
                            onClick={() => handleWatchPreview(rec)}
                            className="flex items-center space-x-1 text-emerald-400 hover:text-emerald-300 font-bold text-[11px] bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20 transition cursor-pointer"
                          >
                            <PlayCircle className="w-3.5 h-3.5" />
                            <span>Watch Stream</span>
                          </button>
                        ) : (
                          <span className="text-[10px] text-zinc-500 font-medium">
                            {isCompleted ? 'File Saved' : 'Auto-Resume Enabled'}
                          </span>
                        )}

                        {/* Right: Action Icons */}
                        <div className="flex items-center space-x-2">
                          {isDownloading ? (
                            <button
                              onClick={() => handlePause(rec.id)}
                              className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-amber-400 border border-zinc-700 transition cursor-pointer"
                              title="Pause Download"
                            >
                              <Pause className="w-3.5 h-3.5" />
                            </button>
                          ) : !isCompleted ? (
                            <button
                              onClick={() => handleResume(rec)}
                              className="p-1.5 rounded-lg bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 transition cursor-pointer"
                              title="Resume Download"
                            >
                              <Play className="w-3.5 h-3.5" />
                            </button>
                          ) : (
                            <button
                              onClick={() => handleSaveToDevice(rec)}
                              className="p-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/30 transition cursor-pointer"
                              title="Save File to Device"
                            >
                              <HardDrive className="w-3.5 h-3.5" />
                            </button>
                          )}

                          <button
                            onClick={() => handleDeleteRequest(rec)}
                            className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-red-400 border border-zinc-700 transition cursor-pointer"
                            title="Remove Download"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>

                      </div>

                    </div>
                  );
                })}
              </div>
            )}

          </div>
        </div>
      )}

      {/* Delete Confirmation Guard Modal */}
      {deleteConfirmRecord && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn select-none">
          <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-5 max-w-xs w-full space-y-3.5 shadow-2xl">
            <div className="flex items-center gap-2.5 text-red-500">
              <div className="p-2.5 rounded-xl bg-red-500/10 border border-red-500/20">
                <Trash2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Delete Download?</h3>
                <p className="text-[10px] text-zinc-400 font-medium">Confirmation Guard</p>
              </div>
            </div>
            
            <p className="text-xs text-zinc-300 leading-relaxed bg-zinc-950/60 p-2.5 rounded-xl border border-zinc-800/80">
              Are you sure you want to delete <span className="font-bold text-white">"{deleteConfirmRecord.movie?.title || deleteConfirmRecord.fileName || 'this file'}"</span>?
            </p>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                onClick={() => setDeleteConfirmRecord(null)}
                className="px-3.5 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-semibold transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteAction}
                className="px-3.5 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white text-xs font-bold transition shadow-lg shadow-red-600/30 cursor-pointer flex items-center gap-1"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>OK, Delete</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
