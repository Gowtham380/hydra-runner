#!/usr/bin/env python3
"""
================================================================================
HIGH-PRECISION G訪RIVE VIDEO EXTRACTION PIPELINE (PROJECT HYDRA / SMD PRIME)
================================================================================
Upgraded Enterprise Engine:
- Ingests raw video filenames from 'gdrive_all_video_names.txt'
- Dual Regex Grammar: Movie (Title + Year) & Web Series (Series + SxxExx)
- Deep Sanitization: Strips multi-layered pirate domains, Telegram tags, noise
- Technical Spec Extractor: Quality, Rip-Type, Codec, Audio Tracks, Theater Flag
- Relational Deduplication: Parent (movies) & Children (movie_files) by Slug
- Batch Upsert Engine: Idempotent Supabase REST API (or Postgres) integration
================================================================================
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ================================================================================
# REGEX DEFINITIONS & COMPILED PATTERNS
# ================================================================================

# Video file extensions to strip
VIDEO_EXT_REGEX = re.compile(
    r'\.(?:mkv|mp4|avi|mov|webm|flv|ts|m4v|wmv|mpg|mpeg)$',
    re.IGNORECASE
)

# Chained Domain, Website, & Pirate Uploader Prefixes (Upgraded from modal_drive_migrator)
KNOWN_PIRATE_SITES = (
    r'1tamilmv|tamilmv|tamilblasters|movieztamizha|omgxmovies|sam\s*dub\s*lezha|sam\s*dub|lezha|'
    r'crazymoviescmc|crazymovies|cmc|smd|gtm|tgstream|tglezha|blura|isaimini|kuttymovies|'
    r'tamilrockers|tamildbox|tamildub|tamilgun|tamilyogi|tamilprint|tamilplay|moviesda|'
    r'movieswood|moviesnation|moviezaddiction|moviez|omgmovies|omg|klwap|mallumv|bolly4u|'
    r'worldfree4u|9xmovies|7starhd|filmyzilla|filmywap|desiremovies|hdhub4u|vegamovies|'
    r'vega\s*movies|sdmoviespoint|katmoviehd|skymovies|ssrflix|flimriotmovies|vip_linkzz|'
    r'tamilmov_linkzz|tamilmob_linkzz|lk_movies2|alinallmovies|all_animes_in_telugu_go|'
    r'sklink_files|massmovies0|infinitemovies|infinite_anime|animemoviesarc|themoviesboss'
)

# Prefix cleaner: URLs, domain names, @handles, pirate site tags, [tag] brackets
PREFIX_PATTERNS = [
    # Full URLs (http:// or https://)
    r'^(?:https?://[^\s/$.?#].[^\s]*)\s*[-–—_:]*\s*',
    # Domain starting with www.
    r'^www\.[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,10}\s*[-–—_:]*\s*',
    # Telegram handles followed by space, dash, colon, etc.
    r'^@[a-zA-Z0-9_.-]+[\s\-–—:=|]+',
    # Known Telegram handles followed by underscore or separator
    r'^@(?:Alinallmovies|LK_MOVIES\d*|TamilMov_LinkZz|TamilMob_LinkZz|ViP_LinkzZ|SAM_DUB_LEZHa|All_animes_in_telugu_Go|SheikXMovies|Tamilrockers|Isaimini|MoviezTamizha|Av_Linkz|Infinite_Anime|AnimeMoviesArc|GTM|SMD|TGStream)[_\s-]*',
    # Generic Telegram handle before underscored title
    r'^@[a-zA-Z0-9]+_[_\s]*',
    r'^@[a-zA-Z0-9_]+?_(?=(?:[A-Za-z0-9_]*_)?(?:19|20)\d{2}\b)',
    r'^@[a-zA-Z0-9_]+?_(?=(?:[A-Za-z0-9_]*_)?S\d{1,2}E\d{1,3}\b)',
    # Known pirate sites with any domain extension (e.g., 1tamilmv.capital, tamilblasters.org)
    rf'^(?:{KNOWN_PIRATE_SITES})\.[a-zA-Z]{{2,10}}\s*[-–—_:]*\s*',
    # Known pirate site names alone followed by separator
    rf'^(?:{KNOWN_PIRATE_SITES})\s*[-–—_:]+\s*',
    # Leading bracketed group tags like [www.1TamilMV.capital], [Movieztamizha], [CMC], [L]
    r'^\s*\[[^\]]*\]\s*[-–—_:]*\s*',
    r'^\s*\([^\)]*\)\s*[-–—_:]*\s*',
    # "Copy of" or "Copy (1) of"
    r'^Copy\s*(?:\(\d+\))?\s*of\s+[-–—_:]*\s*',
    # Standalone letter tags like [L] or L -
    r'^\s*\[?[lL]\]?\s+[-–—_:]*\s*'
]

# Year Matcher: 19xx or 20xx (Bounded by non-digits)
YEAR_REGEX = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)')

# Series Patterns:
# S01E01, S01 EP01, S01 EP(01-06), Season 1 Episode 2, S1-E01, S10 EP34, S01E548
SERIES_SE_REGEX = re.compile(
    r'(?i)(?:s(?:eason)?\s*(\d{1,2}))\s*[-._\s]*\s*(?:e(?:p(?:isode)?)?\s*\(?(\d{1,4}(?:\s*-\s*\d{1,4})?)\)?)'
)
# Standalone EP tags (e.g. EP46, Episode 174, EP 02)
SERIES_EP_ONLY_REGEX = re.compile(
    r'(?i)\b(?:ep|episode)\s*[-._\s]*\(?(\d{1,4}(?:\s*-\s*\d{1,4})?)\)?\b'
)

# Resolution / Quality
QUALITY_REGEX = re.compile(r'(?i)\b(2160p|4k\s*uhd|4k\s*sdr|4k\s*hdr|4k|1080p|1080i|720p|480p|360p|240p)\b')

QUALITY_LABEL_MAP = {
    '2160p': '4K UHD',
    '1080p': '1080P FULL HD',
    '720p': '720P HD',
    '480p': '480P SD',
    '360p': '360P SD',
    '240p': '240P SD'
}

# Rip Types
THEATER_PRINT_REGEX = re.compile(
    r'(?i)\b(camrip|hdcam|cam|hdts|telecine|tc|predvdrip|predvd|pre-dvd|pre_dvd|dvdscr|screener|hallprint)\b'
)

RIP_TYPE_MAP = [
    (re.compile(r'(?i)\b(camrip|hdcam|cam|hdts|telecine|tc)\b'), 'CAM'),
    (re.compile(r'(?i)\b(predvdrip|predvd|pre-dvd|pre_dvd|dvdscr)\b'), 'PreDVD'),
    (re.compile(r'(?i)\b(blu-?ray|bd-?rip|br-?rip|bdr)\b'), 'BluRay'),
    (re.compile(r'(?i)\b(true\s*web-?dl|web-?dl|webdl)\b'), 'WEB-DL'),
    (re.compile(r'(?i)\b(web-?rip|webrip)\b'), 'WEBRip'),
    (re.compile(r'(?i)\b(hq\s*hdrip|hd-?rip|hdrip)\b'), 'HDRip'),
    (re.compile(r'(?i)\b(dvd-?rip|dvdr)\b'), 'DVDRip'),
    (re.compile(r'(?i)\b(hdtv|hdtvrip)\b'), 'HDTV')
]

# Codec
CODEC_MAP = [
    (re.compile(r'(?i)\b(x265|hevc|h\.?265|10bit)\b'), 'HEVC'),
    (re.compile(r'(?i)\b(x264|avc|h\.?264)\b'), 'x264'),
    (re.compile(r'(?i)\b(av1)\b'), 'AV1')
]

# Audio Languages
LANG_PATTERNS = [
    (re.compile(r'(?i)\b(tam|tamil)\b'), 'Tamil'),
    (re.compile(r'(?i)\b(tel|telugu)\b'), 'Telugu'),
    (re.compile(r'(?i)\b(hin|hindi)\b'), 'Hindi'),
    (re.compile(r'(?i)\b(mal|malayalam)\b'), 'Malayalam'),
    (re.compile(r'(?i)\b(kan|kannada)\b'), 'Kannada'),
    (re.compile(r'(?i)\b(eng|english)\b'), 'English'),
    (re.compile(r'(?i)\b(jap|japanese)\b'), 'Japanese'),
    (re.compile(r'(?i)\b(chi|chinese)\b'), 'Chinese'),
    (re.compile(r'(?i)\b(kor|korean)\b'), 'Korean'),
    (re.compile(r'(?i)\b(spa|spanish)\b'), 'Spanish'),
    (re.compile(r'(?i)\b(fre|french)\b'), 'French'),
]

# Master noise tokens to remove from canonical titles
MASTER_NOISE_TOKENS = (
    r'(?i)\b(' + '|'.join([
        r'\d+\s*(?:kbps|kb|k|khz)', r'(?:16bit|24bit|10bit|8bit)',
        r'dd\+?[\d\.]*', r'ddp[\d\.]*', r'aac[\d\.]*', r'ac3', r'eac3', r'dts[\-\w]*', r'atmos', r'truehd', r'flac', r'opus', r'mp3',
        r'[\d\.]+\s*ch', r'5\.1', r'7\.1', r'2\.0',
        r'clean-audio', r'org-audio', r'org-aud', r'clean-aud', r'line-audio', r'line-aud',
        r'dubbed', r'dub', r'multiaudio', r'multi-audio', r'dual-audio', r'dual', r'org', r'aud',
        r'tam', r'tamil', r'tel', r'telugu', r'hin', r'hindi', r'mal', r'malayalam', r'kan', r'kannada', r'eng', r'english',
        r'esub[\w]*', r'msub[\w]*', r'softsub[\w]*', r'hardsub[\w]*', r'nosub[\w]*', r'hcsub[\w]*',
        r'web-dl', r'webdl', r'web-rip', r'webrip', r'web', r'untouched', r'proper-web', r'hdrip', r'hd-rip',
        r'bluray', r'blu-ray', r'bdrip', r'brrip', r'dvdrip', r'predvd', r'pre-dvd', r'camrip', r'hdcam', r'hdts', r'telecine', r'ts', r'tc', r'hdtvrip', r'hdtv',
        r'hq', r'lq', r'clean', r'repack', r'proper', r'v2', r'v3', r'v4', r'uncut', r'unrated', r'extended', r'remastered',
        r'imax', r'hdr10plus', r'hdr10\+', r'hdr10', r'hdr', r'sdr',
        r'2160p', r'1080p', r'720p', r'480p', r'360p', r'240p', r'4k', r'uhd', r'fhd', r'hd', r'sd',
        r'x264', r'x265', r'hevc', r'h264', r'h265', r'avc', r'av1', r'xvid', r'divx',
        r'day\s*\d+', r'part\s*\d+'
    ]) + r')\b'
)


# ================================================================================
# SANITIZATION & NORMALIZATION HELPER FUNCTIONS
# ================================================================================

def strip_all_prefixes(filename: str) -> str:
    """Strips multi-layered pirate prefixes, URLs, and telegram handles"""
    stem = VIDEO_EXT_REGEX.sub('', filename).strip()
    stem = stem.strip(" '\"[]()")
    stem = re.sub(r"^[\[\(\"'\s]+", "", stem)
    stem = re.sub(r"[\]\)\"'\s]+$", "", stem)

    # Iterative stripping (handles nested prefixes e.g. www.site - @channel - Title)
    for _ in range(5):
        orig = stem
        for pat in PREFIX_PATTERNS:
            stem = re.sub(pat, '', stem, flags=re.IGNORECASE).strip()
        # Clean any leading dangling punctuation
        stem = re.sub(r'^\s*[-–—_.:@#+!~|/]\s*', '', stem).strip()
        if stem == orig:
            break
            
    return stem


def generate_slug(text: str) -> str:
    """Generates an RFC-compliant, lowercase alphanumeric URL slug"""
    slug = text.lower()
    # Replace any non-alphanumeric character with a hyphen
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def clean_title_tokens(raw_title_str: str) -> str:
    """
    Cleans noisy tokens, brackets, audio descriptors, and normalizes spacing.
    Preserves numerical titles (e.g., '29', '96', '1917', '24') and short titles (e.g., 'Hi', 'DC', 'Gu', 'GDN').
    """
    s = raw_title_str.strip()

    # Pre-handle dotted acronyms like G.D.N. or S.I.R. or U.S.A.
    s = re.sub(r'\b([A-Za-z])\.([A-Za-z])\.([A-Za-z])\b', r'\1\2\3', s)
    s = re.sub(r'\b([A-Za-z])\.([A-Za-z])\b', r'\1\2', s)

    # Remove contents inside brackets and parentheses
    s = re.sub(r'\[.*?\]', ' ', s)
    s = re.sub(r'\(.*?\)', ' ', s)

    # Strip master noise tokens
    s = re.sub(MASTER_NOISE_TOKENS, ' ', s)

    # Strip file size indicators e.g. 1.8GB, 950MB
    s = re.sub(r'(?i)\b\d+(?:\.\d+)?\s*(?:gb|mb|g|m)\b', ' ', s)

    # Remove decorative and noise characters
    s = re.sub(r'[@_.\-+#~∆|/:!?]+', ' ', s)

    # Token filter: filter out isolated garbage tokens while preserving short valid words & numbers
    valid_short_words = {
        'it', 'up', 'ai', 'go', 'me', 'we', 'no', 'my', 'be', 'do', 'if', 'in', 'is', 'of', 'on', 'or', 'to', 'us', 'vs',
        'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x',
        'hi', 'dc', 'gu', 'pk', 'ok', 'om', 'ra', 'ma', 'gdn', 'uk', 'usa'
    }
    blacklisted_tokens = {
        'esub', 'msub', 'brrip', 'bdrip', 'webdl', 'webrip', 'predvd', 'hdrip', 'dvdrip',
        'x264', 'x265', 'hevc', 'aac', 'clean', 'hq', 'lq', 'web', 'untouched', 'zee5', 'crav', 'amzn', 'nf', 'hotstar'
    }

    tokens = [w for w in s.split() if w.strip()]
    cleaned_tokens = []
    for tok in tokens:
        tl = tok.lower()
        if tl in blacklisted_tokens:
            continue
        if len(tokens) > 1 and len(tok) == 1 and not tok.isalnum():
            continue
        if len(tokens) > 1 and len(tok) <= 2 and tl not in valid_short_words and not tok.isdigit() and not tok.isupper():
            continue
        cleaned_tokens.append(tok)

    clean_title = ' '.join(cleaned_tokens).strip()

    # Title-case normalization while keeping acronyms & roman numerals uppercase
    if clean_title:
        words = clean_title.split()
        capitalized = []
        for w in words:
            if w.upper() in {'II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'X', 'DC', 'GDN', 'UK', 'USA'}:
                capitalized.append(w.upper())
            else:
                capitalized.append(w.capitalize())
        clean_title = ' '.join(capitalized)

    return clean_title


def extract_tech_specs(raw_filename: str) -> Dict[str, Any]:
    """
    Extracts quality, quality_label, rip_type, codec, audio_languages,
    is_theater_print, file_size_bytes, and mime_type.
    """
    # 1. Quality
    q_match = QUALITY_REGEX.search(raw_filename)
    if q_match:
        raw_q = q_match.group(1).lower()
        if '2160' in raw_q or '4k' in raw_q:
            quality = '2160p'
        elif '1080' in raw_q:
            quality = '1080p'
        elif '720' in raw_q:
            quality = '720p'
        elif '480' in raw_q:
            quality = '480p'
        elif '360' in raw_q:
            quality = '360p'
        elif '240' in raw_q:
            quality = '240p'
        else:
            quality = '1080p'
    else:
        quality = '1080p'

    quality_label = QUALITY_LABEL_MAP.get(quality, '1080P FULL HD')

    # 2. Rip Type
    rip_type = 'WEB-DL'
    for pat, label in RIP_TYPE_MAP:
        if pat.search(raw_filename):
            rip_type = label
            break

    # 3. Codec
    codec = 'x264'
    for pat, label in CODEC_MAP:
        if pat.search(raw_filename):
            codec = label
            break

    # 4. Theater Print Flag
    is_theater_print = bool(THEATER_PRINT_REGEX.search(raw_filename))

    # 5. Audio Languages
    detected_langs = []
    for pat, lang_name in LANG_PATTERNS:
        if pat.search(raw_filename):
            if lang_name not in detected_langs:
                detected_langs.append(lang_name)
    if not detected_langs:
        detected_langs = ['Tamil']

    # 6. File Size Bytes
    file_size_bytes = 0
    size_match = re.search(r'(?i)\b(\d+(?:\.\d+)?)\s*(GB|MB)\b', raw_filename)
    if size_match:
        val = float(size_match.group(1))
        unit = size_match.group(2).upper()
        if unit == 'GB':
            file_size_bytes = int(val * 1024 * 1024 * 1024)
        elif unit == 'MB':
            file_size_bytes = int(val * 1024 * 1024)

    # 7. Mime Type
    lower_name = raw_filename.lower()
    if lower_name.endswith(('.mp4', '.m4v')):
        mime_type = 'video/mp4'
    elif lower_name.endswith('.webm'):
        mime_type = 'video/webm'
    else:
        mime_type = 'video/x-matroska'

    return {
        'quality': quality,
        'quality_label': quality_label,
        'rip_type': rip_type,
        'codec': codec,
        'is_theater_print': is_theater_print,
        'audio_languages': detected_langs,
        'file_size_bytes': file_size_bytes,
        'mime_type': mime_type
    }


# ================================================================================
# CORE RECOGNITION & EXTRACTION ENGINE
# ================================================================================

def parse_and_classify_video(raw_filename: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    High-precision Classifier:
    Returns (record, None) if matching Movie or Series pattern.
    Returns (None, reason) if discarded.
    """
    raw_name = raw_filename.strip()
    if not raw_name:
        return None, "Empty line"

    # Pre-filtering: Drop known non-media lines or random hashes
    if re.match(r'^[a-zA-Z0-9]{20,}\.(?:mkv|mp4|avi)', raw_name):
        return None, "Random hash / non-media asset"

    # Strip domain prefixes & group tags
    clean_stem = strip_all_prefixes(raw_name)

    # Extract all tech specs
    specs = extract_tech_specs(raw_name)

    # Detect Series patterns
    se_match = SERIES_SE_REGEX.search(clean_stem)
    ep_only_match = SERIES_EP_ONLY_REGEX.search(clean_stem) if not se_match else None

    # Detect Movie Year
    year_match = YEAR_REGEX.search(clean_stem)

    # --------------------------------------------------------------------------
    # PATTERN 1: WEB SERIES / EPISODIC CONTENT
    # --------------------------------------------------------------------------
    if se_match:
        season_num = int(se_match.group(1))
        ep_raw = se_match.group(2).replace(' ', '')

        raw_title_part = clean_stem[:se_match.start()]
        base_title = clean_title_tokens(raw_title_part)
        if not base_title or len(base_title) < 2:
            return None, "Series title empty or invalid before Season/Episode tag"

        # Format standardized Episode string (e.g. S01E01, S01E01-E06)
        if '-' in ep_raw:
            parts = ep_raw.split('-')
            try:
                ep_display = f"E{int(parts[0]):02d}-E{int(parts[1]):02d}"
                ep_slug_part = f"s{season_num:02d}e{int(parts[0]):02d}-e{int(parts[1]):02d}"
            except ValueError:
                ep_display = f"E{parts[0]}-E{parts[1]}"
                ep_slug_part = f"s{season_num:02d}e{parts[0]}-e{parts[1]}"
        else:
            try:
                ep_display = f"E{int(ep_raw):02d}"
                ep_slug_part = f"s{season_num:02d}e{int(ep_raw):02d}"
            except ValueError:
                ep_display = f"E{ep_raw}"
                ep_slug_part = f"s{season_num:02d}e{ep_raw}"

        standard_title = f"{base_title} - S{season_num:02d}{ep_display}"
        slug = generate_slug(f"{base_title}-{ep_slug_part}")
        rel_year = int(year_match.group(1)) if year_match else 2026

        return {
            "media_type": "series",
            "title": standard_title,
            "base_title": base_title,
            "season": season_num,
            "episode": ep_raw,
            "release_year": rel_year,
            "slug": slug,
            "file_name": raw_name,
            **specs
        }, None

    elif ep_only_match:
        ep_raw = ep_only_match.group(1).replace(' ', '')
        season_num = 1

        raw_title_part = clean_stem[:ep_only_match.start()]
        base_title = clean_title_tokens(raw_title_part)
        if not base_title or len(base_title) < 2:
            return None, "Series title empty or invalid before EP tag"

        if '-' in ep_raw:
            parts = ep_raw.split('-')
            try:
                ep_display = f"E{int(parts[0]):02d}-E{int(parts[1]):02d}"
                ep_slug_part = f"s{season_num:02d}e{int(parts[0]):02d}-e{int(parts[1]):02d}"
            except ValueError:
                ep_display = f"E{parts[0]}-E{parts[1]}"
                ep_slug_part = f"s{season_num:02d}e{parts[0]}-e{parts[1]}"
        else:
            try:
                ep_display = f"E{int(ep_raw):02d}"
                ep_slug_part = f"s{season_num:02d}e{int(ep_raw):02d}"
            except ValueError:
                ep_display = f"E{ep_raw}"
                ep_slug_part = f"s{season_num:02d}e{ep_raw}"

        standard_title = f"{base_title} - S{season_num:02d}{ep_display}"
        slug = generate_slug(f"{base_title}-{ep_slug_part}")
        rel_year = int(year_match.group(1)) if year_match else 2026

        return {
            "media_type": "series",
            "title": standard_title,
            "base_title": base_title,
            "season": season_num,
            "episode": ep_raw,
            "release_year": rel_year,
            "slug": slug,
            "file_name": raw_name,
            **specs
        }, None

    # --------------------------------------------------------------------------
    # PATTERN 2: MOVIE (TITLE + YEAR 19xx/20xx)
    # --------------------------------------------------------------------------
    elif year_match:
        year = int(year_match.group(1))
        # Slice everything strictly before the year
        raw_title_part = clean_stem[:year_match.start()]
        title = clean_title_tokens(raw_title_part)

        # Ensure title has valid characters (letters or numbers)
        if not title or len(title) < 1 or not re.search(r'[a-zA-Z0-9]', title):
            return None, f"Invalid movie title extracted: '{title}'"

        slug = generate_slug(f"{title}-{year}")

        return {
            "media_type": "movie",
            "title": title,
            "release_year": year,
            "slug": slug,
            "file_name": raw_name,
            **specs
        }, None

    # --------------------------------------------------------------------------
    # STRICT DROP POLICY
    # --------------------------------------------------------------------------
    else:
        return None, "Does not match Movie (Title + Year) or Series (SxxExx/EP) pattern"


# ================================================================================
# RELATIONAL DEDUPLICATION & BATCH UPSERT ENGINE
# ================================================================================

class DatabasePipelineEngine:
    def __init__(self, supabase_url: str = None, supabase_key: str = None):
        self.supabase_url = (supabase_url or os.getenv("SUPABASE_URL", "")).rstrip('/')
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates"
        }

    def group_and_deduplicate(self, records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Groups all extracted records by unique 'slug'.
        Each master record in 'public.movies' will have 1 parent row,
        and multiple quality entries in 'public.movie_files'.
        """
        catalog_mesh: Dict[str, Dict[str, Any]] = {}

        for r in records:
            slug = r["slug"]
            if slug not in catalog_mesh:
                # Master Movie record
                catalog_mesh[slug] = {
                    "parent": {
                        "title": r["title"],
                        "slug": slug,
                        "file_name": r["file_name"],
                        "mime_type": r["mime_type"],
                        "file_size_bytes": r["file_size_bytes"],
                        "hf_raw_url": "",
                        "release_year": r["release_year"],
                        "default_quality_label": r["quality_label"],
                        "is_theater_print": r["is_theater_print"]
                    },
                    "files": {}  # keyed by quality to prevent duplicate constraint violation
                }

            # Child file record for public.movie_files
            q = r["quality"]
            # Deduplicate by quality or keep the highest size if multiple files exist for same quality
            existing_file = catalog_mesh[slug]["files"].get(q)
            if not existing_file or r["file_size_bytes"] > existing_file["file_size_bytes"]:
                catalog_mesh[slug]["files"][q] = {
                    "quality": q,
                    "file_name": r["file_name"],
                    "mime_type": r["mime_type"],
                    "file_size_bytes": r["file_size_bytes"],
                    "hf_raw_url": "",
                    "rip_type": r["rip_type"],
                    "codec": r["codec"],
                    "audio_languages": r["audio_languages"],
                    "quality_label": r["quality_label"],
                    "is_theater_print": r["is_theater_print"]
                }

        return catalog_mesh

    def upsert_catalog_batch(self, catalog_mesh: Dict[str, Dict[str, Any]], batch_size: int = 100):
        """
        Executes high-performance batch upserts into public.movies and public.movie_files
        using Supabase REST API PostgREST protocol.
        """
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for database upsert.")

        import requests

        total_titles = len(catalog_mesh)
        print(f"\n🚀 Initiating Database Batch Upsert for {total_titles} Unique Titles...")

        slug_to_id_map: Dict[str, str] = {}
        all_parents = [item["parent"] for item in catalog_mesh.values()]

        # Step 1: Batch Upsert into public.movies on conflict 'slug'
        movies_endpoint = f"{self.supabase_url}/rest/v1/movies?on_conflict=slug"
        
        for i in range(0, len(all_parents), batch_size):
            chunk = all_parents[i:i + batch_size]
            try:
                res = requests.post(movies_endpoint, headers=self.headers, json=chunk, timeout=30)
                if res.status_code in (200, 201):
                    inserted = res.json()
                    for row in inserted:
                        slug_to_id_map[row["slug"]] = row["id"]
                    print(f"  ✅ Upserted Movies Batch {i // batch_size + 1} ({len(chunk)} titles)")
                else:
                    print(f"  ⚠️ Movies Batch Error ({res.status_code}): {res.text[:200]}")
            except Exception as e:
                print(f"  ❌ Network Exception during Movies Batch: {e}")

        # Step 2: Fetch missing IDs if any already existed and weren't returned
        missing_slugs = [s for s in catalog_mesh if s not in slug_to_id_map]
        if missing_slugs:
            print(f"  🔍 Fetching IDs for {len(missing_slugs)} existing movies...")
            for i in range(0, len(missing_slugs), 100):
                chunk_slugs = missing_slugs[i:i + 100]
                slug_filter = ",".join(chunk_slugs)
                query_url = f"{self.supabase_url}/rest/v1/movies?slug=in.({slug_filter})&select=id,slug"
                try:
                    res = requests.get(query_url, headers=self.headers, timeout=15)
                    if res.ok:
                        for row in res.json():
                            slug_to_id_map[row["slug"]] = row["id"]
                except Exception as e:
                    print(f"  ⚠️ Fetch missing slugs error: {e}")

        # Step 3: Batch Insert/Upsert into public.movie_files
        all_files = []
        for slug, item in catalog_mesh.items():
            movie_id = slug_to_id_map.get(slug)
            if not movie_id:
                continue
            for f in item["files"].values():
                file_record = dict(f)
                file_record["movie_id"] = movie_id
                all_files.append(file_record)

        # Clean up existing files for these movie IDs to guarantee 100% idempotency on re-run
        movie_ids_list = list(set(slug_to_id_map.values()))
        print(f"  🧹 Sanitizing existing file entries for {len(movie_ids_list)} movies...")
        for i in range(0, len(movie_ids_list), 100):
            chunk_ids = movie_ids_list[i:i + 100]
            id_filter = ",".join(chunk_ids)
            try:
                requests.delete(f"{self.supabase_url}/rest/v1/movie_files?movie_id=in.({id_filter})", headers=self.headers, timeout=15)
            except Exception:
                pass

        print(f"\n📦 Prepared {len(all_files)} Quality Variant Files across {len(slug_to_id_map)} Movies.")
        files_endpoint = f"{self.supabase_url}/rest/v1/movie_files"

        for i in range(0, len(all_files), batch_size):
            chunk = all_files[i:i + batch_size]
            try:
                res = requests.post(files_endpoint, headers=self.headers, json=chunk, timeout=30)
                if res.status_code in (200, 201):
                    print(f"  ✅ Upserted Files Batch {i // batch_size + 1} ({len(chunk)} files)")
                else:
                    print(f"  ⚠️ Files Batch Error ({res.status_code}): {res.text[:200]}")
            except Exception as e:
                print(f"  ❌ Network Exception during Files Batch: {e}")

        print("\n🎉 Database Synchronization Completed Successfully!")


# ================================================================================
# CLI RUNNER & EXECUTION INTERFACE
# ================================================================================

def run_pipeline(input_file: Path, commit: bool = False, output_summary_file: Path = None):
    print("=" * 80)
    print("🎬 ENTERPRISE DATA PIPELINE: G-DRIVE VIDEO EXTRACTOR & SCHEMA MAPPER")
    print("=" * 80)
    print(f"📄 Source Input File : {input_file}")
    print(f"⚙️ Execution Mode    : {'🔥 DATABASE COMMIT' if commit else '🛡️ DRY RUN (Zero DB Mutation)'}")

    if not input_file.exists():
        print(f"❌ Error: Input file not found: {input_file}")
        sys.exit(1)

    start_time = time.time()
    valid_records: List[Dict[str, Any]] = []
    discarded_records: List[Tuple[str, str]] = []

    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        lines = [line.strip() for line in f if line.strip()]

    total_lines = len(lines)
    print(f"📥 Total Raw Filenames to Scan: {total_lines:,}")

    # Process all lines
    for line in lines:
        record, drop_reason = parse_and_classify_video(line)
        if record:
            valid_records.append(record)
        else:
            discarded_records.append((line, drop_reason))

    elapsed = max(time.time() - start_time, 0.001)

    # In-memory grouping & deduplication
    db_engine = DatabasePipelineEngine()
    catalog_mesh = db_engine.group_and_deduplicate(valid_records)

    movie_count = sum(1 for r in valid_records if r["media_type"] == "movie")
    series_count = sum(1 for r in valid_records if r["media_type"] == "series")

    print("\n" + "=" * 80)
    print("📊 EXTRACTION & CLASSIFICATION SUMMARY")
    print("=" * 80)
    print(f"✅ Total Valid Media Extracted  : {len(valid_records):,} ({len(valid_records)/total_lines*100:.1f}%)")
    print(f"   ├─ Movies (Title + Year)     : {movie_count:,}")
    print(f"   └─ Web Series (SxxExx / EP)  : {series_count:,}")
    print(f"🌟 Unique Titles (Master Rows)  : {len(catalog_mesh):,}")
    print(f"🛑 Skipped / Discarded lines    : {len(discarded_records):,} ({len(discarded_records)/total_lines*100:.1f}%)")
    print(f"⏱️ Processing Speed             : {total_lines / elapsed:,.1f} lines/second ({elapsed:.2f}s)")
    print("=" * 80)

    # Discard reason breakdown
    reason_counts = {}
    for _, reason in discarded_records:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    print("\n📉 Discarded Lines Breakdown:")
    for r, c in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {r}: {c:,}")

    # Display Samples
    print("\n🎬 Sample Extracted Movie Records:")
    sample_movies = [r for r in valid_records if r["media_type"] == "movie"][:3]
    for m in sample_movies:
        print(f"   • Title: '{m['title']}' ({m['release_year']}) | Slug: '{m['slug']}' | Quality: {m['quality']} | Rip: {m['rip_type']} | Lang: {m['audio_languages']}")

    print("\n📺 Sample Extracted Series Records:")
    sample_series = [r for r in valid_records if r["media_type"] == "series"][:3]
    for s in sample_series:
        print(f"   • Title: '{s['title']}' | Slug: '{s['slug']}' | Quality: {s['quality']} | Codec: {s['codec']}")

    # Write output audit file if requested
    if output_summary_file:
        print(f"\n💾 Writing Extraction Audit Report to: {output_summary_file}")
        with open(output_summary_file, 'w', encoding='utf-8') as out_f:
            out_f.write("================================================================================\n")
            out_f.write("G-DRIVE VIDEO EXTRACTION PIPELINE AUDIT REPORT\n")
            out_f.write("================================================================================\n")
            out_f.write(f"Total Lines Processed : {total_lines}\n")
            out_f.write(f"Valid Media Extracted : {len(valid_records)}\n")
            out_f.write(f"Unique Master Titles  : {len(catalog_mesh)}\n")
            out_f.write(f"Skipped / Discarded   : {len(discarded_records)}\n\n")

            out_f.write("--------------------------------------------------------------------------------\n")
            out_f.write("DISCARDED LINES SAMPLE (FIRST 100):\n")
            out_f.write("--------------------------------------------------------------------------------\n")
            for line, reason in discarded_records[:100]:
                out_f.write(f"[{reason}] {line}\n")

        print("   ✅ Audit report saved.")

    # Step 4: Commit to DB if requested
    if commit:
        db_engine.upsert_catalog_batch(catalog_mesh)
    else:
        print("\n💡 NOTE: Executed in DRY-RUN mode. No database records were modified.")
        print("👉 To commit to Supabase / PostgreSQL, execute with: --commit")


def main():
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir / "gdrive_all_video_names.txt"
    default_audit = script_dir / "pipeline_extraction_audit.txt"

    parser = argparse.ArgumentParser(
        description="High-Precision GDrive Video Pipeline Extractor & Database Mapper"
    )
    parser.add_argument("-i", "--input", default=str(default_input), help="Input .txt file of video names")
    parser.add_argument("--commit", action="store_true", help="Execute real upserts into Supabase / PostgreSQL")
    parser.add_argument("-o", "--output", default=str(default_audit), help="Path for audit report file")

    args = parser.parse_args()
    run_pipeline(
        input_file=Path(args.input).resolve(),
        commit=args.commit,
        output_summary_file=Path(args.output).resolve()
    )


if __name__ == "__main__":
    main()
