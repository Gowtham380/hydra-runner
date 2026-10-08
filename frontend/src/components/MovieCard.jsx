import React from 'react';
import { Film, Star, Layers, Tv, Play, Download } from 'lucide-react';
import { formatBytes } from '../lib/api';
import { generateDynamicSVGPoster } from '../lib/grouping';

export default function MovieCard({ movie, onSelectMovie }) {
  if (!movie) return null;

  const isSeries = movie.type === 'series';
  const sources = movie.sources || [movie];
  const primarySource = sources[0] || movie;

  const has4k = sources.some(s => s.qualityCode === '4k' || (s.file_name || s.title || '').toLowerCase().includes('2160p'));
  
  const qualityBadge = isSeries 
    ? `WEB SERIES` 
    : (has4k ? '4K ULTRA HD' : (sources.length > 1 ? `${sources.length} QUALITIES` : (primarySource.qualityLabel || '1080p HD')));

  const languageTag = primarySource.language || 'Tamil';

  const posterSrc = (movie.poster_url && movie.poster_url.trim().length > 5)
    ? movie.poster_url
    : generateDynamicSVGPoster(movie.title, isSeries ? 'TV SERIES' : 'MOVIE');

  // Compute file size label
  const rawSizeBytes = movie.file_size_bytes || 
    primarySource.file_size_bytes || 
    (sources.length > 0 ? sources.reduce((sum, s) => sum + (s.file_size_bytes || 0), 0) : 0);

  const sizeLabel = isSeries 
    ? `${movie.totalEpisodes || 1} Ep` 
    : (rawSizeBytes > 0 ? formatBytes(rawSizeBytes) : (primarySource.qualityLabel || '1080p'));

  return (
    <div 
      onClick={() => onSelectMovie(movie)}
      className="group relative flex flex-col bg-zinc-900/80 rounded-2xl border border-zinc-800/80 overflow-hidden cursor-pointer transition-all duration-300 hover:border-red-500/50 hover:shadow-[0_12px_32px_rgba(239,68,68,0.15)] hover:-translate-y-1 active:scale-[0.98]"
    >
      {/* Poster Image Container */}
      <div className="relative aspect-[2/3] w-full overflow-hidden bg-zinc-950">
        <img 
          src={posterSrc} 
          alt={movie.title}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          onError={(e) => {
            e.target.onerror = null;
            e.target.src = generateDynamicSVGPoster(movie.title, isSeries ? 'TV SERIES' : 'MOVIE');
          }}
        />
        
        {/* Top Floating Badges */}
        <div className="absolute top-1.5 left-1.5 right-1.5 flex items-center justify-between pointer-events-none z-10">
          <span className={`px-1.5 py-0.5 text-[8.5px] sm:text-[9px] font-mono font-extrabold uppercase rounded-md backdrop-blur-md text-white shadow-md ${
            isSeries 
              ? 'bg-gradient-to-r from-red-600 to-rose-600 border border-red-400/40' 
              : (has4k ? 'bg-amber-500 text-black border border-amber-300/40 font-black' : 'bg-zinc-900/90 border border-zinc-700 text-zinc-200')
          }`}>
            {qualityBadge}
          </span>
          <span className="px-1.5 py-0.5 text-[9.5px] sm:text-[10px] font-bold rounded-md bg-zinc-950/90 backdrop-blur-md text-amber-300 shadow-md border border-zinc-800 flex items-center gap-1">
            <Star className="w-2.5 h-2.5 sm:w-3 sm:h-3 fill-amber-400 text-amber-400" />
            <span>{movie.rating || 8.5}</span>
          </span>
        </div>

        {/* Hover Quick Action Backdrop Overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-zinc-950/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-2.5 sm:p-3 z-20">
          <button className="w-full py-2 sm:py-2.5 px-2.5 sm:px-3 rounded-xl bg-gradient-to-r from-red-600 via-rose-600 to-red-500 text-white font-bold text-xs flex items-center justify-center space-x-1.5 shadow-lg shadow-red-600/30 border border-red-400/30">
            {isSeries ? <Tv className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 fill-white" />}
            <span>{isSeries ? 'View Seasons' : 'Stream & Download'}</span>
          </button>
        </div>
      </div>

      {/* Movie Metadata Footer */}
      <div className="p-2 sm:p-3 flex flex-col justify-between flex-1 space-y-1.5 sm:space-y-2 bg-zinc-900/60">
        <div>
          <h3 className="font-bold text-xs sm:text-sm text-zinc-100 line-clamp-1 group-hover:text-red-400 transition-colors tracking-tight">
            {movie.title}
          </h3>
          <p className="text-[10px] sm:text-[11px] text-zinc-400 mt-0.5 truncate font-medium">
            {movie.release_year || 2026} • {isSeries ? `${movie.totalSeasons || 1} Seasons` : languageTag}
          </p>
        </div>

        {/* Info Indicator */}
        <div className="pt-1.5 border-t border-zinc-800/80 flex items-center justify-between text-[10px] sm:text-[11px] font-semibold text-zinc-400">
          <span className="flex items-center gap-1 text-zinc-300 text-[9.5px] sm:text-[10px]">
            {isSeries ? <Tv className="w-3 h-3 text-red-500" /> : <Layers className="w-3 h-3 text-red-400" />}
            <span>{isSeries ? `${movie.totalEpisodes || 1} Ep` : `${sources.length} ${sources.length === 1 ? 'Variant' : 'Variants'}`}</span>
          </span>
          <span className="text-emerald-400 font-bold font-mono text-[10px] sm:text-[11px]">
            {sizeLabel}
          </span>
        </div>
      </div>

    </div>
  );
}
