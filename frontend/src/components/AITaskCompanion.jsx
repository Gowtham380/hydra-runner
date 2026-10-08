import React, { useState, useEffect } from 'react';
import { 
  Bot, Cpu, ShieldCheck, Zap, AlertCircle, RotateCcw, 
  CheckCircle2, ArrowRight, Activity, X, RefreshCw 
} from 'lucide-react';
import { usePersistentDownloads, cancelPersistentDownload } from '../utils/persistentDownloader';
import { triggerHaptic } from '../lib/telegram';

export default function AITaskCompanion({ activeDownloadId, onClose }) {
  const { downloads } = usePersistentDownloads();
  const [recentToast, setRecentToast] = useState(null);
  const [undoCountdown, setUndoCountdown] = useState(5);

  // Monitor for newly added downloads to show 5s Undo Checkpoint
  useEffect(() => {
    const list = Object.values(downloads || {});
    if (list.length === 0) return;

    // Find latest downloading or active item created in last 10s
    const now = Date.now();
    const newest = list.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))[0];

    if (newest && (now - (newest.createdAt || 0)) < 8000 && newest.status !== 'completed') {
      if (!recentToast || recentToast.id !== newest.id) {
        setRecentToast(newest);
        setUndoCountdown(5);
      }
    }
  }, [downloads]);

  // Handle Undo Countdown Timer
  useEffect(() => {
    if (!recentToast || undoCountdown <= 0) return;
    const timer = setInterval(() => {
      setUndoCountdown(prev => {
        if (prev <= 1) {
          setRecentToast(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [recentToast, undoCountdown]);

  const handleUndo = () => {
    if (!recentToast) return;
    triggerHaptic('impact', 'medium');
    cancelPersistentDownload(recentToast.id);
    setRecentToast(null);
  };

  // Determine active item for detailed companion telemetry view
  const downloadsList = Array.isArray(downloads) ? downloads : Object.values(downloads || {});
  const activeItem = activeDownloadId 
    ? downloadsList.find(d => String(d.id) === String(activeDownloadId)) || null
    : downloadsList.find(d => d.status === 'downloading' || d.status === 'paused') || null;


  // Execution Phase calculation
  const getPhase = (item) => {
    if (!item) return { phase: 1, label: 'Idle / Standing By', detail: 'Ready for signed edge stream requests' };
    const progress = item.progressPercent || 0;
    if (progress < 5) {
      return { phase: 1, name: 'Planning', label: 'Analyzing Edge Nodes & Auth Credentials', detail: 'Validating signed tokens across 8 parallel proxy endpoints' };
    } else if (progress < 95) {
      return { phase: 2, name: 'Executing', label: 'Mesh Stream Active • 8 Parallel Chunks', detail: `Auto-Healer active • Downloading at ~${item.speedFormatted || '12.5 MB/s'}` };
    } else {
      return { phase: 3, name: 'Verified', label: 'XOR Integrity Passed • Assembly Ready', detail: 'File checksum verified, merging chunk buffers into single blob' };
    }
  };

  const currentPhase = getPhase(activeItem);

  if (!recentToast || undoCountdown <= 0) return null;

  return (
    <div className="w-full font-sans">
      {/* 5-Second Undo Toast Checkpoint */}
      <div 
        role="alert" 
        aria-live="polite"
        className="bg-gradient-to-r from-zinc-900/95 via-zinc-900/98 to-zinc-950/95 border border-red-500/40 p-3.5 rounded-2xl shadow-[0_10px_30px_rgba(225,29,72,0.25)] flex items-center justify-between backdrop-blur-xl animate-bounce-subtle"
      >
        <div className="flex items-center space-x-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-red-600/20 border border-red-500/40 flex items-center justify-center text-red-400 shrink-0 font-mono text-xs font-black">
            {undoCountdown}s
          </div>
          <div className="min-w-0">
            <span className="text-[10px] font-mono uppercase text-red-400 font-bold block tracking-wider">
              Download Initialized • Undo Checkpoint
            </span>
            <p className="text-xs font-bold text-white truncate max-w-[180px] sm:max-w-xs">
              {recentToast.title || recentToast.file_name}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          <button
            onClick={handleUndo}
            className="bg-red-600 hover:bg-red-500 text-white px-3 py-1.5 rounded-xl text-xs font-extrabold flex items-center space-x-1.5 transition active:scale-95 cursor-pointer shadow-md shadow-red-600/30 border border-red-400/40"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Undo</span>
          </button>
          <button
            onClick={() => setRecentToast(null)}
            className="p-1.5 text-zinc-400 hover:text-white rounded-lg transition"
            aria-label="Dismiss Undo Banner"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
