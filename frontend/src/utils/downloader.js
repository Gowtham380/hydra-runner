/**
 * SMD PRIME / HYDRA - MULTI-THREADED PARALLEL CHUNK DOWNLOADER & DE-OBFUSCATOR
 * 
 * Features:
 * 1. Concurrent chunk downloading (4-6 parallel streams).
 * 2. In-memory XOR de-obfuscation on the first 1024 bytes (uint8[i] ^= 0x5F).
 * 3. Real-time speed and percentage progress tracking.
 * 4. Blob reassembly & native browser file trigger.
 */

const XOR_KEY = 0x5F;
const MASK_LIMIT = 1024;
const DEFAULT_CONCURRENCY = 4;

/**
 * De-obfuscate chunk header bytes in place (reverse XOR mask)
 * @param {Uint8Array} uint8
 */
export function deobfuscateHeader(uint8) {
  const limit = Math.min(MASK_LIMIT, uint8.length);
  for (let i = 0; i < limit; i++) {
    uint8[i] ^= XOR_KEY;
  }
  return uint8;
}

/**
 * Download movie chunks in parallel, de-obfuscate headers, and trigger file download
 * @param {Array<string>} chunkUrls List of chunk URLs
 * @param {string} fileName Target download file name
 * @param {Function} onProgress Progress callback ({ percentage, completedChunks, totalChunks, downloadedBytes, speedMBs })
 * @param {string} mimeType Video mime type (e.g. 'video/mp4' or 'video/x-matroska')
 * @param {number} concurrency Number of parallel download streams (default 4)
 * @returns {Promise<boolean>}
 */
export async function downloadMovieInParallel(
  chunkUrls,
  fileName = 'movie.mp4',
  onProgress = null,
  mimeType = 'video/mp4',
  concurrency = DEFAULT_CONCURRENCY,
  totalFileSize = 0
) {
  if (!chunkUrls || chunkUrls.length === 0) {
    throw new Error('No chunk URLs provided for download.');
  }

  const totalChunks = chunkUrls.length;
  const chunkBuffers = new Array(totalChunks);
  let completedChunks = 0;
  let downloadedBytes = 0;
  let maxPercentage = 0;

  const startTime = Date.now();

  // Helper to fetch and de-obfuscate a single chunk
  const fetchChunk = async (url, index) => {
    const hfToken = import.meta.env.VITE_HF_TOKEN;
    const fetchHeaders = {};
    if (hfToken) {
      fetchHeaders['Authorization'] = `Bearer ${hfToken}`;
    }

    const response = await fetch(url, { headers: fetchHeaders });
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error(`Failed to download chunk ${index + 1}/${totalChunks} (HTTP 401 Unauthorized - Add VITE_HF_TOKEN to frontend/.env or set HF dataset to Public)`);
      }
      throw new Error(`Failed to download chunk ${index + 1}/${totalChunks} (HTTP ${response.status})`);
    }

    const contentLength = +(response.headers.get('Content-Length') || 0);
    const reader = response.body.getReader();
    const chunks = [];
    let chunkReceivedBytes = 0;

    // Determine reliable total byte estimate
    const estTotalBytes = totalFileSize > 0 ? totalFileSize : (totalChunks * (contentLength || 104857600));

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      chunkReceivedBytes += value.byteLength;
      downloadedBytes += value.byteLength;

      if (onProgress) {
        const elapsedSec = (Date.now() - startTime) / 1000;
        const speedMBs = elapsedSec > 0 ? ((downloadedBytes / (1024 * 1024)) / elapsedSec).toFixed(1) : '0.0';
        
        let rawPct = estTotalBytes > 0 ? Math.min(99.99, (downloadedBytes / estTotalBytes) * 100) : ((completedChunks / totalChunks) * 100);
        if (rawPct > maxPercentage) {
          maxPercentage = rawPct;
        }

        onProgress({
          percentage: maxPercentage.toFixed(2),
          completedChunks,
          totalChunks,
          downloadedBytes,
          speedMBs: parseFloat(speedMBs)
        });
      }
    }

    // Concatenate received stream chunks for this single 100MB chunk
    const singleChunkUint8 = new Uint8Array(chunkReceivedBytes);
    let offset = 0;
    for (const c of chunks) {
      singleChunkUint8.set(c, offset);
      offset += c.byteLength;
    }

    // De-obfuscate header (reverse XOR)
    deobfuscateHeader(singleChunkUint8);

    chunkBuffers[index] = singleChunkUint8;
    completedChunks++;

    if (onProgress) {
      const elapsedSec = (Date.now() - startTime) / 1000;
      const speedMBs = elapsedSec > 0 ? ((downloadedBytes / (1024 * 1024)) / elapsedSec).toFixed(1) : '0.0';
      
      let rawPct = completedChunks === totalChunks ? 100.00 : Math.min(99.99, (downloadedBytes / estTotalBytes) * 100);
      if (rawPct > maxPercentage) {
        maxPercentage = rawPct;
      }

      onProgress({
        percentage: maxPercentage.toFixed(2),
        completedChunks,
        totalChunks,
        downloadedBytes,
        speedMBs: parseFloat(speedMBs)
      });
    }
  };

  // Process chunks in controlled parallel batches
  const queue = chunkUrls.map((url, idx) => ({ url, idx }));
  const workers = Array.from({ length: Math.min(concurrency, totalChunks) }, async () => {
    while (queue.length > 0) {
      const item = queue.shift();
      if (item) {
        await fetchChunk(item.url, item.idx);
      }
    }
  });

  await Promise.all(workers);

  // FIX: Convert each Uint8Array to its ArrayBuffer before Blob creation.
  // Using Uint8Array objects directly in Blob is unreliable for large binary video files.
  const blobParts = chunkBuffers.map(u8 => u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength));
  const finalBlob = new Blob(blobParts, { type: mimeType });

  // Trigger native browser file download
  const blobUrl = URL.createObjectURL(finalBlob);
  const anchor = document.createElement('a');
  anchor.href = blobUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();

  // Clean up ObjectURL and DOM element
  setTimeout(() => {
    document.body.removeChild(anchor);
    URL.revokeObjectURL(blobUrl);
  }, 1000);

  return true;
}
