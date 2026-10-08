import React from 'react';
import { Search, Film } from 'lucide-react';
import DownloadHub from './DownloadHub';

export default function Navbar({ searchQuery, setSearchQuery, onOpenSearch }) {
  return (
    <header className="sticky top-0 z-40 w-full bg-zinc-950/90 text-white border-b border-zinc-800/80 shadow-[0_8px_32px_rgba(0,0,0,0.7)] backdrop-blur-2xl px-4 sm:px-8 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        
        {/* Brand Logo */}
        <div className="flex items-center gap-3 cursor-pointer">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-red-600 via-rose-600 to-red-500 flex items-center justify-center text-white shadow-lg shadow-red-600/30 border border-white/10">
            <Film className="w-4.5 h-4.5 stroke-[2.5]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-black text-lg tracking-tight font-heading leading-none">
                <span className="text-white">SMD</span>
                <span className="text-red-500 ml-1">PRIME</span>
              </span>
            </div>
            <p className="text-[10px] text-zinc-400 hidden sm:block font-medium leading-none mt-1">Cinema & Downloads</p>
          </div>
        </div>

        {/* Consumer Search Input */}
        <div className="flex-1 max-w-md mx-2 sm:mx-4">
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
            <input
              type="text"
              value={searchQuery || ''}
              onChange={(e) => setSearchQuery && setSearchQuery(e.target.value)}
              onClick={onOpenSearch}
              placeholder="Search movies, series..."
              className="w-full bg-zinc-900/90 border border-zinc-800 rounded-xl pl-10 pr-4 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-red-500/60 focus:ring-1 focus:ring-red-500/60 transition font-medium"
            />
          </div>
        </div>

        {/* Download Hub Badge */}
        <div className="flex items-center space-x-3">
          <DownloadHub />
        </div>

      </div>
    </header>
  );
}
