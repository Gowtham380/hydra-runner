import React, { useState, useEffect } from 'react';
import { 
  ArrowLeft, 
  ShieldCheck, 
  Zap, 
  HardDrive, 
  Crown, 
  CheckCircle2, 
  Sparkles, 
  Smartphone, 
  Lock, 
  RefreshCw,
  LogOut
} from 'lucide-react';
import { triggerHaptic, getTelegramUserInfo } from '../lib/telegram';

export default function VIPProfilePage({ onBack }) {
  const [userInfo, setUserInfo] = useState(null);
  const [storageEstimate, setStorageEstimate] = useState({ usage: 0, quota: 0 });

  useEffect(() => {
    const info = getTelegramUserInfo();
    if (info) {
      setUserInfo(info);
    }

    if (navigator.storage && navigator.storage.estimate) {
      navigator.storage.estimate().then(est => {
        setStorageEstimate({
          usage: Math.round((est.usage || 0) / (1024 * 1024)),
          quota: Math.round((est.quota || 0) / (1024 * 1024 * 1024))
        });
      });
    }
  }, []);

  const handleRefreshSession = () => {
    triggerHaptic('notification', 'success');
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white flex flex-col font-sans animate-fadeIn">
      
      {/* Minimal Top Header */}
      <header className="relative z-20 w-full bg-zinc-950/90 backdrop-blur-2xl border-b border-zinc-800/60 px-4 sm:px-6 py-3">
        <div className="w-full max-w-4xl mx-auto flex items-center justify-between">
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

          <div className="flex items-center gap-1.5 text-xs font-bold text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-500/20">
            <Crown className="w-3.5 h-3.5" />
            <span>VIP Pass Active</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-6 pb-24">
        
        {/* Minimalist Profile Card */}
        <div className="rounded-2xl p-5 bg-zinc-900/50 border border-zinc-800/80 space-y-4">
          <div className="flex items-center gap-4">
            <div className="relative shrink-0">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-red-600 to-rose-600 text-white flex items-center justify-center text-2xl font-black shadow-md">
                {userInfo?.first_name ? userInfo.first_name[0].toUpperCase() : 'S'}
              </div>
              <div className="absolute -bottom-1 -right-1 bg-emerald-500 text-white p-1 rounded-lg ring-2 ring-zinc-950" title="Verified VIP">
                <ShieldCheck className="w-3.5 h-3.5" />
              </div>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 text-[10px] font-bold text-red-400 uppercase tracking-wider">
                <Crown className="w-3 h-3" />
                <span>VIP Ultra Premium</span>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight truncate mt-0.5">
                {userInfo ? `${userInfo.first_name || ''} ${userInfo.last_name || ''}` : 'SMD VIP Member'}
              </h2>
              <p className="text-xs text-zinc-400 font-medium">
                Unlimited 4K Uncapped Streaming & Fast Offline Downloads
              </p>
            </div>
          </div>
        </div>

        {/* Features & Benefits */}
        <div className="space-y-3">
          <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-red-500" />
            <span>VIP Benefits</span>
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-3.5 space-y-1.5">
              <Zap className="w-4 h-4 text-amber-400" />
              <h4 className="text-xs font-bold text-white">4K & 1080p Ultra HD</h4>
              <p className="text-[11px] text-zinc-400">Pristine quality streams with zero speed limits.</p>
            </div>

            <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-3.5 space-y-1.5">
              <HardDrive className="w-4 h-4 text-emerald-400" />
              <h4 className="text-xs font-bold text-white">Offline Storage</h4>
              <p className="text-[11px] text-zinc-400">Save movies directly to device storage for offline playback.</p>
            </div>

            <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-3.5 space-y-1.5">
              <Smartphone className="w-4 h-4 text-sky-400" />
              <h4 className="text-xs font-bold text-white">Multi-Device Handoff</h4>
              <p className="text-[11px] text-zinc-400">Seamless playback on Mobile, Web, and TV.</p>
            </div>
          </div>
        </div>

        {/* Device Storage Diagnostic */}
        <div className="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
              <HardDrive className="w-3.5 h-3.5 text-emerald-400" />
              <span>Storage Usage</span>
            </span>
            <button
              onClick={handleRefreshSession}
              className="text-xs text-zinc-400 hover:text-amber-400 flex items-center gap-1 transition cursor-pointer"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Refresh</span>
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500">Offline Cache</span>
              <p className="text-sm font-bold text-white font-mono mt-0.5">{storageEstimate.usage} MB</p>
            </div>
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500">Device Quota</span>
              <p className="text-sm font-bold text-emerald-400 font-mono mt-0.5">~{storageEstimate.quota} GB</p>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}

