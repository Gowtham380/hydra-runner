import React, { useRef } from 'react';
import MovieCard from './MovieCard';
import { Sparkles, ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';

export default function MovieRow({ 
  title, 
  movies, 
  onSelectMovie, 
  onViewAll, 
  icon: Icon = Sparkles,
  isGrid = false 
}) {
  const rowRef = useRef(null);

  if (!movies || movies.length === 0) return null;

  const scrollLeft = () => {
    if (rowRef.current) {
      rowRef.current.scrollBy({ left: -450, behavior: 'smooth' });
    }
  };

  const scrollRight = () => {
    if (rowRef.current) {
      rowRef.current.scrollBy({ left: 450, behavior: 'smooth' });
    }
  };

  return (
    <div className="my-3 sm:my-6 space-y-2 sm:space-y-3">
      {/* Row Header */}
      <div className="flex items-center justify-between px-1 sm:px-2">
        {/* Left Title & Icon & Count Badge */}
        <div className="flex items-center space-x-2 sm:space-x-3">
          <div className="p-1.5 sm:p-2 rounded-xl bg-red-600/10 border border-red-500/20 text-red-500">
            <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
          </div>
          <h2 className="text-base sm:text-xl font-black text-white font-heading tracking-tight flex items-center gap-2">
            <span>{title}</span>
            <span className="text-[10px] sm:text-xs font-mono font-bold text-zinc-400 bg-zinc-900/90 border border-zinc-800 px-2 py-0.5 rounded-full">
              {movies.length}
            </span>
          </h2>
        </div>

        {/* Right Controls: View All & Navigation Arrows */}
        <div className="flex items-center space-x-2">
          {onViewAll && (
            <button
              onClick={() => onViewAll(title)}
              className="group flex items-center space-x-1 text-xs font-extrabold text-red-400 hover:text-red-300 transition-colors px-2.5 py-1 rounded-lg hover:bg-red-500/10 border border-transparent hover:border-red-500/20"
            >
              <span>View All</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
            </button>
          )}

          {!isGrid && (
            <div className="hidden sm:flex items-center space-x-1 pl-1">
              <button
                onClick={scrollLeft}
                aria-label="Scroll left"
                className="p-1.5 rounded-lg bg-zinc-900/80 hover:bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-800/80 hover:border-zinc-700 transition-all cursor-pointer active:scale-95"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={scrollRight}
                aria-label="Scroll right"
                className="p-1.5 rounded-lg bg-zinc-900/80 hover:bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-800/80 hover:border-zinc-700 transition-all cursor-pointer active:scale-95"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Content Rendering: Grid vs Horizontal Carousel Slider */}
      {isGrid ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3.5 sm:gap-4.5 pt-1">
          {movies.map((movie) => (
            <MovieCard 
              key={movie.id || movie.master_id || movie.slug || movie.title} 
              movie={movie} 
              onSelectMovie={onSelectMovie} 
            />
          ))}
        </div>
      ) : (
        <div 
          ref={rowRef}
          className="flex overflow-x-auto gap-3 sm:gap-4 no-scrollbar scroll-smooth snap-x snap-mandatory py-1 px-1 scroll-touch"
        >
          {movies.map((movie) => (
            <div 
              key={movie.id || movie.master_id || movie.slug || movie.title}
              className="shrink-0 w-[140px] sm:w-[175px] md:w-[195px] lg:w-[210px] snap-start"
            >
              <MovieCard movie={movie} onSelectMovie={onSelectMovie} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
