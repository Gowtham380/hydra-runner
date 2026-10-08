import React, { useEffect, useState } from 'react';
import { Loader2, Play, Copy, Check, ArrowLeft } from 'lucide-react';

export default function PlayerGateway() {
  const [app, setApp] = useState('vlc');
  const [rawUrl, setRawUrl] = useState('');
  const [targetProtocolUrl, setTargetProtocolUrl] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const appParam = (params.get('app') || 'vlc').toLowerCase();
    const urlParam = params.get('url') || '';

    let decodedUrl = '';
    try {
      decodedUrl = decodeURIComponent(urlParam).trim();
    } catch (e) {
      decodedUrl = urlParam.trim();
    }

    setApp(appParam);
    setRawUrl(decodedUrl);

    if (decodedUrl) {
      let finalTarget = '';
      const isAndroid = /android/i.test(navigator.userAgent || '');

      if (appParam === 'vlc') {
        finalTarget = isAndroid
          ? `intent:${decodedUrl}#Intent;package=org.videolan.vlc;type=video/*;scheme=https;end;`
          : `vlc://${decodedUrl}`;
      } else if (appParam === 'mx') {
        finalTarget = `intent:${decodedUrl}#Intent;package=com.mxtech.videoplayer.ad;type=video/*;scheme=https;end;`;
      } else if (appParam === 'system') {
        finalTarget = `intent:${decodedUrl}#Intent;action=android.intent.action.VIEW;type=video/*;scheme=https;end;`;
      } else {
        finalTarget = decodedUrl;
      }

      setTargetProtocolUrl(finalTarget);

      const timer = setTimeout(() => {
        try {
          window.location.href = finalTarget;
        } catch (err) {
          console.error("Gateway redirect error:", err);
        }
      }, 200);

      return () => clearTimeout(timer);
    }
  }, []);

  const handleManualLaunch = (e) => {
    if (e) e.preventDefault();
    if (!targetProtocolUrl) return;

    try {
      window.location.href = targetProtocolUrl;
    } catch (err) {
      const a = document.createElement('a');
      a.href = targetProtocolUrl;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        try { document.body.removeChild(a); } catch (e) {}
      }, 500);
    }
  };

  const handleCopyLink = () => {
    if (!rawUrl) return;
    navigator.clipboard.writeText(rawUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    });
  };

  return (
    <div className="min-h-screen bg-[#06080d] text-white flex flex-col items-center justify-center p-4 font-sans select-none relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none z-0">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full bg-cyan-600/20 blur-3xl" />
      </div>

      <div className="relative z-10 max-w-md w-full p-6 rounded-3xl bg-zinc-950/90 border border-white/10 shadow-2xl backdrop-blur-2xl text-center space-y-6">
        <div className="flex items-center justify-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center font-black text-sm shadow-md">
            H
          </div>
          <span className="text-sm font-black tracking-wider uppercase text-white font-mono">
            HYDRA STREAM GATEWAY
          </span>
        </div>

        <div className="py-4 flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-10 h-10 text-cyan-400 animate-spin" />
          <div>
            <h2 className="text-base font-extrabold text-white">
              Redirecting to {app.toUpperCase()} Player...
            </h2>
            <p className="text-xs font-mono text-zinc-400 mt-1">
              Escaping Telegram sandbox & launching native player
            </p>
          </div>
        </div>

        <div className="space-y-3 pt-2">
          <a
            href={targetProtocolUrl}
            onClick={handleManualLaunch}
            className="w-full py-3.5 px-4 rounded-2xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-extrabold text-xs tracking-wider uppercase shadow-xl shadow-cyan-600/30 flex items-center justify-center gap-2 active:scale-95 transition-all"
          >
            <Play className="w-4 h-4 fill-current" />
            <span>Click Here if App Doesn't Open</span>
          </a>

          <button
            onClick={handleCopyLink}
            className="w-full py-3 px-4 rounded-2xl bg-zinc-900 hover:bg-zinc-800 border border-white/10 text-zinc-300 font-extrabold text-xs flex items-center justify-center gap-2 active:scale-95 transition-all"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4 text-zinc-400" />}
            <span>{copied ? 'Link Copied!' : 'Copy Direct Stream Link'}</span>
          </button>
        </div>

        <div className="pt-2">
          <button
            onClick={() => window.history.back()}
            className="text-[11px] text-zinc-500 hover:text-zinc-300 font-mono flex items-center justify-center gap-1 mx-auto transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            <span>Return to App</span>
          </button>
        </div>
      </div>
    </div>
  );
}
