import React, { useState, useEffect } from 'react';
import { X, Download, ExternalLink, Copy, Check, HardDrive, RefreshCw, CheckCircle2, AlertCircle, Zap, Globe } from 'lucide-react';
import { generateDownloadLink, formatBytes } from '../lib/api';
import { downloadMovieInParallel } from '../utils/downloader';
import { triggerSwMeshDownload } from '../utils/swStreamer';
import { startOrResumePersistentDownload } from '../utils/persistentDownloader';
import ExternalPlayerMenu from './ExternalPlayerMenu';

export default function DownloadModal({ movie, onClose }) {
  const [loading, setLoading] = useState(true);
  const [linkData, setLinkData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  // Parallel Download State
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(null);
  const [downloadDone, setDownloadDone] = useState(false);

  // Parse exact single file quality from movie object/filename
  const getMovieQualities = (mov) => {
    if (mov?.available_qualities && Array.isArray(mov.available_qualities) && mov.available_qualities.length > 0) {
      return mov.available_qualities;
    }
    if (mov?.qualities && Array.isArray(mov.qualities) && mov.qualities.length > 0) {
      return mov.qualities;
    }

    const text = (mov?.file_name || mov?.title || '').toLowerCase();
    if (text.includes('2160p') || text.includes('4k')) {
      return [{ label: '2160p 4K UHD', code: '2160p' }];
    }
    if (text.includes('720p')) {
      return [{ label: '720p HD', code: '720p' }];
    }
    if (text.includes('480p')) {
      return [{ label: '480p SD', code: '480p' }];
    }

    return [{ label: '1080p Full HD', code: '1080p' }];
  };

  const availableQualities = getMovieQualities(movie);
  const [selectedQuality, setSelectedQuality] = useState(() => availableQualities[0]?.code || '1080p');

  useEffect(() => {
    if (!movie) return;

    let isMounted = true;
    setLoading(true);
    setError(null);
    setDownloading(false);
    setProgress(null);
    setDownloadDone(false);

    const qualities = getMovieQualities(movie);
    setSelectedQuality(qualities[0]?.code || '1080p');

    generateDownloadLink(movie.id)
      .then(data => {
        if (isMounted) {
          setLinkData(data);
          setLoading(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => { isMounted = false; };
  }, [movie]);

  if (!movie) return null;

  const handleCopyLink = () => {
    if (linkData?.download_url) {
      navigator.clipboard.writeText(linkData.download_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const baseSizeBytes = movie.file_size_bytes || 285754607;
  const currentQualityObj = availableQualities.find(q => q.code === selectedQuality) || availableQualities[0];

  const handleNativeSwDownload = async () => {
    try {
      setError(null);
      const directUrl = linkData?.download_url || movie.download_url;
      const urls = (movie.chunk_urls && movie.chunk_urls.length > 0) 
        ? movie.chunk_urls 
        : (directUrl ? [directUrl] : null);

      const moviePayload = {
        ...movie,
        download_url: directUrl,
        chunk_urls: urls,
        file_size_bytes: movie.file_size_bytes || baseSizeBytes || 2684354560
      };

      await triggerSwMeshDownload(moviePayload, urls || []);
    } catch (err) {
      console.error("Native Download Trigger Error:", err);
      setError("Native download failed. Falling back to background downloader.");
      handleStartParallelDownload();
    }
  };

  const handleStartParallelDownload = async () => {
    const urls = (movie.chunk_urls && movie.chunk_urls.length > 0)
      ? movie.chunk_urls 
      : (movie.stream_url || movie.download_url || movie.drive_url || movie.url)
        ? [movie.stream_url || movie.download_url || movie.drive_url || movie.url]
        : (linkData?.download_url ? [linkData.download_url] : []);

    try {
      setDownloading(true);
      setDownloadDone(false);
      setError(null);

      await startOrResumePersistentDownload(movie, urls);

      setDownloading(false);
      setDownloadDone(true);
    } catch (err) {
      console.error("Download Error:", err);
      setError("Download failed. Please try external player link.");
      setDownloading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fadeIn">
      
      {/* Modal Container */}
      <div className="relative w-full max-w-lg rounded-3xl border border-zinc-800 bg-zinc-950 p-6 sm:p-8 shadow-2xl overflow-hidden">
        
        {/* Subtle Ambient Glow */}
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-red-600/10 rounded-full blur-3xl pointer-events-none" />

        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-zinc-400 hover:text-white p-2 rounded-xl bg-zinc-900 hover:bg-zinc-800 transition cursor-pointer border border-zinc-800"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="flex items-start space-x-4 mb-5">
          <div className="w-16 h-20 rounded-xl overflow-hidden bg-zinc-900 border border-zinc-800 shrink-0 shadow-lg">
            <img src={movie.poster_url || "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=300&q=80"} alt={movie.title} className="w-full h-full object-cover" />
          </div>
          <div className="flex-1 pr-6">
            <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
              <span className="inline-flex items-center space-x-1 bg-red-600/10 text-red-400 text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-red-500/20">
                <span>Tamil Audio HQ</span>
              </span>
              <span className="inline-flex items-center space-x-1 bg-zinc-800 text-zinc-200 text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-zinc-700">
                <span>{currentQualityObj.label}</span>
              </span>
            </div>
            <h3 className="text-xl font-bold text-white line-clamp-1">{movie.title}</h3>
            <p className="text-xs text-zinc-400 mt-0.5 font-medium">Download Movie</p>
          </div>
        </div>

        {/* Quality Selector */}
        <div className="mb-5">
          <div className="flex items-center justify-between mb-2">
            <label className="text-[11px] font-semibold text-zinc-400">Selected Quality:</label>
            <span className="text-[10px] font-mono text-emerald-400 font-bold">{availableQualities.length} {availableQualities.length === 1 ? 'Quality' : 'Qualities'} Available</span>
          </div>

          <div className={`grid gap-2 ${availableQualities.length >= 3 ? 'grid-cols-3' : availableQualities.length === 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
            {availableQualities.map((qual) => {
              const active = selectedQuality === qual.code;
              return (
                <button
                  key={qual.code}
                  onClick={() => setSelectedQuality(qual.code)}
                  className={`py-2.5 px-3 text-center text-xs font-semibold rounded-xl border transition cursor-pointer truncate ${
                    active 
                      ? 'bg-red-600/20 border-red-500 text-red-400 shadow-md font-extrabold ring-1 ring-red-500/50' 
                      : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                  }`}
                >
                  {qual.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Dynamic File Size Card */}
        <div className="bg-zinc-900/90 border border-zinc-800 p-3.5 rounded-2xl mb-5 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2 text-zinc-300">
            <HardDrive className="w-4 h-4 text-red-500" />
            <span>File Size</span>
          </div>
          <span className="font-bold text-white font-mono text-sm text-red-400">
            {formatBytes(baseSizeBytes)}
          </span>
        </div>

        {/* Dynamic State Body */}
        {loading ? (
          <div className="py-8 flex flex-col items-center justify-center space-y-3">
            <RefreshCw className="w-7 h-7 text-red-500 animate-spin" />
            <p className="text-xs text-zinc-400 font-medium">Preparing download options...</p>
          </div>
        ) : (
          <div className="space-y-3">
            
            {/* Error Banner */}
            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-2xl text-red-400 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Download Progress State */}
            {downloading ? (
              <div className="bg-zinc-900 border border-red-500/30 p-4.5 rounded-2xl space-y-3">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-red-300 flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-red-500" />
                    Downloading Movie...
                  </span>
                  <span className="text-white font-black font-mono text-sm">{progress?.percentage || "0"}%</span>
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-zinc-950 rounded-full h-3 overflow-hidden border border-zinc-800 p-0.5">
                  <div 
                    className="bg-gradient-to-r from-red-600 to-rose-500 h-full rounded-full transition-all duration-300"
                    style={{ width: `${progress?.percentage || 0}%` }}
                  />
                </div>
              </div>
            ) : downloadDone ? (
              <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl text-emerald-300 text-xs text-center flex items-center justify-center gap-2 font-bold">
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                <span>Download Started! Check the top-right Downloads icon.</span>
              </div>
            ) : (
              <>
                {/* Unified High Speed Download CTA */}
                <button
                  onClick={handleStartParallelDownload}
                  disabled={downloading}
                  className="w-full bg-gradient-to-r from-red-600 via-rose-600 to-red-500 hover:brightness-110 text-white font-extrabold py-3.5 px-5 rounded-2xl shadow-lg shadow-red-600/30 flex items-center justify-between transition active:scale-[0.98] cursor-pointer text-sm group disabled:opacity-50"
                >
                  <div className="flex items-center space-x-2.5">
                    <Download className="w-5 h-5 group-hover:scale-110 transition-transform" />
                    <span>Start Download</span>
                  </div>
                  <span className="bg-black/40 text-emerald-400 text-[11px] font-mono font-black px-2.5 py-1 rounded-lg border border-emerald-500/30 flex items-center gap-1.5 shadow-inner">
                    <Zap className="w-3.5 h-3.5 text-emerald-400 fill-emerald-400 animate-pulse" />
                    <span>AUTO-HEALER ON</span>
                  </span>
                </button>
              </>
            )}

          </div>
        )}

      </div>
    </div>
  );
}
