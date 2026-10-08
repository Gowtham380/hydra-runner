/**
 * SMD PRIME - ServiceWorker Mesh Streamer Helper
 * Manages ServiceWorker Registration and Triggering Native Chrome Downloads
 */

let swRegistration = null;

/**
 * Register SW-Mesh Service Worker
 */
export async function registerSwMesh() {
  if ('serviceWorker' in navigator) {
    try {
      swRegistration = await navigator.serviceWorker.register('/sw-mesh.js', {
        scope: '/'
      });
      console.log('🚀 [SW-Mesh] ServiceWorker registered successfully with scope:', swRegistration.scope);
      return swRegistration;
    } catch (err) {
      console.warn('⚠️ [SW-Mesh] ServiceWorker registration failed:', err);
    }
  } else {
    console.warn('⚠️ [SW-Mesh] ServiceWorker not supported in this browser environment.');
  }
  return null;
}

/**
 * Trigger Native Chrome Stream Download via SW-Mesh
 * @param {Object} movie Movie object with chunk_urls, slug, title, file_size_bytes
 * @param {Array<string>} fallbackUrls Optional array of fallback URLs
 */
export async function triggerSwMeshDownload(movie, fallbackUrls = []) {
  if (!movie) {
    throw new Error('Invalid movie payload');
  }

  const slug = movie.slug || movie.id || 'movie';
  const chunkUrls = (movie.chunk_urls && movie.chunk_urls.length > 0)
    ? movie.chunk_urls
    : ((movie.urls && movie.urls.length > 0) ? movie.urls : fallbackUrls);

  // If a direct single stream URL is available (or single chunk URL), trigger native browser download directly
  const directUrl = movie.download_url || movie.stream_url || movie.url;
  if (directUrl || (chunkUrls && chunkUrls.length === 1 && !chunkUrls[0].includes('.bin') && !chunkUrls[0].includes('part_'))) {
    const targetUrl = directUrl || chunkUrls[0];
    const fileName = movie.file_name || `${slug}.mp4`;
    
    const a = document.createElement('a');
    a.href = targetUrl;
    a.download = fileName;
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    return;
  }

  if (!chunkUrls || chunkUrls.length === 0) {
    throw new Error('No valid download URLs or chunks available.');
  }

  // Ensure Service Worker is registered and active for multi-part mesh downloads
  if (!navigator.serviceWorker.controller) {
    await registerSwMesh();
    await new Promise(resolve => setTimeout(resolve, 300));
  }

  const hfToken = import.meta.env.VITE_HF_TOKEN || '';

  const payload = {
    title: movie.title || movie.name || 'Movie',
    slug: slug,
    file_name: movie.file_name || `${slug}.mp4`,
    file_size_bytes: movie.file_size_bytes || movie.size_bytes || 2684354560, // Default ~2.5GB if unknown
    mime_type: movie.mime_type || 'video/mp4',
    chunk_urls: chunkUrls,
    hf_token: hfToken
  };

  // Post metadata to SW scope
  if (navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: 'REGISTER_STREAM',
      slug: slug,
      movie: payload
    });
  }

  // Encode metadata in URL query for maximum reliability
  const metaParam = encodeURIComponent(JSON.stringify(payload));
  const streamUrl = `/sw-stream/${slug}?meta=${metaParam}`;

  // Trigger native Chrome download bar via <a> link anchor
  const a = document.createElement('a');
  a.href = streamUrl;
  a.download = payload.file_name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
