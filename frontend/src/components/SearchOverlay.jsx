import React, { useState, useEffect } from 'react';
import { Search, X, Film, Download, HardDrive, Tv, Sparkles, Command } from 'lucide-react';
import { formatBytes } from '../lib/api';
import { generateDynamicSVGPoster } from '../lib/grouping';

export default function SearchOverlay({ movies, onClose, onSelectMovie }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredMovies, setFilteredMovies] = useState(movies || []);

  useEffect(() => {
    if (!searchTerm.trim()) {
      setFilteredMovies(movies || []);
      return;
    }

    const term = searchTerm.toLowerCase().trim();
    const filtered = (movies || []).filter(m => {
      // 1. Direct title or slug match
      if (m.title && m.title.toLowerCase().includes(term)) return true;
      if (m.slug && m.slug.toLowerCase().includes(term)) return true;
      
      // 2. Source file name or quality/language match
      if (m.sources && Array.isArray(m.sources)) {
        const hasSourceMatch = m.sources.some(s => 
          (s.title && s.title.toLowerCase().includes(term)) ||
          (s.file_name && s.file_name.toLowerCase().includes(term)) ||
          (s.qualityLabel && s.qualityLabel.toLowerCase().includes(term)) ||
          (s.language && s.language.toLowerCase().includes(term))
        );
        if (hasSourceMatch) return true;
      }

      // 3. Series season / episode title match
      if (m.type === 'series' && m.seasons) {
        let hasEpMatch = false;
        Object.values(m.seasons).forEach(epMap => {
          Object.values(epMap).forEach(ep => {
            if (ep.title && ep.title.toLowerCase().includes(term)) hasEpMatch = true;
          });
        });
        if (hasEpMatch) return true;
      }

      return false;
    });

    setFilteredMovies(filtered);
  }, [searchTerm, movies]);

  // Handle ESC key listener
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-zinc-950/90 backdrop-blur-2xl animate-fadeIn p-4 sm:p-8">
      
      {/* Raycast Spotlight Search Box */}
      <div className="w-full max-w-3xl mx-auto flex items-center justify-between gap-3 mb-6 bg-zinc-900/90 border border-white/[0.12] rounded-2xl p-2.5 shadow-2xl shadow-black/80">
        <div className="relative flex-1 flex items-center">
          <Search className="w-5 h-5 text-red-500 ml-3 shrink-0" />
          <input
            type="text"
            autoFocus
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Type to search movies, series, 4K UHD, Tamil dubs..."
            className="w-full bg-transparent border-0 pl-3 pr-4 py-2 text-sm font-semibold text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-0"
          />
        </div>

        <div className="flex items-center gap-2">
          <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded bg-zinc-800 border border-white/[0.1] text-[10px] font-mono font-medium text-slate-400">
            <span>ESC</span>
          </kbd>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-zinc-800/80 hover:bg-zinc-700 text-slate-400 hover:text-white border border-white/[0.08] transition cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Search Results Grid Container */}
      <div className="w-full max-w-3xl mx-auto flex-1 overflow-y-auto no-scrollbar pr-1">
        <div className="flex items-center justify-between mb-4">
          <span className="text-[11px] font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-red-400" />
            <span>{searchTerm ? `Matches found (${filteredMovies.length})` : 'All Indexed Content'}</span>
          </span>
        </div>

        {filteredMovies.length === 0 ? (
          <div className="py-16 text-center text-slate-400 flex flex-col items-center bg-zinc-900/40 rounded-2xl border border-white/[0.06]">
            <Film className="w-10 h-10 text-slate-600 mb-3" />
            <p className="text-sm font-semibold text-slate-300">No content matches "{searchTerm}"</p>
            <p className="text-xs text-slate-500 mt-1">Try searching for alternative titles, resolution (e.g. 4K, 1080p), or language.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {filteredMovies.map((movie) => {
              const isSeries = movie.type === 'series';
              const sources = movie.sources || [movie];
              const primarySource = sources[0] || movie;
              
              // Calculate actual file size dynamically
              const rawSizeBytes = movie.file_size_bytes || 
                primarySource.file_size_bytes || 
                (sources.length > 0 ? sources.reduce((sum, s) => sum + (s.file_size_bytes || 0), 0) : 0);

              const sizeLabel = isSeries 
                ? `${movie.totalSeasons || 1}S • ${movie.totalEpisodes || 1} Ep` 
                : (rawSizeBytes > 0 ? formatBytes(rawSizeBytes) : (primarySource.qualityLabel || '1080p HD'));

              const posterSrc = (movie.poster_url && movie.poster_url.trim().length > 5)
                ? movie.poster_url
                : generateDynamicSVGPoster(movie.title, isSeries ? 'TV SERIES' : 'MOVIE');

              return (
                <div
                  key={movie.master_id || movie.id || movie.slug}
                  onClick={() => {
                    onSelectMovie(movie);
                    onClose();
                  }}
                  className="flex items-center gap-3 p-2.5 rounded-xl bg-zinc-900/80 border border-white/[0.08] hover:border-red-500/40 hover:bg-zinc-800/90 transition cursor-pointer group shadow-sm"
                >
                  <div className="w-12 h-16 rounded-lg overflow-hidden bg-zinc-950 shrink-0 border border-white/[0.08]">
                    <img 
                      src={posterSrc} 
                      alt={movie.title} 
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = generateDynamicSVGPoster(movie.title, isSeries ? 'TV SERIES' : 'MOVIE');
                      }}
                    />
                  </div>
                  <div className="flex-1 min-w-0 pr-1">
                    <div className="flex items-center gap-1.5">
                      {isSeries && (
                        <span className="px-1 py-0.2 text-[8px] font-mono font-bold rounded bg-gradient-to-r from-red-600 to-rose-600 text-white uppercase">
                          Series
                        </span>
                      )}
                      <h4 className="font-bold text-xs sm:text-sm text-slate-100 line-clamp-1 group-hover:text-red-400 transition-colors">
                        {movie.title}
                      </h4>
                    </div>
                    <p className="text-[11px] text-slate-400 font-medium mt-0.5 truncate">
                      {movie.release_year || 2026} • {primarySource.language || 'Tamil Dubbed'}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-slate-400 font-medium">
                      <span className="text-emerald-400 flex items-center gap-1 font-mono font-semibold">
                        {isSeries ? <Tv className="w-3 h-3 text-red-400" /> : <HardDrive className="w-3 h-3 text-emerald-400" />}
                        {sizeLabel}
                      </span>
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-red-600/10 text-red-400 group-hover:bg-red-600 group-hover:text-white transition">
                    <Download className="w-3.5 h-3.5" />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

    </div>
  );
}

