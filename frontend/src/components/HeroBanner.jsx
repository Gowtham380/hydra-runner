import React from 'react';
import { Download, Info, Star, Calendar, Sparkles, Film, Layers, Play, Volume2, Shield } from 'lucide-react';
import { formatBytes } from '../lib/api';
import { generateDynamicSVGPoster } from '../lib/grouping';

export default function HeroBanner({ movie, onSelectMovie }) {
  if (!movie) return null;

  const isSeries = movie.type === 'series';
  const sources = movie.sources || [movie];
  const primarySource = sources[0] || movie;

  const bgImage = (movie.backdrop_url && movie.backdrop_url.trim().length > 5)
    ? movie.backdrop_url
    : ((movie.poster_url && movie.poster_url.trim().length > 5) ? movie.poster_url : generateDynamicSVGPoster(movie.title));

  const has4k = sources.some(s => s.qualityCode === '4k' || (s.file_name || s.title || '').toLowerCase().includes('2160p'));

  return (
    <div className="relative w-full overflow-hidden rounded-xl sm:rounded-3xl my-1 sm:my-4 border border-zinc-800/80 shadow-[0_20px_50px_rgba(0,0,0,0.8)] bg-zinc-950 group">
      
      {/* Background Banner Image with Vivid Visibility & Subtle Text Ambient Overlay */}
      <div className="relative h-[280px] sm:h-[460px] w-full overflow-hidden bg-zinc-950">
        <img
          src={bgImage}
          alt={movie.title}
          className="w-full h-full object-cover object-center filter brightness-105 contrast-[1.05] transition-transform duration-700 group-hover:scale-105"
          onError={(e) => {
            e.target.onerror = null;
            e.target.src = generateDynamicSVGPoster(movie.title);
          }}
        />

        {/* Crisp Ambient Vignette & Text Contrast Gradients */}
        <div className="absolute inset-0 bg-gradient-to-t from-[#08090d] via-[#08090d]/50 via-50% to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#08090d]/80 via-[#08090d]/30 via-40% to-transparent" />
      </div>

      {/* Featured Content Overlay */}
      <div className="absolute bottom-0 left-0 right-0 p-3 sm:p-8 flex flex-col justify-end text-white z-10">
        
        {/* Featured Badges */}
        <div className="flex items-center gap-1 sm:gap-2 mb-1 sm:mb-2 flex-wrap">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 sm:px-3 sm:py-1 rounded-md sm:rounded-lg text-[9px] sm:text-[11px] font-black uppercase tracking-wider bg-gradient-to-r from-red-600 via-rose-600 to-red-500 text-white shadow-md shadow-red-600/30 border border-red-400/30 font-mono">
            <Sparkles className="w-3 h-3 sm:w-3.5 sm:h-3.5 fill-current animate-pulse" />
            FEATURED CINEMA
          </span>
          {has4k && (
            <span className="px-1.5 py-0.5 sm:px-2.5 sm:py-1 rounded-md sm:rounded-lg text-[9px] sm:text-[11px] font-mono font-extrabold bg-amber-500/20 border border-amber-500/40 text-amber-300 backdrop-blur-md">
              4K ULTRA HD
            </span>
          )}
          <span className="px-1.5 py-0.5 sm:px-2.5 sm:py-1 rounded-md sm:rounded-lg text-[9px] sm:text-[11px] font-semibold bg-zinc-900/90 backdrop-blur-md border border-zinc-800 text-emerald-400 flex items-center gap-1">
            <Volume2 className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-emerald-400" />
            <span>Tamil Dubbed HQ</span>
          </span>
          <span className="px-1.5 py-0.5 sm:px-2.5 sm:py-1 rounded-md sm:rounded-lg text-[9px] sm:text-[11px] font-semibold bg-zinc-900/90 backdrop-blur-md border border-zinc-800 text-zinc-300 flex items-center gap-1">
            <Layers className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-red-400" />
            <span>{isSeries ? `${movie.totalSeasons || 1} Seasons` : `${sources.length} ${sources.length === 1 ? 'Variant' : 'Variants'}`}</span>
          </span>
        </div>

        {/* Movie Title */}
        <h1 className="text-xl sm:text-4xl font-black tracking-tight font-heading leading-tight drop-shadow-2xl text-white mb-1 sm:mb-2">
          {movie.title}
        </h1>

        {/* Movie Metadata */}
        <div className="flex items-center gap-1.5 sm:gap-3 my-1 sm:my-2 text-[10px] sm:text-sm font-semibold text-zinc-300 flex-wrap">
          <div className="flex items-center gap-1 text-amber-400 font-extrabold bg-zinc-900/90 px-1.5 py-0.5 sm:px-2.5 sm:py-1 rounded-md sm:rounded-lg backdrop-blur-md border border-zinc-800">
            <Star className="w-3 h-3 sm:w-3.5 sm:h-3.5 fill-amber-400 text-amber-400" />
            <span>{movie.rating || 8.8} IMDb</span>
          </div>
          <span className="text-zinc-600 font-mono">•</span>
          <div className="flex items-center gap-1 text-zinc-300 font-medium">
            <Calendar className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-red-500" />
            <span>{movie.release_year || 2026}</span>
          </div>
          <span className="text-zinc-600 font-mono">•</span>
          <span className="text-emerald-400 font-bold font-mono bg-zinc-900/90 px-1.5 py-0.5 sm:px-2.5 sm:py-1 rounded-md sm:rounded-lg border border-zinc-800">
            {isSeries ? `${movie.totalEpisodes || 1} Episodes` : formatBytes(primarySource.file_size_bytes || 285000000)}
          </span>
          <span className="text-zinc-600 font-mono hidden sm:inline">•</span>
          <div className="hidden sm:flex items-center gap-1 text-zinc-400 text-xs font-mono">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Fast Direct Server</span>
          </div>
        </div>

        {/* Description */}
        <p className="text-[10px] sm:text-sm text-zinc-300 line-clamp-2 max-w-2xl my-1 sm:my-2 font-medium leading-normal drop-shadow-sm">
          {movie.description || 'Stream instantly in high quality or download for offline viewing with full auto-resume support.'}
        </p>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 sm:gap-3 mt-1.5 sm:mt-3 flex-wrap">
          <button
            onClick={() => onSelectMovie(movie)}
            className="px-3 py-2 sm:px-5 sm:py-3 rounded-lg sm:rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-1.5 sm:gap-2 bg-gradient-to-r from-red-600 via-rose-600 to-red-500 hover:brightness-110 text-white shadow-lg shadow-red-600/30 border border-red-400/40 active:scale-95 transition-all cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 sm:w-4 sm:h-4 fill-white stroke-[2.5]" />
            <span>Stream Instantly</span>
          </button>

          <button
            onClick={() => onSelectMovie(movie)}
            className="px-3 py-2 sm:px-5 sm:py-3 rounded-lg sm:rounded-xl bg-zinc-900/90 hover:bg-zinc-800 text-zinc-200 hover:text-white font-bold text-xs sm:text-sm flex items-center justify-center gap-1.5 sm:gap-2 backdrop-blur-xl border border-zinc-800 hover:border-red-500/40 shadow-md active:scale-95 transition-all cursor-pointer group/btn"
          >
            <Download className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-red-500 group-hover/btn:scale-110 transition-transform" />
            <span>Download Now</span>
          </button>

          <button
            onClick={() => onSelectMovie(movie)}
            className="px-2.5 py-2 sm:px-4 sm:py-3 rounded-lg sm:rounded-xl bg-zinc-900/70 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 font-medium text-xs flex items-center justify-center gap-1 sm:gap-1.5 border border-zinc-800 transition-all cursor-pointer"
          >
            <Info className="w-3.5 h-3.5" />
            <span>Details</span>
          </button>
        </div>

      </div>
    </div>
  );
}
