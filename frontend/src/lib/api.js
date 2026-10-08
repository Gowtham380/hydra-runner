/**
 * Project Hydra API Helper for Edge Worker Token Generation
 */

const WORKER_BASE_URL = import.meta.env.VITE_WORKER_URL || 'http://127.0.0.1:8787';

/**
 * Generate a signed download JWT and Intent link for a movie
 * @param {string} movieId Movie UUID
 * @returns {Promise<{ download_url: string, intent_url: string, token: string }>}
 */
export async function generateDownloadLink(movieId) {
  try {
    const res = await fetch(`${WORKER_BASE_URL}/api/token/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        movie_id: movieId,
        expires_in_seconds: 86400 // 24 Hours
      })
    });

    if (!res.ok) {
      throw new Error(`Worker API returned status ${res.status}`);
    }

    return await res.json();
  } catch (err) {
    console.warn('Worker API reachability error, falling back to client-simulated link:', err);

    // Development fallback mock when worker is offline locally
    const mockToken = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI${movieId.substring(0, 8)}...`;
    return {
      download_url: `${WORKER_BASE_URL}/dl/${mockToken}`,
      intent_url: `intent://${new URL(WORKER_BASE_URL).host}/dl/${mockToken}#Intent;scheme=https;package=com.android.chrome;end`,
      token: mockToken
    };
  }
}

/**
 * Format bytes to readable string (GB, MB)
 */
export function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  if (i === 0) return `${bytes} B`;
  const val = bytes / Math.pow(k, i);
  if (sizes[i] === 'MB') {
    return `${Math.round(val)} MB`;
  }
  if (sizes[i] === 'GB') {
    return `${val.toFixed(1)} GB`;
  }
  return `${val.toFixed(1)} ${sizes[i]}`;
}
