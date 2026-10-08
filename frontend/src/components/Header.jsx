import React, { useState, useEffect } from 'react';
import { Search, Film, ShieldCheck, X, Download } from 'lucide-react';
import { usePersistentDownloads } from '../utils/persistentDownloader';

export default function Header({ 
  onOpenSearch, 
  setActiveCategory,
  onOpenProfile,
  onOpenDownloads
}) {
  const [internalProfileCard, setInternalProfileCard] = useState(false);
  const [isMac, setIsMac] = useState(false);
  const { downloads } = usePersistentDownloads();

  const activeCount = Object.values(downloads || {}).filter(
    d => d.status === 'downloading' || d.status === 'paused' || d.status === 'stalled'
  ).length;

  const handleProfileClick = () => {
    if (onOpenProfile) {
      onOpenProfile();
    } else {
      setInternalProfileCard(!internalProfileCard);
    }
  };

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setIsMac(navigator.platform.toUpperCase().indexOf('MAC') >= 0);
    }
  }, []);

  return (
    <>
      <header className="sticky top-0 z-50 w-full transition-all duration-300 bg-zinc-950/95 text-white border-b border-zinc-800/80 shadow-[0_8px_32px_rgba(0,0,0,0.8)] backdrop-blur-2xl px-2 sm:px-6 md:px-8 py-2 sm:py-3">
        <div className="w-full flex items-center justify-between gap-1.5 sm:gap-4">
          
          {/* Brand Logo - Responsive Consumer Styling */}
          <div 
            className="flex items-center gap-1.5 sm:gap-3 cursor-pointer group shrink-0" 
            onClick={() => setActiveCategory && setActiveCategory('All')}
          >
            <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-gradient-to-tr from-red-600 to-rose-600 flex items-center justify-center text-white shadow-lg shadow-red-600/25 group-hover:scale-105 transition-all duration-200 border border-white/10 shrink-0">
              <Film className="w-4 h-4 sm:w-4.5 sm:h-4.5 stroke-[2.5]" />
            </div>
            <div className="shrink-0">
              <div className="flex items-center gap-1 sm:gap-2">
                <span className="font-black text-base sm:text-lg tracking-tight font-heading leading-none">
                  <span className="text-white">SMD</span>
                  <span className="text-red-500 ml-0.5 sm:ml-1">PRIME</span>
                </span>
              </div>
              <p className="text-[10px] font-medium text-zinc-400 leading-none mt-1 hidden sm:block">
                Cinema & Downloads
              </p>
            </div>
          </div>

          {/* Minimal Centered Search Bar */}
          <div className="flex-1 min-w-0 max-w-xs sm:max-w-md mx-1 sm:mx-2">
            <button
              onClick={onOpenSearch}
              className="w-full py-1.5 sm:py-2 px-2.5 sm:px-3.5 rounded-xl bg-zinc-900/90 hover:bg-zinc-800 text-zinc-300 border border-zinc-800/80 hover:border-zinc-700 shadow-inner flex items-center justify-between text-xs font-medium transition-all duration-200 group active:scale-[0.99] cursor-pointer"
              aria-label="Search Catalog (Ctrl+K)"
            >
              <div className="flex items-center gap-1.5 sm:gap-2.5 text-zinc-400 group-hover:text-zinc-200 transition-colors truncate min-w-0">
                <Search className="w-3.5 h-3.5 text-red-500 group-hover:scale-110 transition-transform shrink-0" />
                <span className="truncate text-[11px] sm:text-xs">Search movies...</span>
              </div>
              
              <div className="hidden sm:flex items-center gap-1 bg-zinc-800 border border-zinc-700 px-1.5 py-0.5 rounded text-[10px] text-zinc-400 font-mono font-semibold shrink-0">
                <span className="text-[11px]">{isMac ? '⌘' : 'Ctrl'}</span>
                <span>K</span>
              </div>
            </button>
          </div>

          {/* Right Action Icons & Download Hub - Desktop Only (Mobile uses BottomNav) */}
          <div className="hidden sm:flex items-center gap-1.5 sm:gap-3 shrink-0 ml-auto">
            {/* Download Hub Icon Badge Trigger */}
            <button
              onClick={onOpenDownloads}
              className="relative p-2 sm:p-2.5 rounded-xl border transition flex items-center gap-2 cursor-pointer bg-zinc-900 border-zinc-800 text-zinc-300 hover:text-white hover:border-zinc-700 active:scale-95"
              title="Download Hub"
            >
              <Download className="w-4 h-4 text-emerald-400" />
              <span className="hidden sm:inline text-xs font-bold">Downloads</span>
              {activeCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-red-600 text-white font-extrabold text-[10px] w-5 h-5 rounded-full flex items-center justify-center border-2 border-zinc-950 shadow-md">
                  {activeCount}
                </span>
              )}
            </button>

            {/* Profile Avatar */}
            <div className="pl-1 border-l border-zinc-800/80 shrink-0">
              <button
                onClick={handleProfileClick}
                className="flex items-center gap-2 p-0.5 rounded-full hover:opacity-90 active:scale-95 transition-all group cursor-pointer"
                title="Account"
              >
                <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full text-white border-2 border-red-500/80 flex items-center justify-center text-xs font-black bg-gradient-to-tr from-red-600 to-rose-600 shadow-md shadow-red-600/20 shrink-0">
                  S
                </div>
              </button>
            </div>
          </div>

        </div>
      </header>

      {/* Member Profile Modal */}
      {internalProfileCard && (
        <div 
          onClick={() => setInternalProfileCard(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn"
        >
          <div 
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xs rounded-2xl p-5 shadow-2xl transition-all duration-300 relative border bg-zinc-950 border-zinc-800 text-white"
          >
            <button
              onClick={() => setInternalProfileCard(false)}
              className="absolute top-3.5 right-3.5 p-1 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white transition cursor-pointer border border-zinc-800"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex flex-col items-center text-center">
              <div className="relative mb-3">
                <div className="w-16 h-16 rounded-full bg-gradient-to-tr from-red-600 to-rose-600 text-white border-2 border-red-500 flex items-center justify-center text-xl font-black shadow-xl ring-4 ring-red-500/20">
                  S
                </div>
                <div className="absolute bottom-0 right-0 bg-emerald-500 text-white p-1 rounded-full ring-2 ring-zinc-950" title="VIP Member">
                  <ShieldCheck className="w-3.5 h-3.5 stroke-[2.5]" />
                </div>
              </div>

              <h3 className="text-base font-bold font-heading tracking-tight">
                SMD VIP Member
              </h3>
              <p className="text-[11px] font-medium text-zinc-400 mt-0.5">
                Unlimited High-Speed Downloads & Direct Streaming
              </p>

              <div className="w-full mt-4 pt-3.5 border-t border-zinc-800 flex flex-col gap-2 text-xs">
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-zinc-900 border border-zinc-800">
                  <span className="font-medium text-zinc-400">Account Tier</span>
                  <span className="font-bold text-amber-400">⭐ VIP Premium</span>
                </div>
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-zinc-900 border border-zinc-800">
                  <span className="font-medium text-zinc-400">Download Speed</span>
                  <span className="font-bold text-emerald-400">Maximum Uncapped</span>
                </div>
              </div>
            </div>

          </div>
        </div>
      )}
    </>
  );
}
