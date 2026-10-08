/**
 * Project Hydra - Lightweight Supabase REST API Client
 * Bypasses heavy JS SDK to ensure sub-5ms worker execution.
 */

/**
 * Fetch movie metadata by ID from Supabase
 * @param {string} movieId Movie UUID
 * @param {Object} env Cloudflare Worker environment bindings
 * @returns {Promise<Object|null>} Movie object or null
 */
export async function fetchMovieFromSupabase(movieId, env) {
  if (!env.SUPABASE_URL) {
    throw new Error('SUPABASE_URL environment variable is missing');
  }

  const apiKey = env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY;
  if (!apiKey) {
    throw new Error('Supabase API Key is missing in environment variables');
  }

  const endpoint = `${env.SUPABASE_URL.replace(/\/$/, '')}/rest/v1/movies?id=eq.${encodeURIComponent(movieId)}&select=id,title,slug,file_name,mime_type,file_size_bytes,hf_raw_url`;

  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      'apikey': apiKey,
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    }
  });

  if (!response.ok) {
    console.error(`Supabase REST error [${response.status}]: ${await response.text()}`);
    return null;
  }

  const data = await response.json();
  if (Array.isArray(data) && data.length > 0) {
    return data[0];
  }

  return null;
}

/**
 * Audit log a download token generation
 * @param {Object} auditData Audit details
 * @param {Object} env Environment bindings
 */
export async function logDownloadLinkToSupabase(auditData, env) {
  const apiKey = env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY;
  if (!apiKey || !env.SUPABASE_URL) return;

  const endpoint = `${env.SUPABASE_URL.replace(/\/$/, '')}/rest/v1/download_links`;

  try {
    await fetch(endpoint, {
      method: 'POST',
      headers: {
        'apikey': apiKey,
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
      },
      body: JSON.stringify({
        movie_id: auditData.movie_id,
        token_jti: auditData.token_jti,
        client_ip: auditData.client_ip,
        expires_at: auditData.expires_at
      })
    });
  } catch (err) {
    console.error('Failed to write download link audit log to Supabase:', err);
  }
}
