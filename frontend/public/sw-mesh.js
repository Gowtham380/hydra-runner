/**
 * SMD PRIME / PROJECT HYDRA - SERVICE WORKER RANGE STREAMER (SW-MESH)
 * High-Speed Native Streamer & Pause/Resume Support
 */

const CACHE_NAME = 'sw-mesh-metadata-v1';
const XOR_KEY = 0x5F;
const HEADER_MASK_LIMIT = 1024;

// Store for active movie stream metadata in-memory inside SW scope
const activeStreams = new Map();

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Listen for metadata registration messages from main thread
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'REGISTER_STREAM') {
    const { slug, movie } = event.data;
    if (slug && movie) {
      activeStreams.set(slug, movie);
      console.log(`[SW-Mesh] Registered stream metadata for slug: ${slug}`);
    }
  }
});

/**
 * XOR byte-masking decoder for chunk headers
 */
function obfuscateHeader(buffer, key = XOR_KEY, maskLimit = HEADER_MASK_LIMIT) {
  const bytes = new Uint8Array(buffer);
  const limit = Math.min(maskLimit, bytes.length);
  for (let i = 0; i < limit; i++) {
    bytes[i] ^= key;
  }
  return bytes;
}

/**
 * Fetch and decode a single chunk
 */
async function fetchAndDecodeChunk(chunkUrl, isFirstChunk = false, hfToken = '') {
  const headers = {};
  if (hfToken) {
    headers['Authorization'] = `Bearer ${hfToken}`;
  }
  
  let res;
  try {
    res = await fetch(chunkUrl, { headers });
  } catch (err) {
    // Retry without custom headers if CORS preflight blocked Authorization header
    res = await fetch(chunkUrl);
  }

  if (!res.ok) {
    throw new Error(`Failed to fetch chunk: ${res.status}`);
  }
  
  const buffer = await res.arrayBuffer();

  // Only apply XOR obfuscation if chunkUrl is a masked chunk file (e.g. .bin, part_0, or obfuscated)
  const isObfuscated = isFirstChunk && (
    chunkUrl.includes('.bin') || 
    chunkUrl.includes('part_') || 
    chunkUrl.includes('segment') ||
    chunkUrl.includes('chunk_0')
  );

  if (isObfuscated) {
    return obfuscateHeader(buffer);
  }
  return new Uint8Array(buffer);
}

// Intercept fetch requests matching /sw-stream/
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/sw-stream/')) {
    event.respondWith(handleStreamRequest(event.request, url));
  }
});

async function handleStreamRequest(request, url) {
  const pathParts = url.pathname.split('/');
  const slug = pathParts[pathParts.length - 1];

  let movie = activeStreams.get(slug);

  // Fallback: Check url search params if postMessage missed
  if (!movie) {
    const rawMeta = url.searchParams.get('meta');
    if (rawMeta) {
      try {
        movie = JSON.parse(decodeURIComponent(rawMeta));
      } catch (e) {
        console.error('[SW-Mesh] Failed to parse URL metadata:', e);
      }
    }
  }

  if (!movie || !movie.chunk_urls || movie.chunk_urls.length === 0) {
    return new Response('Stream metadata not found', { status: 404 });
  }

  const chunkUrls = movie.chunk_urls;
  const totalSizeBytes = movie.file_size_bytes || 2684354560; // 2.5GB default
  const mimeType = movie.mime_type || 'video/mp4';
  const fileName = movie.file_name || `${slug}.mp4`;
  const hfToken = movie.hf_token || '';

  // Parse HTTP Range Header (for native Pause / Resume support in Chrome)
  const rangeHeader = request.headers.get('Range');
  let startByte = 0;
  let endByte = totalSizeBytes - 1;

  if (rangeHeader) {
    const parts = rangeHeader.replace(/bytes=/, '').split('-');
    startByte = parseInt(parts[0], 10);
    if (parts[1]) {
      endByte = parseInt(parts[1], 10);
    }
  }

  const contentLength = endByte - startByte + 1;

  // Stream readable chunks sequentially/pipelined into native Chrome downloader
  const stream = new ReadableStream({
    async start(controller) {
      try {
        let currentByteOffset = 0;

        for (let i = 0; i < chunkUrls.length; i++) {
          const isFirstChunk = (i === 0);
          const chunkData = await fetchAndDecodeChunk(chunkUrls[i], isFirstChunk, hfToken);
          const chunkLength = chunkData.byteLength;
          const chunkEndByte = currentByteOffset + chunkLength - 1;

          // Check if current chunk intersects with requested Range
          if (chunkEndByte >= startByte && currentByteOffset <= endByte) {
            let sliceStart = 0;
            let sliceEnd = chunkLength;

            if (startByte > currentByteOffset) {
              sliceStart = startByte - currentByteOffset;
            }
            if (endByte < chunkEndByte) {
              sliceEnd = chunkLength - (chunkEndByte - endByte);
            }

            const chunkSlice = chunkData.subarray(sliceStart, sliceEnd);
            controller.enqueue(chunkSlice);
          }

          currentByteOffset += chunkLength;

          if (currentByteOffset > endByte) {
            break;
          }
        }

        controller.close();
      } catch (err) {
        console.error('[SW-Mesh] Error during stream enqueue:', err);
        controller.error(err);
      }
    }
  });

  const responseHeaders = new Headers({
    'Content-Type': mimeType,
    'Content-Length': contentLength.toString(),
    'Content-Disposition': `attachment; filename="${encodeURIComponent(fileName)}"`,
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-cache'
  });

  if (rangeHeader) {
    responseHeaders.set('Content-Range', `bytes ${startByte}-${endByte}/${totalSizeBytes}`);
    return new Response(stream, {
      status: 206, // Partial Content
      statusText: 'Partial Content',
      headers: responseHeaders
    });
  }

  return new Response(stream, {
    status: 200,
    headers: responseHeaders
  });
}
