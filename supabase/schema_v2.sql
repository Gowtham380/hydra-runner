-- ==============================================================================
-- SUPABASE POSTGRESQL SCHEMA & ROW LEVEL SECURITY (RLS) POLICIES
-- Tables: users, movies, movie_sources, watch_history
-- Role Access: free (480p/720p), vip (1080p/4K), admin (full access & inserts)
-- ==============================================================================

-- 0. Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------------------------
-- 1. USERS TABLE
-- Roles: 'free', 'vip', 'admin'
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id VARCHAR(100) UNIQUE,
    username VARCHAR(100),
    first_name VARCHAR(100),
    avatar_url TEXT,
    role VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (role IN ('free', 'vip', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure missing columns exist if table was previously created
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (role IN ('free', 'vip', 'admin'));
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS telegram_user_id VARCHAR(100);

-- ------------------------------------------------------------------------------
-- 2. MOVIES TABLE
-- Core Movie Metadata
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.movies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    poster_url TEXT,
    backdrop_url TEXT,
    release_year INT DEFAULT 2026,
    rating NUMERIC(3, 1) DEFAULT 8.0,
    duration VARCHAR(50) DEFAULT '2h 15m',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 3. MOVIE_SOURCES TABLE
-- Stream sources linked to movies with resolutions: 480p, 720p, 1080p, 4K
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.movie_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    resolution VARCHAR(20) NOT NULL CHECK (resolution IN ('480p', '720p', '1080p', '4K')),
    xor_hash_url TEXT NOT NULL,
    file_size_bytes BIGINT DEFAULT 0,
    mime_type VARCHAR(100) DEFAULT 'video/x-matroska',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------------------
-- 4. WATCH_HISTORY TABLE
-- Telemetry and Continue Watching state
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.watch_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    telegram_user_id VARCHAR(100),
    movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    progress_seconds INT DEFAULT 0,
    duration_seconds INT DEFAULT 0,
    last_watched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT watch_history_user_movie_unique UNIQUE (telegram_user_id, movie_id)
);

-- ------------------------------------------------------------------------------
-- 5. INDEXES FOR HIGH-PERFORMANCE QUERYING
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON public.users(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_movies_slug ON public.movies(slug);
CREATE INDEX IF NOT EXISTS idx_movie_sources_movie_id ON public.movie_sources(movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_sources_resolution ON public.movie_sources(resolution);
CREATE INDEX IF NOT EXISTS idx_watch_history_user_movie ON public.watch_history(telegram_user_id, movie_id);

-- ------------------------------------------------------------------------------
-- 6. HELPER FUNCTION TO GET CURRENT USER ROLE
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_current_user_role()
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT COALESCE(
    (SELECT role FROM public.users WHERE id = auth.uid()),
    (SELECT role FROM public.users WHERE telegram_user_id = NULLIF(current_setting('request.jwt.claims', true)::json->>'telegram_user_id', '')),
    'free'
  );
$$;

-- ------------------------------------------------------------------------------
-- 7. ROW LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.movies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.movie_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watch_history ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------
-- A. USERS POLICIES
-- ----------------------------------------
DROP POLICY IF EXISTS "Users can view their own profile or admin view all" ON public.users;
CREATE POLICY "Users can view their own profile or admin view all"
ON public.users FOR SELECT
USING (
    auth.uid() = id
    OR telegram_user_id = NULLIF(current_setting('request.jwt.claims', true)::json->>'telegram_user_id', '')
    OR public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

DROP POLICY IF EXISTS "Users can update their own profile or admin update all" ON public.users;
CREATE POLICY "Users can update their own profile or admin update all"
ON public.users FOR UPDATE
USING (
    auth.uid() = id
    OR telegram_user_id = NULLIF(current_setting('request.jwt.claims', true)::json->>'telegram_user_id', '')
    OR public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

DROP POLICY IF EXISTS "Allow user profile registration" ON public.users;
CREATE POLICY "Allow user profile registration"
ON public.users FOR INSERT
WITH CHECK (true);

-- ----------------------------------------
-- B. MOVIES POLICIES
-- Read: Everyone (Free, VIP, Admin, Public)
-- Insert: ONLY Admins (or service_role)
-- ----------------------------------------
DROP POLICY IF EXISTS "Anyone can view movies catalog" ON public.movies;
CREATE POLICY "Anyone can view movies catalog"
ON public.movies FOR SELECT
USING (true);

DROP POLICY IF EXISTS "Only Admins can insert movies" ON public.movies;
CREATE POLICY "Only Admins can insert movies"
ON public.movies FOR INSERT
WITH CHECK (
    public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

DROP POLICY IF EXISTS "Only Admins can update movies" ON public.movies;
CREATE POLICY "Only Admins can update movies"
ON public.movies FOR UPDATE
USING (
    public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

DROP POLICY IF EXISTS "Only Admins can delete movies" ON public.movies;
CREATE POLICY "Only Admins can delete movies"
ON public.movies FOR DELETE
USING (
    public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

-- ----------------------------------------
-- C. MOVIE_SOURCES POLICIES
-- Free Users: Only read 480p and 720p
-- VIP Users: Read 1080p and 4K (plus 480p/720p)
-- Admin Users: Read all & modify all
-- ----------------------------------------
DROP POLICY IF EXISTS "Role-based resolution access for movie_sources" ON public.movie_sources;
CREATE POLICY "Role-based resolution access for movie_sources"
ON public.movie_sources FOR SELECT
USING (
    -- Admin & Service Role can view all sources
    public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
    -- VIP users can view 1080p, 4K (and all resolutions)
    OR (public.get_current_user_role() = 'vip' AND resolution IN ('480p', '720p', '1080p', '4K'))
    -- Free users can ONLY view 480p and 720p
    OR (public.get_current_user_role() = 'free' AND resolution IN ('480p', '720p'))
);

DROP POLICY IF EXISTS "Only Admins can manage movie sources" ON public.movie_sources;
CREATE POLICY "Only Admins can manage movie sources"
ON public.movie_sources FOR ALL
USING (
    public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

-- ----------------------------------------
-- D. WATCH_HISTORY POLICIES
-- Users manage their own watch history
-- ----------------------------------------
DROP POLICY IF EXISTS "Users can view their watch history" ON public.watch_history;
CREATE POLICY "Users can view their watch history"
ON public.watch_history FOR SELECT
USING (
    user_id = auth.uid()
    OR telegram_user_id = NULLIF(current_setting('request.jwt.claims', true)::json->>'telegram_user_id', '')
    OR public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);

DROP POLICY IF EXISTS "Users can record watch history" ON public.watch_history;
CREATE POLICY "Users can record watch history"
ON public.watch_history FOR INSERT
WITH CHECK (true);

DROP POLICY IF EXISTS "Users can update their watch history" ON public.watch_history;
CREATE POLICY "Users can update their watch history"
ON public.watch_history FOR UPDATE
USING (
    user_id = auth.uid()
    OR telegram_user_id = NULLIF(current_setting('request.jwt.claims', true)::json->>'telegram_user_id', '')
    OR public.get_current_user_role() = 'admin'
    OR auth.role() = 'service_role'
);
