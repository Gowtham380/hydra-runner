import React from 'react';
import { Film, Download, Sparkles, User } from 'lucide-react';
import { usePersistentDownloads } from '../utils/persistentDownloader';

export default function BottomNav({ 
  onOpenProfile, 
  onOpenDownloads,
  activeCategory, 
  setActiveCategory,
  onGoHome,
  currentView = 'catalog',
  hasSelectedGroup = false
}) {
  const { downloads } = usePersistentDownloads();
  
  // Count active/paused downloads
  const activeCount = Object.values(downloads || {}).filter(
    d => d.status === 'downloading' || d.status === 'paused' || d.status === 'stalled'
  ).length;

  const isHomeActive = currentView === 'catalog' && !hasSelectedGroup && activeCategory === 'All';
  const isExploreActive = currentView === 'catalog' && !hasSelectedGroup && activeCategory !== 'All';
  const isDownloadsActive = currentView === 'downloads' && !hasSelectedGroup;
  const isProfileActive = currentView === 'profile' && !hasSelectedGroup;

  return (
    <div className="md:hidden fixed bottom-4 left-4 right-4 z-50 animate-slideUp">
      <nav 
        aria-label="Mobile Navigation" 
        className="bg-[#070A0F]/95 backdrop-blur-2xl border border-zinc-800/90 rounded-2xl py-2 px-3 shadow-[0_16px_50px_rgba(0,0,0,0.95)] flex items-center justify-between"
      >
        
        {/* Home */}
        <button
          onClick={() => {
            if (onGoHome) onGoHome();
            if (setActiveCategory) setActiveCategory('All');
          }}
          className={`flex flex-col items-center justify-center py-1.5 px-3 rounded-xl transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
            isHomeActive
              ? 'text-red-500 font-extrabold scale-105' 
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          aria-label="Navigate to Home"
          aria-current={isHomeActive ? 'page' : undefined}
        >
          <Film className={`w-5 h-5 ${isHomeActive ? 'text-red-500' : ''}`} />
          <span className="text-[10px] font-bold mt-0.5">Home</span>
        </button>

        {/* Explore Categories */}
        <button
          onClick={() => {
            if (onGoHome) onGoHome();
            if (setActiveCategory) setActiveCategory(activeCategory === 'Web Series' ? '4K Ultra HD' : 'Web Series');
          }}
          className={`flex flex-col items-center justify-center py-1.5 px-3 rounded-xl transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
            isExploreActive
              ? 'text-amber-400 font-extrabold scale-105' 
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          aria-label="Explore Movie & Series Categories"
          aria-current={isExploreActive ? 'page' : undefined}
        >
          <Sparkles className={`w-5 h-5 ${isExploreActive ? 'text-amber-400' : 'text-amber-400/70'}`} />
          <span className="text-[10px] font-bold mt-0.5">Explore</span>
        </button>

        {/* Downloads with Active Count Badge */}
        <button
          onClick={onOpenDownloads}
          className={`flex flex-col items-center justify-center py-1.5 px-3 rounded-xl transition-all cursor-pointer relative focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
            isDownloadsActive
              ? 'text-emerald-400 font-extrabold scale-105' 
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          aria-label={`Downloads Manager (${activeCount} active downloads)`}
          aria-current={isDownloadsActive ? 'page' : undefined}
        >
          <div className="relative">
            <Download className={`w-5 h-5 ${isDownloadsActive ? 'text-emerald-400' : 'text-emerald-400/80'}`} />
            {activeCount > 0 && (
              <span className="absolute -top-1.5 -right-2 bg-red-600 text-white text-[9px] font-black px-1.5 py-0.2 rounded-full animate-pulse shadow-md border border-white/20">
                {activeCount}
              </span>
            )}
          </div>
          <span className="text-[10px] font-bold mt-0.5">Downloads</span>
        </button>

        {/* VIP Profile */}
        <button
          onClick={onOpenProfile}
          className={`flex flex-col items-center justify-center py-1.5 px-3 rounded-xl transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
            isProfileActive
              ? 'text-rose-400 font-extrabold scale-105' 
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
          aria-label="Open User VIP Profile"
          aria-current={isProfileActive ? 'page' : undefined}
        >
          <div className={`w-5 h-5 rounded-full bg-gradient-to-tr from-red-600 to-rose-600 flex items-center justify-center text-[10px] font-black text-white border ${
            isProfileActive ? 'border-red-400 ring-2 ring-red-500/50' : 'border-red-400/50'
          } shadow-sm`}>
            S
          </div>
          <span className="text-[10px] font-bold mt-0.5">VIP</span>
        </button>

      </nav>
    </div>
  );
}
