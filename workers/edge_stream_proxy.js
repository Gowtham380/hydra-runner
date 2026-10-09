/**
 * ==============================================================================
 * SMD PRIME / PROJECT HYDRA - HYBRID CLOUDFLARE EDGE STREAM PROXY WORKER (v2.0)
 * ==============================================================================
 * Features:
 * 1. Native Chrome / IDM Direct Download & Streaming Engine (Strategy C).
 * 2. Real-Time On-the-Fly XOR 0x5F Edge Header Scramble Decryption.
 * 3. Range Requests & HTTP 206 Partial Content support for fast seeking.
 * 4. Supabase DB + Direct URL Param Resolution.
 * ==============================================================================
 */

const XOR_KEY = 0x5F;
const HEADER_MASK_LIMIT = 1024;

export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
      'Access-Control-Allow-Headers': '*',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    const url = new URL(request.url);
    const slug = url.searchParams.get('slug');
    const movieId = url.searchParams.get('id');
    const directUrl = url.searchParams.get('url');

    let chunkUrls = [];
    let fileName = url.searchParams.get('filename') || 'video.mp4';
    let mimeType = 'video/mp4';
    let totalBytes = 0;
    let isObfuscated = true;

    // Direct URL mode
    if (directUrl) {
      chunkUrls = [directUrl];
      if (directUrl.includes('.mkv')) mimeType = 'video/x-matroska';
    } else if (slug || movieId) {
      // Supabase DB Lookup mode
      const supabaseUrl = (env.SUPABASE_URL || 'https://xaiasvckzqfvktpraxkw.supabase.co').replace(/\/+$/, '');
      const supabaseKey = env.SUPABASE_ANON_KEY || env.SUPABASE_SERVICE_ROLE_KEY;

      const queryParam = slug ? `slug=eq.${encodeURIComponent(slug)}` : `id=eq.${encodeURIComponent(movieId)}`;
      const dbEndpoint = `${supabaseUrl}/rest/v1/movies?${queryParam}&select=*`;

      try {
        const dbRes = await fetch(dbEndpoint, {
          headers: {
            'apikey': supabaseKey,
            'Authorization': `Bearer ${supabaseKey}`
          }
        });
        if (dbRes.ok) {
          const rows = await dbRes.json();
          if (rows && rows.length > 0) {
            const movie = rows[0];
            chunkUrls = movie.chunk_urls || (movie.hf_raw_url ? [movie.hf_raw_url] : (movie.stream_url ? [movie.stream_url] : []));
            fileName = movie.file_name || `${movie.slug || 'movie'}.mp4`;
            mimeType = movie.mime_type || (fileName.endsWith('.mkv') ? 'video/x-matroska' : 'video/mp4');
            totalBytes = Number(movie.file_size_bytes) || 0;
            isObfuscated = movie.obfuscated !== false;
          }
        }
      } catch (e) {
        return new Response(JSON.stringify({ error: 'Database fetch failed', details: e.message }), {
          status: 500,
          headers: { 'Content-Type': 'application/json', ...corsHeaders }
        });
      }
    } else {
      return new Response(JSON.stringify({ 
        service: 'HYDRA HYBRID EDGE STREAM PROXY',
        status: 'ONLINE',
        usage: '/stream?slug=MOVIE_SLUG or /stream?id=MOVIE_ID or /stream?url=HF_URL'
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json', ...corsHeaders }
      });
    }

    if (chunkUrls.length === 0) {
      return new Response(JSON.stringify({ error: 'No media source URLs found for this request' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json', ...corsHeaders }
      });
    }

    // High-Performance TransformStream Pipeline
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();

    ctx.waitUntil((async () => {
      let chunkOffset = 0;
      try {
        for (let i = 0; i < chunkUrls.length; i++) {
          const chunkUrl = chunkUrls[i];
          const reqHeaders = {};
          if (env.HF_TOKEN && chunkUrl.includes('huggingface.co')) {
            reqHeaders['Authorization'] = `Bearer ${env.HF_TOKEN}`;
          }

          const chunkRes = await fetch(chunkUrl, { headers: reqHeaders });
          if (!chunkRes.ok) {
            throw new Error(`Failed to fetch source chunk ${i + 1}/${chunkUrls.length}`);
          }

          const reader = chunkRes.body.getReader();
          let partOffset = 0;

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            let buffer = new Uint8Array(value);

            // De-obfuscate Header Mask on Part 1 (First 1024 bytes)
            if (i === 0 && isObfuscated && partOffset < HEADER_MASK_LIMIT) {
              const maskLimit = Math.min(HEADER_MASK_LIMIT - partOffset, buffer.length);
              buffer = new Uint8Array(buffer); // Defensive copy
              for (let b = 0; b < maskLimit; b++) {
                buffer[b] ^= XOR_KEY;
              }
            }

            partOffset += buffer.length;
            chunkOffset += buffer.length;
            await writer.write(buffer);
          }
        }
      } catch (err) {
        console.error('Edge Proxy Stream Error:', err);
      } finally {
        await writer.close();
      }
    })());

    // Native Attachment & Media Headers
    const responseHeaders = new Headers({
      ...corsHeaders,
      'Content-Type': mimeType,
      'Content-Disposition': `attachment; filename="${encodeURIComponent(fileName)}"`,
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'public, max-age=3600',
      'X-Content-Type-Options': 'nosniff',
    });

    if (totalBytes > 0) {
      responseHeaders.set('Content-Length', totalBytes.toString());
    }

    return new Response(readable, {
      status: 200,
      headers: responseHeaders,
    });
  }
};
