# ==============================================================================
# PROJECT HYDRA / SMD PRIME - 2026 HIGH-PRECISION MEDIA TITLE SANITIZER & SPECS ENGINE
# 5-Stage Dual-Grammar Parser for Movies, Web Series (Single/Batch), Audio/Video Specs
# ==============================================================================

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Valid Video Extensions
VALID_VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v', '.ts'}

# Known Pirate Sites & Multi-Layer Domain Extensions
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

KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS = {
    "of", "to", "in", "on", "at", "by", "as", "is", "it", "or", "an", "am", "up",
    "no", "so", "my", "he", "we", "me", "us", "go", "do", "if", "be", "ok",
    "hi", "dj", "pk", "dr", "mr", "ms", "dd", "kg", "7g", "18", "24", "96", "1917",
    "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii",
    "kgf", "rrr", "ps1", "ps2", "gdn", "don", "leo", "beast", "jailer", "goat",
    "vikram", "master", "mersal", "sarkar", "bigil", "theri", "dune"
}

PRESERVED_CULT_TITLES = {
    "96", "24", "18", "7g", "1917", "3", "se7en", "127", "127 hours", "district 9",
    "kgf", "rrr", "ps1", "ps2", "gdn", "dj", "pk", "don", "leo", "beast", "jailer",
    "goat", "vikram", "master", "mersal", "sarkar", "bigil", "theri", "anbe sivam",
    "thupakki", "kaththi", "ghilli", "mankatha", "billa", "enthiran", "2.0", "sivaji",
    "baahubali", "salaar", "kantara", "devara", "kalki", "pushpa", "game changer",
    "indian", "indian 2", "viduthalai", "raayan", "vada chennai", "asuran", "karnan",
    "man of steel", "the pursuit of happyness", "dd returns", "dhilluku dhuddu", "dune"
}

SEQUEL_PATTERNS = [
    r'\b(?:part|chapter|vol|volume|pt)\s*[-._:]?\s*([0-9ivx]+|one|two|three|four)\b',
    r'\b(chapter\s*[0-9ivx]+)\b',
    r'\b([0-9ivx]+)(?:st|nd|rd|th)\s+(?:part|installment)\b',
    r'\b(?:returns|reloaded|revolution|resurrection|final\s*chapter)\b'
]

MASTER_NOISE_TOKENS = [
    r'\d+\s*(kbps|kb|k|khz)', r'(16bit|24bit)',
    r'dd\+?[\d\.]*', r'ddp[\d\.]*', r'aac[\d\.]*', r'ac3', r'eac3', r'dts[\-\w]*', r'atmos', r'truehd', r'flac', r'opus', r'mp3',
    r'[\d\.]+\s*ch', r'5\.1', r'7\.1', r'2\.0',
    r'clean-audio', r'org-audio', r'org-aud', r'clean-aud', r'line-audio', r'line-aud', r'line', r'hall-audio', r'dubbed', r'dub', r'multiaudio', r'multi-audio', r'dual-audio', r'dual', r'org', r'aud',
    r'tam', r'tamil', r'tel', r'telugu', r'hin', r'hindi', r'mal', r'malayalam', r'kan', r'kannada', r'eng', r'english', r'mar', r'marathi', r'ben', r'bengali', r'pun', r'punjabi', r'spa', r'spanish', r'fre', r'french', r'ger', r'german', r'kor', r'korean', r'jap', r'japanese',
    r'esub[\w]*', r'msub[\w]*', r'softsub[\w]*', r'hardsub[\w]*', r'nosub[\w]*', r'hcsub[\w]*', r'sub', r'subs',
    r'web-dl', r'webdl', r'web-rip', r'webrip', r'web', r'untouched', r'proper-web', r'hdrip', r'hd-rip', r'bluray', r'blu-ray', r'bdrip', r'brrip', r'dvdrip', r'predvd', r'pre-dvd', r'camrip', r'hdcam', r'hdts', r'telecine', r'ts', r'tc', r'hdtvrip', r'hdtv',
    r'hq', r'lq', r'clean', r'repack', r'proper', r'v2', r'v3', r'v4', r'uncut', r'unrated', r'extended', r'remastered', r'imax', r'hdr10plus', r'hdr10\+', r'hdr10', r'hdr', r'sdr', r'10bit', r'8bit', r'combined',
    r'2160p', r'1080p', r'720p', r'480p', r'360p', r'240p', r'4k', r'uhd', r'fhd', r'hd', r'sd',
    r'x264', r'x265', r'hevc', r'h264', r'h265', r'avc', r'av1', r'xvid', r'divx',
    r'\d+(\.\d+)?\s*(?:gb|mb|g|m)\b',
    r'snxt|amzn|netflix|hotstar|aha|zee5|sonyliv|jiocinema|mxplayer|voot'
]

COMPILED_NOISE_REGEX = re.compile(r'(?i)\b(' + '|'.join(MASTER_NOISE_TOKENS) + r')\b')

PIRATE_WATERMARK_PATTERNS = [
    r'(?i)^(?:copy\s*(?:\(\d+\))?\s*of\s+)+',
    r'(?i)^\[\s*copy\s*of\s*\]\s*',
    r'(?i)https?://\S+',
    r'(?i)^(?:https?://|www\.)[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,12}\b\s*[-_:~|]*\s*',
    r'(?i)^[a-zA-Z0-9\-]+\.(?:com|org|net|me|in|co|cc|top|hair|capital|baby|yachts|vip|pw|to|is|ws|pe|pm|ph|ag|by|gs|cards|meme|lease|rocks|live|lat|club|info|ms|tel|si|ing|vin|promo|solar|reisen)\b\s*[-_:~|]+\s*',
    r'(?i)^@(?:[A-Za-z0-9_.-]+)[\s\-–—:=|]+',
    r'(?i)^@(?:Alinallmovies|LK_MOVIES\d*|TamilMov_LinkZz|TamilMob_LinkZz|ViP_LinkzZ|SAM_DUB_LEZHa|All_animes_in_telugu_Go|SheikXMovies|Tamilrockers|Isaimini|MoviezTamizha|Av_Linkz|Infinite_Anime|AnimeMoviesArc|GTM|SMD|TGStream)[_\s-]*',
    r'(?i)^\[\s*(?:tgstream|smd|gtm|crazymoviescmc|exclusive|tamildbox|tnhits|1tamilmv|hindianimezone|toonworld4all|mkvcinemas|bolly4u|hdhub4u|filmyzilla|desiremovies|world4ufree|snxt|razor|lezha|tglezha)[^\]]*\]\s*[-_:~|]*\s*',
    r'(?i)^(?:1\s*tamilmv|1\s*amilmv|tamilblasters|tamilrockers|movieztamizha|movieemanhd|movieeman|massmovies\d*|lkmovies\d*|dctamil|dc\s*tamil|omgxmovies|sam\s*dub\s*lezha|samdub|lezha|tglezha|tamilyogi|isaimini|kuttymovies|cinemavilla|bolly4u|hdhub4u|filmyzilla|desiremovies|world4ufree|snxt|skymovieshd|cinevood|moviesda|jioblasters|ibomma)\b\s*[-_:~| ]*'

]


def strip_pirate_and_channel_prefixes(name: str) -> str:
    """Removes pirate domains, telegram handles, and copy prefixes with non-greedy precision."""
    cleaned = name.strip(" '\"[]()")
    for ext in VALID_VIDEO_EXTENSIONS:
        if cleaned.lower().endswith(ext):
            cleaned = cleaned[:-len(ext)].strip()
            break

    cleaned = cleaned.replace('_', ' ')
    # Fix glued years like Shoot_The_Kuruvi2023 -> Shoot The Kuruvi 2023
    cleaned = re.sub(r'([a-zA-Z])((?:19|20)\d{2})\b', r'\1 \2', cleaned)

    for _ in range(5):
        prev = cleaned
        for pat in PIRATE_WATERMARK_PATTERNS:
            cleaned = re.sub(pat, '', cleaned).strip(' .-_:[]()\'\"')
        for site in KNOWN_PIRATE_SITES:
            cleaned = re.sub(r'(?i)^' + site + r'\s*[-:_]*\s*', '', cleaned).strip(' .-_:[]()\'\"')
        if cleaned == prev:
            break
    return cleaned.strip()


def extract_tech_specs(raw_name: str) -> Dict[str, Any]:
    """Extracts resolution, rip type, codec, audio languages, audio channels and scores."""
    lower = raw_name.lower()

    # Resolution & Label
    quality = "1080p"
    quality_label = "1080P FULL HD"
    if any(k in lower for k in ["2160p", "4k", "uhd"]):
        quality = "2160p"
        quality_label = "4K ULTRA HD"
    elif any(k in lower for k in ["1080p", "fhd"]):
        quality = "1080p"
        quality_label = "1080P FULL HD"
    elif any(k in lower for k in ["720p", "hd"]):
        quality = "720p"
        quality_label = "720P HD"
    elif any(k in lower for k in ["480p", "sd", "360p", "240p"]):
        quality = "480p"
        quality_label = "480P SD"

    # Rip Type
    rip_type = "WEB-DL"
    rip_score = 85
    is_theater_print = False
    if any(k in lower for k in ["bluray", "blu-ray", "bdrip", "brrip", "remux"]):
        rip_type = "BluRay"
        rip_score = 100
    elif any(k in lower for k in ["web-dl", "webdl", "webrip", "web-rip", "proper-web"]):
        rip_type = "WEB-DL"
        rip_score = 85
    elif any(k in lower for k in ["hdrip", "hd-rip", "dvdrip"]):
        rip_type = "HDRip"
        rip_score = 60
    elif any(k in lower for k in ["hdtv", "hdtvrip"]):
        rip_type = "HDTV"
        rip_score = 50
    elif any(k in lower for k in ["predvd", "pre-dvd", "camrip", "hdcam", "hdts", "telecine", "tc", "ts"]):
        rip_type = "PreDVD"
        rip_score = 15
        is_theater_print = True

    # Codec
    codec = "x264"
    codec_score = 20
    if any(k in lower for k in ["x265", "hevc", "h265", "10bit", "10-bit"]):
        codec = "HEVC"
        codec_score = 30
    elif "av1" in lower:
        codec = "AV1"
        codec_score = 35
    elif any(k in lower for k in ["x264", "h264", "avc"]):
        codec = "x264"
        codec_score = 20

    # Audio Languages
    audio_langs = []
    lang_map = {
        "tamil": ["tam", "tamil"],
        "telugu": ["tel", "telugu"],
        "hindi": ["hin", "hindi"],
        "malayalam": ["mal", "malayalam"],
        "kannada": ["kan", "kannada"],
        "english": ["eng", "english"]
    }
    for lang, aliases in lang_map.items():
        if any(re.search(r'(?i)\b' + a + r'\b', raw_name) for a in aliases):
            audio_langs.append(lang.title())

    has_tamil = "Tamil" in audio_langs
    if not audio_langs:
        audio_langs = ["Tamil"]
        has_tamil = True

    audio_channels = "2.0 Stereo"
    audio_channels_tag = ""
    audio_score = 50
    if any(k in lower for k in ["atmos", "ddp atmos", "truehd atmos"]):
        audio_channels = "7.1 Atmos"
        audio_channels_tag = "Atmos"
        audio_score = 90
    elif any(k in lower for k in ["7.1", "truehd7.1", "dts-hd"]):
        audio_channels = "7.1 Surround"
        audio_channels_tag = "7.1"
        audio_score = 85
    elif any(k in lower for k in ["ddp5.1", "ddp 5.1", "dd+ 5.1", "eac3"]):
        audio_channels = "5.1 DDP"
        audio_channels_tag = "DDP 5.1"
        audio_score = 80
    elif any(k in lower for k in ["5.1", "ac3", "dts"]):
        audio_channels = "5.1 Surround"
        audio_channels_tag = "DDP 5.1"
        audio_score = 75
    elif any(k in lower for k in ["line-audio", "line audio", "line-aud"]):
        audio_channels = "Line Audio"
        audio_channels_tag = "Line Audio"
        audio_score = 40
    elif any(k in lower for k in ["2.0", "stereo", "aac"]):
        audio_channels = "2.0 Stereo"
        audio_channels_tag = ""
        audio_score = 50

    merit_score = rip_score + codec_score + audio_score + (30 if has_tamil else 0)

    return {
        "quality": quality,
        "quality_label": quality_label,
        "rip_type": rip_type,
        "rip_score": rip_score,
        "is_theater_print": is_theater_print,
        "codec": codec,
        "codec_score": codec_score,
        "audio_languages": audio_langs,
        "audio_channels": audio_channels,
        "audio_channels_tag": audio_channels_tag,
        "audio_score": audio_score,
        "has_tamil": has_tamil,
        "merit_score": merit_score,
        "confidence_score": 0.95,
        "needs_lazy_sniff": False
    }


def build_scene_canonical_name(meta: Dict[str, Any], ext: str = ".mkv") -> str:
    """
    PROJECT HYDRA 2026 - GOLDEN HYBRID SCENE CANONICAL NAMING PROTOCOL
    Rules:
    1. Title & Year: Natural spaces + Year in parentheses '(Year)'.
    2. Quality & Source: Clean spaces, NO brackets (e.g. '1080p WEB-DL' or 'HQ-PreDVD 1080p').
    3. Audio:
       - Single Language (<= 1 lang): NO BRACKETS! (e.g. 'Tamil - DDP 5.1')
       - Multi-Language (> 1 lang): BRACKETED HOOK! (e.g. '[Tamil + English - DDP 5.1]')
    4. Series: S01E01 for single, EP(01-10) for batches.
    5. Tail: Codec + Brand: 'x264 - SMD{ext}'
    """
    category = meta.get("category", "MOVIE")
    quality = meta.get("quality", "1080p")
    rip_type = meta.get("rip_type", "WEB-DL")
    is_theater = meta.get("is_theater_print", False)
    codec = meta.get("codec", "x264")
    langs = meta.get("audio_languages") or ["Tamil"]
    channels_tag = meta.get("audio_channels_tag") or ""
    if not channels_tag:
        raw_ch = meta.get("audio_channels", "")
        if "atmos" in raw_ch.lower():
            channels_tag = "Atmos"
        elif "ddp" in raw_ch.lower() or "5.1" in raw_ch.lower():
            channels_tag = "DDP 5.1"
        elif "7.1" in raw_ch.lower():
            channels_tag = "7.1"
        elif "line" in raw_ch.lower():
            channels_tag = "Line Audio"

    year = meta.get("year") or 2026

    # 1. Base Title & Anchor
    if category in ("SERIES_SINGLE", "SERIES_BATCH"):
        series_title = meta.get("series_title") or meta.get("clean_title") or "Series"
        s_num = meta.get("season", 1)
        ep_start = meta.get("episode", 1)
        ep_end = meta.get("episode_end", ep_start)
        is_batch = meta.get("is_batch", False)
        year_str = f" ({year})" if meta.get("year") else ""
        if is_batch:
            ep_tag = f"EP({ep_start:02d}-{ep_end:02d})" if ep_end > ep_start else f"S{s_num:02d} Complete"
            base_anchor = f"{series_title} S{s_num:02d}{year_str} {ep_tag}"
        else:
            base_anchor = f"{series_title} S{s_num:02d}E{ep_start:02d}{year_str}"
    else:
        movie_title = meta.get("clean_title") or "Movie"
        clean_name = re.sub(r'\s*\((?:19|20)\d{2}\)', '', movie_title).strip()
        base_anchor = f"{clean_name} ({year})"

    # 2. Source & Quality (Clean spaces, NO brackets)
    if is_theater:
        source_quality = f"HQ-PreDVD {quality}" if "predvd" not in quality.lower() else quality
    else:
        if rip_type.lower() in quality.lower():
            source_quality = quality
        else:
            source_quality = f"{quality} {rip_type}"

    # 3. Audio & Channels (The Bracket Rule: ONLY if > 1 language)
    lang_joined = " + ".join(langs)
    audio_full = f"{lang_joined} - {channels_tag}" if channels_tag else lang_joined

    if len(langs) > 1:
        audio_token = f"[{audio_full}]"
    else:
        audio_token = audio_full

    # 4. Construct Final Scene Name
    ext_clean = ext if (not ext or ext.startswith('.')) else f".{ext}"
    final_name = f"{base_anchor} {source_quality} {audio_token} {codec} - SMD{ext_clean}"
    return re.sub(r'\s+', ' ', final_name).strip()


def clean_movie_title(raw_title: str, year: Optional[str] = None) -> str:
    """Removes spec tags, noise tokens, and cleans movie title."""
    s = strip_pirate_and_channel_prefixes(raw_title)
    if year:
        s = re.sub(r'\b' + re.escape(str(year)) + r'\b', '', s)
    s = COMPILED_NOISE_REGEX.sub(' ', s)
    s = re.sub(r'[@_.\-+#\[\]\(\)]', ' ', s).strip()
    words = [w.title() for w in s.split() if w.strip()]
    return ' '.join(words)


def clean_series_title(raw_title: str) -> str:
    """Extracts pristine TV Show series title."""
    s = strip_pirate_and_channel_prefixes(raw_title)
    s = re.sub(r'\(\s*(?:19|20)\d{2}(?:\s*[-–]\s*(?:\d{2}|\d{4}))?\s*\)', '', s)
    s = re.sub(r'\b(?:19|20)\d{2}\b', '', s)
    s = COMPILED_NOISE_REGEX.sub(' ', s)
    s = re.sub(r'[\[\]\(\)]', ' ', s)
    s = re.sub(r'[@_.\-+#]', ' ', s).strip()
    words = []
    for w in s.split():
        wl = w.lower()
        if wl in KNOWN_VALID_ACRONYMS_AND_SHORT_WORDS:
            words.append(w.upper() if len(w) <= 2 and wl not in {"of", "to", "in", "on", "at", "by", "as", "is", "it", "or", "an", "am", "up", "no", "so", "my", "he", "we", "me", "us", "go", "do", "if", "be"} else w)
        else:
            words.append(w.title())
    return ' '.join(words) if words else "Web Series"


def parse_video_line(raw_line: str) -> Optional[Dict[str, Any]]:
    """
    Production-grade Unified Dual-Grammar Parser for Movies and Series.
    Returns structured metadata dict or None if rejected.
    """
    raw_name = Path(raw_line.strip()).name
    ext = Path(raw_name).suffix.lower()
    cleaned_stem = strip_pirate_and_channel_prefixes(raw_name)

    if not cleaned_stem:
        return None

    # Hex Hash / UUID / Empty Discard
    if re.match(r'^[a-fA-F0-9]{24,64}$', cleaned_stem):
        return None
    if cleaned_stem.lower() in ['testing', 'test', 'untitled', 'temp', 'video']:
        return None
    if re.search(r'(?i)(?:\b|[-._\[])(sample|trailer|teaser|preview|extras|featurette)(?:\b|[-._\]])', cleaned_stem):
        return None

    tech_specs = extract_tech_specs(raw_name)
    year_match = re.search(r'\b((?:19|20)\d{2})\b', cleaned_stem)
    found_year = int(year_match.group(1)) if year_match else None

    # --------------------------------------------------------------------------
    # 1. GRAMMAR CHECK: TV Series Matrix v4 (Single / Batch / Complete)
    # --------------------------------------------------------------------------
    batch_paren_pat = r'(?i)\b(?:S(\d{1,2})[\s._-]*)?(?:E|EP|Episode|Episodes)\s*[\(\[]\s*(\d{1,3})\s*[-–~to]+\s*(?:E|EP|Episode)?\.?\s*(\d{1,3})\s*[\)\]]'
    batch_std_pat = r'(?i)\b(?:S(\d{1,2})[\s._-]*)?(?:E|EP|Episode|Episodes)\.?\s*(\d{1,3})\s*[-–~to]+\s*(?:E|EP|Episode)?\.?\s*(\d{1,3})\b'
    complete_pat = r'(?i)\b(?:S(\d{1,2})|Season\s*(\d{1,2}))\s*[-._ ]*(?:Complete|Full|Pack|All\s*Episodes)\b'
    multi_season_pat = r'(?i)\b(?:S|Season\s*)(\d{1,2})\s*[-–~to]+\s*(?:S|Season\s*)?(\d{1,2})\b'
    single_pat = r'(?i)\b(?:S(\d{1,2})[\s._-]*)?(?:E|EP|Episode)\.?\s*[\(\[]?\s*(\d{1,3})\s*[\)\]]?\b'
    turkish_pat = r'(?i)\b(\d{1,3})\s*\.?\s*Bölüm\b'
    day_pat = r'(?i)\bDay\s*(\d{1,3})\b'

    bm_paren = re.search(batch_paren_pat, cleaned_stem)
    bm_std = re.search(batch_std_pat, cleaned_stem)
    cm = re.search(complete_pat, cleaned_stem)
    msm = re.search(multi_season_pat, cleaned_stem)
    sm = re.search(single_pat, cleaned_stem)
    tm = re.search(turkish_pat, cleaned_stem)
    dm = re.search(day_pat, cleaned_stem)

    if bm_paren or bm_std or cm or msm or sm or tm or dm:
        season_num = 1
        ep_start = 1
        ep_end = 1
        is_batch = False
        is_season_pack = False

        if bm_paren:
            season_num = int(bm_paren.group(1) or 1)
            ep_start = int(bm_paren.group(2))
            ep_end = int(bm_paren.group(3))
            is_batch = True
            match_span = bm_paren.span()
        elif bm_std:
            season_num = int(bm_std.group(1) or 1)
            ep_start = int(bm_std.group(2))
            ep_end = int(bm_std.group(3))
            is_batch = True
            match_span = bm_std.span()
        elif cm:
            season_num = int(cm.group(1) or cm.group(2) or 1)
            is_batch = True
            is_season_pack = True
            match_span = cm.span()
        elif msm:
            season_num = int(msm.group(1))
            is_batch = True
            is_season_pack = True
            match_span = msm.span()
        elif sm:
            season_num = int(sm.group(1) or 1)
            ep_start = int(sm.group(2))
            ep_end = ep_start
            match_span = sm.span()
        elif tm:
            season_num = 1
            ep_start = int(tm.group(1))
            ep_end = ep_start
            match_span = tm.span()
        elif dm:
            season_num = 1
            ep_start = int(dm.group(1))
            ep_end = ep_start
            match_span = dm.span()

        if is_batch and ep_end < ep_start:
            ep_start, ep_end = ep_end, ep_start

        title_part = cleaned_stem[:match_span[0]].strip(' .-_:[]()')
        if not title_part:
            title_part = cleaned_stem[match_span[1]:].strip(' .-_:[]()')

        series_title = clean_series_title(title_part)
        slug_base = re.sub(r'[^a-z0-9]+', '-', series_title.lower()).strip('-') or "series"

        if is_season_pack:
            tag = f"S{season_num:02d} Complete Pack"
            batch_range = f"Season {season_num} Complete Pack"
            media_type = "series_batch"
            slug = f"{slug_base}-s{season_num:02d}-complete"
        elif is_batch:
            tag = f"S{season_num:02d} EP {ep_start:02d} - {ep_end:02d}"
            batch_range = f"EP {ep_start:02d} - {ep_end:02d}"
            media_type = "series_batch"
            slug = f"{slug_base}-s{season_num:02d}-ep{ep_start:02d}-{ep_end:02d}"
        else:
            tag = f"S{season_num:02d}E{ep_start:02d}"
            batch_range = None
            media_type = "series_single"
            slug = f"{slug_base}-s{season_num:02d}e{ep_start:02d}"

        clean_display_title = f"{series_title} {tag}"
        res_meta = {
            "media_type": media_type,
            "category": "SERIES_BATCH" if is_batch else "SERIES_SINGLE",
            "clean_title": clean_display_title,
            "series_title": series_title,
            "season": season_num,
            "episode": ep_start,
            "episode_end": ep_end,
            "is_batch": is_batch,
            "is_season_pack": is_season_pack,
            "batch_range": batch_range,
            "year": found_year,
            "slug": slug,
            "series_slug": slug_base,
            "quality": tech_specs["quality"],
            "quality_label": tech_specs["quality_label"],
            "rip_type": tech_specs["rip_type"],
            "rip_score": tech_specs["rip_score"],
            "codec": tech_specs["codec"],
            "codec_score": tech_specs["codec_score"],
            "audio_languages": tech_specs["audio_languages"],
            "audio_channels": tech_specs["audio_channels"],
            "audio_channels_tag": tech_specs.get("audio_channels_tag", ""),
            "audio_score": tech_specs["audio_score"],
            "has_tamil": tech_specs["has_tamil"],
            "merit_score": tech_specs["merit_score"],
            "confidence_score": tech_specs["confidence_score"],
            "needs_lazy_sniff": tech_specs["needs_lazy_sniff"],
            "is_theater_print": tech_specs["is_theater_print"],
            "raw_filename": raw_name,
        }
        canonical_name = build_scene_canonical_name(res_meta, ext="")
        clean_fn = build_scene_canonical_name(res_meta, ext=ext if ext else ".mkv")
        res_meta["canonical_name"] = canonical_name
        res_meta["clean_filename"] = clean_fn
        res_meta["sanitized_filename"] = clean_fn
        res_meta["scene_bin_name"] = build_scene_canonical_name(res_meta, ext=".bin")
        return res_meta

    # --------------------------------------------------------------------------
    # 2. GRAMMAR CHECK: Movie Pattern (Title + Year or Sequel)
    # --------------------------------------------------------------------------
    year_match = re.search(r'\b((?:19|20)\d{2})\b', cleaned_stem)
    year = int(year_match.group(1)) if year_match else None

    sequel_suffix = ""
    for sp in SEQUEL_PATTERNS:
        sqm = re.search(sp, cleaned_stem, flags=re.IGNORECASE)
        if sqm:
            sequel_suffix = f" {sqm.group(0).replace('.', ' ').strip().title()}"
            break

    raw_movie_part = cleaned_stem[:year_match.start()] if year_match else cleaned_stem
    clean_title = clean_movie_title(raw_movie_part, str(year) if year else None)
    already_has_sequel = bool(re.search(r'\b(?:part|chapter|vol|volume|pt)\s*[-._:]?\s*([0-9ivx]+|one|two|three|four)\b', clean_title, re.IGNORECASE))
    if sequel_suffix and not already_has_sequel:
        clean_title = f"{clean_title}{sequel_suffix}"

    if not clean_title or len(clean_title) < 2:
        return None

    slug_base = re.sub(r'[^a-z0-9]+', '-', clean_title.lower()).strip('-') or "movie"
    slug = f"{slug_base}-{year}" if year else f"{slug_base}-2026"
    res_movie = {
        "media_type": "movie",
        "category": "MOVIE",
        "clean_title": clean_title,
        "series_title": None,
        "season": None,
        "episode": None,
        "episode_end": None,
        "is_batch": False,
        "is_season_pack": False,
        "batch_range": None,
        "year": year,
        "slug": slug,
        "series_slug": None,
        "quality": tech_specs["quality"],
        "quality_label": tech_specs["quality_label"],
        "rip_type": tech_specs["rip_type"],
        "rip_score": tech_specs["rip_score"],
        "codec": tech_specs["codec"],
        "codec_score": tech_specs["codec_score"],
        "audio_languages": tech_specs["audio_languages"],
        "audio_channels": tech_specs["audio_channels"],
        "audio_channels_tag": tech_specs.get("audio_channels_tag", ""),
        "audio_score": tech_specs["audio_score"],
        "has_tamil": tech_specs["has_tamil"],
        "merit_score": tech_specs["merit_score"],
        "confidence_score": tech_specs["confidence_score"],
        "needs_lazy_sniff": tech_specs["needs_lazy_sniff"],
        "is_theater_print": tech_specs["is_theater_print"],
        "raw_filename": raw_name,
    }
    canonical_name = build_scene_canonical_name(res_movie, ext="")
    clean_fn = build_scene_canonical_name(res_movie, ext=ext if ext else ".mkv")
    res_movie["canonical_name"] = canonical_name
    res_movie["clean_filename"] = clean_fn
    res_movie["sanitized_filename"] = clean_fn
    res_movie["scene_bin_name"] = build_scene_canonical_name(res_movie, ext=".bin")
    return res_movie


def sanitize_movie_title(raw_filename: str) -> Tuple[str, str, str, str, Dict[str, Any]]:
    """Universal 5-variable return sanitizer for SMD PRIME codebase."""
    parsed = parse_video_line(raw_filename)
    if parsed:
        display = f"{parsed['clean_title']} ({parsed['year']})" if parsed.get("year") else parsed["clean_title"]
        return (display, parsed["sanitized_filename"], parsed["slug"], parsed["quality"], parsed)

    # Fallback if unparseable
    specs = extract_tech_specs(raw_filename)
    stem = Path(raw_filename).stem
    ext = Path(raw_filename).suffix.lower()
    cleaned = strip_pirate_and_channel_prefixes(stem)
    slug = re.sub(r'[^a-z0-9]+', '-', cleaned.lower()).strip('-') or "media"
    sanitized = f"{slug}.{specs['quality']}{ext if ext else '.mkv'}"
    meta = {
        "media_type": "movie",
        "category": "MOVIE",
        "clean_title": cleaned.title(),
        "series_title": None,
        "season": None,
        "episode": None,
        "episode_end": None,
        "is_batch": False,
        "batch_range": None,
        "year": None,
        "slug": slug,
        **specs
    }
    return (cleaned.title(), sanitized, slug, specs["quality"], meta)
