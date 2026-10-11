# ==============================================================================
# PROJECT HYDRA / SMD PRIME - HIGH-PRECISION MEDIA TITLE SANITIZER & SPECS ENGINE
# Production-Grade Dual-Grammar Parser for Movies, Web Series & Audio/Video Specs
# ==============================================================================

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Known Pirate Sites & Multi-Layer Domain Extensions to Strip
KNOWN_PIRATE_SITES = [
    r'1tamilmv\.[a-z]{2,15}',
    r'tamilmv\.[a-z]{2,15}',
    r'movieztamizha\.[a-z]{2,15}',
    r'isaimini\.[a-z]{2,15}',
    r'kuttymovies\.[a-z]{2,15}',
    r'tamilrockers\.[a-z]{2,15}',
    r'tamilblasters\.[a-z]{2,15}',
    r'omgxmovies\.[a-z]{2,15}',
    r'crazymoviescmc\.[a-z]{2,15}',
    r'vegamovies\.[a-z]{2,15}',
    r'bolly4u\.[a-z]{2,15}',
    r'9xmovies\.[a-z]{2,15}',
    r'filmyzilla\.[a-z]{2,15}',
    r'katmoviehd\.[a-z]{2,15}',
    r'worldfree4u\.[a-z]{2,15}',
    r'skymovieshd\.[a-z]{2,15}',
    r'cinevood\.[a-z]{2,15}',
    r'moviesda\.[a-z]{2,15}',
    r'cinemavilla\.[a-z]{2,15}',
    r'jioblasters\.[a-z]{2,15}',
    r'ibomma\.[a-z]{2,15}'
]

# Valid Short Words, Roman Numerals, Acronyms and Tamil Pop Cult Titles
KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS = {
    "hi", "dc", "kgf", "rrr", "ps1", "ps2", "gdn", "dj", "pk", "don",
    "leo", "beast", "jailer", "goat", "vikram", "master", "mersal", "sarkar",
    "bigil", "theri", "anbe", "sivam", "96", "24", "18", "7g",
    "it", "up", "ai", "go", "me", "we", "no", "my", "be", "do", "if", "in",
    "is", "of", "on", "or", "to", "us", "vs", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"
}

# Master Noise Regex for Titles
MASTER_NOISE_TOKENS = [
    r'\d+\s*(kbps|kb|k|khz)', r'(16bit|24bit)',
    r'dd\+?[\d\.]*', r'ddp[\d\.]*', r'aac[\d\.]*', r'ac3', r'eac3', r'dts[\-\w]*', r'atmos', r'truehd', r'flac', r'opus', r'mp3',
    r'[\d\.]+\s*ch', r'5\.1', r'7\.1', r'2\.0',
    r'clean-audio', r'org-audio', r'org-aud', r'clean-aud', r'line-audio', r'line-aud', r'dubbed', r'dub', r'multiaudio', r'multi-audio', r'dual-audio', r'dual', r'org', r'aud',
    r'tam', r'tamil', r'tel', r'telugu', r'hin', r'hindi', r'mal', r'malayalam', r'kan', r'kannada', r'eng', r'english', r'mar', r'marathi', r'ben', r'bengali', r'pun', r'punjabi', r'spa', r'spanish', r'fre', r'french', r'ger', r'german', r'kor', r'korean', r'jap', r'japanese',
    r'esub[\w]*', r'msub[\w]*', r'softsub[\w]*', r'hardsub[\w]*', r'nosub[\w]*', r'hcsub[\w]*',
    r'web-dl', r'webdl', r'web-rip', r'webrip', r'web', r'untouched', r'proper-web', r'hdrip', r'hd-rip', r'bluray', r'blu-ray', r'bdrip', r'brrip', r'dvdrip', r'predvd', r'pre-dvd', r'camrip', r'hdcam', r'hdts', r'telecine', r'ts', r'tc', r'hdtvrip', r'hdtv',
    r'hq', r'lq', r'clean', r'repack', r'proper', r'v2', r'v3', r'v4', r'uncut', r'unrated', r'extended', r'remastered', r'imax', r'hdr10plus', r'hdr10\+', r'hdr10', r'hdr', r'sdr', r'10bit', r'8bit',
    r'2160p', r'1080p', r'720p', r'480p', r'360p', r'240p', r'4k', r'uhd', r'fhd', r'hd', r'sd',
    r'x264', r'x265', r'hevc', r'h264', r'h265', r'avc', r'av1', r'xvid', r'divx'
]

COMPILED_NOISE_REGEX = re.compile(r'(?i)\b(' + '|'.join(MASTER_NOISE_TOKENS) + r')\b')


def strip_pirate_and_channel_prefixes(name: str) -> str:
    """Removes pirate domains, telegram handles, and copy prefixes with non-greedy precision."""
    cleaned = name.strip(" '\"[]()")
    cleaned = re.sub(r"^[\[\(\"'\s]+", "", cleaned)
    cleaned = re.sub(r"[\]\)\"'\s]+$", "", cleaned)

    for _ in range(4):
        cleaned = re.sub(r'^(?:Copy\s*(?:\(\d+\))?\s*of\s+)', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^(?:https?://)?(?:www\.)?[a-z0-9\.-]+\.[a-z]{2,15}\s*[-:_]*\s*', '', cleaned, flags=re.IGNORECASE).strip()
        for site in KNOWN_PIRATE_SITES:
            cleaned = re.sub(r'^' + site + r'\s*[-:_]*\s*', '', cleaned, flags=re.IGNORECASE).strip()
        
        # 1. Telegram handles followed by space, dash, colon, etc. (e.g. "@Channel - Title")
        cleaned = re.sub(r'^@[A-Za-z0-9_.-]+[\s\-–—:=|]+', '', cleaned, flags=re.IGNORECASE).strip()
        
        # 2. Known Telegram channel tags followed by underscore or spaces
        cleaned = re.sub(r'^@(?:Alinallmovies|LK_MOVIES\d*|TamilMov_LinkZz|TamilMob_LinkZz|ViP_LinkzZ|SAM_DUB_LEZHa|All_animes_in_telugu_Go|SheikXMovies|Tamilrockers|Isaimini|MoviezTamizha|Av_Linkz|Infinite_Anime|AnimeMoviesArc|GTM|SMD|TGStream)[_\s-]*', '', cleaned, flags=re.IGNORECASE).strip()
        
        # 3. Generic Telegram handles (@word_ followed by Title)
        cleaned = re.sub(r'^@[A-Za-z0-9]+_[_\s]*', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^@[A-Za-z0-9_]+?_(?=(?:[A-Z0-9][a-zA-Z0-9_]*_)?(?:19|20)\d{2}\b)', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^@[A-Za-z0-9_]+?_(?=(?:[A-Z0-9][a-zA-Z0-9_]*_)?S\d{1,2}E\d{1,3}\b)', '', cleaned, flags=re.IGNORECASE).strip()

        cleaned = re.sub(r'^\s*\[\s*(?:tgstream|smd|gtm|crazymoviescmc|exclusive|tamildbox|tnhits|1tamilmv|hindianimezone|toonworld4all)[^\]]*\]\s*[-:_]*\s*', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^(?:www\.)?[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.(?:com|org|net|me|in|co|cc|top|hair|capital|baby|yachts|vip|pw|to|is|ws|pe|pm|ph|ag|by|gs|cards|meme)\s*[-:_]*\s*', '', cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def extract_tech_specs(raw_name: str) -> Dict[str, Any]:
    """Extracts resolution, rip type, codec, audio languages, and print quality flags."""
    lower = raw_name.lower()

    # Resolution
    quality = "1080p"
    quality_label = "1080P FULL HD"
    if "2160p" in lower or "4k" in lower or "uhd" in lower:
        quality = "2160p"
        quality_label = "4K ULTRA HD"
    elif "1080p" in lower or "fhd" in lower:
        quality = "1080p"
        quality_label = "1080P FULL HD"
    elif "720p" in lower or "hd" in lower:
        quality = "720p"
        quality_label = "720P HD"
    elif "480p" in lower or "sd" in lower:
        quality = "480p"
        quality_label = "480P SD"

    # Rip Type
    rip_type = "WEB-DL"
    if any(k in lower for k in ["bluray", "blu-ray", "bdrip", "brrip"]):
        rip_type = "BluRay"
    elif any(k in lower for k in ["web-dl", "webdl", "webrip", "web-rip"]):
        rip_type = "WEB-DL"
    elif any(k in lower for k in ["hdrip", "hd-rip", "dvdrip"]):
        rip_type = "HDRip"
    elif any(k in lower for k in ["hdtv", "hdtvrip"]):
        rip_type = "HDTV"
    elif any(k in lower for k in ["predvd", "pre-dvd", "camrip", "hdcam", "hdts", "telecine", "tc", "ts"]):
        rip_type = "PreDVD"

    # Codec
    codec = "x264"
    if any(k in lower for k in ["x265", "hevc", "h265"]):
        codec = "HEVC"
    elif any(k in lower for k in ["x264", "h264", "avc"]):
        codec = "x264"
    elif "av1" in lower:
        codec = "AV1"

    # Audio Languages
    audio_langs: List[str] = []
    lang_mapping = [
        (r'\b(tam|tamil)\b', 'Tamil'),
        (r'\b(tel|telugu)\b', 'Telugu'),
        (r'\b(hin|hindi)\b', 'Hindi'),
        (r'\b(mal|malayalam)\b', 'Malayalam'),
        (r'\b(kan|kannada)\b', 'Kannada'),
        (r'\b(eng|english)\b', 'English'),
    ]
    for pattern, lang_name in lang_mapping:
        if re.search(pattern, lower):
            audio_langs.append(lang_name)
    if not audio_langs:
        audio_langs = ["Tamil"]

    # Theater Print Flag
    is_theater_print = bool(re.search(r'\b(predvd|pre-dvd|camrip|hdcam|hdts|telecine|tc|ts)\b', lower))

    return {
        "quality": quality,
        "quality_label": quality_label,
        "rip_type": rip_type,
        "codec": codec,
        "audio_languages": audio_langs,
        "is_theater_print": is_theater_print
    }


def clean_movie_title(raw_title: str, year: str) -> str:
    """Sanitizes movie title part, preserving acronyms and numerical titles."""
    s = strip_pirate_and_channel_prefixes(raw_title)
    s = re.sub(r'\[.*?\]|\(.*?\)', ' ', s)
    s = COMPILED_NOISE_REGEX.sub(' ', s)
    s = re.sub(r'(?i)\b\d+(\.\d+)?\s*(gb|mb|g|m)\b', ' ', s)
    s = re.sub(r'[@_.\-+#\[\]\(\)]', ' ', s)

    words = [w for w in s.split() if w.strip()]
    clean_words = []
    for w in words:
        wl = w.lower()
        if wl == year.lower():
            continue
        if len(w) <= 2:
            if wl in KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS or w.isdigit():
                clean_words.append(w.upper() if len(w) <= 2 and not w.isdigit() else w)
            continue
        clean_words.append(w)

    clean_title = ' '.join(clean_words).strip()
    return clean_title.title() if clean_title else raw_title.replace('.', ' ').strip().title()


def clean_series_title(raw_title: str) -> str:
    """Sanitizes web series title, preserving show name integrity."""
    s = strip_pirate_and_channel_prefixes(raw_title)
    s = re.sub(r'\[.*?\]|\(.*?\)', ' ', s)
    s = COMPILED_NOISE_REGEX.sub(' ', s)
    s = re.sub(r'(?i)\b\d+(\.\d+)?\s*(gb|mb|g|m)\b', ' ', s)
    s = re.sub(r'[@_.\-+#\[\]\(\)]', ' ', s)

    words = [w for w in s.split() if w.strip()]
    clean_words = []
    for w in words:
        wl = w.lower()
        if len(w) <= 2:
            if wl in KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS or w.isdigit():
                clean_words.append(w.upper() if len(w) <= 2 and not w.isdigit() else w)
            continue
        clean_words.append(w)

    clean_title = ' '.join(clean_words).strip()
    return clean_title.title() if clean_title else raw_title.replace('.', ' ').strip().title()


def parse_video_line(raw_line: str) -> Optional[Dict[str, Any]]:
    """
    Dual-Grammar parsing engine:
    Discards non-media junk, sub/sample files, or text lines.
    Validates either Movie Grammar (Title + Year) or Series Grammar (Title + SxxExx/EP).
    """
    raw_name = raw_line.strip()
    if not raw_name or len(raw_name) < 4:
        return None

    # Exclude non-video file formats
    ext = Path(raw_name).suffix.lower()
    valid_exts = {'.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v'}
    if ext and ext not in valid_exts:
        return None

    stem = Path(raw_name).stem

    # Exclude junk lines
    stem_lower = stem.lower()
    if any(junk in stem_lower for junk in ['sample', 'trailer', 'promo', 'txt', 'torrent', 'infopack']):
        return None

    tech_specs = extract_tech_specs(raw_name)
    cleaned_stem = strip_pirate_and_channel_prefixes(stem)

    # 1. GRAMMAR CHECK: Web Series Pattern (SxxExx / Episode / Day)
    series_match = re.search(r'(?i)\b(S(\d{1,2})\s*[-._ ]*E(?:P)?(\d{1,3})|EP(\d{1,3})|Episode\s*(\d{1,3})|Day\s*(\d{1,3}))\b', cleaned_stem)
    if series_match:
        series_token = series_match.group(0)
        title_part = cleaned_stem[:series_match.start()].strip(' .-_')
        series_title = clean_series_title(title_part)
        if not series_title:
            return None

        # Build clean season/episode tags
        season_num = series_match.group(2) or "01"
        episode_num = series_match.group(3) or series_match.group(4) or series_match.group(5) or series_match.group(6) or "01"
        normalized_ep_tag = f"S{int(season_num):02d}E{int(episode_num):02d}"

        clean_display_title = f"{series_title} {normalized_ep_tag}"
        slug_base = re.sub(r'[^a-z0-9]', '', series_title.lower())
        slug = f"{slug_base}-s{int(season_num):02d}e{int(episode_num):02d}"
        sanitized_filename = f"{slug}.{tech_specs['quality']}{ext if ext else '.mkv'}"

        return {
            "media_type": "series",
            "clean_title": clean_display_title,
            "series_title": series_title,
            "season": int(season_num),
            "episode": int(episode_num),
            "year": None,
            "slug": slug,
            "quality": tech_specs["quality"],
            "rip_type": tech_specs["rip_type"],
            "codec": tech_specs["codec"],
            "audio_languages": tech_specs["audio_languages"],
            "quality_label": tech_specs["quality_label"],
            "is_theater_print": tech_specs["is_theater_print"],
            "raw_filename": raw_name,
            "sanitized_filename": sanitized_filename
        }

    # 2. GRAMMAR CHECK: Movie Pattern (Title + Year: 19XX or 20XX)
    year_match = re.search(r'\b((?:19|20)\d{2})\b', cleaned_stem)
    if year_match:
        year = year_match.group(1)
        title_part = cleaned_stem[:year_match.start()].strip(' .-_')
        clean_title = clean_movie_title(title_part, year)
        if not clean_title:
            return None

        slug_base = re.sub(r'[^a-z0-9]', '', clean_title.lower())
        slug = f"{slug_base}-{year}"
        sanitized_filename = f"{slug}.{tech_specs['quality']}{ext if ext else '.mkv'}"

        return {
            "media_type": "movie",
            "clean_title": clean_title,
            "year": int(year),
            "slug": slug,
            "quality": tech_specs["quality"],
            "rip_type": tech_specs["rip_type"],
            "codec": tech_specs["codec"],
            "audio_languages": tech_specs["audio_languages"],
            "quality_label": tech_specs["quality_label"],
            "is_theater_print": tech_specs["is_theater_print"],
            "raw_filename": raw_name,
            "sanitized_filename": sanitized_filename
        }

    # Line does NOT match strict Movie or Series grammar -> Discard
    return None


def sanitize_movie_title(raw_filename: str) -> Tuple[str, str, str, str, Dict[str, Any]]:
    """
    Backward-compatible universal sanitizer for the entire SMD PRIME codebase.
    Returns: (clean_title_with_year, sanitized_filename, slug, quality, metadata_dict)
    Supports both 4-variable and 5-variable unpacking.
    """
    parsed = parse_video_line(raw_filename)
    if parsed:
        if parsed.get("year"):
            display_title = f"{parsed['clean_title']} ({parsed['year']})"
        else:
            display_title = parsed["clean_title"]

        meta = {
            "quality": parsed["quality"],
            "quality_label": parsed["quality_label"],
            "rip_type": parsed["rip_type"],
            "codec": parsed["codec"],
            "audio_languages": parsed["audio_languages"],
            "is_theater_print": parsed["is_theater_print"],
            "year": parsed.get("year", ""),
            "media_type": parsed["media_type"]
        }
        return (display_title, parsed["sanitized_filename"], parsed["slug"], parsed["quality"], meta)

    # Fallback for filenames without year or series tag
    stem = Path(raw_filename).stem
    ext = Path(raw_filename).suffix.lower()
    cleaned = strip_pirate_and_channel_prefixes(stem)
    specs = extract_tech_specs(raw_filename)
    s = COMPILED_NOISE_REGEX.sub(' ', cleaned)
    s = re.sub(r'[@_.\-+#\[\]\(\)]', ' ', s).strip()
    words = [w.title() for w in s.split() if w.strip()]
    clean_title = ' '.join(words) if words else stem.title()
    slug_base = re.sub(r'[^a-z0-9]', '', clean_title.lower()) or "movie"
    slug = f"{slug_base}-unknown"
    sanitized_filename = f"{slug}.{specs['quality']}{ext if ext else '.mp4'}"

    meta = {
        "quality": specs["quality"],
        "quality_label": specs["quality_label"],
        "rip_type": specs["rip_type"],
        "codec": specs["codec"],
        "audio_languages": specs["audio_languages"],
        "is_theater_print": specs["is_theater_print"],
        "year": "",
        "media_type": "movie"
    }
    return (clean_title, sanitized_filename, slug, specs["quality"], meta)
