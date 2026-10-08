-- ==============================================================================
-- PROJECT HYDRA - MINIMALIST 2-TABLE DATABASE SCHEMA
-- Table 1: MOVIES (One Master Record per Title with unique UUID)
-- Table 2: MOVIE_FILES (All Quality Variants/Rips referencing movie_id UUID)
-- ==============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------------------------
-- CLEANUP LEGACY TABLES & VIEWS (Optional/Clean Migration)
-- ------------------------------------------------------------------------------
DROP VIEW IF EXISTS public.v_movies_full_catalog CASCADE;
DROP TABLE IF EXISTS public.movie_genres CASCADE;
DROP TABLE IF EXISTS public.genres CASCADE;
DROP TABLE IF EXISTS public.download_links CASCADE;

-- ------------------------------------------------------------------------------
-- 1. MOVIES TABLE (Master Record per Title - Unique UUID)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.movies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    poster_url TEXT,
    backdrop_url TEXT,
    release_year INT DEFAULT 2026,
    rating NUMERIC(3, 1) DEFAULT 8.9,
    duration VARCHAR(50) DEFAULT '2h 15m',
    default_quality_label VARCHAR(100) DEFAULT '1080P FULL HD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safely add missing columns if table already exists
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS release_year INT DEFAULT 2026;
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS rating NUMERIC(3, 1) DEFAULT 8.9;
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS duration VARCHAR(50) DEFAULT '2h 15m';
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS default_quality_label VARCHAR(100) DEFAULT '1080P FULL HD';
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS backdrop_url TEXT;
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE public.movies ADD COLUMN IF NOT EXISTS poster_url TEXT;

-- ------------------------------------------------------------------------------
-- 2. MOVIE_FILES TABLE (All File Variants linked to Master Movie UUID)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.movie_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    quality VARCHAR(50) NOT NULL DEFAULT '1080p',
    rip_type VARCHAR(50) DEFAULT 'WEB-DL',
    codec VARCHAR(50) DEFAULT 'x264',
    audio_languages TEXT DEFAULT 'Tamil',
    quality_label VARCHAR(100) DEFAULT '1080P FULL HD',
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL DEFAULT 'video/x-matroska',
    file_size_bytes BIGINT NOT NULL,
    hf_raw_url TEXT NOT NULL,
    chunk_urls TEXT[],
    obfuscated BOOLEAN DEFAULT TRUE,
    chunk_size_mb INT DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safely add missing columns if table already exists
ALTER TABLE public.movie_files ADD COLUMN IF NOT EXISTS rip_type VARCHAR(50) DEFAULT 'WEB-DL';
ALTER TABLE public.movie_files ADD COLUMN IF NOT EXISTS codec VARCHAR(50) DEFAULT 'x264';
ALTER TABLE public.movie_files ADD COLUMN IF NOT EXISTS audio_languages TEXT DEFAULT 'Tamil';
ALTER TABLE public.movie_files ADD COLUMN IF NOT EXISTS quality_label VARCHAR(100) DEFAULT '1080P FULL HD';

-- ------------------------------------------------------------------------------
-- 3. HIGH-PERFORMANCE INDEXES
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_movies_slug ON public.movies(slug);
CREATE INDEX IF NOT EXISTS idx_movies_created_at ON public.movies(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_movie_files_movie_id ON public.movie_files(movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_files_quality ON public.movie_files(quality);
CREATE INDEX IF NOT EXISTS idx_movie_files_rip_type ON public.movie_files(rip_type);

-- ------------------------------------------------------------------------------
-- 4. UNIFIED CATALOG VIEW
-- ------------------------------------------------------------------------------
DROP VIEW IF EXISTS public.v_movies_catalog CASCADE;

CREATE OR REPLACE VIEW public.v_movies_catalog AS
SELECT 
    m.id AS movie_id,
    f.id AS file_id,
    m.title,
    m.slug,
    f.quality,
    f.rip_type,
    f.codec,
    f.audio_languages,
    f.quality_label,
    f.file_name,
    f.mime_type,
    f.file_size_bytes,
    f.hf_raw_url,
    f.chunk_urls,
    f.obfuscated,
    f.chunk_size_mb,
    m.poster_url,
    m.backdrop_url,
    m.description,
    m.release_year,
    m.rating,
    m.duration,
    m.created_at,
    m.updated_at
FROM public.movies m
LEFT JOIN public.movie_files f ON m.id = f.movie_id;

-- ------------------------------------------------------------------------------
-- 5. ROW LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------
ALTER TABLE public.movies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.movie_files ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read for movies" ON public.movies;
CREATE POLICY "Public read for movies" ON public.movies FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read for movie_files" ON public.movie_files;
CREATE POLICY "Public read for movie_files" ON public.movie_files FOR SELECT USING (true);
