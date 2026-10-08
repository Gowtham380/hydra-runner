import React, { useState, useEffect, useRef } from 'react';
import { 
  ArrowLeft, 
  Download, 
  Pause, 
  Play, 
  Trash2, 
  HardDrive, 
  CheckCircle2, 
  PlayCircle, 
  Sparkles,
  RefreshCw,
  Film,
  Zap,
  X
} from 'lucide-react';
import { 
  subscribeDownloads, 
  startOrResumePersistentDownload, 
  pausePersistentDownload, 
  deleteDownloadRecord, 
  assembleAndTriggerSave,
  getStreamBlobUrl,
  openWithSystemPlayer
} from '../utils/persistentDownloader';
import { triggerHaptic } from '../lib/telegram';
import { generateDynamicSVGPoster } from '../lib/grouping';

function DownloadCard({ rec, onPause, onResume, onDelete, onSave, onWatch }) {
  const targetProgress = parseFloat(rec.percentage || rec.progress || 0);
  const [displayProgress, setDisplayProgress] = useState(targetProgress);

  useEffect(() => {
    if (rec.status === 'completed' || targetProgress >= 100) {
      setDisplayProgress(100);
      return;
    }

    if (rec.status === 'paused' || rec.status === 'stalled') {
      setDisplayProgress(targetProgress);
      return;
    }

    const speed = rec.speedMBs || 1.0;
    const stepInterval = Math.max(20, Math.min(100, Math.round(75 / Math.max(0.5, speed))));

    const timer = setInterval(() => {
      setDisplayProgress(prev => {
        if (Math.abs(prev - targetProgress) < 0.005) {
          return targetProgress;
        }
        if (prev < targetProgress) {
          return Math.min(targetProgress, +(prev + 0.01).toFixed(2));
        } else {
          return targetProgress;
        }
      });
    }, stepInterval);

    return () => clearInterval(timer);
  }, [targetProgress, rec.status, rec.speedMBs]);

  const fileSize = rec.totalFileSize || rec.fileSize || rec.movie?.file_size_bytes || 0;
  const quality = rec.quality || rec.movie?.qualityCode || '1080p HD';
  const isDownloading = rec.status === 'downloading';
  const isCompleted = rec.status === 'completed';
  const hasDirectUrl = Boolean(rec.urls && rec.urls.length > 0 && typeof rec.urls[0] === 'string' && rec.urls[0].startsWith('http'));
  const canWatch = Boolean(
    isCompleted || 
    rec.streamReady || 
    (rec.completedChunks && rec.completedChunks >= 1) || 
    hasDirectUrl
  );

  const title = rec.movie?.title || rec.fileName || 'Video File';
  const rawPoster = rec.movie?.poster_url || rec.movie?.poster || rec.movie?.poster_path || rec.movie?.backdrop_url;
  const posterSrc = (rawPoster && typeof rawPoster === 'string' && rawPoster.trim().length > 5)
    ? (rawPoster.startsWith('http') ? rawPoster : `https://image.tmdb.org/t/p/w500${rawPoster}`)
    : generateDynamicSVGPoster(title, quality);

  // Card body click handler (Toggles Pause/Resume)
  const handleCardClick = () => {
    if (isCompleted) {
      if (canWatch) onWatch(rec);
      return;
    }
    if (isDownloading) {
      onPause(rec.id);
    } else {
      onResume(rec);
    }
  };

  // Poster click handler (Triggers Watch Preview)
  const handlePosterClick = (e) => {
    e.stopPropagation();
    if (canWatch) {
      onWatch(rec);
    } else if (isDownloading) {
      onPause(rec.id);
    } else {
      onResume(rec);
    }
  };

  return (
    <div 
      onClick={handleCardClick}
      className="bg-zinc-900/50 hover:bg-zinc-900/80 border border-zinc-800/80 hover:border-zinc-700/90 rounded-2xl p-3.5 transition duration-200 shadow-sm cursor-pointer group select-none relative overflow-hidden"
    >
      <div className="flex gap-3">
        {/* Poster Thumbnail Zone */}
        <div 
          onClick={handlePosterClick}
          className="w-16 h-22 rounded-xl overflow-hidden bg-zinc-950 border border-zinc-800/80 shrink-0 relative flex items-center justify-center group/poster cursor-pointer"
          title={canWatch ? "Touch to Play Movie" : "Downloading Chunks..."}
        >
          <img 
            src={posterSrc} 
            alt={title}
            className="w-full h-full object-cover group-hover/poster:scale-105 transition duration-300"
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = generateDynamicSVGPoster(title, quality);
            }}
          />

          {/* Glowing Play Overlay Badge on Poster when Movie is Ready to Watch */}
          {canWatch ? (
            <div className="absolute inset-0 bg-black/40 backdrop-blur-[1px] flex items-center justify-center group-hover/poster:bg-black/20 transition duration-300">
              <div className="w-8 h-8 rounded-full bg-emerald-500/90 border border-emerald-400/80 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.5)] group-hover/poster:scale-110 transition duration-300 animate-pulse">
                <Play className="w-4 h-4 fill-white text-white translate-x-0.5" />
              </div>
            </div>
          ) : (
            isCompleted && (
              <div className="absolute top-1 right-1 bg-emerald-500 text-white p-0.5 rounded-full shadow z-10">
                <CheckCircle2 className="w-3 h-3" />
              </div>
            )
          )}
        </div>

        {/* Metadata & Progress */}
        <div className="flex-1 min-w-0 flex flex-col justify-between py-0.5">
          <div>
            {/* Top Row: Quality Tag + File Size + Small Action Controls */}
            <div className="flex items-center justify-between gap-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded border border-red-500/20">
                  {quality}
                </span>
                <span className="text-[10px] font-mono text-zinc-400">
                  {fileSize ? `${(fileSize / (1024 * 1024)).toFixed(1)} MB` : 'Multi-Segment'}
                </span>
              </div>

              {/* Small Top-Right Action Controls */}
              <div className="flex items-center gap-1">
                {!isCompleted && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isDownloading) {
                        onPause(rec.id);
                      } else {
                        onResume(rec);
                      }
                    }}
                    className={`p-1.5 rounded-lg transition active:scale-95 cursor-pointer border ${
                      isDownloading 
                        ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/30' 
                        : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-700'
                    }`}
                    title={isDownloading ? "Pause Download" : "Resume Download"}
                  >
                    {isDownloading ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                  </button>
                )}

                {isCompleted && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSave(rec);
                    }}
                    className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sky-400 border border-zinc-700 transition active:scale-95 cursor-pointer"
                    title="Save File to Disk"
                  >
                    <HardDrive className="w-3.5 h-3.5" />
                  </button>
                )}

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(rec);
                  }}
                  className="p-1.5 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition active:scale-95 cursor-pointer"
                  title="Delete Download"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <h4 className="text-xs font-bold text-white tracking-tight truncate mt-1" title={title}>
              {title}
            </h4>
          </div>

          {/* Status indicator with single clean percentage */}
          <div className="mt-2 space-y-1">
            <div className="flex justify-between items-center text-[10px]">
              <span className={`font-semibold flex items-center gap-1 ${isCompleted ? 'text-emerald-400' : isDownloading ? 'text-amber-400' : rec.status === 'stalled' || rec.status === 'error' ? 'text-rose-400' : 'text-zinc-400'}`}>
                {isCompleted ? (
                  '📺 Open in System Player (VLC)'
                ) : isDownloading ? (
                  <span className="flex items-center gap-1.5 flex-wrap">
                    <span>Downloading</span>
                    {rec.speedMBs !== undefined && rec.speedMBs !== null && rec.speedMBs > 0 && (
                      <span className="inline-flex items-center gap-0.5 text-[9px] font-mono text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                        <Zap className="w-2.5 h-2.5 fill-amber-400 text-amber-400 animate-pulse" />
                        {rec.speedMBs.toFixed(1)} MB/s
                      </span>
                    )}
                  </span>
                ) : rec.status === 'stalled' || rec.status === 'error' ? (
                  <span className="truncate max-w-[200px]" title={rec.errorMessage || 'Stalled'}>
                    ⚠️ Stalled • Tap to Retry
                  </span>
                ) : (
                  'Paused • Tap Card to Resume'
                )}
              </span>
              <span className="font-mono text-zinc-300 font-bold">
                {displayProgress.toFixed(2)}%
              </span>
            </div>

            {/* Bar */}
            <div className="w-full bg-zinc-950 h-1.5 rounded-full overflow-hidden border border-zinc-800/80">
              <div 
                className={`h-full transition-all duration-75 rounded-full ${
                  isCompleted 
                    ? 'bg-emerald-500' 
                    : isDownloading 
                    ? 'bg-gradient-to-r from-red-600 to-amber-500 animate-pulse' 
                    : 'bg-zinc-700'
                }`}
                style={{ width: `${displayProgress}%` }}
              />
            </div>

            {/* Prominent High-ROI 100% Save to Device Button */}
            {isCompleted && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSave(rec);
                }}
                className="mt-2 w-full py-2 px-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/20 transition active:scale-95 cursor-pointer"
              >
                <HardDrive className="w-4 h-4 shrink-0" />
                <span>Save to Device Storage (100% Ready)</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Premium Chrome/YouTube Style Video Player Modal with Click-to-Play/Pause & Direct Auto-Play
 */
function VideoPlayerModal({ rec, onClose }) {
  const videoRef = useRef(null);
  const [blobUrl, setBlobUrl] = useState(null);
  const [isPreparing, setIsPreparing] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [centerFeedback, setCenterFeedback] = useState(null); // 'play' | 'pause' | null

  const title = rec.movie?.title || rec.fileName || 'Movie Stream';
  const rawPoster = rec.movie?.poster_url || rec.movie?.poster || rec.movie?.poster_path || rec.movie?.backdrop_url;
  const posterSrc = (rawPoster && typeof rawPoster === 'string' && rawPoster.trim().length > 5)
    ? (rawPoster.startsWith('http') ? rawPoster : `https://image.tmdb.org/t/p/w500${rawPoster}`)
    : generateDynamicSVGPoster(title, rec.quality || '1080p');

  // Instant Hybrid Stream Engine: Prefers offline blob or direct stream fallback
  useEffect(() => {
    let isMounted = true;
    let timer = null;

    const fetchSource = async () => {
      if (!isMounted) return;

      const directUrl = (rec.urls && rec.urls.length > 0) ? rec.urls[0] : (rec.movie?.stream_url || rec.movie?.url);

      // If download is completed (100%), load full offline blob
      if (rec.status === 'completed') {
        const offlineUrl = await getStreamBlobUrl(rec.id, rec.movie?.mime_type || 'video/mp4');
        if (offlineUrl && isMounted) {
          setBlobUrl(prevUrl => {
            if (prevUrl && prevUrl.startsWith('blob:')) URL.revokeObjectURL(prevUrl);
            return offlineUrl;
          });
          setIsPreparing(false);
          return;
        }
      }

      // Try offline contiguous blob first if available
      const partialBlobUrl = await getStreamBlobUrl(rec.id, rec.movie?.mime_type || 'video/mp4');
      if (partialBlobUrl && isMounted) {
        setBlobUrl(prevUrl => {
          if (prevUrl && prevUrl.startsWith('blob:')) URL.revokeObjectURL(prevUrl);
          return partialBlobUrl;
        });
        setIsPreparing(false);
        return;
      }

      // High-ROI Instant Fallback: Use direct stream URL for instant 0s playback
      if (directUrl && isMounted) {
        setBlobUrl(directUrl);
        setIsPreparing(false);
        return;
      }

      // Retry if no source ready yet
      if (isMounted) {
        timer = setTimeout(fetchSource, 1000);
      }
    };

    fetchSource();

    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
  }, [rec.id, rec.status]);

  // Handle video element demux / playback errors (e.g. partial blob header issues)
  const handleVideoError = (e) => {
    console.warn("Video playback notice, switching to instant direct stream fallback...", e);
    const directUrl = (rec.urls && rec.urls.length > 0) ? rec.urls[0] : (rec.movie?.stream_url || rec.movie?.url);
    if (directUrl && blobUrl !== directUrl) {
      setBlobUrl(directUrl);
      setIsPreparing(false);
    }
  };

  // Auto-play when blobUrl is ready
  useEffect(() => {
    if (blobUrl && videoRef.current) {
      videoRef.current.play().then(() => {
        setIsPlaying(true);
      }).catch(err => {
        console.warn("Autoplay notice:", err);
      });
    }
  }, [blobUrl]);

  // Clean up blob URL on unmount
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  // Trigger feedback animation
  const showCenterIcon = (type) => {
    setCenterFeedback(type);
    setTimeout(() => {
      setCenterFeedback(null);
    }, 600);
  };

  // Click on Video Screen toggles Play / Pause (Chrome / YouTube style)
  const handleVideoClick = () => {
    if (!videoRef.current) return;
    triggerHaptic('impact', 'medium');
    
    if (videoRef.current.paused) {
      videoRef.current.play().then(() => {
        setIsPlaying(true);
        showCenterIcon('play');
      }).catch(err => console.warn("Video play error:", err));
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
      showCenterIcon('pause');
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/95 backdrop-blur-2xl flex flex-col items-center justify-center p-2 sm:p-6 animate-fadeIn select-none">
      <div className="w-full max-w-5xl bg-zinc-950 border border-zinc-800/90 rounded-3xl overflow-hidden shadow-2xl flex flex-col relative">
        
        {/* Top Header */}
        <div className="px-5 py-3.5 bg-zinc-900/90 backdrop-blur-md border-b border-zinc-800/80 flex items-center justify-between z-20">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <PlayCircle className="w-5 h-5 text-emerald-400 shrink-0 animate-pulse" />
            <div className="truncate">
              <h3 className="text-xs sm:text-sm font-bold text-white truncate">{title}</h3>
              <p className="text-[10px] font-mono text-zinc-400 truncate">
                {rec.quality || '1080p HD'} • Direct Offline Stream
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              triggerHaptic('impact', 'light');
              onClose();
            }}
            className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition cursor-pointer active:scale-95"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Main Player Screen Area */}
        <div className="relative aspect-video w-full bg-black flex items-center justify-center overflow-hidden">
          
          {/* State 1: Preparing Stream Chunks */}
          {isPreparing ? (
            <div className="relative w-full h-full flex flex-col items-center justify-center p-6 text-center space-y-4">
              <img 
                src={posterSrc} 
                alt="" 
                className="absolute inset-0 w-full h-full object-cover opacity-20 blur-xl scale-110" 
              />
              <div className="relative z-10 w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                <RefreshCw className="w-8 h-8 animate-spin text-emerald-400" />
              </div>
              <div className="relative z-10 space-y-1">
                <h4 className="text-sm font-bold text-white">Initializing Stream Engine...</h4>
                <p className="text-xs text-zinc-400 max-w-xs leading-relaxed">
                  Fetching initial segment chunks. Movie will start playing automatically in a few seconds.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Actual Video Tag - Auto-plays directly */}
              <video
                ref={videoRef}
                src={blobUrl}
                autoPlay
                controls
                playsInline
                className="w-full h-full max-h-[80vh] object-contain cursor-pointer"
                onClick={handleVideoClick}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onError={handleVideoError}
              />

              {/* Center Click-to-Play/Pause Feedback Pulse Icon */}
              {centerFeedback && (
                <div className="absolute z-20 pointer-events-none flex items-center justify-center">
                  <div className="w-20 h-20 rounded-full bg-black/60 backdrop-blur-md border border-white/20 flex items-center justify-center animate-ping text-white shadow-2xl">
                    {centerFeedback === 'play' ? (
                      <Play className="w-10 h-10 fill-white text-white translate-x-0.5" />
                    ) : (
                      <Pause className="w-10 h-10 fill-white text-white" />
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DownloadsPage({ onBack }) {
  const [downloads, setDownloads] = useState([]);
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'active', 'completed'
  const [playingRecord, setPlayingRecord] = useState(null);
  const [exportToast, setExportToast] = useState(null);
  const [deleteConfirmRecord, setDeleteConfirmRecord] = useState(null);

  // Auto-hide toast notification after 3.5 seconds
  useEffect(() => {
    if (!exportToast) return;
    const timer = setTimeout(() => {
      setExportToast(null);
    }, 3500);
    return () => clearTimeout(timer);
  }, [exportToast]);

  useEffect(() => {
    const handleExportComplete = (e) => {
      const msg = e.detail?.message || '🎉 Movie 100% Exported to Local Downloads!';
      setExportToast(msg);
    };

    window.addEventListener('hydra_export_complete', handleExportComplete);
    return () => window.removeEventListener('hydra_export_complete', handleExportComplete);
  }, []);

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

  const sortedDownloads = [...downloads].sort((a, b) => {
    const timeA = a.createdAt || a.addedAt || a.updatedAt || 0;
    const timeB = b.createdAt || b.addedAt || b.updatedAt || 0;
    return timeB - timeA;
  });

  const activeDownloads = sortedDownloads.filter(d => d.status === 'downloading' || d.status === 'paused' || d.status === 'stalled');
  const completedDownloads = sortedDownloads.filter(d => d.status === 'completed');

  const filteredDownloads = sortedDownloads.filter(d => {
    if (activeTab === 'active') return d.status === 'downloading' || d.status === 'paused' || d.status === 'stalled';
    if (activeTab === 'completed') return d.status === 'completed';
    return true;
  });

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
    setExportToast('🗑️ Download deleted from local storage');
  };

  const handleSaveToDevice = async (rec) => {
    triggerHaptic('notification', 'success');
    setExportToast(`⏳ Assembling & Exporting ${rec.fileName || 'Movie'}...`);
    await assembleAndTriggerSave(rec.id, rec.fileName, rec.movie?.mime_type || 'video/mp4');
  };

  const handleWatchPreview = async (rec) => {
    triggerHaptic('impact', 'medium');
    await openWithSystemPlayer(rec);
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white flex flex-col font-sans animate-fadeIn relative">
      
      {/* Floating In-Build Export Notification Toast */}
      {exportToast && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 bg-emerald-950/95 text-emerald-200 border border-emerald-500/50 px-4 py-3 rounded-2xl shadow-[0_10px_35px_rgba(16,185,129,0.4)] backdrop-blur-xl flex items-center gap-3 text-xs font-bold animate-bounce select-none">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <span>{exportToast}</span>
          <button 
            onClick={() => setExportToast(null)}
            className="ml-2 text-emerald-400 hover:text-white p-0.5 rounded-full"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Glassmorphic Delete Confirmation Guard Modal */}
      {deleteConfirmRecord && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn select-none">
          <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 max-w-sm w-full space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-red-500">
              <div className="p-3 rounded-2xl bg-red-500/10 border border-red-500/20">
                <Trash2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Delete Download?</h3>
                <p className="text-xs text-zinc-400 font-medium">Confirmation Guard</p>
              </div>
            </div>
            
            <p className="text-xs text-zinc-300 leading-relaxed bg-zinc-950/60 p-3 rounded-xl border border-zinc-800/80">
              Are you sure you want to remove <span className="font-bold text-white">"{deleteConfirmRecord.movie?.title || deleteConfirmRecord.fileName || 'this movie'}"</span> from offline storage?
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                onClick={() => setDeleteConfirmRecord(null)}
                className="px-4 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-semibold transition active:scale-95 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteAction}
                className="px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 text-white text-xs font-bold transition shadow-lg shadow-red-600/30 active:scale-95 cursor-pointer flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>OK, Confirm Delete</span>
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Sleek Minimal Top Navigation */}
      <header className="relative z-20 w-full bg-zinc-950/90 backdrop-blur-2xl border-b border-zinc-800/60 px-4 sm:px-6 py-3">
        <div className="w-full max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                triggerHaptic('impact', 'light');
                onBack();
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-zinc-900/80 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 transition active:scale-95 cursor-pointer text-xs font-semibold"
            >
              <ArrowLeft className="w-3.5 h-3.5 text-red-500" />
              <span>Back</span>
            </button>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-white tracking-tight">Downloads</h1>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                {downloads.length}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-medium">
            <HardDrive className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">Offline Hub</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-5 space-y-5 pb-24">
        
        {/* Minimalist Filter Pills */}
        <div className="flex items-center gap-1.5 bg-zinc-900/60 p-1 rounded-xl border border-zinc-800/80 w-fit">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeTab === 'all' 
                ? 'bg-red-600 text-white shadow-md' 
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            All ({downloads.length})
          </button>
          <button
            onClick={() => setActiveTab('active')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeTab === 'active' 
                ? 'bg-red-600 text-white shadow-md' 
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            Active ({activeDownloads.length})
          </button>
          <button
            onClick={() => setActiveTab('completed')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeTab === 'completed' 
                ? 'bg-red-600 text-white shadow-md' 
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            Completed ({completedDownloads.length})
          </button>
        </div>

        {/* Downloads List */}
        {filteredDownloads.length === 0 ? (
          <div className="py-16 text-center rounded-2xl border border-zinc-800/80 my-4 space-y-3 max-w-sm mx-auto bg-zinc-900/30 p-6">
            <div className="w-12 h-12 bg-red-500/10 text-red-500 rounded-xl flex items-center justify-center mx-auto border border-red-500/20">
              <Download className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-bold text-white">No Downloads Found</h3>
            <p className="text-xs text-zinc-400 leading-relaxed">
              {activeTab === 'all' 
                ? 'Your download storage is empty.' 
                : `No items matching "${activeTab}".`}
            </p>
            <button
              onClick={onBack}
              className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white font-semibold text-xs shadow-md hover:scale-105 transition active:scale-95 cursor-pointer inline-flex items-center gap-1.5"
            >
              <Film className="w-3.5 h-3.5" />
              <span>Browse Catalog</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {filteredDownloads.map((rec) => (
              <DownloadCard 
                key={rec.id}
                rec={rec}
                onPause={handlePause}
                onResume={handleResume}
                onDelete={handleDeleteRequest}
                onSave={handleSaveToDevice}
                onWatch={handleWatchPreview}
              />
            ))}
          </div>
        )}

      </main>

      {/* Video Player Modal */}
      {playingRecord && (
        <VideoPlayerModal 
          rec={playingRecord} 
          onClose={() => setPlayingRecord(null)} 
        />
      )}
    </div>
  );
}
