import React, { useState } from 'react';
import { Copy, Check, Play, ExternalLink } from 'lucide-react';
import { triggerHaptic, openExternalLink } from '../lib/telegram';

export function VlcIcon({ className = "w-5 h-5" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M20.5 4L27.5 4L31 16H17L20.5 4Z" fill="#FF8800" />
      <path d="M17 16L31 16L34 26H14L17 16Z" fill="#FFFFFF" />
      <path d="M14 26L34 26L37.5 36H10.5L14 26Z" fill="#FF7700" />
      <path d="M10.5 36L37.5 36L39.5 42H8.5L10.5 36Z" fill="#FFFFFF" />
      <rect x="5" y="41" width="38" height="4" rx="2" fill="#E65100" />
    </svg>
  );
}

export function MxPlayerIcon({ className = "w-5 h-5" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="48" height="48" rx="14" fill="url(#mx_grad_sm)" />
      <circle cx="24" cy="24" r="14" fill="white" />
      <path d="M21 17L31 24L21 31V17Z" fill="#0066FF" />
      <defs>
        <linearGradient id="mx_grad_sm" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop stopColor="#00A2FF" />
          <stop offset="1" stopColor="#0055FF" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function SystemPlayerIcon({ className = "w-5 h-5" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="48" height="48" rx="14" fill="url(#sys_grad_sm)" />
      <rect x="8" y="10" width="32" height="22" rx="4" fill="#10B981" fillOpacity="0.3" stroke="#34D399" strokeWidth="2" />
      <path d="M21 16L30 21L21 26V16Z" fill="#34D399" />
      <path d="M16 38L24 32L32 38" stroke="#34D399" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <defs>
        <linearGradient id="sys_grad_sm" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop stopColor="#065F46" />
          <stop offset="1" stopColor="#022C22" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function generatePlayerUrls(streamUrl) {
  if (!streamUrl) return { vlcScheme: '', vlcIntent: '', mxIntent: '', systemIntent: '', raw: '' };
  const raw = String(streamUrl).trim();
  return {
    raw,
    vlcScheme: `vlc://${raw}`,
    vlcIntent: `intent:${raw}#Intent;package=org.videolan.vlc;type=video/*;scheme=https;end`,
    mxIntent: `intent:${raw}#Intent;package=com.mxtech.videoplayer.ad;type=video/*;scheme=https;end`,
    systemIntent: `intent:${raw}#Intent;action=android.intent.action.VIEW;type=video/*;scheme=https;end`
  };
}

export default function ExternalPlayerMenu({ streamUrl, movieTitle = 'Movie Stream', onExternalPlayTriggered }) {
  const [copied, setCopied] = useState(false);

  if (!streamUrl) return null;

  const urls = generatePlayerUrls(streamUrl);

  const handleLaunchPlayer = (e, playerType) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    triggerHaptic('heavy');

    const rawStreamUrl = urls.raw;
    if (!rawStreamUrl) return;

    if (typeof onExternalPlayTriggered === 'function') {
      onExternalPlayTriggered();
    }

    setTimeout(() => {
      const gatewayUrl = `${window.location.origin}/player-gate?app=${encodeURIComponent(playerType)}&url=${encodeURIComponent(rawStreamUrl)}`;
      openExternalLink(gatewayUrl);
    }, 150);
  };

  const handleCopyLink = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    triggerHaptic('light');
    if (!urls.raw) return;

    navigator.clipboard.writeText(urls.raw).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    }).catch(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    });
  };

  return (
    <div className="w-full space-y-2.5 font-sans select-none">
      {/* 1-Line Minimalist Section Header */}
      <div className="flex items-center justify-between px-1 text-[10px] font-mono font-bold tracking-widest text-cyan-400 uppercase">
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span>EXTERNAL MEDIA PLAYERS</span>
        </span>
        <span className="text-[9px] text-zinc-500 font-normal">0-Latency Handoff</span>
      </div>

      {/* Responsive Snap Horizontal Carousel / Grid with FULL Non-Truncated Labels */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar scroll-touch px-0.5">
        
        {/* 1. VLC Player */}
        <a
          href={urls.vlcIntent}
          onClick={(e) => handleLaunchPlayer(e, 'vlc')}
          className="flex items-center space-x-2 px-3.5 py-2.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 transition-all active:scale-[0.96] shrink-0 cursor-pointer shadow-sm group hover:border-amber-400/50"
          title="Play in VLC Player"
          aria-label="Play in VLC Player"
        >
          <VlcIcon className="w-5 h-5 shrink-0 group-hover:scale-110 transition-transform drop-shadow-[0_2px_8px_rgba(255,136,0,0.4)]" />
          <div className="flex flex-col text-left">
            <span className="text-xs font-black text-white group-hover:text-amber-300 whitespace-nowrap">VLC Player</span>
            <span className="text-[9px] text-amber-400/80 font-mono leading-none">Instant Play</span>
          </div>
        </a>

        {/* 2. MX Player */}
        <a
          href={urls.mxIntent}
          onClick={(e) => handleLaunchPlayer(e, 'mx')}
          className="flex items-center space-x-2 px-3.5 py-2.5 rounded-xl bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 text-blue-300 transition-all active:scale-[0.96] shrink-0 cursor-pointer shadow-sm group hover:border-blue-400/50"
          title="Play in MX Player"
          aria-label="Play in MX Player"
        >
          <MxPlayerIcon className="w-5 h-5 shrink-0 group-hover:scale-110 transition-transform drop-shadow-[0_2px_8px_rgba(0,102,255,0.4)]" />
          <div className="flex flex-col text-left">
            <span className="text-xs font-black text-white group-hover:text-blue-300 whitespace-nowrap">MX Player</span>
            <span className="text-[9px] text-blue-400/80 font-mono leading-none">Hardware HW+</span>
          </div>
        </a>

        {/* 3. System Player */}
        <a
          href={urls.systemIntent}
          onClick={(e) => handleLaunchPlayer(e, 'system')}
          className="flex items-center space-x-2 px-3.5 py-2.5 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 transition-all active:scale-[0.96] shrink-0 cursor-pointer shadow-sm group hover:border-emerald-400/50"
          title="Play in System Default Player"
          aria-label="Play in System Default Player"
        >
          <SystemPlayerIcon className="w-5 h-5 shrink-0 group-hover:scale-110 transition-transform drop-shadow-[0_2px_8px_rgba(16,185,129,0.4)]" />
          <div className="flex flex-col text-left">
            <span className="text-xs font-black text-white group-hover:text-emerald-300 whitespace-nowrap">System Player</span>
            <span className="text-[9px] text-emerald-400/80 font-mono leading-none">Native OS</span>
          </div>
        </a>

        {/* 4. Copy Stream Link */}
        <button
          onClick={handleCopyLink}
          className="flex items-center space-x-2 px-3.5 py-2.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/30 text-purple-300 transition-all active:scale-[0.96] shrink-0 cursor-pointer shadow-sm group hover:border-purple-400/50"
          title="Copy Direct Stream Link"
          aria-label="Copy Direct Stream Link"
        >
          {copied ? <Check className="w-5 h-5 text-emerald-400 shrink-0" /> : <Copy className="w-5 h-5 text-purple-300 shrink-0" />}
          <div className="flex flex-col text-left">
            <span className="text-xs font-black text-white group-hover:text-purple-300 whitespace-nowrap">
              {copied ? 'Copied!' : 'Copy Stream Link'}
            </span>
            <span className="text-[9px] text-purple-400/80 font-mono leading-none">
              {copied ? 'Clipboard Ready' : 'External Paste'}
            </span>
          </div>
        </button>

      </div>
    </div>
  );
}
