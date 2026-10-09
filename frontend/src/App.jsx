import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import HeroBanner from './components/HeroBanner';
import MovieRow from './components/MovieRow';
import SearchOverlay from './components/SearchOverlay';
import PlayerGateway from './components/PlayerGateway';
import MovieDetailsPage from './components/MovieDetailsPage';
import SeriesDetailsPage from './components/SeriesDetailsPage';
import DownloadsPage from './components/DownloadsPage';
import VIPProfilePage from './components/VIPProfilePage';
import BottomNav from './components/BottomNav';
import DownloadHub from './components/DownloadHub';
import { supabase, MOCK_MOVIES, syncTelegramUser } from './lib/supabase';
import { groupMovies } from './lib/grouping';
import { initTelegramApp, getTelegramUserInfo } from './lib/telegram';
import { Sparkles, Flame, ShieldCheck, X } from 'lucide-react';

export default function App() {
  const [rawMovies, setRawMovies] = useState([]);
  const [groupedMovies, setGroupedMovies] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [showSearch, setShowSearch] = useState(false);
  const [currentView, setCurrentView] = useState('catalog'); // 'catalog', 'downloads', 'profile'
  const [activeCategory, setActiveCategory] = useState('All');
  const [loading, setLoading] = useState(true);

  const isPlayerGate = typeof window !== 'undefined' && window.location.pathname.startsWith('/player-gate');

  useEffect(() => {
    initTelegramApp();
    const user = getTelegramUserInfo();
    if (user) {
      syncTelegramUser(user);
    }
  }, []);

  // Fetch movies from Supabase and group them into Master Movies
  useEffect(() => {
    async function loadCatalog() {
      try {
        const { data, error } = await supabase
          .from('movies')
          .select('*')
          .order('created_at', { ascending: false });

        if (!error && data && data.length > 0) {
          setRawMovies(data);
          const groups = groupMovies(data);
          setGroupedMovies(groups);
        } else {
          console.warn('Supabase returned no data, using mock catalog:', error?.message);
          setRawMovies(MOCK_MOVIES);
          setGroupedMovies(groupMovies(MOCK_MOVIES));
        }
      } catch (err) {
        console.warn('Error loading catalog from Supabase, using mock catalog:', err);
        setRawMovies(MOCK_MOVIES);
        setGroupedMovies(groupMovies(MOCK_MOVIES));
      } finally {
        setLoading(false);
      }
    }
    loadCatalog();
  }, []);

  const handleOpenDownloads = () => {
    setSelectedGroup(null);
    setCurrentView('downloads');
    if (window.location.pathname !== '/downloads') {
      window.history.pushState({ view: 'downloads' }, '', '/downloads');
    }
  };

  const handleOpenProfile = () => {
    setSelectedGroup(null);
    setCurrentView('profile');
    if (window.location.pathname !== '/profile') {
      window.history.pushState({ view: 'profile' }, '', '/profile');
    }
  };

  // Sync URL dynamic routing (/movie/:slug, /downloads, /profile, /)
  useEffect(() => {
    const handleLocationChange = () => {
      const path = window.location.pathname;
      const searchParams = new URLSearchParams(window.location.search);
      const querySlug = searchParams.get('movie');

      if (path === '/downloads') {
        setSelectedGroup(null);
        setCurrentView('downloads');
        return;
      }

      if (path === '/profile') {
        setSelectedGroup(null);
        setCurrentView('profile');
        return;
      }

      if (path.startsWith('/movie/')) {
        const slug = path.replace('/movie/', '').trim();
        if (groupedMovies.length > 0) {
          const found = groupedMovies.find(g => g.slug === slug || g.master_id === slug);
          if (found) {
            setSelectedGroup(found);
            setCurrentView('catalog');
            return;
          }
        }
      } else if (querySlug && groupedMovies.length > 0) {
        const found = groupedMovies.find(g => g.slug === querySlug || g.master_id === querySlug);
        if (found) {
          setSelectedGroup(found);
          setCurrentView('catalog');
          return;
        }
      }

      if (path === '/' || path === '') {
        setSelectedGroup(null);
        setCurrentView('catalog');
      }
    };

    handleLocationChange();
    window.addEventListener('popstate', handleLocationChange);
    return () => window.removeEventListener('popstate', handleLocationChange);
  }, [groupedMovies]);

  const handleSelectMovie = (groupOrMovie) => {
    // If passed raw movie, find its group
    let targetGroup = groupOrMovie;
    if (!groupOrMovie.sources && !groupOrMovie.seasons) {
      targetGroup = groupedMovies.find(g => 
        (g.sources && g.sources.some(s => s.id === groupOrMovie.id)) || g.title === groupOrMovie.title
      ) || groupOrMovie;
    }

    setSelectedGroup(targetGroup);
    setCurrentView('catalog');
    const targetSlug = targetGroup.slug || targetGroup.master_id;
    if (window.location.pathname !== `/movie/${targetSlug}`) {
      window.history.pushState({ slug: targetSlug }, '', `/movie/${targetSlug}`);
    }
  };

  const handleBackToCatalog = () => {
    setSelectedGroup(null);
    setCurrentView('catalog');
    if (window.location.pathname !== '/') {
      window.history.pushState(null, '', '/');
    }
  };

  if (isPlayerGate) {
    return <PlayerGateway />;
  }

  const categories = ['All', 'Action Blockbusters', 'Dramatic Classics', 'Web Series', '4K Ultra HD', 'Tamil Audio', 'All Synced Library Files'];

  // Category Filtering Logic
  const actionMovies = groupedMovies.filter(group => {
    const genre = (group.genre || '').toLowerCase();
    const title = (group.title || '').toLowerCase();
    return genre.includes('action') || title.includes('avengers') || title.includes('captain') || title.includes('vikram') || title.includes('civil') || title.includes('war');
  });

  const dramaMovies = groupedMovies.filter(group => {
    const genre = (group.genre || '').toLowerCase();
    const title = (group.title || '').toLowerCase();
    return genre.includes('drama') || title.includes('until') || title.includes('mayaanadhi') || title.includes('resort') || title.includes('bombay') || title.includes('2+2') || title.includes('test') || title.includes('malena') || title.includes('thalaivan');
  });

  const webSeriesMovies = groupedMovies.filter(group => group.type === 'series');

  const ultraHDMovies = groupedMovies.filter(group =>
    group.sources ? group.sources.some(s => s.qualityCode === '4k' || (s.file_name || s.title || '').toLowerCase().includes('2160p')) : false
  );

  const tamilAudioMovies = groupedMovies.filter(group =>
    group.sources ? group.sources.some(s => (s.language || '').toLowerCase().includes('tamil')) : true
  );

  // Filter grouped movies by active category pill
  const filteredMovies = groupedMovies.filter(group => {
    if (activeCategory === 'All') return true;
    if (activeCategory === 'Action Blockbusters') return actionMovies.includes(group);
    if (activeCategory === 'Dramatic Classics') return dramaMovies.includes(group);
    if (activeCategory === 'Web Series') return group.type === 'series';
    if (activeCategory === '4K Ultra HD') return ultraHDMovies.includes(group);
    if (activeCategory === 'Tamil Audio') return tamilAudioMovies.includes(group);
    return true;
  });

  const featuredMovieGroup = groupedMovies[0] || null;

  // Render view body based on routing state
  const renderMainContent = () => {
    if (currentView === 'downloads') {
      return <DownloadsPage onBack={handleBackToCatalog} />;
    }

    if (currentView === 'profile') {
      return <VIPProfilePage onBack={handleBackToCatalog} />;
    }

    if (selectedGroup) {
      if (selectedGroup.type === 'series') {
        return (
          <SeriesDetailsPage
            series={selectedGroup}
            onBack={handleBackToCatalog}
            onOpenDownloads={handleOpenDownloads}
          />
        );
      }
      return (
        <MovieDetailsPage
          movieGroup={selectedGroup}
          onBack={handleBackToCatalog}
          onOpenDownloads={handleOpenDownloads}
        />
      );
    }

    // Default Catalog View
    return (
      <main className="flex-1 w-full px-2.5 sm:px-6 lg:px-8 pb-28 md:pb-12 space-y-3 sm:space-y-6">
        {/* Category Navigation Pills */}
        <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar py-1.5 my-0.5 sm:my-2 scroll-touch">
          {categories.map((cat) => {
            const active = activeCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => {
                  setActiveCategory(cat);
                  setCurrentView('catalog');
                  setSelectedGroup(null);
                }}
                className={`px-3 py-1.5 sm:px-4.5 sm:py-2 rounded-lg sm:rounded-xl text-[11px] sm:text-xs font-extrabold whitespace-nowrap transition-all duration-200 cursor-pointer border ${
                  active 
                    ? 'bg-gradient-to-r from-red-600 to-rose-600 text-white border-red-400/50 shadow-lg shadow-red-600/30' 
                    : 'bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 border-zinc-800 hover:text-white'
                }`}
              >
                {cat}
              </button>
            );
          })}
        </div>

        {/* Loading / Empty / Populated Content State */}
        {loading ? (
          <div className="py-24 text-center space-y-3">
            <div className="w-8 h-8 border-2 border-red-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs text-zinc-400">Loading catalog from Supabase...</p>
          </div>
        ) : groupedMovies.length === 0 ? (
          <div className="py-20 px-4 text-center glass-panel rounded-3xl border border-zinc-800 my-8 space-y-4 max-w-xl mx-auto">
            <div className="w-16 h-16 bg-red-600/10 text-red-500 rounded-2xl flex items-center justify-center mx-auto border border-red-500/20">
              <Sparkles className="w-8 h-8" />
            </div>
            <h3 className="text-xl font-bold text-white">No Movies In DB Yet</h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto leading-relaxed">
              Supabase database-il movies-um illai. Run your Google Drive ingestion engine to auto-populate movies!
            </p>
            <div className="pt-2 font-mono text-[11px] bg-zinc-950 p-3 rounded-xl text-red-400 inline-block border border-zinc-800">
              python ingester/auto_drive_watcher.py --once
            </div>
          </div>
        ) : activeCategory === 'All' ? (
          <>
            {/* Featured Hero Banner */}
            {featuredMovieGroup && (
              <HeroBanner 
                movie={featuredMovieGroup} 
                onSelectMovie={handleSelectMovie} 
              />
            )}

            {/* Category Wise Rows (Matching SMD PRIME UI) */}
            <MovieRow
              title="Action Blockbusters"
              movies={actionMovies.length > 0 ? actionMovies : groupedMovies.slice(0, 8)}
              onSelectMovie={handleSelectMovie}
              onViewAll={() => setActiveCategory('Action Blockbusters')}
              icon={Flame}
              isGrid={false}
            />

            <MovieRow
              title="Dramatic Classics"
              movies={dramaMovies.length > 0 ? dramaMovies : groupedMovies.slice(2, 10)}
              onSelectMovie={handleSelectMovie}
              onViewAll={() => setActiveCategory('Dramatic Classics')}
              icon={Sparkles}
              isGrid={false}
            />

            {webSeriesMovies.length > 0 && (
              <MovieRow
                title="Web Series & Shows"
                movies={webSeriesMovies}
                onSelectMovie={handleSelectMovie}
                onViewAll={() => setActiveCategory('Web Series')}
                icon={Flame}
                isGrid={false}
              />
            )}

            {ultraHDMovies.length > 0 && (
              <MovieRow
                title="4K Ultra HD Collection"
                movies={ultraHDMovies}
                onSelectMovie={handleSelectMovie}
                onViewAll={() => setActiveCategory('4K Ultra HD')}
                icon={Sparkles}
                isGrid={false}
              />
            )}

            <MovieRow
              title="All Synced Library Files"
              movies={groupedMovies}
              onSelectMovie={handleSelectMovie}
              onViewAll={() => setActiveCategory('All Synced Library Files')}
              icon={Flame}
              isGrid={false}
            />
          </>
        ) : (
          /* Filtered Category Grid View */
          <MovieRow
            title={`${activeCategory}`}
            movies={filteredMovies}
            onSelectMovie={handleSelectMovie}
            icon={Flame}
            isGrid={true}
          />
        )}
      </main>
    );
  };


  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans relative">
      
      {/* SMD PRIME Header Navbar */}
      <Header
        onOpenSearch={() => setShowSearch(true)}
        activeCategory={activeCategory}
        setActiveCategory={(cat) => {
          setActiveCategory(cat);
          handleBackToCatalog();
        }}
        onOpenProfile={handleOpenProfile}
        onOpenDownloads={handleOpenDownloads}
      />

      {/* Dynamic Main View */}
      {renderMainContent()}

      {/* Mobile Glassmorphic Bottom Dock Navigation - Always Persistent */}
      <BottomNav
        onOpenSearch={() => setShowSearch(true)}
        onOpenProfile={handleOpenProfile}
        onOpenDownloads={handleOpenDownloads}
        activeCategory={activeCategory}
        setActiveCategory={(cat) => {
          setActiveCategory(cat);
          handleBackToCatalog();
        }}
        onGoHome={handleBackToCatalog}
        currentView={currentView}
        hasSelectedGroup={!!selectedGroup}
      />

      {/* Live Search Modal Overlay */}
      {showSearch && (
        <SearchOverlay
          movies={groupedMovies}
          onClose={() => setShowSearch(false)}
          onSelectMovie={handleSelectMovie}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-zinc-800/80 bg-zinc-950 py-3 sm:py-4 text-center text-xs text-zinc-500 pb-16 md:pb-4">
        <div className="w-full px-4 sm:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-black text-white font-heading text-sm">SMD PRIME</span>
            <span className="text-red-500 font-semibold text-xs">CINEMA</span>
          </div>
          <p className="text-zinc-400 font-medium">Ultra HD Direct Cinema Platform © 2026</p>
          <div className="flex items-center gap-2 text-zinc-400 text-xs font-semibold">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Encrypted Direct Stream</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
