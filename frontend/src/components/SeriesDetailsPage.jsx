import React, { useState, useEffect } from 'react';
import { 
  ArrowLeft, Download, ExternalLink, Copy, Check, Tv, 
  RefreshCw, CheckCircle2, AlertCircle, Star, Calendar, 
  Play, ShieldCheck, Sparkles, Layers, Volume2, Film, Zap,
  Globe, SlidersHorizontal, Info, PlayCircle
} from 'lucide-react';
import { generateDownloadLink, formatBytes } from '../lib/api';
import { startOrResumePersistentDownload } from '../utils/persistentDownloader';
import { triggerSwMeshDownload } from '../utils/swStreamer';
import ExternalPlayerMenu from './ExternalPlayerMenu';
import AITaskCompanion from './AITaskCompanion';
import { generateDynamicSVGPoster } from '../lib/grouping';
import { triggerHaptic } from '../lib/telegram';

export default function SeriesDetailsPage({ series, onBack, onOpenDownloads }) {
  if (!series) return null;

  const seasonNumbers = series.seasonNumbers || [1];
  const initialSeason = (seasonNumbers.length > 0 && seasonNumbers[0] !== undefined) ? seasonNumbers[0] : 1;
  const [activeSeason, setActiveSeason] = useState(initialSeason);

  // Episodes for active season
  const currentSeasonEpisodesMap = (series.seasons && series.seasons[activeSeason]) || {};
  const episodeNumbers = Object.keys(currentSeasonEpisodesMap).map(Number).sort((a, b) => a - b);

  // Active selected episode number & active selected quality index per episode
  const initialEp = (episodeNumbers.length > 0 && episodeNumbers[0] !== undefined) ? episodeNumbers[0] : 1;
  const [selectedEpisodeNum, setSelectedEpisodeNum] = useState(initialEp);
  const [selectedQualityIndex, setSelectedQualityIndex] = useState(0);

  // Download & Stream State for Active Episode
  const currentEpisodeObj = currentSeasonEpisodesMap[selectedEpisodeNum] || (episodeNumbers.length > 0 ? currentSeasonEpisodesMap[episodeNumbers[0]] : null);
  const sources = currentEpisodeObj?.sources || [];
  const currentSource = sources[selectedQualityIndex] || sources[0] || null;

  const [loading, setLoading] = useState(false);
  const [linkData, setLinkData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [seasonCopied, setSeasonCopied] = useState(false);
  const [error, setError] = useState(null);

  // Download Hub Feedback state
  const [downloadStarted, setDownloadStarted] = useState(false);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [series]);

  // Reset selected episode when season changes
  useEffect(() => {
    if (episodeNumbers.length > 0) {
      setSelectedEpisodeNum(episodeNumbers[0]);
      setSelectedQualityIndex(0);
    }
  }, [activeSeason]);

  // Generate stream link when selected source changes
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
          setError(err.message || 'Failed to generate edge download stream.');
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

  const handleCopySeasonLinks = () => {
    const urls = [];
    episodeNumbers.forEach(eNum => {
      const ep = currentSeasonEpisodesMap[eNum];
      if (ep && ep.sources && ep.sources.length > 0) {
        const src = ep.sources[0];
        if (src.hf_raw_url) urls.push(src.hf_raw_url);
      }
    });

    if (urls.length > 0) {
      navigator.clipboard.writeText(urls.join('\n'));
      setSeasonCopied(true);
      setTimeout(() => setSeasonCopied(false), 2500);
    }
  };

  const handleNativeSwDownload = async () => {
    if (!currentSource) return;
    try {
      setError(null);
      await triggerSwMeshDownload(currentSource);
    } catch (err) {
      console.error('SW Download Error:', err);
      setError('Native stream download failed. Switching to FSD Persistent Mesh Downloader.');
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

    const downloadId = `${series.slug || 'series'}-S${activeSeason}E${selectedEpisodeNum}-${currentSource.qualityCode || '1080p'}`;
    const fileName = currentSource.file_name || `${series.title || 'Series'} S${activeSeason}E${selectedEpisodeNum}.mp4`;

    const seriesObj = {
      id: downloadId,
      title: `${series.title} S${activeSeason}E${selectedEpisodeNum}`,
      file_name: fileName,
      slug: series.slug,
      file_size_bytes: currentSource.file_size_bytes || 285000000,
      mime_type: currentSource.mime_type || 'video/mp4',
      poster_url: series.poster_url,
      backdrop_url: series.backdrop_url,
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
          seriesObj.chunk_urls = urls;
        }
      } catch (err) {
        console.error('Failed to generate link:', err);
      }
    }

    startOrResumePersistentDownload(seriesObj, urls).catch(err => {
      console.error('Persistent Mesh Download Error:', err);
    });
  };

  const fallbackSvg = generateDynamicSVGPoster(series.title, 'TV SERIES');
  const posterSrc = (series.poster_url && series.poster_url.trim().length > 5 && !series.poster_url.includes('undefined'))
    ? series.poster_url
    : fallbackSvg;

  const backdropSrc = (series.backdrop_url && series.backdrop_url.trim().length > 5 && !series.backdrop_url.includes('undefined'))
    ? series.backdrop_url
    : posterSrc;

  return (
    <div className="w-full flex-1 bg-[#070A0F] text-zinc-100 flex flex-col font-sans relative overflow-x-hidden animate-fadeIn selection:bg-red-500 selection:text-white pb-4 sm:pb-6">
      
      {/* Top Breadcrumb Navigation Header */}
      <nav aria-label="Breadcrumb" className="relative z-20 bg-[#070A0F]/90 backdrop-blur-2xl border-b border-zinc-800/80 px-3 sm:px-8 py-2.5 sm:py-3.5 flex items-center justify-between">
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
            <Tv className="w-3.5 h-3.5 text-red-400" />
            <span>SERIES BENTO 2026</span>
          </span>
        </div>
      </nav>

      {/* Hero Bento Header */}
      <div className="relative w-full overflow-hidden border-b border-zinc-800/80 bg-[#070A0F]">
        
        {/* Dynamic Multi-Stage Ambient Vignette */}
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          <img
            src={backdropSrc}
            alt=""
            className="w-full h-full object-cover filter blur-xl opacity-20 scale-110"
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = fallbackSvg;
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#070A0F] via-[#070A0F]/90 to-transparent" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-red-900/15 via-[#070A0F]/60 to-[#070A0F]" />
        </div>

        {/* Hero Bento Box Content */}
        <div className="relative z-10 w-full px-4 sm:px-8 py-4 sm:py-6 max-w-7xl mx-auto">
          
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4 sm:gap-6 items-center">
            
            {/* Poster Bento Box (Span 5) - Landscape Orientation */}
            <div className="md:col-span-5 flex justify-center md:justify-start">
              <div className="relative w-full max-w-sm sm:max-w-md aspect-video rounded-3xl overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.9)] border border-zinc-700/80 bg-zinc-900 group hover:border-red-500/50 transition-all duration-300">
                <img
                  src={backdropSrc}
                  alt={series.title}
                  className="w-full h-full object-cover transition duration-500 group-hover:scale-105"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = fallbackSvg;
                  }}
                />
                <div className="absolute top-3 right-3 bg-zinc-950/90 backdrop-blur-md text-red-400 font-mono font-bold text-[10px] px-3 py-1 rounded-xl border border-red-500/30 uppercase shadow-lg">
                  {series.totalSeasons} {series.totalSeasons === 1 ? 'SEASON' : 'SEASONS'}
                </div>
              </div>
            </div>

            {/* Title & Overview Bento Box (Span 7) */}
            <div className="md:col-span-7 space-y-2.5 sm:space-y-3.5 text-center md:text-left">
              
              {/* Meta Badges Strip */}
              <div className="flex items-center justify-center md:justify-start gap-2 flex-wrap text-xs font-semibold">
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-amber-500/10 text-amber-300 border border-amber-500/30 font-mono">
                  <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  <span>{series.rating || 8.9} IMDb</span>
                </span>
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-zinc-900/90 text-zinc-300 border border-zinc-800 font-mono">
                  <Calendar className="w-3.5 h-3.5 text-zinc-400" />
                  <span>{series.release_year || 2026}</span>
                </span>
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-zinc-900/90 text-zinc-300 border border-zinc-800 font-mono">
                  <Layers className="w-3.5 h-3.5 text-red-400" />
                  <span>{series.totalEpisodes} Episodes</span>
                </span>
                <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-red-600/15 text-red-400 border border-red-500/30 font-mono">
                  <Volume2 className="w-3.5 h-3.5" />
                  <span>Multi-Audio HD</span>
                </span>
              </div>

              {/* Title */}
              <h1 className="text-2xl sm:text-4xl md:text-5xl font-black text-white tracking-tight leading-tight">
                {series.title}
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
              <span>S{activeSeason} Ep {selectedEpisodeNum} download added to Chrome Downloads Manager!</span>
            </div>
            <span className="text-[10px] font-mono text-emerald-400 uppercase bg-emerald-950/80 px-2 py-1 rounded border border-emerald-500/20">
              Auto-Healer Active
            </span>
          </div>
        )}

        {/* Season Selector & Batch Download Header */}
        <div className="bg-zinc-900/60 backdrop-blur-xl p-5 rounded-3xl border border-zinc-800/80 space-y-4 shadow-lg">
          <div className="flex items-center justify-between">
            <span className="text-xs font-extrabold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
              <Film className="w-4 h-4 text-red-400" />
              <span>Select Season</span>
            </span>
            <span className="text-[11px] font-mono text-zinc-400">
              {seasonNumbers.length} Season{seasonNumbers.length > 1 ? 's' : ''} Available
            </span>
          </div>

          <div className="flex items-center justify-between gap-3 flex-wrap">
            {/* Season Pills */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
              {seasonNumbers.map((sNum) => {
                const active = sNum === activeSeason;
                const epCount = Object.keys((series.seasons && series.seasons[sNum]) || {}).length;
                return (
                  <button
                    key={sNum}
                    onClick={() => setActiveSeason(sNum)}
                    className={`px-4 py-2 rounded-xl text-xs font-extrabold flex items-center gap-2 shrink-0 transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
                      active 
                        ? 'bg-gradient-to-r from-red-600 via-rose-600 to-red-500 text-white shadow-md border border-red-400/40 scale-[1.01]' 
                        : 'bg-zinc-950 hover:bg-zinc-800 text-zinc-300 border border-zinc-800'
                    }`}
                    aria-label={`Select Season ${sNum}`}
                  >
                    <span>Season {sNum}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                      active ? 'bg-black/40 text-amber-300' : 'bg-zinc-800 text-zinc-400'
                    }`}>
                      {epCount} Ep
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Batch Season Download Button */}
            <button
              onClick={() => {
                // Trigger download for first episode in season
                if (episodeNumbers.length > 0) {
                  setSelectedEpisodeNum(episodeNumbers[0]);
                  setSelectedQualityIndex(0);
                  handleStartParallelDownload();
                }
              }}
              className="px-4 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-400 text-xs font-extrabold flex items-center gap-2 transition cursor-pointer shrink-0"
              title="Download all episodes in this season"
            >
              <Zap className="w-3.5 h-3.5 text-emerald-400 fill-emerald-400" />
              <span>Download Season {activeSeason}</span>
            </button>
          </div>
        </div>

        {/* 1-Column Episode Directory */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-bold text-zinc-400 px-1">
            <span>SEASON {activeSeason} EPISODES</span>
            <span className="font-mono">{episodeNumbers.length} EPISODES AVAILABLE</span>
          </div>

          <div className="space-y-3">
            {episodeNumbers.map((eNum) => {
              const ep = currentSeasonEpisodesMap[eNum];
              const isSelected = eNum === selectedEpisodeNum;
              const epSources = ep?.sources || [];
              const firstSource = epSources[0];

              return (
                <div
                  key={eNum}
                  onClick={() => {
                    setSelectedEpisodeNum(eNum);
                    setSelectedQualityIndex(0);
                  }}
                  tabIndex={0}
                  role="button"
                  aria-pressed={isSelected}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      setSelectedEpisodeNum(eNum);
                      setSelectedQualityIndex(0);
                    }
                  }}
                  className={`p-3 sm:p-4 rounded-2xl border transition-all cursor-pointer grid grid-cols-[105px_1fr_115px] items-center gap-1.5 sm:gap-3 group focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none ${
                    isSelected
                      ? 'bg-zinc-900 border-l-4 border-l-red-500 border-t-zinc-800 border-r-zinc-800 border-b-zinc-800 shadow-xl shadow-red-600/10 scale-[1.01]'
                      : 'bg-zinc-900/60 border-zinc-800/80 hover:border-zinc-700 hover:bg-zinc-900'
                  }`}
                >
                  {/* Left Zone: Episode Tag & Quality Stack (Strict Fixed 105px Column) */}
                  <div className="w-[105px] shrink-0 flex items-center justify-start">
                    <div className={`w-14 h-12 rounded-xl flex flex-col items-center justify-center font-mono font-black shrink-0 ${
                      isSelected ? 'bg-red-600 text-white shadow-md shadow-red-600/30' : 'bg-zinc-950 text-zinc-300 border border-zinc-800'
                    }`}>
                      <span className="text-[11px] leading-none">EP {eNum < 10 ? `0${eNum}` : eNum}</span>
                      <span className="text-[9px] font-bold text-amber-300 uppercase mt-1 leading-none tracking-tight">
                        {firstSource?.qualityCode?.toUpperCase() || '1080P'}
                      </span>
                    </div>
                  </div>

                  {/* Center Zone: Audio Language (Strict Centered Column) */}
                  <div className="flex justify-center items-center px-1">
                    <span className="w-[80px] text-center text-[10px] sm:text-xs font-extrabold text-amber-300 bg-amber-500/10 px-2 py-1 rounded-lg border border-amber-500/20 uppercase tracking-wide truncate flex justify-center items-center">
                      {firstSource?.language?.toUpperCase() || 'TAMIL'}
                    </span>
                  </div>

                  {/* Right Zone: Size & Download Button (Strict Fixed 115px Column) */}
                  <div className="w-[115px] shrink-0 flex items-center justify-end gap-2">
                    {firstSource && (
                      <span className="w-[58px] text-right text-xs sm:text-sm font-black text-emerald-400 font-mono shrink-0">
                        {formatBytes(firstSource.file_size_bytes || 285000000)}
                      </span>
                    )}

                    {/* Direct Episode Download Action Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEpisodeNum(eNum);
                        setSelectedQualityIndex(0);
                        handleStartParallelDownload();
                      }}
                      className="w-8 h-8 sm:w-auto sm:px-3.5 sm:py-2 rounded-xl bg-gradient-to-r from-red-600 via-rose-600 to-red-500 hover:brightness-110 text-white font-extrabold flex items-center justify-center gap-1.5 transition active:scale-95 shadow-md shadow-red-600/30 cursor-pointer text-xs shrink-0"
                      title="Download Episode"
                      aria-label={`Download Episode ${eNum}`}
                    >
                      <Download className="w-3.5 h-3.5 text-white" />
                      <span className="hidden sm:inline">Download</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Ambient AI Telemetry Companion */}
        <AITaskCompanion />

      </main>

    </div>
  );
}
