/**
 * PROJECT HYDRA - EDGE GATEWAY & STREAM PIPE (LAYER 3)
 * Cloudflare Worker ES Module Router
 * 
 * Key Architecture Features:
 * 1. Zero DB Overload: CF KV edge cache before hitting Supabase DB.
 * 2. Piping over Buffering: Zero RAM usage via native fetch Response stream.
 * 3. Anti-Leech Security: JWT verification with client IP binding.
 * 4. TMA Intent Bounce: Telegram Webview exit bounce for large 4GB+ file downloads.
 */

import { signJwt, verifyJwt } from './crypto.js';
import { fetchMovieFromSupabase, logDownloadLinkToSupabase } from './supabase.js';

const CACHE_TTL_SECONDS = 86400; // 24 Hours KV Edge Cache

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Extract client IP address from Cloudflare headers
    const clientIp = request.headers.get('cf-connecting-ip') || 
                     request.headers.get('x-real-ip') || 
                     '127.0.0.1';

    // CORS preflight handling
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, Range'
        }
      });
    }

    try {
      // ROUTE 1: Stream Pipe Download Endpoint (/dl/:token or /dl?token=...)
      if (path.startsWith('/dl/') || path === '/dl') {
        const token = path.startsWith('/dl/') 
          ? path.substring(4) 
          : url.searchParams.get('token');

        return await handleDownloadStream(token, request, env, ctx, clientIp, url);
      }

      // ROUTE 2: Telegram Mini App Intent Bounce (/intent/:token)
      if (path.startsWith('/intent/')) {
        const token = path.substring(8);
        return handleIntentBounce(token, url);
      }

      // ROUTE 3: Admin / API Token Generation (/api/token/generate)
      if (path === '/api/token/generate' && request.method === 'POST') {
        return await handleTokenGeneration(request, env, clientIp);
      }

      // ROUTE 4: Health check & info
      if (path === '/' || path === '/health') {
        return new Response(JSON.stringify({
          status: 'online',
          system: 'Project Hydra Edge Gateway',
          version: '1.0.0',
          timestamp: new Date().toISOString()
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      return new Response(JSON.stringify({ error: 'Endpoint not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });

    } catch (err) {
      console.error('Unhandled Edge Gateway Error:', err);
      return new Response(JSON.stringify({ 
        error: 'Internal Gateway Error', 
        details: err.message 
      }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      });
    }
  }
};

/**
 * Handle direct movie stream piping with JWT validation & KV caching
 */
async function handleDownloadStream(token, request, env, ctx, clientIp, url) {
  const secret = env.JWT_SECRET || 'hydra_default_secret_key_change_in_prod';
  const enforceIpBinding = env.ENABLE_IP_BINDING !== 'false';

  // 1. Verify JWT & Anti-Leech Protection
  const verifyResult = await verifyJwt(token, secret, enforceIpBinding ? clientIp : null);
  if (!verifyResult.valid) {
    return new Response(JSON.stringify({
      error: 'Access Denied',
      reason: verifyResult.error
    }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const { sub: movieId } = verifyResult.payload;
  if (!movieId) {
    return new Response(JSON.stringify({ error: 'Invalid token payload: missing movie ID' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // Check if intent bounce parameter is set (forcing Android Chrome download)
  if (url.searchParams.get('bounce') === 'true') {
    return handleIntentBounce(token, url);
  }

  // 2. Edge Caching Layer: Query Cloudflare KV first
  const kvKey = `movie:${movieId}`;
  let movieData = null;
  const kvBinding = env.KV || env.HYDRA_KV;

  if (kvBinding) {
    try {
      movieData = await kvBinding.get(kvKey, 'json');
    } catch (kvErr) {
      console.warn('KV Read Warning:', kvErr.message);
    }
  }

  // Fallback: Query Supabase DB on KV Cache Miss
  if (!movieData) {
    console.log(`KV Cache Miss for movie ${movieId}. Fetching from Supabase...`);
    movieData = await fetchMovieFromSupabase(movieId, env);

    if (!movieData) {
      return new Response(JSON.stringify({ error: 'Movie record not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Save fetched record into KV cache asynchronously (0 latency block)
    if (kvBinding) {
      ctx.waitUntil(
        kvBinding.put(kvKey, JSON.stringify(movieData), {
          expirationTtl: CACHE_TTL_SECONDS
        }).catch(err => console.error('KV Write Error:', err))
      );
    }
  } else {
    console.log(`KV Cache Hit for movie ${movieId}`);
  }

  // 3. Prepare Downstream Stream Pipe to HuggingFace Raw asset
  const hfUrl = movieData.hf_raw_url;
  if (!hfUrl) {
    return new Response(JSON.stringify({ error: 'Storage asset URL missing' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // Forward client Range header to allow resumable multi-threaded downloads (Aria2 / Chrome)
  const forwardHeaders = new Headers();
  const rangeHeader = request.headers.get('Range');
  if (rangeHeader) {
    forwardHeaders.set('Range', rangeHeader);
  }
  forwardHeaders.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ProjectHydra/1.0');

  // Fetch spoofed .bin / weights file from Hugging Face Git LFS (Follows AWS CloudFront redirect)
  const hfResponse = await fetch(hfUrl, {
    method: 'GET',
    headers: forwardHeaders,
    redirect: 'follow'
  });

  if (!hfResponse.ok && hfResponse.status !== 206) {
    return new Response(JSON.stringify({
      error: 'Upstream Storage Error',
      upstreamStatus: hfResponse.status
    }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // 4. Header-Rewrite Stream Pipe
  // Mask `.bin` extension -> Rewrite Content-Disposition to real movie name (`.mkv` / `.mp4`)
  const responseHeaders = new Headers();
  
  const realFileName = movieData.file_name || 'movie.mkv';
  const encodedFileName = encodeURIComponent(realFileName);
  
  responseHeaders.set('Content-Type', movieData.mime_type || 'video/x-matroska');
  responseHeaders.set('Content-Disposition', `attachment; filename="${realFileName}"; filename*=UTF-8''${encodedFileName}`);
  responseHeaders.set('Accept-Ranges', 'bytes');
  responseHeaders.set('Transfer-Encoding', 'chunked');
  responseHeaders.set('X-Content-Type-Options', 'nosniff');
  responseHeaders.set('Access-Control-Allow-Origin', '*');

  // Forward Content-Range & Content-Length if provided by AWS CloudFront / HF
  if (hfResponse.headers.get('Content-Range')) {
    responseHeaders.set('Content-Range', hfResponse.headers.get('Content-Range'));
  }
  if (hfResponse.headers.get('Content-Length')) {
    responseHeaders.set('Content-Length', hfResponse.headers.get('Content-Length'));
  }

  // Stream pipe directly to client without buffering in Worker RAM
  return new Response(hfResponse.body, {
    status: hfResponse.status, // 200 or 206 Partial Content
    headers: responseHeaders
  });
}

/**
 * Handles Telegram Mini App (TMA) intent bounce to force external Chrome launch
 */
function handleIntentBounce(token, currentUrl) {
  const downloadUrl = `${currentUrl.origin}/dl/${token}`;
  const intentScheme = `intent://${currentUrl.host}/dl/${token}#Intent;scheme=https;package=com.android.chrome;end`;

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting to External Browser...</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; text-align: center; }
        .card { background: #1e293b; padding: 32px; border-radius: 16px; max-width: 440px; width: 100%; border: 1px solid #334155; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); }
        h2 { color: #38bdf8; margin-top: 0; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
        .btn { display: inline-block; background: #0284c7; color: white; text-decoration: none; padding: 14px 24px; border-radius: 8px; font-weight: 600; margin-top: 16px; width: 100%; box-sizing: border-box; }
        .btn:hover { background: #0369a1; }
    </style>
    <script>
        window.onload = function() {
            // Attempt Android Chrome Intent Bounce
            window.location.href = "${intentScheme}";
            
            // Fallback timeout redirect after 1.5 seconds
            setTimeout(function() {
                window.location.href = "${downloadUrl}";
            }, 1500);
        };
    </script>
</head>
<body>
    <div class="card">
        <h2>⚡ Hydra High-Speed Downloader</h2>
        <p>Bypassing Telegram Webview restriction to enable 10Gbps pause/resume multi-gigabyte file download in Chrome...</p>
        <a href="${downloadUrl}" class="btn">Direct Download Link</a>
    </div>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}

/**
 * Handle API token generation endpoint (/api/token/generate)
 */
async function handleTokenGeneration(request, env, defaultIp) {
  const secret = env.JWT_SECRET || 'hydra_default_secret_key_change_in_prod';
  
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return new Response(JSON.stringify({ error: 'Invalid JSON request body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const { movie_id, client_ip, expires_in_seconds } = body;
  if (!movie_id) {
    return new Response(JSON.stringify({ error: 'movie_id is required' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const targetIp = client_ip || defaultIp;
  const ttl = expires_in_seconds || 86400; // Default 24 hours
  const now = Math.floor(Date.now() / 1000);
  const exp = now + ttl;
  const jti = crypto.randomUUID();

  const payload = {
    sub: movie_id,
    ip: targetIp,
    exp: exp,
    jti: jti,
    iat: now
  };

  const token = await signJwt(payload, secret);
  const host = request.headers.get('host') || 'worker.dev';
  const protocol = request.headers.get('x-forwarded-proto') || 'https';
  
  const downloadUrl = `${protocol}://${host}/dl/${token}`;
  const intentUrl = `${protocol}://${host}/intent/${token}`;

  // Log link generation to Supabase audit log
  await logDownloadLinkToSupabase({
    movie_id,
    token_jti: jti,
    client_ip: targetIp,
    expires_at: new Date(exp * 1000).toISOString()
  }, env);

  return new Response(JSON.stringify({
    success: true,
    token,
    download_url: downloadUrl,
    intent_url: intentUrl,
    expires_at: new Date(exp * 1000).toISOString(),
    bound_ip: targetIp
  }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' }
  });
}
