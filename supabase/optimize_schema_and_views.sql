-- ==============================================================================
-- PROJECT HYDRA / SMD PRIME - OPTIMIZED SUPABASE SCHEMA & CATALOG VIEWS
-- Tables: movies, movie_files, download_links, genres, movie_genres
-- Features: Instant multi-quality indexing, RLS, & single-query view for UI
-- ==============================================================================

-- 0. Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. MOVIES TABLE (Master Metadata)
CREATE TABLE IF NOT EXISTS public.movies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title VARCHAR(255) NOT NULL,
  slug VARCHAR(255) UNIQUE NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  mime_type VARCHAR(100) NOT NULL DEFAULT 'video/x-matroska',
  file_size_bytes BIGINT NOT NULL,
  hf_raw_url TEXT NOT NULL,
  poster_url TEXT,
  backdrop_url TEXT,
  description TEXT,
  rating NUMERIC(3, 1) DEFAULT 8.9,
  release_year INT DEFAULT 2026,
  duration VARCHAR(50) DEFAULT '2h 15m',
  chunk_urls TEXT[],
  obfuscated BOOLEAN DEFAULT true,
  chunk_size_mb INT DEFAULT 100,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. MOVIE_FILES TABLE (Quality Specific Variants)
CREATE TABLE IF NOT EXISTS public.movie_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
  quality VARCHAR(20) NOT NULL DEFAULT '1080p',
  file_name VARCHAR(255) NOT NULL,
  mime_type VARCHAR(100) NOT NULL DEFAULT 'video/x-matroska',
  file_size_bytes BIGINT NOT NULL,
  hf_raw_url TEXT NOT NULL,
  chunk_urls TEXT[],
  obfuscated BOOLEAN DEFAULT true,
  chunk_size_mb INT DEFAULT 100,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT movie_files_unique_movie_quality UNIQUE (movie_id, quality)
);

-- 3. GENRES & MOVIE_GENRES
CREATE TABLE IF NOT EXISTS public.genres (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(100) UNIQUE NOT NULL,
  slug VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS public.movie_genres (
  movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
  genre_id UUID NOT NULL REFERENCES public.genres(id) ON DELETE CASCADE,
  PRIMARY KEY (movie_id, genre_id)
);

-- 4. DOWNLOAD LINKS
CREATE TABLE IF NOT EXISTS public.download_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
  token_jti VARCHAR(255) UNIQUE NOT NULL,
  client_ip VARCHAR(100) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '2 hours',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. HIGH-PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS idx_movies_slug ON public.movies(slug);
CREATE INDEX IF NOT EXISTS idx_movie_files_movie_id ON public.movie_files(movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_files_quality ON public.movie_files(quality);

-- 6. ROW LEVEL SECURITY (RLS) POLICIES
ALTER TABLE public.movies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.movie_files ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public can view movies" ON public.movies;
CREATE POLICY "Public can view movies" ON public.movies FOR SELECT USING (true);

DROP POLICY IF EXISTS "Service role & Admin full access on movies" ON public.movies;
CREATE POLICY "Service role & Admin full access on movies" ON public.movies FOR ALL USING (true);

DROP POLICY IF EXISTS "Public can view movie files" ON public.movie_files;
CREATE POLICY "Public can view movie files" ON public.movie_files FOR SELECT USING (true);

DROP POLICY IF EXISTS "Service role & Admin full access on movie_files" ON public.movie_files;
CREATE POLICY "Service role & Admin full access on movie_files" ON public.movie_files FOR ALL USING (true);

-- 7. DEVELOPER-FRIENDLY COMBINED CATALOG VIEW FOR UI
CREATE OR REPLACE VIEW public.v_movies_full_catalog AS
SELECT 
    m.id,
    m.title,
    m.slug,
    m.file_name,
    m.mime_type,
    m.file_size_bytes,
    m.hf_raw_url,
    m.chunk_urls,
    m.poster_url,
    m.backdrop_url,
    m.description,
    m.rating,
    m.release_year,
    m.duration,
    m.obfuscated,
    m.chunk_size_mb,
    m.created_at,
    m.updated_at,
    COALESCE(
        json_agg(
            json_build_object(
                'id', mf.id,
                'quality', mf.quality,
                'file_name', mf.file_name,
                'file_size_bytes', mf.file_size_bytes,
                'hf_raw_url', mf.hf_raw_url,
                'chunk_urls', mf.chunk_urls,
                'obfuscated', mf.obfuscated,
                'chunk_size_mb', mf.chunk_size_mb
            )
        ) FILTER (WHERE mf.id IS NOT NULL),
        '[]'::json
    ) AS available_qualities
FROM public.movies m
LEFT JOIN public.movie_files mf ON m.id = mf.movie_id
GROUP BY m.id;
