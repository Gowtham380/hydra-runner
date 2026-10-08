import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://placeholder.supabase.co';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'placeholder_anon_key';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// Fallback Mock Catalog Data for instant UI preview when DB is not populated yet
export const MOCK_MOVIES = [
  {
    id: 'e01a87b1-4b11-4a12-87a1-1234567890ab',
    title: 'Avatar: The Way of Water',
    slug: 'avatar-the-way-of-water-2022',
    file_name: 'Avatar.The.Way.of.Water.2022.2160p.UHD.Remux.mkv',
    mime_type: 'video/x-matroska',
    file_size_bytes: 48318382080, // ~45 GB
    poster_url: 'https://image.tmdb.org/t/p/w500/t6HIqrRAclMCA60NsSmeqe9RmNV.jpg',
    backdrop_url: 'https://image.tmdb.org/t/p/w1280/vL5LR6WdxWPjUnFRiW3pjWGl02D.jpg',
    rating: 7.7,
    release_year: 2022,
    description: 'Jake Sully lives with his newfound family formed on the extrasolar moon Pandora. Once a familiar threat returns, Jake must work with Neytiri and the army of the Na\'vi race to protect their home.',
    created_at: new Date().toISOString()
  },
  {
    id: 'f02b98c2-5c22-5b23-98b2-2345678901bc',
    title: 'Oppenheimer',
    slug: 'oppenheimer-2023-4k',
    file_name: 'Oppenheimer.2023.2160p.IMAX.UHD.BluRay.mkv',
    mime_type: 'video/x-matroska',
    file_size_bytes: 69793218560, // ~65 GB
    poster_url: 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg',
    backdrop_url: 'https://image.tmdb.org/t/p/w1280/fm6K8OfiRs9RWRfqODiGOfWo22O.jpg',
    rating: 8.1,
    release_year: 2023,
    description: 'The story of J. Robert Oppenheimer\'s role in the development of the atomic bomb during World War II.',
    created_at: new Date().toISOString()
  },
  {
    id: 'a03c09d3-6d33-6c34-09c3-3456789012cd',
    title: 'Interstellar',
    slug: 'interstellar-2014-imax',
    file_name: 'Interstellar.2014.2160p.IMAX.UHD.Remux.mkv',
    mime_type: 'video/x-matroska',
    file_size_bytes: 78383182080, // ~73 GB
    poster_url: 'https://image.tmdb.org/t/p/w500/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg',
    backdrop_url: 'https://image.tmdb.org/t/p/w1280/xJHokMbljvjADYdit5fKSuV0vEG.jpg',
    rating: 8.4,
    release_year: 2014,
    description: 'The adventures of a group of explorers who make use of a newly discovered wormhole to surpass the limitations on human space travel and conquer the vast distances involved in an interstellar voyage.',
    created_at: new Date().toISOString()
  }
];

// Helper to sync Telegram User Profile with Supabase
export async function syncTelegramUser(user) {
  if (!user || !user.id) return null;
  try {
    const payload = {
      telegram_user_id: String(user.id),
      username: user.username || '',
      first_name: user.first_name || '',
      avatar_url: user.photo_url || '',
      last_seen_at: new Date().toISOString()
    };
    const { data, error } = await supabase
      .from('users')
      .upsert(payload, { onConflict: 'telegram_user_id' })
      .select()
      .single();
    if (!error) return data;
  } catch (e) {
    console.warn('syncTelegramUser note:', e);
  }
  return null;
}

// Helper to save Watch Progress Telemetry (Continue Watching Engine)
export async function saveWatchProgress(telegramUserId, movieId, progressSeconds, durationSeconds) {
  if (!telegramUserId || !movieId || progressSeconds < 5) return;
  try {
    await supabase.from('user_watch_history').upsert({
      telegram_user_id: String(telegramUserId),
      movie_id: movieId,
      progress_seconds: Math.floor(progressSeconds),
      duration_seconds: Math.floor(durationSeconds),
      last_watched_at: new Date().toISOString()
    }, { onConflict: 'telegram_user_id,movie_id' });
  } catch (e) {
    console.warn('saveWatchProgress note:', e);
  }
}

// Fetch user watch history for Continue Watching row
export async function fetchUserWatchHistory(telegramUserId) {
  if (!telegramUserId) return [];
  try {
    const { data, error } = await supabase
      .from('user_watch_history')
      .select('*, movie:movies(*)')
      .eq('telegram_user_id', String(telegramUserId))
      .order('last_watched_at', { ascending: false });
    if (!error && data) return data;
  } catch (e) {}
  return [];
}

