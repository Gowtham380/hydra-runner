import React, { useState, useEffect, useMemo } from 'react';
import { 
  ArrowLeft, Download, ExternalLink, Copy, Check, HardDrive, 
  RefreshCw, CheckCircle2, AlertCircle, Star, Calendar, Clock, 
  Film, ShieldCheck, Sparkles, Layers, Volume2, Zap, Play, Globe,
  CheckCircle, SlidersHorizontal, Info, PlayCircle, Cpu, Activity
} from 'lucide-react';
import { generateDownloadLink, formatBytes } from '../lib/api';
import { triggerSwMeshDownload } from '../utils/swStreamer';
import { startOrResumePersistentDownload } from '../utils/persistentDownloader';
import ExternalPlayerMenu from './ExternalPlayerMenu';
import AITaskCompanion from './AITaskCompanion';
import HorizontalTextRoller from './ui/horizontal-text-roller';
import { generateDynamicSVGPoster } from '../lib/grouping';
import { triggerHaptic } from '../lib/telegram';

export default function MovieDetailsPage({ movieGroup, onBack, onOpenDownloads }) {
  if (!movieGroup) return null;

  const sources = movieGroup.sources && movieGroup.sources.length > 0 
    ? movieGroup.sources 
    : [movieGroup];

  // Helper to extract numeric file size in bytes for sorting
  const getSourceByteSize = (src) => {
    if (typeof src.file_size_bytes === 'number' && src.file_size_bytes > 0) return src.file_size_bytes;
    if (typeof src.fileSize === 'number' && src.fileSize > 0) return src.fileSize;
    if (typeof src.file_size === 'number' && src.file_size > 0) return src.file_size;
    return 0;
  };

  // Helper to get language priority (Tamil = 1, others = 2)
  const getLangPriority = (langStr) => {
    const l = (langStr || '').toLowerCase().trim();
    if (l.includes('tamil')) return 1;
    return 2;
  };

  // Organize unique languages dynamically (Tamil prioritized first)
  const rawLanguages = useMemo(() => {
    const langs = new Set();
    sources.forEach(src => {
      if (src.language) {
        const parts = src.language.split(/[\+\,\&]/);
        parts.forEach(p => {
          const cleaned = p.trim();
          if (cleaned) langs.add(cleaned);
        });
      }
    });
    return Array.from(langs).sort((a, b) => {
      const pA = getLangPriority(a);
      const pB = getLangPriority(b);
      if (pA !== pB) return pA - pB;
      return a.localeCompare(b);
    });
  }, [sources]);

  const availableLanguages = useMemo(() => {
    return rawLanguages.length > 1 ? ['ALL', ...rawLanguages] : rawLanguages;
  }, [rawLanguages]);

  const [activeLangTab, setActiveLangTab] = useState('ALL');

  // Filter sources based on active language tab, sorted by:
  // 1. Language priority (Tamil first)
  // 2. Language group
  // 3. File size descending (largest to smallest)
  const filteredSources = useMemo(() => {
    const filtered = sources.filter(src => {
      if (rawLanguages.length <= 1 || activeLangTab === 'ALL') return true;
      const srcLang = (src.language || '').toLowerCase().trim();
      const targetLang = (activeLangTab || 'ALL').toLowerCase().trim();
      return srcLang === targetLang || srcLang.includes(targetLang);
    });

    return [...filtered].sort((a, b) => {
      // 1. Tamil priority first
      const pA = getLangPriority(a.language);
      const pB = getLangPriority(b.language);
      if (pA !== pB) return pA - pB;

      // 2. Group same languages together
      const langA = (a.language || '').toLowerCase().trim();
      const langB = (b.language || '').toLowerCase().trim();
      if (langA !== langB) return langA.localeCompare(langB);

      // 3. File size descending
      const sizeA = getSourceByteSize(a);
      const sizeB = getSourceByteSize(b);
      return sizeB - sizeA;
    });
  }, [sources, activeLangTab, rawLanguages.length]);

  const [selectedSourceIndex, setSelectedSourceIndex] = useState(0);
  
  // Ensure selected source index points to a valid filtered source or falls back to first
  const currentSource = filteredSources[selectedSourceIndex] || filteredSources[0] || sources[0];

  const [loading, setLoading] = useState(true);
  const [linkData, setLinkData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  // Download Feedback State
  const [downloadStarted, setDownloadStarted] = useState(false);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [movieGroup]);

  // Reset selected source index when filter changes
  useEffect(() => {
    setSelectedSourceIndex(0);
  }, [activeLangTab]);

  useEffect(() => {
    if (!currentSource) return;

    let isMounted = true;
    setLoading(true);
    setError(null);
    setDownloadStarted(false);

    generateDownloadLink(currentSource.id)
      .then(data => {
        if (isMounted) {
          setLinkData(data);
          setLoading(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          setError(err.message || 'Failed to generate download stream.');
          setLoading(false);
        }
      });

    return () => { isMounted = false; };
  }, [currentSource]);

  const handleCopyLink = () => {
    if (linkData?.download_url) {
      navigator.clipboard.writeText(linkData.download_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleNativeSwDownload = async () => {
    if (!currentSource) return;
    try {
      setError(null);
      const directUrl = linkData?.download_url || currentSource.download_url || currentSource.stream_url || currentSource.url;
      const urls = (currentSource.chunk_urls && currentSource.chunk_urls.length > 0)
        ? currentSource.chunk_urls
        : (currentSource.urls && currentSource.urls.length > 0)
          ? currentSource.urls
          : (directUrl ? [directUrl] : null);

      const payload = {
        id: currentSource.id,
        title: movieGroup.title,
        file_name: currentSource.file_name || `${movieGroup.title || 'Movie'} [${currentSource.qualityCode || '1080p'}].mp4`,
        slug: movieGroup.slug || 'movie',
        file_size_bytes: currentSource.file_size_bytes || 2684354560,
        mime_type: currentSource.mime_type || 'video/mp4',
        download_url: directUrl,
        chunk_urls: urls || []
      };

      await triggerSwMeshDownload(payload, urls || []);
    } catch (err) {
      console.error('Download Error:', err);
      setError('Native download failed. Switching to high speed downloader.');
      handleStartParallelDownload();
    }
  };

  const handleStartParallelDownload = async () => {
    if (!currentSource) return;

    triggerHaptic('impact', 'medium');

    // Instant redirect (0 Latency UI response)
    if (onOpenDownloads) {
      onOpenDownloads();
    }

    let urls = (currentSource.chunk_urls && currentSource.chunk_urls.length > 0)
      ? currentSource.chunk_urls 
      : (currentSource.stream_url || currentSource.download_url || currentSource.drive_url || currentSource.url)
        ? [currentSource.stream_url || currentSource.download_url || currentSource.drive_url || currentSource.url]
        : (linkData?.download_url ? [linkData.download_url] : []);

    const downloadId = `${movieGroup.slug || 'movie'}-${currentSource.id || currentSource.qualityCode}-${currentSource.language || 'audio'}`;
    const fileName = currentSource.file_name || `${movieGroup.title || 'Movie'} [${currentSource.qualityCode || '1080p'}].mp4`;

    const movieObj = {
      id: downloadId,
      title: movieGroup.title,
      file_name: fileName,
      slug: movieGroup.slug,
      file_size_bytes: currentSource.file_size_bytes || 285000000,
      mime_type: currentSource.mime_type || 'video/mp4',
      poster_url: movieGroup.poster_url,
      backdrop_url: movieGroup.backdrop_url,
      qualityCode: currentSource.qualityCode || '1080p',
      language: currentSource.language || 'Tamil',
      chunk_urls: urls,
      stream_url: currentSource.stream_url,
      download_url: currentSource.download_url,
      drive_url: currentSource.drive_url
    };

    if (urls.length === 0) {
      try {
        const data = await generateDownloadLink(currentSource.id);
        if (data?.download_url) {
          urls = [data.download_url];
          movieObj.chunk_urls = urls;
        }
      } catch (err) {
        console.error('Failed to generate link:', err);
      }
    }

    // Always initiate persistent download engine with auto fallback inside persistentDownloader
    startOrResumePersistentDownload(movieObj, urls).catch(err => {
      console.error('Persistent Mesh Download Error:', err);
    });
  };

  const posterSrc = (movieGroup.poster_url && movieGroup.poster_url.trim().length > 5)
    ? movieGroup.poster_url
    : generateDynamicSVGPoster(movieGroup.title);

  const backdropSrc = (movieGroup.backdrop_url && movieGroup.backdrop_url.trim().length > 5)
    ? movieGroup.backdrop_url
    : posterSrc;

  // Extract all unique languages string for hero tag
  const allLangsFormatted = availableLanguages.filter(l => l !== 'ALL').join(' • ') || 'Tamil • Multi Audio';

  return (
    <div className="w-full flex-1 bg-[#070A0F] text-zinc-100 flex flex-col font-sans relative overflow-x-hidden animate-fadeIn selection:bg-red-500 selection:text-white pb-4 sm:pb-6">
      
      {/* Top Navigation Header */}
      <nav aria-label="Navigation" className="relative z-20 bg-[#070A0F]/90 backdrop-blur-2xl border-b border-zinc-800/80 px-3 sm:px-8 py-2.5 sm:py-3.5 flex items-center justify-between">
        <div className="flex items-center text-xs sm:text-sm font-semibold text-zinc-400">
          <button
            onClick={onBack}
            className="flex items-center space-x-2 text-zinc-300 hover:text-red-400 transition cursor-pointer bg-zinc-900 hover:bg-zinc-800 px-3.5 py-1.5 rounded-xl border border-zinc-800 shadow-sm active:scale-95 focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none"
            aria-label="Back to Catalog"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Catalog</span>
          </button>
        </div>

        <div className="flex items-center space-x-2">
          <span className="px-3 py-1 text-[11px] font-mono font-bold tracking-wide rounded-xl bg-gradient-to-r from-red-600/20 via-rose-600/20 to-red-600/20 text-red-400 border border-red-500/30 uppercase flex items-center gap-1.5 shadow-sm">
            <Film className="w-3.5 h-3.5 text-red-400" />
            <span>SMD BENTO 2026</span>
          </span>
        </div>
      </nav>

      {/* Bento Grid Header & Hero Section */}
      <div className="relative w-full overflow-hidden border-b border-zinc-800/80 bg-[#070A0F]">
        
        {/* Dynamic Multi-Stage Ambient Gradient Vignette */}
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          <img
            src={backdropSrc}
            alt=""
            className="w-full h-full object-cover filter blur-xl opacity-20 scale-110"
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = generateDynamicSVGPoster(movieGroup.title);
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#070A0F] via-[#070A0F]/50 to-transparent" />
          <div className="absolute inset-0 bg-radial-at-c from-transparent via-[#070A0F]/30 to-[#070A0F]" />
        </div>

        {/* Hero Bento Box Content */}
        <div className="relative z-10 w-full px-4 sm:px-8 py-4 sm:py-6 max-w-7xl mx-auto">
          
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4 sm:gap-6 items-center">
            
            {/* Poster Bento Box (Span 5) - Landscape Poster */}
            <div className="md:col-span-5 flex justify-center md:justify-start">
              <div className="relative w-full max-w-sm sm:max-w-md aspect-video rounded-3xl overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.9)] border border-zinc-700/80 bg-zinc-900 group hover:border-red-500/50 transition-all duration-300">
                <img
                  src={backdropSrc}
                  alt={movieGroup.title}
                  className="w-full h-full object-cover transition duration-500 group-hover:scale-105"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = posterSrc;
                  }}
                />
                <div className="absolute top-3 right-3 bg-zinc-950/90 backdrop-blur-md text-red-400 font-mono font-bold text-[10px] px-3 py-1 rounded-xl border border-red-500/30 uppercase shadow-lg">
                  {sources.length} {sources.length === 1 ? 'FILE' : 'VARIANTS'}
                </div>
              </div>
            </div>

            {/* Title & Overview Bento Box (Span 7) */}
            <div className="md:col-span-7 space-y-2.5 sm:space-y-3.5 text-center md:text-left">
              
              {/* Meta Badges Strip */}
              <div className="flex items-center justify-center md:justify-start gap-2 flex-wrap text-xs font-semibold">
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-amber-500/10 text-amber-300 border border-amber-500/30 font-mono">
                  <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  <span>{movieGroup.rating || 8.5} IMDb</span>
                </span>
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-zinc-900/90 text-zinc-300 border border-zinc-800 font-mono">
                  <Calendar className="w-3.5 h-3.5 text-zinc-400" />
                  <span>{movieGroup.release_year || 2026}</span>
                </span>
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-zinc-900/90 text-zinc-300 border border-zinc-800 font-mono">
                  <Clock className="w-3.5 h-3.5 text-zinc-400" />
                  <span>{movieGroup.duration || '2h 15m'}</span>
                </span>
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-red-600/15 text-red-400 border border-red-500/30 font-mono">
                  <Volume2 className="w-3.5 h-3.5" />
                  <span>{allLangsFormatted}</span>
                </span>
              </div>

              {/* Title */}
              <h1 className="text-2xl sm:text-4xl md:text-5xl font-black text-white tracking-tight leading-tight">
                {movieGroup.title}
              </h1>

            </div>

          </div>

        </div>

      </div>

      {/* Main Interactive Workstation (1-Column Ambient Architecture) */}
      <main className="flex-1 w-full px-3 sm:px-6 pt-3 pb-2 sm:pt-4 sm:pb-3 max-w-4xl mx-auto space-y-4 sm:space-y-5">
        
        {/* Status / Download Notification Banner */}
        {error && (
          <div role="alert" className="p-4 bg-red-500/10 border border-red-500/30 rounded-2xl text-red-400 text-xs flex items-center gap-3 shadow-lg">
            <AlertCircle className="w-5 h-5 shrink-0 text-red-400" />
            <span className="font-medium">{error}</span>
          </div>
        )}

        {downloadStarted && (
          <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl text-emerald-300 text-xs flex items-center justify-between font-bold shadow-lg animate-in fade-in duration-300">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <span>Download added to Chrome Downloads Manager! (Background execution ready)</span>
            </div>
            <span className="text-[10px] font-mono text-emerald-400 uppercase bg-emerald-950/80 px-2 py-1 rounded border border-emerald-500/20">
              Auto-Healer Active
            </span>
          </div>
        )}

        {/* Audio Track Switcher - Only visible if more than 1 language exists */}
        {rawLanguages.length > 1 && (
          <div className="bg-zinc-950/80 backdrop-blur-2xl p-3 sm:p-4 rounded-3xl border border-zinc-800/80 space-y-2.5 sm:space-y-3 shadow-xl">
            <div className="flex items-center justify-between px-2">
              <span className="text-xs font-extrabold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                <Globe className="w-4 h-4 text-red-500 animate-pulse" />
                <span>AUDIO TRACK</span>
              </span>
              <span className="text-[11px] font-mono text-zinc-400 bg-zinc-900/90 px-2.5 py-1 rounded-full border border-zinc-800">
                {filteredSources.length} / {sources.length} items
              </span>
            </div>

            <HorizontalTextRoller
              items={availableLanguages.map(l => l === 'ALL' ? 'ALL' : l.toUpperCase())}
              selectedIndex={Math.max(0, availableLanguages.findIndex(l => l.toLowerCase() === activeLangTab.toLowerCase()))}
              onSelect={(item, index) => {
                const selectedLang = availableLanguages[index] || 'ALL';
                setActiveLangTab(selectedLang);
              }}
            />
          </div>
        )}

        {/* Filtered File Variants List with Direct Download Triggers */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-zinc-400 px-1">
            <span>AVAILABLE DOWNLOAD OPTIONS</span>
            <span className="font-mono">{filteredSources.length} ITEMS</span>
          </div>

          {filteredSources.length === 0 ? (
            <div className="p-6 text-center bg-zinc-900/60 border border-zinc-800 rounded-3xl text-zinc-400 text-xs">
              No files matching language <strong className="text-red-400">{activeLangTab}</strong>.
            </div>
          ) : (
            filteredSources.map((src, idx) => {
              const active = activeLangTab !== 'ALL' && currentSource && currentSource.id === src.id;
              return (
                <div
                  key={src.id || idx}
                  onClick={() => setSelectedSourceIndex(idx)}
                  tabIndex={0}
                  role="button"
                  aria-pressed={active}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      setSelectedSourceIndex(idx);
                    }
                  }}
                  className={`p-2.5 sm:p-3.5 rounded-2xl border transition-all cursor-pointer grid grid-cols-[105px_1fr_115px] items-center gap-1.5 sm:gap-3 group focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
                    active 
                      ? 'bg-zinc-900 border-l-4 border-l-red-500 border-t-zinc-800 border-r-zinc-800 border-b-zinc-800 shadow-xl shadow-red-600/10 scale-[1.01]' 
                      : 'bg-zinc-900/60 border-zinc-800/80 hover:border-zinc-700 hover:bg-zinc-900'
                  }`}
                >
                  {/* Left Zone: Quality & Source Badge (Strict Fixed 105px Column) */}
                  <div className="w-[105px] shrink-0 flex items-center justify-start">
                    {src.isTheaterPrint || src.qualityCode === 'PreDVD' || src.ripType === 'PreDVD' || src.ripType === 'CAM/TS' ? (
                      <span className="w-full text-center px-1 py-1.5 rounded-xl font-mono font-black text-[9px] sm:text-[10px] uppercase tracking-tight border bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-md shadow-amber-500/10 truncate flex items-center justify-center gap-0.5" title={`${src.ripType || 'PreDVD'} Print (${src.qualityCode || '720p'})`}>
                        <span>⚠️ PRE-DVD • {(src.qualityCode && src.qualityCode !== 'PreDVD') ? src.qualityCode.toUpperCase() : '720P'}</span>
                      </span>
                    ) : (
                      <span className={`w-full text-center px-2 py-1.5 rounded-xl font-mono font-black text-[10px] sm:text-xs uppercase tracking-tight border truncate ${
                        active 
                          ? 'bg-red-600 text-white border-red-500 shadow-md shadow-red-600/30' 
                          : 'bg-zinc-950 text-emerald-400 border-zinc-800'
                      }`}>
                        {src.qualityLabel || src.qualityCode?.toUpperCase() || '1080P'}
                      </span>
                    )}
                  </div>

                  {/* Center Zone: Audio Language (Strict Centered Column) */}
                  <div className="flex justify-center items-center px-1">
                    <span className="max-w-[140px] w-auto text-center text-[10px] sm:text-xs font-extrabold text-amber-300 bg-amber-500/10 px-2 py-1 rounded-lg border border-amber-500/20 uppercase tracking-wide truncate flex justify-center items-center">
                      {src.language?.toUpperCase() || 'TAMIL'}
                    </span>
                  </div>

                  {/* Right Zone: Size & Download Button (Strict Fixed 115px Column) */}
                  <div className="w-[115px] shrink-0 flex items-center justify-end gap-2">
                    <span className="w-[58px] text-right text-xs sm:text-sm font-black text-emerald-400 font-mono shrink-0">
                      {formatBytes(src.file_size_bytes || 285000000)}
                    </span>

                    {/* Direct File-Level Download Action Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedSourceIndex(idx);
                        handleStartParallelDownload();
                      }}
                      className="w-8 h-8 sm:w-auto sm:px-3.5 sm:py-2 rounded-xl bg-gradient-to-r from-red-600 via-rose-600 to-red-500 hover:brightness-110 text-white font-extrabold flex items-center justify-center gap-1.5 transition active:scale-95 shadow-md shadow-red-600/30 cursor-pointer text-xs shrink-0"
                      title="Start Direct Download"
                      aria-label={`Download ${src.qualityCode || 'Movie'} file`}
                    >
                      <Download className="w-3.5 h-3.5 text-white" />
                      <span className="hidden sm:inline">Download</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Ambient AI Task Companion */}
        <AITaskCompanion />

      </main>

    </div>
  );
}
