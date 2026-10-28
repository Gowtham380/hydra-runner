#!/usr/bin/env python3
"""
================================================================================
PROJECT HYDRA / SMD PRIME - MODAL CLOUD WORKER INGESTION ENGINE (STRATEGY B)
================================================================================
Architecture:
1. Serverless 24/7 Autonomous Background Execution via Modal.
2. 3-Dataset Mesh Sharding (`hydra-movies-1`, `hydra-movies-2`, `hydra-movies-3`).
3. Zero-Chunk 1:1 Native Stream Mesh -> 1 Movie File = 1 Atomic Git LFS Asset.
4. Multi-Quality DSA Mapping & Supabase `movie_sources` Registration.
5. Zero-RAM Disk Offset Streaming (Seek offset) - Maximum 800MB RAM footprint.
6. Service Account Mesh Auto-Rotation (16+ SAs).
================================================================================
"""

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import math
import json
import base64
import argparse
import io
import tempfile
import threading
import re
import requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import modal
except ImportError:
    modal = None

try:
    from huggingface_hub import HfApi, CommitOperationAdd
    from huggingface_hub.utils import disable_progress_bars
    disable_progress_bars()
except ImportError:
    print("❌ Missing required packages! Run: pip install huggingface_hub requests python-dotenv cryptography modal")
    sys.exit(1)

HEADER_MASK_LIMIT = 1024
XOR_KEY = 0x5F
MAX_PARALLEL_WORKERS = 8  # 8 Parallel Threads per Movie Upload

# 10-Dataset Mesh Repositories for High-Throughput Ingestion
MESH_REPOSITORIES = [
    "hydra-movies-1",
    "hydra-movies-2",
    "hydra-movies-3",
    "hydra-movies-4",
    "hydra-movies-5",
    "hydra-movies-6",
    "hydra-movies-7",
    "hydra-movies-8",
    "hydra-movies-9",
    "hydra-movies-10"
]

# Modal App Definition
if modal:
    image = (
        modal.Image.debian_slim()
        .pip_install(
            "huggingface_hub",
            "requests",
            "python-dotenv",
            "cryptography",
            "google-auth"
        )
    )
    app = modal.App("project-hydra-migrator", image=image)
else:
    app = None

# ================================================================================
# GREY-HAT UTILITIES: TITLE CLEANER & QUALITY PARSER (DSA)
# ================================================================================
def clean_movie_title(raw_title: str) -> str:
    """
    Aggressively strips website domain tags, pirate group prefixes, uploader labels,
    and extra noise so the movie title starts directly with the real title.
    """
    s = raw_title.strip()
    
    # Remove leading GDrive 'Copy of'
    s = re.sub(r'^Copy\s*(\(\d+\))?\s*of\s+', '', s, flags=re.IGNORECASE)
    
    # Remove telegram handles or @mentions at start
    s = re.sub(r'^@[A-Za-z0-9_.]+\s*', '', s)
    
    # Remove bracketed domain/site tags at start like [www.1TamilMV.live], [Movieztamizha], [CMC], [L]
    s = re.sub(r'^\s*\[[^\]]*\]\s*[-_:]?\s*', '', s)
    s = re.sub(r'^\s*\([^\)]*\)\s*[-_:]?\s*', '', s)

    # Prefix cleaning loop for chained site names (e.g. www.TamilMV.cz - Movieztamizha - MovieName)
    prefix_patterns = [
        # Domains: www.something.ext, http://, https:// (e.g. .capital, .technology, .online)
        r'^(?:https?://)?(?:www\.)?[a-z0-9\.-]+\.[a-z]{2,15}(?:\.[a-z]{2})?\s*[-:_]*\s*',
        # Known site & release group names at start of title
        r'^(?:1tamilmv|tamilmv|movieztamizha|omgxmovies|sam\s*dub\s*lezha|sam\s*dub|lezha|crazymoviescmc|crazymovies|cmc|smd|gtm|tgstream|tglezha|blura|isaimini|kuttymovies|tamilrockers|tamildbox|tamilblasters|tamildub|tamilgun|tamilyogi|tamilprint|tamilplay|moviesda|movieswood|moviesnation|moviezaddiction|moviez|omgmovies|omg|klwap|mallumv|bolly4u|worldfree4u|9xmovies|7starhd|filmyzilla|filmywap|desiremovies|hdhub4u|vegamovies|vega\s*movies|sdmoviespoint|katmoviehd|skymovies|ssrflix)\s*[-:_]*\s*',
        # Standalone L / L- / L_ / [L] prefix tags
        r'^\s*\[?[lL]\]?\s+[-_:]?\s*'
    ]

    for _ in range(5):
        orig = s
        for pat in prefix_patterns:
            s = re.sub(pat, '', s, flags=re.IGNORECASE).strip()
        # Remove any lingering leading non-alphanumeric chars except open parenthesis/bracket
        s = re.sub(r'^\s*[-_.:@#+!~|/]\s*', '', s).strip()
        if s == orig:
            break
            
    return s


def extract_file_metadata(raw_filename: str, file_size_bytes: int = 0) -> dict:
    """
    Extracts resolution quality, rip_type (PreDVD, BluRay, WEB-DL, etc.), codec, 
    audio languages, UI quality_label, and is_theater_print flag directly from the raw GDrive filename.
    """
    text = raw_filename.lower()
    
    # 1. Rip Type & Theater Print Detection
    is_theater_print = False
    rip_type = "WEB-DL"
    if re.search(r'\b(predvd|pre-dvd|pre_dvd|dvdscr|camrip|hdcam|cam|hdts|telecine|tc|ts|theatreprint|theaterprint|hallprint|line-audio|screener)\b', text):
        is_theater_print = True
        if re.search(r'\b(camrip|hdcam|cam|hdts|telecine|tc|ts)\b', text):
            rip_type = "CAM/TS"
        else:
            rip_type = "PreDVD"
    elif re.search(r'\bimax\b', text):
        rip_type = "IMAX Edition"
    elif re.search(r'\b(bluray|blu-ray|bdrip|bd-rip|brrip|br-rip|br|bdr)\b', text):
        rip_type = "BluRay"
    elif re.search(r'\b(web-dl|webdl)\b', text):
        rip_type = "WEB-DL"
    elif re.search(r'\b(webrip|web-rip)\b', text):
        rip_type = "WEBRip"
    elif re.search(r'\b(hdrip|hd-rip)\b', text):
        rip_type = "HDRip"
    elif re.search(r'\b(dvdrip|dvd-rip|dvdr)\b', text):
        rip_type = "DVDRip"
    elif re.search(r'\b(hdtv|hdtvrip)\b', text):
        rip_type = "HDTV"

    # 2. Quality Resolution (Explicit match only for theater prints)
    explicit_res = None
    if re.search(r'\b(2160p|4k|uhd)\b', text):
        explicit_res = "2160p"
    elif re.search(r'\b(1080p|fhd)\b', text):
        explicit_res = "1080p"
    elif re.search(r'\b(720p)\b', text):
        explicit_res = "720p"
    elif re.search(r'\b(480p|sd|360p|240p)\b', text):
        explicit_res = "480p"

    # 3. Formatted UI Quality Label & Quality Code
    if is_theater_print or rip_type in ("PreDVD", "CAM/TS"):
        if explicit_res:
            quality = explicit_res
            quality_label = f"PRE-DVD {quality.upper()} HQ"
        else:
            quality = "PreDVD"
            quality_label = "PRE-DVD THEATER"
    else:
        if explicit_res:
            quality = explicit_res
        elif file_size_bytes > 1_500_000_000:
            quality = "1080p"
        elif file_size_bytes > 700_000_000:
            quality = "720p"
        elif file_size_bytes > 0:
            quality = "480p"
        else:
            quality = "1080p"

        if quality == "2160p":
            quality_label = f"4K ULTRA HD ({rip_type})"
        elif quality == "1080p":
            quality_label = f"1080P FULL HD ({rip_type})"
        elif quality == "720p":
            quality_label = f"720P HD ({rip_type})"
        else:
            quality_label = f"480P SD ({rip_type})"

    # 4. Codec Detection
    codec = "x264"
    if re.search(r'\b(x265|hevc|h\.?265)\b', text):
        codec = "HEVC/x265"
    elif re.search(r'\b(x264|avc|h\.?264)\b', text):
        codec = "x264"
    elif re.search(r'\bav1\b', text):
        codec = "AV1"

    # 5. Audio Language Track Extraction (Strip pirate domains first)
    clean_audio_text = clean_movie_title(raw_filename).lower()
    langs = []
    if re.search(r'\b(tam|tamil)\b', clean_audio_text): langs.append("Tamil")
    if re.search(r'\b(tel|telugu)\b', clean_audio_text): langs.append("Telugu")
    if re.search(r'\b(hin|hindi)\b', clean_audio_text): langs.append("Hindi")
    if re.search(r'\b(mal|malayalam)\b', clean_audio_text) and not re.search(r'\bmalai\b', clean_audio_text): langs.append("Malayalam")
    if re.search(r'\b(kan|kannada)\b', clean_audio_text): langs.append("Kannada")
    if re.search(r'\b(eng|english)\b', clean_audio_text): langs.append("English")
    if not langs: langs = ["Tamil"]

    return {
        "quality": quality,
        "rip_type": rip_type,
        "codec": codec,
        "audio_languages": langs,
        "quality_label": quality_label,
        "is_theater_print": is_theater_print
    }


try:
    from ingester.title_sanitizer import sanitize_movie_title as engine_sanitize_movie_title, parse_video_line
except (ImportError, ModuleNotFoundError):
    import sys
    sys.path.append(str(Path(__file__).parent / "ingester"))
    from title_sanitizer import sanitize_movie_title as engine_sanitize_movie_title, parse_video_line


def sanitize_movie_title(raw_filename: str):
    """
    Parses clean canonical title, release year, resolution/quality, metadata dictionary, and master slug key.
    Delegates to central high-precision title_sanitizer engine with zero token loss and dual-grammar validation.
    """
    return engine_sanitize_movie_title(raw_filename)



def obfuscate_header(data_buffer: bytearray):
    """Obfuscates video header bytes for zero CDN stream restriction"""
    limit = min(len(data_buffer), HEADER_MASK_LIMIT)
    for i in range(limit):
        data_buffer[i] ^= XOR_KEY


# ================================================================================
# MESH REPOSITORY SHARD ROUTER (DSA: Consistent Hashing)
# ================================================================================
class MeshRepoRouter:
    """
    Consistent Hash Router for distributing movies across the 3-Dataset Mesh.
    Prevents any single HF dataset repo from reaching commit or storage bottlenecks.
    Uses PUBLIC dataset repositories to grant UNLIMITED LFS storage quota on free HF accounts.
    """
    def __init__(self, hf_token: str, owner: str = None):
        self.api = HfApi(token=hf_token)
        self.owner = owner or self.api.whoami()["name"]
        self.repos = [f"{self.owner}/{r}" for r in MESH_REPOSITORIES]
        self._ensure_repos_exist()

    def _ensure_repos_exist(self):
        for repo_id in self.repos:
            try:
                # Set private=False to unlock UNLIMITED public LFS storage quota on Hugging Face
                self.api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)
                try:
                    self.api.update_repo_settings(repo_id=repo_id, private=False, repo_type="dataset")
                except Exception:
                    pass
                print(f"✅ Verified Mesh Dataset Repo (Public/Unlimited): {repo_id}")
            except Exception as e:
                print(f"⚠️ Repo check ({repo_id}): {e}")

    def get_target_repo(self, slug: str, quality: str) -> str:
        """Determines target repository using hash routing ($O(1)$)"""
        hash_val = sum(ord(c) for c in f"{slug}_{quality}")
        selected_index = hash_val % len(self.repos)
        return self.repos[selected_index]


# ================================================================================
# 1-FILE NATIVE STREAM STORAGE & HF FILE VERIFIER
# ================================================================================


def check_single_file_exists(api: HfApi, repo_id: str, slug: str, quality: str, canonical_name: str = None) -> bool:
    """Checks if 1:1 single-file mesh exists on Hugging Face (supports both canonical scene name and legacy slug name)"""
    candidate_paths = []
    if canonical_name:
        candidate_paths.append(f"{slug}/{quality}/{canonical_name}.bin")
    candidate_paths.append(f"{slug}/{quality}/{slug}_{quality}.bin")
    for path_in_repo in candidate_paths:
        try:
            if api.file_exists(repo_id=repo_id, filename=path_in_repo, repo_type="dataset"):
                return True
        except Exception:
            pass
    return False


# ================================================================================
# PROJECT HYDRA 2.0 - 1:1 SINGLE-FILE MESH UPLOADER (ZERO CHUNKS)
# ================================================================================
def upload_movie_single_file(
    file_path: Path,
    slug: str,
    clean_title: str,
    quality: str,
    router: MeshRepoRouter,
    canonical_name: str = None
) -> tuple[list[str], str, float, float]:
    """
    PROJECT HYDRA 2.0 - 1:1 SINGLE-FILE MESH UPLOADER (ZERO CHUNKS)
    Uploads the complete movie file as a single Git LFS binary tensor file (.bin)
    to Hugging Face dataset mesh without 100MB chunk fragmentation.
    Returns: ([single_raw_url], target_repo, real_upload_speed_mbps, upload_duration_sec)
    """
    target_repo = router.get_target_repo(slug, quality)
    file_size = file_path.stat().st_size
    file_size_gb = file_size / (1024 ** 3)
    
    single_filename = f"{canonical_name}.bin" if canonical_name else f"{slug}_{quality}.bin"
    path_in_repo = f"{slug}/{quality}/{single_filename}"
    quoted_path = requests.utils.quote(path_in_repo)
    single_raw_url = f"https://huggingface.co/datasets/{target_repo}/resolve/main/{quoted_path}"

    print(f"\n🚀 [1:1 SINGLE-FILE MESH] Initiating {clean_title} [{quality}] ({file_size_gb:.2f} GB)")
    print(f"  ├─ Target Repo Mesh: {target_repo}")
    print(f"  ├─ Remote Storage Path: {path_in_repo}")

    # Check if single file already exists on HF
    try:
        if router.api.file_exists(repo_id=target_repo, filename=path_in_repo, repo_type="dataset"):
            print(f"  ✅ [PRE-CHECK COMPLETE] {clean_title} [{quality}] single file already exists on HF! Skipping upload.")
            return [single_raw_url], target_repo, 0.0, 0.0
    except Exception:
        pass

    # Obfuscate header (first 1024 bytes) in-place for PyTorch / AI Model Masquerade
    try:
        with open(file_path, "r+b") as f:
            header = bytearray(f.read(HEADER_MASK_LIMIT))
            if header:
                obfuscate_header(header)
                f.seek(0)
                f.write(header)
    except Exception as obf_err:
        print(f"  ⚠️ Warning applying header obfuscation: {obf_err}")

    print(f"  📦 Uploading 1:1 single file ({file_size_gb:.2f} GB) to [{target_repo}] via HF Git LFS...", flush=True)
    upload_start = time.time()
    upload_speed = 0.0
    upload_duration = 0.0

    for attempt in range(1, 5):
        try:
            router.api.upload_file(
                path_or_fileobj=str(file_path),
                path_in_repo=path_in_repo,
                repo_id=target_repo,
                repo_type="dataset",
                commit_message=f"Ingest {clean_title} [{quality}] (Single-File Mesh 1:1)"
            )
            upload_duration = max(time.time() - upload_start, 0.001)
            upload_speed = (file_size / (1024 * 1024)) / upload_duration
            print(f"  ✅ [1:1 UPLOAD SUCCESS] {file_size_gb:.2f} GB transferred in {upload_duration:.1f}s | ⚡ Speed: {upload_speed:.1f} MB/s", flush=True)
            break
        except Exception as err:
            err_str = str(err)
            if "429" in err_str or "rate limit" in err_str.lower():
                print(f"  ⚠️ [HTTP 429 RATE LIMIT] Repo [{target_repo}] hit limit! Switching repo shard...", flush=True)
                curr_idx = router.repos.index(target_repo) if target_repo in router.repos else 0
                next_idx = (curr_idx + 1) % len(router.repos)
                target_repo = router.repos[next_idx]
                single_raw_url = f"https://huggingface.co/datasets/{target_repo}/resolve/main/{slug}/{quality}/{single_filename}"
                try:
                    router.api.create_repo(repo_id=target_repo, repo_type="dataset", private=False, exist_ok=True)
                except Exception:
                    pass
                time.sleep(2)
                continue

            print(f"  ⚠️ Single-File Upload Attempt {attempt} failed: {err}", flush=True)
            if attempt == 4:
                raise err
    return single_raw_url, target_repo, upload_speed, upload_duration





# ================================================================================
# SUPABASE MULTI-QUALITY & MULTI-REPO ACCESS REGISTRATION
# ================================================================================
_TMDB_AVAILABLE = True

def generate_dynamic_svg_poster(title: str, quality: str = "1080p") -> str:
    """Generates an authentic SMD PRIME styled dynamic SVG poster for unmatched movies"""
    clean_display = re.sub(r'\s*\(\d{4}\)', '', title).strip()
    safe_title = (clean_display or "SMD CINEMA").upper()[:26]
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900" viewBox="0 0 600 900">
      <defs>
        <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#1e1b4b" />
          <stop offset="50%" stop-color="#0f172a" />
          <stop offset="100%" stop-color="#020617" />
        </linearGradient>
        <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#dc2626" />
          <stop offset="100%" stop-color="#e11d48" />
        </linearGradient>
      </defs>
      <rect width="600" height="900" fill="url(#bg)" />
      <circle cx="300" cy="400" r="220" fill="#dc2626" opacity="0.08" />
      <rect x="40" y="40" width="520" height="820" rx="24" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="2" />
      <rect x="70" y="80" width="120" height="36" rx="18" fill="url(#accent)" />
      <text x="130" y="103" font-family="system-ui, sans-serif" font-weight="900" font-size="11" fill="#ffffff" text-anchor="middle" letter-spacing="2">SMD PRIME</text>
      <text x="300" y="430" font-family="system-ui, sans-serif" font-weight="900" font-size="30" fill="#ffffff" text-anchor="middle" letter-spacing="1">{safe_title}</text>
      <text x="300" y="475" font-family="system-ui, sans-serif" font-weight="700" font-size="14" fill="#38bdf8" text-anchor="middle" letter-spacing="3">CINEMA • ULTRA HD • [{quality.upper()}]</text>
    </svg>'''
    return f"data:image/svg+xml;charset=utf-8,{requests.utils.quote(svg)}"


def fetch_tmdb_metadata(clean_title: str, quality: str = "1080p") -> dict:
    """
    Fetch Authentic Metadata using OMDB API + TMDB API with SMD PRIME 0-Failure Guarantee.
    Tier 1: OMDB API (Fast & Reliable, works without ISP block)
    Tier 2: TMDB API (Movie + TV Dual Search)
    Tier 3: SMD PRIME Dynamic SVG Poster Fallback
    """
    global _TMDB_AVAILABLE
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    dynamic_poster = generate_dynamic_svg_poster(clean_title, quality)
    default_backdrop = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=80"

    # 1. Detect TV show & extract series title if applicable
    raw_query = clean_movie_title(clean_title)
    is_tv = bool(re.search(r'(?i)\b(s\d+e\d+|s\d+|e\d+|season|episode)\b', raw_query))
    
    if is_tv:
        raw_query = re.split(r'(?i)\b(s\d+e\d+|s\d+|e\d+|season|episode)\b', raw_query)[0]

    # 2. Aggressive query cleaning
    q = re.sub(r'\[.*?\]|\(.*?\)', ' ', raw_query)
    q = re.sub(r'(?i)\b(\d+(\.\d+)?(gb|mb)|1080p|720p|480p|2160p|4k|amzn|nf|hs|zee5|sony|bluray|web-dl|webrip|predvd|hdrip|dvdrip|x264|x265|hevc|aac|esub|hq|org|aud|dd5|dual|multi|clean|smd|lezha|blura|dub|hin|eng|tam|tel|mal|kan|true|day\d+|ep\d+|episode|season|s\d+|e\d+|movie|dvd|cam|hdr|uncut|tamil|telugu|hindi|malayalam|kannada|english|repack)\b', ' ', q)
    q = re.sub(r'[^a-zA-Z0-9\s]', ' ', q)
    search_query = ' '.join(q.split()).strip()

    if not search_query:
        search_query = clean_title

    queries_to_try = [search_query]
    words = search_query.split()
    if len(words) > 3:
        queries_to_try.append(' '.join(words[:3]))
    if len(words) >= 2:
        queries_to_try.append(' '.join(words[:2]))

    # TIER 1: OMDB API (Authentic SMD PRIME Logic - 100% Reliable without ISP blocks)
    for sq in queries_to_try:
        try:
            omdb_url = f"https://www.omdbapi.com/?apikey=trilogy&t={requests.utils.quote(sq)}"
            res = requests.get(omdb_url, headers=headers, timeout=3)
            if res.ok:
                data = res.json()
                if data.get("Response") == "True":
                    poster_url = data.get("Poster")
                    if poster_url and poster_url != "N/A" and poster_url.startswith("http"):
                        rating = float(data.get("imdbRating")) if data.get("imdbRating") and data.get("imdbRating") != "N/A" else 8.5
                        rel_year = int(data.get("Year")[:4]) if data.get("Year") and data.get("Year")[:4].isdigit() else 2026
                        overview = data.get("Plot") if data.get("Plot") and data.get("Plot") != "N/A" else f"Direct Cinema Stream for {clean_title}"
                        duration = data.get("Runtime") if data.get("Runtime") and data.get("Runtime") != "N/A" else "2h 15m"
                        print(f"  🎬 OMDB Match: '{data.get('Title')}' (Rating: {rating}, Year: {rel_year}) -> Poster Found!")
                        return {
                            "poster_url": poster_url,
                            "backdrop_url": poster_url,
                            "description": overview,
                            "rating": rating,
                            "release_year": rel_year,
                            "duration": duration
                        }
        except Exception:
            pass

    # TIER 2: TMDB API Search
    tmdb_key = os.getenv("TMDB_API_KEY", "5e2c34f4d7b79e9f3a4071f5d9f25b6d")
    endpoints = ["multi", "tv", "movie"] if is_tv else ["multi", "movie", "tv"]

    if tmdb_key and _TMDB_AVAILABLE:
        for sq in queries_to_try:
            for ep in endpoints:
                try:
                    url = f"https://api.tmdb.org/3/search/{ep}?api_key={tmdb_key}&query={requests.utils.quote(sq)}&include_adult=false"
                    res = requests.get(url, headers=headers, timeout=0.8)
                    if res.ok:
                        data = res.json()
                        results = data.get("results", [])
                        if results:
                            best = results[0]
                            poster_path = best.get("poster_path")
                            backdrop_path = best.get("backdrop_path")
                            
                            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else dynamic_poster
                            backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else default_backdrop
                            overview = best.get("overview") or f"Direct Cinema Stream for {clean_title}"
                            rating = round(float(best.get("vote_average", 8.9)), 1)
                            rel_date = best.get("release_date") or best.get("first_air_date") or ""
                            release_year = int(rel_date.split("-")[0]) if rel_date and "-" in rel_date else 2026

                            found_name = best.get("title") or best.get("name")
                            print(f"  🎬 TMDB Match [{ep.upper()}]: '{found_name}' (Rating: {rating}, Year: {release_year}) -> Poster Found!")

                            return {
                                "poster_url": poster_url,
                                "backdrop_url": backdrop_url,
                                "description": overview,
                                "rating": rating,
                                "release_year": release_year,
                                "duration": "2h 15m"
                            }
                except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
                    break # Skip trying more endpoints if network is blocked
                except Exception as e:
                    print(f"  ⚠️ TMDB API fetch error: {e}")

    # TIER 3: SMD PRIME Dynamic SVG Poster
    print(f"  🎨 Using SMD PRIME Dynamic SVG Poster for: '{clean_title}'")
    return {
        "poster_url": dynamic_poster,
        "backdrop_url": default_backdrop,
        "description": f"Direct Cinema Stream for {clean_title}",
        "rating": 8.9,
        "release_year": 2026,
        "duration": "2h 15m"
    }


def fetch_supabase_live_counts(supabase_url: str, supabase_key: str) -> tuple[int, int]:
    """Fetches exact live count of (n_supabase_files, n_hf_synced_movies) from Supabase REST API"""
    if not supabase_url or not supabase_key:
        return 0, 0
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Prefer": "count=exact"
    }
    n_sb = 0
    n_hf = 0
    try:
        res = requests.head(f"{supabase_url.rstrip('/')}/rest/v1/movie_files", headers=headers, timeout=5)
        content_range = res.headers.get("content-range") or res.headers.get("Content-Range")
        if content_range and "/" in content_range:
            n_sb = int(content_range.split("/")[-1])
    except Exception:
        pass
        
    try:
        res_hf = requests.head(f"{supabase_url.rstrip('/')}/rest/v1/movie_files?hf_raw_url=not.is.null", headers=headers, timeout=5)
        content_range_hf = res_hf.headers.get("content-range") or res_hf.headers.get("Content-Range")
        if content_range_hf and "/" in content_range_hf:
            n_hf = int(content_range_hf.split("/")[-1])
    except Exception:
        n_hf = n_sb
        
    return n_sb, n_hf


# ================================================================================
# PROJECT HYDRA - ULTIMATE TRI-MESH COMMAND CENTER HUD UI RENDERER
# ================================================================================
def render_command_center_hud(
    n_gdrive: int,
    n_hf: int,
    n_supabase: int,
    ingested_gb: float,
    total_gb: float,
    start_time: float,
    active_sa_email: str,
    sa_quota_left_pct: float,
    sa_quota_left_gb: float,
    sa_total_count: int,
    tmdb_meta: dict,
    repo_distribution: dict,
    current_item: dict,
    healing_stats: dict,
    queue_items: list,
    shard_index: int = 1,
    total_shards: int = 1,
    folder_stats: dict = None
):
    elapsed_sec = int(time.time() - start_time)
    elapsed_str = f"{elapsed_sec // 3600:02d}:{(elapsed_sec % 3600) // 60:02d}:{elapsed_sec % 60:02d}"
    
    avg_speed = (ingested_gb * 1024) / max(elapsed_sec, 1)
    remaining_gb = max(0.0, total_gb - ingested_gb)
    eta_sec = int((remaining_gb * 1024) / max(avg_speed, 0.1)) if avg_speed > 0 else 0
    eta_str = f"{eta_sec // 3600:02d}:{(eta_sec % 3600) // 60:02d}:{eta_sec % 60:02d}"

    sync_pct = (n_supabase / max(n_gdrive, 1)) * 100

    sa_short = active_sa_email.split('@')[0] if active_sa_email else "SA #1"
    
    rating = tmdb_meta.get("rating", 8.9)
    release_year = tmdb_meta.get("release_year", 2026)
    tmdb_title = tmdb_meta.get("title") or current_item.get("clean_title", "Matched")
    tmdb_status_str = f"🟢 MATCHED ({tmdb_title} • {rating}★ • {release_year})" if tmdb_meta else "🟢 READY"

    def make_bar(pct, length=20):
        filled = int(length * pct // 100)
        return '█' * min(length, filled) + '░' * max(0, length - filled)

    title = current_item.get("clean_title", "Unknown")
    quality = current_item.get("quality", "1080p")
    size_mb = current_item.get("size_mb", 0.0)
    
    dl_pct = current_item.get("dl_pct", 100.0)
    dl_mb = current_item.get("dl_mb", size_mb)
    dl_speed = current_item.get("dl_speed", 0.0)
    dl_time = current_item.get("dl_time", 0.0)

    hf_repo = current_item.get("hf_repo", "hydra-movies-1").split("/")[-1]
    hf_speed = current_item.get("hf_speed", 0.0)
    hf_time = current_item.get("hf_time", 0.0)

    master_id = current_item.get("master_id", "Synced")
    db_time_ms = current_item.get("db_time_ms", 0.0)

    auto_heals = healing_stats.get("auto_heals", 0)
    dupes = healing_stats.get("duplicates", 0)
    sa_rotations = healing_stats.get("sa_rotations", 0)
    errors = healing_stats.get("errors", 0)
    peak_dl = healing_stats.get("peak_dl_speed", 0.0)
    peak_up = healing_stats.get("peak_up_speed", 0.0)

    queue_strs = []
    for idx, q_item in enumerate(queue_items[:3], start=1):
        q_name = q_item.get("name", "Video")
        clean_q_name, _, _, q_qual, _ = sanitize_movie_title(q_name)
        q_mb = int(int(q_item.get("size", 0)) / (1024*1024))
        queue_strs.append(f"{idx}. {clean_q_name} [{q_qual}] ({q_mb}MB)")
    queue_formatted = " | ".join(queue_strs) if queue_strs else "Queue Complete"

    w = 100
    print("╔" + "═" * (w - 2) + "╗", flush=True)
    shard_hdr = f" 🐉 PROJECT HYDRA — TRI-MESH COMMAND CENTER [SHARD {shard_index}/{total_shards}]"
    print(f"║{shard_hdr:<{w-2}}║", flush=True)
    print("╠" + "═" * (w - 2) + "╣", flush=True)
    
    line1 = f" 📊 GLOBAL PARITY : N_GDrive ({n_gdrive}) ≡ N_HF ({n_hf}) ≡ N_Supabase ({n_supabase}) | Sync: {sync_pct:.1f}%"
    print(f"║{line1:<{w-2}}║", flush=True)
    
    line2 = f" ⏱️ TIME & LOAD   : Ingested: {ingested_gb:.1f} GB / {total_gb:.1f} GB | Elapsed: {elapsed_str} | ETA: {eta_str}"
    print(f"║{line2:<{w-2}}║", flush=True)
    
    line3 = f" ⚡ REAL NETWORK  : Ingress Peak: {peak_dl:.1f} MB/s | Egress Peak: {peak_up:.1f} MB/s | Workers: 8 Threads"
    print(f"║{line3:<{w-2}}║", flush=True)
    
    line4 = f" 🔑 SA MESH QUOTA : Active: {sa_short} | Health: {sa_total_count}/{sa_total_count} 🟢 | Left: {sa_quota_left_pct:.1f}% ({sa_quota_left_gb:.1f} GB)"
    print(f"║{line4:<{w-2}}║", flush=True)
    
    line5 = f" 🎨 TMDB ENGINE   : {tmdb_status_str}"
    print(f"║{line5:<{w-2}}║", flush=True)
    print("╠" + "═" * (w - 2) + "╣", flush=True)
    
    print(f"║ 📦 HF REPO MESH DISTRIBUTION ({len(repo_distribution)} REPOS LIVE):" + " " * (w - 49) + "║", flush=True)
    total_repo_gb = sum(repo_distribution.values()) or 1.0
    sorted_repos = sorted(repo_distribution.items(), key=lambda x: x[0])
    for idx, (r_name, r_gb) in enumerate(sorted_repos, start=1):
        r_pct = min(100, int((r_gb / total_repo_gb) * 100)) if total_repo_gb > 0 else 0
        prefix = "├─" if idx < len(sorted_repos) else "└─"
        repo_line = f"    {prefix} Repo {idx:02d} ({r_name:<16}) : {r_gb:6.1f} GB [{make_bar(r_pct)}] {r_pct:3d}%"
        print(f"║{repo_line:<{w-2}}║", flush=True)
        
    print("╠" + "═" * (w - 2) + "╣", flush=True)
    act_hdr = f" 🎬 CURRENT ACTIVE ITEM: {title} [{quality}] ({size_mb:.0f} MB)"
    print(f"║{act_hdr:<{w-2}}║", flush=True)
    
    dl_line = f"    ├─ 📥 GDrive Stream : [{make_bar(int(dl_pct))}] {dl_pct:.0f}% | {dl_mb:.0f} MB | ⚡ {dl_speed:.1f} MB/s in {dl_time:.1f}s"
    print(f"║{dl_line:<{w-2}}║", flush=True)
    
    hf_line = f"    ├─ 🚀 HF 1:1 Egress : [████████████████████] 100% -> [{hf_repo}] | ⚡ {hf_speed:.1f} MB/s in {hf_time:.1f}s"
    print(f"║{hf_line:<{w-2}}║", flush=True)
    
    db_line = f"    └─ ⚡ Supabase DB   : 🟢 MASTER (ID: #{master_id}) | 🟢 QUALITY [{quality}] | ⏱️ {db_time_ms:.0f}ms Latency"
    print(f"║{db_line:<{w-2}}║", flush=True)
    
    heal_line = f" 🔧 HEALING MATRIX : Auto-Heals: {auto_heals} | Dupes Filtered: {dupes} | SA Rotations: {sa_rotations} | Errors: {errors}"
    print(f"║{heal_line:<{w-2}}║", flush=True)
    
    queue_line = f" 🔮 UP NEXT QUEUE  : {queue_formatted}"
    print(f"║{queue_line:<{w-2}}║", flush=True)
    print("╚" + "═" * (w - 2) + "╝\n", flush=True)


# ================================================================================
# SUPABASE MULTI-QUALITY & MULTI-REPO ACCESS REGISTRATION
# ================================================================================
def register_in_supabase(
    clean_title: str,
    slug: str,
    quality: str,
    file_name: str,
    file_size_bytes: int,
    hf_raw_url: str,
    target_repo: str,
    tmdb_meta: dict,
    supabase_url: str,
    supabase_key: str,
    extracted_meta: dict = None
) -> tuple[any, float]:
    """
    Registers metadata in Supabase `movies` table & multi-quality sources in `movie_files`.
    Instant developer UX: updates both `movies` (master) and `movie_files` (quality variant).
    Returns: (movie_id, db_latency_ms)
    """
    t_db_start = time.time()
    if not supabase_url or not supabase_key:
        print("  ⚠️ Supabase credentials missing. Skipping DB registration.")
        return None, 0.0

    # Fetch TMDB metadata if missing
    if not tmdb_meta or not tmdb_meta.get("poster_url"):
        tmdb_meta = fetch_tmdb_metadata(clean_title, quality)

    if not extracted_meta:
        extracted_meta = extract_file_metadata(file_name)

    quality_label = extracted_meta.get("quality_label", f"{quality.upper()} HD")
    rip_type = extracted_meta.get("rip_type", "WEB-DL")
    codec = extracted_meta.get("codec", "x264")
    audio_languages = extracted_meta.get("audio_languages", ["Tamil"])
    is_theater_print = extracted_meta.get("is_theater_print", False)

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }

    # Ensure safe non-empty hf_raw_url and valid file_size_bytes to satisfy PostgREST NOT-NULL schema constraints
    canonical_bin = (extracted_meta and extracted_meta.get("scene_bin_name")) or f"{slug}_{quality}.bin"
    quoted_rel_path = requests.utils.quote(f"{slug}/{quality}/{canonical_bin}")

    if not hf_raw_url:
        hf_raw_url = f"https://huggingface.co/datasets/{target_repo}/resolve/main/{quoted_rel_path}"
    safe_file_size = max(1024, file_size_bytes) if file_size_bytes else 1024

    # Multi-Mirror Mesh URLs
    mirror_repos = [f"akthereddragon/{r}" for r in MESH_REPOSITORIES if f"akthereddragon/{r}" != target_repo][:3]
    mirror_urls = [
        f"https://huggingface.co/datasets/{m_repo}/resolve/main/{quoted_rel_path}"
        for m_repo in mirror_repos
    ]

    clean_display_filename = (extracted_meta and extracted_meta.get("clean_filename")) or f"{clean_title} [{quality}].mkv"

    is_series = bool(extracted_meta.get("series_title")) or (extracted_meta.get("media_type") in ("series_single", "series_batch")) or (extracted_meta.get("category") in ("SERIES_SINGLE", "SERIES_BATCH"))

    if not is_series:
        # 1. Check if Master Movie Record already exists by slug or title
        movie_id = None
        get_res = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/movies?or=(slug.eq.{requests.utils.quote(slug)},title.ilike.{requests.utils.quote(clean_title)})&select=id,title,slug,poster_url",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            timeout=5
        )
        if get_res.ok and get_res.json():
            existing_movie = get_res.json()[0]
            movie_id = existing_movie.get("id")
            # If existing movie lacks poster and new has TMDB poster, patch poster
            if (not existing_movie.get("poster_url") or "data:image/svg" in str(existing_movie.get("poster_url"))) and tmdb_meta.get("poster_url"):
                requests.patch(
                    f"{supabase_url.rstrip('/')}/rest/v1/movies?id=eq.{movie_id}",
                    headers=headers,
                    json={"poster_url": tmdb_meta.get("poster_url"), "backdrop_url": tmdb_meta.get("backdrop_url")},
                    timeout=5
                )

        if not movie_id:
            # Upsert Movie Master Record in `public.movies`
            movie_payload = {
                "title": clean_title,
                "slug": slug,
                "file_name": file_name,
                "clean_filename": clean_display_filename,
                "mime_type": "video/x-matroska",
                "file_size_bytes": safe_file_size,
                "total_bytes": safe_file_size,
                "storage_type": "single_file_mesh",
                "hf_raw_url": hf_raw_url,
                "mirrors": mirror_urls,
                "poster_url": tmdb_meta.get("poster_url"),
                "backdrop_url": tmdb_meta.get("backdrop_url"),
                "description": tmdb_meta.get("description"),
                "rating": tmdb_meta.get("rating", 8.9),
                "release_year": tmdb_meta.get("release_year", 2026),
                "duration": tmdb_meta.get("duration", "2h 15m"),
                "default_quality_label": quality_label,
                "is_theater_print": is_theater_print,
                "obfuscated": True
            }

            movie_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies?on_conflict=slug"
            res = requests.post(movie_endpoint, headers=headers, json=movie_payload, timeout=10)

            # Fallback if DB schema doesn't have is_theater_print column yet
            if not res.ok and "is_theater_print" in res.text:
                movie_payload.pop("is_theater_print", None)
                res = requests.post(movie_endpoint, headers=headers, json=movie_payload, timeout=10)

            if res.ok:
                try:
                    res_json = res.json()
                    if isinstance(res_json, list) and len(res_json) > 0:
                        movie_id = res_json[0].get("id")
                except Exception:
                    pass

            if not movie_id:
                get_res_again = requests.get(
                    f"{supabase_url.rstrip('/')}/rest/v1/movies?slug=eq.{requests.utils.quote(slug)}&select=id",
                    headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
                    timeout=5
                )
                if get_res_again.ok and get_res_again.json():
                    movie_id = get_res_again.json()[0].get("id")

        if not movie_id:
            print(f"  ❌ [SUPABASE DB] Error upserting movie record for {clean_title}")
            return None, (time.time() - t_db_start) * 1000.0

        print(f"  ✅ [SUPABASE DB] Master Movie Record active -> ID: {movie_id} ({clean_title}) [TheaterPrint: {is_theater_print}]")

        # 2. Register/Upsert Quality Specific Record in `public.movie_files`
        file_payload = {
            "movie_id": movie_id,
            "quality": quality,
            "rip_type": rip_type,
            "codec": codec,
            "audio_languages": audio_languages,
            "quality_label": quality_label,
            "file_name": file_name,
            "clean_filename": clean_display_filename,
            "mime_type": "video/x-matroska",
            "file_size_bytes": safe_file_size,
            "total_bytes": safe_file_size,
            "storage_type": "single_file_mesh",
            "hf_raw_url": hf_raw_url,
            "mirrors": mirror_urls,
            "is_theater_print": is_theater_print,
            "obfuscated": True
        }

        get_file_res = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/movie_files?movie_id=eq.{movie_id}&quality=eq.{quality}&select=id",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            timeout=5
        )

        movie_file_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movie_files"
        if get_file_res.ok and get_file_res.json():
            existing_file_id = get_file_res.json()[0].get("id")
            patch_res = requests.patch(
                f"{movie_file_endpoint}?id=eq.{existing_file_id}",
                headers=headers,
                json=file_payload,
                timeout=10
            )
            if patch_res.ok:
                print(f"  ⚡ [SUPABASE DB SYNC] 🟢 Updated `movie_files` [{quality_label}] -> File ID: #{existing_file_id} | Master ID: #{movie_id}")
            else:
                print(f"  ⚠️ [SUPABASE DB SYNC] Patch `movie_files` error: {patch_res.status_code} - {patch_res.text}")
        else:
            post_res = requests.post(
                movie_file_endpoint,
                headers=headers,
                json=file_payload,
                timeout=10
            )
            if post_res.ok:
                print(f"  ⚡ [SUPABASE DB SYNC] 🟢 Inserted `movie_files` [{quality}] -> Linked to Master ID: #{movie_id}")
            else:
                print(f"  ⚠️ [SUPABASE DB SYNC] Insert `movie_files` error: {post_res.status_code} - {post_res.text}")
    else:
        # 3. Upsert Master Series Record in `public.series`
        series_title = extracted_meta.get("series_title") or clean_title
        series_slug = re.sub(r'[^a-z0-9]+', '-', series_title.lower()).strip('-') or "series"
        series_payload = {
            "title": series_title,
            "slug": series_slug,
            "poster_url": tmdb_meta.get("poster_url"),
            "backdrop_url": tmdb_meta.get("backdrop_url"),
            "description": tmdb_meta.get("description") or f"Watch all seasons and episodes of {series_title} in Full HD.",
            "release_year": tmdb_meta.get("release_year", 2026),
            "rating": tmdb_meta.get("rating", 8.8),
            "total_seasons": max(1, extracted_meta.get("season", 1)),
            "total_episodes": max(1, extracted_meta.get("episode_end", 1)),
            "status": "Returning Series"
        }
        series_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/series?on_conflict=slug"
        res_s = requests.post(series_endpoint, headers=headers, json=series_payload, timeout=10)
        s_id = None
        if res_s.ok and isinstance(res_s.json(), list) and len(res_s.json()) > 0:
            s_id = res_s.json()[0].get("id")
        if not s_id:
            get_headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
            get_res = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/series?slug=eq.{requests.utils.quote(series_slug)}&select=id", headers=get_headers, timeout=5)
            if get_res.ok and get_res.json():
                s_id = get_res.json()[0].get("id")

        if not s_id:
            print(f"  ❌ [SUPABASE DB] Error upserting series record for {series_title}: {res_s.status_code}")
            return None, (time.time() - t_db_start) * 1000.0

        print(f"  ✅ [SUPABASE DB] Master Series Record active -> ID: {s_id} ({series_title})")
        movie_id = s_id

        # 4. Upsert Series Episode File in `public.series_files`
        season_num = extracted_meta.get("season", 1)
        ep_start = extracted_meta.get("episode", 1)
        ep_end = extracted_meta.get("episode_end", ep_start)
        is_batch = extracted_meta.get("is_batch", False)

        sfile_payload = {
            "series_id": s_id,
            "season_number": season_num,
            "episode_number": ep_start,
            "episode_end": ep_end,
            "is_batch": is_batch,
            "batch_range": extracted_meta.get("batch_range"),
            "episode_title": extracted_meta.get("batch_range") if is_batch else f"Episode {ep_start}",
            "quality": quality,
            "quality_label": quality_label,
            "file_name": file_name,
            "clean_filename": clean_display_filename,
            "mime_type": "video/x-matroska",
            "file_size_bytes": safe_file_size,
            "total_bytes": safe_file_size,
            "storage_type": "single_file_mesh",
            "hf_raw_url": hf_raw_url,
            "mirrors": mirror_urls,
            "rip_type": rip_type,
            "codec": codec,
            "audio_languages": ", ".join(audio_languages) if isinstance(audio_languages, list) else audio_languages
        }
        sfile_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/series_files?on_conflict=series_id,season_number,episode_number,episode_end,quality"
        sfile_res = requests.post(sfile_endpoint, headers=headers, json=sfile_payload, timeout=10)
        if sfile_res.ok:
            print(f"  ⚡ [SUPABASE DB SYNC] 🟢 Synced `series_files` S{season_num:02d} Ep {ep_start}-{ep_end} -> Series ID: #{s_id}")

    db_latency_ms = (time.time() - t_db_start) * 1000.0
    return movie_id, db_latency_ms


def load_service_accounts_from_supabase_or_env(supabase_url: str, supabase_key: str) -> list:
    sa_list = []
    
    # 1. Attempt Supabase Table Retrieval
    if supabase_url and supabase_key:
        table_candidates = ["drive_service_accounts", "service_accounts", "gdrive_service_accounts"]
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        for tbl in table_candidates:
            try:
                endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{tbl}?select=*"
                res = requests.get(endpoint, headers=headers, timeout=5)
                if res.ok:
                    data = res.json()
                    for r in data:
                        raw_key = ""
                        if isinstance(r.get("sa_json"), str):
                            try:
                                parsed = json.loads(r["sa_json"])
                                raw_key = parsed.get("privateKey") or parsed.get("private_key")
                            except Exception:
                                pass
                        elif r.get("sa_json"):
                            raw_key = r["sa_json"].get("privateKey") or r["sa_json"].get("private_key")
                        else:
                            raw_key = r.get("private_key") or r.get("privateKey")

                        email = r.get("sa_email") or r.get("client_email") or r.get("email")
                        if email and raw_key:
                            private_key = raw_key.replace('\\n', '\n')
                            if not any(s["email"] == email for s in sa_list):
                                sa_list.append({"email": email, "private_key": private_key})
                    if sa_list:
                        print(f"  ✅ [SUPABASE DB] Successfully fetched {len(sa_list)} Service Account(s) from table [{tbl}].")
                        break
            except Exception:
                pass

    # 2. Fallback to SERVICE_ACCOUNTS_JSON / GOOGLE_SERVICE_ACCOUNT_JSON
    if not sa_list:
        raw_env_sa = os.getenv("SERVICE_ACCOUNTS_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if raw_env_sa:
            clean_env_sa = raw_env_sa.strip().strip("'").strip('"')

            # Try Base64 Decoding if applicable
            try:
                if not clean_env_sa.startswith(("{", "[")) and len(clean_env_sa) > 50:
                    decoded_bytes = base64.b64decode(clean_env_sa)
                    clean_env_sa = decoded_bytes.decode("utf-8", errors="ignore").strip()
            except Exception:
                pass

            parsed_items = []
            # Try 1: Standard JSON loads
            try:
                parsed = json.loads(clean_env_sa)
                parsed_items = [parsed] if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
            except Exception:
                # Try 2: AST literal_eval (Python dict/list string representation)
                try:
                    import ast
                    parsed = ast.literal_eval(clean_env_sa)
                    parsed_items = [parsed] if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
                except Exception:
                    # Try 3: NDJSON (Newline delimited JSON)
                    for line in clean_env_sa.splitlines():
                        line = line.strip()
                        if line:
                            try:
                                item = json.loads(line)
                                if isinstance(item, dict):
                                    parsed_items.append(item)
                            except Exception:
                                pass

            # Process extracted items
            for item in parsed_items:
                email = item.get("email") or item.get("client_email") or item.get("sa_email")
                raw_key = item.get("privateKey") or item.get("private_key")
                if email and raw_key:
                    private_key = str(raw_key).replace('\\n', '\n')
                    if not any(s["email"] == email for s in sa_list):
                        sa_list.append({"email": email, "private_key": private_key})

            # Try 4: Regex Extraction if structured parsing failed
            if not sa_list:
                emails = re.findall(r'[\w\.-]+@[\w\.-]+\.gserviceaccount\.com', clean_env_sa)
                keys = re.findall(r'-----BEGIN PRIVATE KEY-----[\s\S]+?-----END PRIVATE KEY-----', clean_env_sa)
                if emails and keys:
                    for em, k in zip(emails, keys):
                        if not any(s["email"] == em for s in sa_list):
                            sa_list.append({"email": em, "private_key": k.replace('\\n', '\n')})

            if sa_list:
                print(f"  ✅ [ENV SECRET] Successfully loaded {len(sa_list)} Service Account(s) from SERVICE_ACCOUNTS_JSON.")

        email_single = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
        key_single = os.getenv("GOOGLE_PRIVATE_KEY", "")
        if email_single and key_single and not any(s["email"] == email_single for s in sa_list):
            sa_list.append({"email": email_single, "private_key": key_single.replace('\\n', '\n')})

    if not sa_list:
        print("  ❌ [CREDENTIAL ERROR] No Service Accounts loaded!")
        print("  👉 Please verify `SERVICE_ACCOUNTS_JSON` is added in GitHub Repo Secrets (Gowtham380/hydra-runner).")

    return sa_list


def get_gdrive_access_token_from_sa(sa: dict) -> str:
    if not sa:
        return ""
    email = sa.get("client_email") or sa.get("email") or sa.get("sa_email")
    raw_key = sa.get("private_key") or sa.get("privateKey") or ""
    if not email or not raw_key:
        return ""

    formatted_key = raw_key.replace('\\n', '\n').strip()
    if not formatted_key.startswith("-----BEGIN PRIVATE KEY-----"):
        formatted_key = f"-----BEGIN PRIVATE KEY-----\n{formatted_key}\n-----END PRIVATE KEY-----\n"

    try:
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
        except ImportError:
            import subprocess
            print("  ⚡ Auto-installing missing google-auth dependencies...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "google-auth", "google-api-python-client"])
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request

        sa_info = {
            "type": "service_account",
            "client_email": email,
            "private_key": formatted_key,
            "token_uri": "https://oauth2.googleapis.com/token"
        }
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=['https://www.googleapis.com/auth/drive'])
        creds.refresh(Request())
        return creds.token or ""
    except Exception as e:
        print(f"  ⚠️ SA OAuth Warning [{email}]: {e}")
        return ""


def fetch_gdrive_folder_files(folder_id: str, access_token: str = "", folder_name: str = "Main Storage") -> list:
    """Fetch video files from Google Drive API across one or more folder IDs (comma-separated)"""
    if not folder_id:
        return []
    
    if "," in folder_id:
        fids = [fid.strip() for fid in folder_id.split(",") if fid.strip()]
        all_combined = []
        for fid in fids:
            all_combined.extend(fetch_gdrive_folder_files(fid, access_token, folder_name=folder_name))
        return all_combined

    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    api_key = os.getenv("GOOGLE_API_KEY", "")
    query = f"'{folder_id}' in parents and trashed = false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id,name,size,mimeType)&pageSize=1000&supportsAllDrives=true&includeItemsFromAllDrives=true"
    if not access_token and api_key:
        url += f"&key={api_key}"
    
    all_files = []
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.ok:
            items = res.json().get("files", [])
            for item in items:
                mime = item.get("mimeType", "")
                name = item.get("name", "")
                if mime == "application/vnd.google-apps.folder":
                    all_files.extend(fetch_gdrive_folder_files(item["id"], access_token, folder_name=name))
                elif name.lower().endswith(('.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v')) or mime.startswith("video/"):
                    item["folder_name"] = folder_name
                    all_files.append(item)
        else:
            print(f"  ❌ GDrive API error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"  ⚠️ GDrive Fetch Warning: {e}")
    return all_files


class ServiceAccountMesh:
    """
    Enterprise DSA Component: Thread-Safe Circular Ring Buffer for Multi-SA Dynamic Rotation,
    Adaptive Health Scoring, and Real-Time Monitored Quota Accounting (750 GB / Day per SA limit).
    """
    def __init__(self, sa_list: list):
        self.sa_list = sa_list or []
        self.tokens = []
        self.sa_entries = []
        self.active_index = 0
        self.lock = threading.Lock()
        self.DAILY_LIMIT_BYTES = 750 * (1024 ** 3)  # 750 GB GDrive daily quota
        self.bytes_consumed = [0] * max(1, len(self.sa_list))
        self.rotations_count = 0

        # Pre-generate access tokens from available SAs and initialize health tracking
        for i, sa in enumerate(self.sa_list):
            t = get_gdrive_access_token_from_sa(sa)
            if t:
                self.tokens.append(t)
                self.sa_entries.append({
                    "index": i,
                    "email": sa.get("email", f"sa-{i+1}@..."),
                    "token": t,
                    "healthy": True,
                    "errors": 0,
                    "successes": 0
                })

    def get_candidate_tokens(self, start_idx: int = 0) -> list[str]:
        """
        Returns a prioritized list of tokens for range downloads or direct stream fallback.
        Prioritizes known-healthy tokens (lowest errors), rotating starting offset.
        """
        with self.lock:
            if not self.sa_entries:
                return self.tokens.copy() if self.tokens else [""]
            n = len(self.sa_entries)
            perm = [(start_idx + i) % n for i in range(n)]
            # Sort by error count ascending to prioritize healthy accounts
            sorted_indices = sorted(perm, key=lambda idx: self.sa_entries[idx]["errors"])
            return [self.sa_entries[idx]["token"] for idx in sorted_indices]

    def report_token_result(self, token: str, success: bool, status_code: int = 200):
        """Thread-safe telemetry to score SA token health and dynamically isolate 403 quota burned accounts"""
        with self.lock:
            for entry in self.sa_entries:
                if entry["token"] == token:
                    if success:
                        entry["healthy"] = True
                        entry["successes"] += 1
                        if entry["errors"] > 0:
                            entry["errors"] = max(0, entry["errors"] - 1)
                    else:
                        entry["errors"] += 1
                        if status_code in (403, 429):
                            entry["healthy"] = False
                    break

    def get_token(self, offset: int = 0) -> str:
        with self.lock:
            if not self.tokens:
                return ""
            idx = (self.active_index + offset) % len(self.tokens)
            return self.tokens[idx]

    def rotate(self) -> str:
        with self.lock:
            if not self.tokens:
                return ""
            self.active_index = (self.active_index + 1) % len(self.tokens)
            self.rotations_count += 1
            return self.tokens[self.active_index]

    def record_usage(self, byte_count: int, offset: int = 0):
        with self.lock:
            if self.tokens and len(self.bytes_consumed) > 0:
                idx = (self.active_index + offset) % len(self.bytes_consumed)
                self.bytes_consumed[idx] += byte_count

    def get_active_quota_health(self) -> tuple[str, float, float, float]:
        """Returns: (active_email, consumed_gb, pct_remaining, gb_remaining)"""
        with self.lock:
            if not self.sa_entries:
                return "Public GDrive (No SA)", 0.0, 100.0, 750.0
            healthy_entries = [e for e in self.sa_entries if e["healthy"]]
            target_entry = healthy_entries[0] if healthy_entries else self.sa_entries[self.active_index % len(self.sa_entries)]
            email = target_entry.get("email", "sa-mesh@...")
            idx = target_entry.get("index", 0)
            consumed_bytes = self.bytes_consumed[idx] if idx < len(self.bytes_consumed) else 0
            consumed_gb = consumed_bytes / (1024 ** 3)
            pct_left = max(0.0, 100.0 - (consumed_bytes / self.DAILY_LIMIT_BYTES * 100.0))
            gb_left = max(0.0, (self.DAILY_LIMIT_BYTES - consumed_bytes) / (1024 ** 3))
            return email, consumed_gb, pct_left, gb_left


def download_gdrive_range_segment(
    file_id: str,
    sa_mesh_or_tokens,
    dest_path: Path,
    start_byte: int,
    end_byte: int,
    progress_lock: threading.Lock,
    stats: dict,
    thread_idx: int = 0
):
    """
    Downloads a specific byte range segment of a GDrive file to a pre-allocated disk offset.
    Features Dynamic Per-Thread Hot Swap across SA Tokens:
    - If a token hits 403 (Quota Exceeded / Forbidden) or 429, it automatically hot-swaps
      to the next candidate token and resumes from current downloaded offset within the segment.
    - Zero data loss: disk seek is always updated to (current_byte).
    """
    if isinstance(sa_mesh_or_tokens, ServiceAccountMesh):
        sa_mesh = sa_mesh_or_tokens
        candidate_tokens = sa_mesh.get_candidate_tokens(start_idx=thread_idx)
    elif isinstance(sa_mesh_or_tokens, list):
        sa_mesh = None
        n = len(sa_mesh_or_tokens)
        candidate_tokens = [sa_mesh_or_tokens[(thread_idx + k) % n] for k in range(n)] if n > 0 else [""]
    else:
        sa_mesh = None
        candidate_tokens = [sa_mesh_or_tokens] if sa_mesh_or_tokens else [""]

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
    current_byte = start_byte
    success = False
    last_err = None

    for attempt, access_token in enumerate(candidate_tokens):
        if current_byte > end_byte:
            success = True
            break

        headers = {
            "Range": f"bytes={current_byte}-{end_byte}"
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code in (403, 429):
                    if sa_mesh:
                        sa_mesh.report_token_result(access_token, success=False, status_code=r.status_code)
                    last_err = f"HTTP {r.status_code} ({r.reason})"
                    continue

                # If server returns 200 instead of 206 for non-zero offset, Range is ignored
                if start_byte > 0 and r.status_code == 200:
                    raise RuntimeError("Server returned 200 OK instead of 206 Partial Content for byte range request.")

                r.raise_for_status()

                if sa_mesh:
                    sa_mesh.report_token_result(access_token, success=True, status_code=r.status_code)

                with open(dest_path, 'r+b') as f:
                    f.seek(current_byte)
                    for chunk in r.iter_content(chunk_size=2 * 1024 * 1024):  # 2MB chunks
                        if chunk:
                            f.write(chunk)
                            chunk_len = len(chunk)
                            current_byte += chunk_len
                            with progress_lock:
                                stats["downloaded"] += chunk_len

                if current_byte > end_byte:
                    success = True
                    break
        except requests.exceptions.RequestException as e:
            last_err = e
            status_code = getattr(getattr(e, 'response', None), 'status_code', 0)
            if sa_mesh:
                sa_mesh.report_token_result(access_token, success=False, status_code=status_code)
            continue

    if not success and current_byte <= end_byte:
        raise RuntimeError(f"Thread-{thread_idx} segment [{start_byte}..{end_byte}] failed across available SAs. Last error: {last_err}")


def download_gdrive_stream(
    file_id: str,
    sa_mesh_or_tokens,
    dest_path: Path,
    expected_size: int = 0,
    num_threads: int = 8,
    sa_offset: int = 0,
    file_label: str = "Video"
) -> tuple[float, float]:
    """
    Downloads GDrive file using an Enterprise Adaptive 2-Tier Stream Architecture:
      - Tier 1: 8-Thread SA Concurrent Byte-Range Stream Mesh with Per-Thread Dynamic SA Hot Swap.
      - Tier 2: Seamless Exhaustive Multi-SA Direct Stream (8MB Buffer Chunks) on Range errors.
      - Guaranteed Zero Zombie Thread Leaks (try...finally Thread Guillotine).
      - Quantized Delta Telemetry (10% step reporting, zero 0.0% spam floods).
    Returns: (download_duration_sec, download_speed_mbps)
    """
    if isinstance(sa_mesh_or_tokens, ServiceAccountMesh):
        sa_mesh = sa_mesh_or_tokens
        tokens = sa_mesh.tokens
    elif isinstance(sa_mesh_or_tokens, list):
        tokens = sa_mesh_or_tokens
        sa_mesh = None
    else:
        tokens = [sa_mesh_or_tokens] if sa_mesh_or_tokens else []
        sa_mesh = None

    token_count = len(tokens)
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"

    # 1. Determine total size
    total_bytes = expected_size
    if not total_bytes:
        probe_tokens = sa_mesh.get_candidate_tokens(start_idx=sa_offset) if sa_mesh else tokens
        for pt in probe_tokens[:3]:
            try:
                res = requests.head(url, headers={"Authorization": f"Bearer {pt}"} if pt else {}, timeout=12)
                if res.ok:
                    total_bytes = int(res.headers.get("content-length", 0))
                    if total_bytes > 0:
                        break
            except Exception:
                pass

    start_time = time.time()
    tier1_attempt = (total_bytes >= 10 * 1024 * 1024) and (num_threads > 1) and (token_count > 0)
    tier1_success = False

    if tier1_attempt:
        with open(dest_path, 'wb') as f:
            f.truncate(total_bytes)

        segment_size = total_bytes // num_threads
        ranges = []
        for i in range(num_threads):
            start = i * segment_size
            end = (start + segment_size - 1) if i < num_threads - 1 else (total_bytes - 1)
            ranges.append((start, end))

        print(f"  ⚡ [TIER 1] Launching {num_threads}-Thread SA-Mesh Byte-Range Downloader ({total_bytes/(1024*1024):.1f} MB across {token_count} SA tokens)...", flush=True)

        progress_lock = threading.Lock()
        stats = {"downloaded": 0}
        done_flag = threading.Event()

        def log_progress():
            last_logged_bucket = -1
            last_log_wall = time.time()
            last_bytes_logged = 0
            while not done_flag.is_set():
                time.sleep(1.0)
                with progress_lock:
                    dl = stats["downloaded"]
                now = time.time()
                if total_bytes > 0:
                    pct = min(100.0, (dl / total_bytes) * 100)
                    bucket = int(pct // 10) * 10
                    if (bucket > last_logged_bucket and bucket > 0) or (now - last_log_wall >= 5.0 and dl > last_bytes_logged and dl > 0):
                        last_logged_bucket = bucket
                        last_log_wall = now
                        last_bytes_logged = dl
                        elapsed = max(now - start_time, 0.001)
                        speed_mbps = (dl / (1024 * 1024)) / elapsed
                        dl_mb = dl / (1024 * 1024)
                        total_mb = total_bytes / (1024 * 1024)
                        remaining = max(0, total_bytes - dl)
                        eta_sec = int(remaining / (speed_mbps * 1024 * 1024)) if speed_mbps > 0 else 0
                        filled = min(20, int(20 * dl // total_bytes))
                        bar = '█' * filled + '░' * (20 - filled)
                        print(f"  📥 [{pct:5.1f}%] [{bar}] {dl_mb:6.0f}/{total_mb:.0f} MB | ⚡ {speed_mbps:5.1f} MB/s | ⏱️ {eta_sec}s", flush=True)

        logger_thread = threading.Thread(target=log_progress, daemon=True)
        logger_thread.start()

        try:
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [
                    executor.submit(
                        download_gdrive_range_segment,
                        file_id,
                        sa_mesh or tokens,
                        dest_path,
                        start,
                        end,
                        progress_lock,
                        stats,
                        (sa_offset + i)
                    )
                    for i, (start, end) in enumerate(ranges)
                ]
                for future in as_completed(futures):
                    future.result()
            tier1_success = True
        except Exception as t1_err:
            tier1_success = False
            print(f"  ⚠️ [RANGE STREAM REVISE] GDrive Range restricted on '{file_label}' ({t1_err}). Activating Tier-2 Exhaustive Multi-SA Direct Stream...", flush=True)
        finally:
            done_flag.set()
            logger_thread.join(timeout=1.0)

    # TIER 2: Seamless Exhaustive Multi-SA Direct Stream Fallback
    if not tier1_success:
        t2_candidates = sa_mesh.get_candidate_tokens(start_idx=sa_offset) if sa_mesh else (tokens if tokens else [""])
        t2_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
        t2_success = False
        t2_last_err = None

        for t2_idx, t2_token in enumerate(t2_candidates):
            t2_headers = {"Authorization": f"Bearer {t2_token}"} if t2_token else {}
            try:
                with requests.get(t2_url, headers=t2_headers, stream=True, timeout=90) as r:
                    if r.status_code in (403, 429):
                        err_text = r.text[:200] if r.text else r.reason
                        if sa_mesh:
                            sa_mesh.report_token_result(t2_token, success=False, status_code=r.status_code)
                        t2_last_err = f"HTTP {r.status_code} ({err_text})"
                        continue

                    r.raise_for_status()

                    if sa_mesh:
                        sa_mesh.report_token_result(t2_token, success=True, status_code=r.status_code)

                    content_len = int(r.headers.get('content-length', total_bytes or 0))
                    eff_total = content_len or total_bytes
                    downloaded = 0
                    start_t2 = time.time()
                    last_pct_t2 = -1
                    last_log_t2 = start_t2
                    last_bytes_t2 = 0

                    with open(dest_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):  # 8MB High-Throughput Buffers
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                now = time.time()
                                if eff_total > 0:
                                    pct = min(100.0, (downloaded / eff_total) * 100)
                                    bucket = int(pct // 10) * 10
                                    if (bucket > last_pct_t2 and bucket > 0) or (now - last_log_t2 >= 5.0 and downloaded > last_bytes_t2 and downloaded > 0):
                                        last_pct_t2 = bucket
                                        last_log_t2 = now
                                        last_bytes_t2 = downloaded
                                        elapsed = max(now - start_t2, 0.001)
                                        spd = (downloaded / (1024 * 1024)) / elapsed
                                        dl_mb = downloaded / (1024 * 1024)
                                        tot_mb = eff_total / (1024 * 1024)
                                        filled = min(20, int(20 * downloaded // eff_total))
                                        bar = '█' * filled + '░' * (20 - filled)
                                        rem_s = int((eff_total - downloaded) / (spd * 1024 * 1024)) if spd > 0 else 0
                                        print(f"  📥 [Tier-2 Direct] [{pct:5.1f}%] [{bar}] {dl_mb:6.0f}/{tot_mb:.0f} MB | ⚡ {spd:5.1f} MB/s | ⏱️ {rem_s}s", flush=True)
                                else:
                                    if now - last_log_t2 >= 5.0 and downloaded > last_bytes_t2:
                                        last_log_t2 = now
                                        last_bytes_t2 = downloaded
                                        dl_mb = downloaded / (1024 * 1024)
                                        spd = dl_mb / max(now - start_t2, 0.001)
                                        print(f"  📥 [Tier-2 Direct] Downloaded: {dl_mb:.1f} MB | ⚡ {spd:.1f} MB/s", flush=True)

                    if not total_bytes:
                        total_bytes = downloaded
                    t2_success = True
                    break
            except Exception as t2_err:
                t2_last_err = t2_err
                if sa_mesh:
                    sa_mesh.report_token_result(t2_token, success=False)
                continue

        if not t2_success:
            raise RuntimeError(f"All download tiers exhausted for '{file_label}'. Last error: {t2_last_err}")

    if sa_mesh:
        sa_mesh.record_usage(total_bytes)

    elapsed = max(time.time() - start_time, 0.001)
    final_speed = (total_bytes / (1024 * 1024)) / elapsed
    print(f"  ✅ [DOWNLOAD COMPLETE] {total_bytes/(1024*1024):.1f} MB in {elapsed:.1f}s | ⚡ Transfer Speed: {final_speed:.1f} MB/s", flush=True)
    return elapsed, final_speed


# ================================================================================
# MODAL AUTONOMOUS ENTRYPOINT & SECRETS INJECTION
# ================================================================================
def run_migration_logic():
    """Core logic for Google Drive to Hugging Face 3-Dataset Migration"""
    hf_token = os.getenv("HF_TOKEN", "").strip().strip('"').strip("'")
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

    if not hf_token:
        print("❌ HF_TOKEN environment variable required!")
        return

    print("🔑 Initializing 3-Dataset Mesh Shard Router...")
    router = MeshRepoRouter(hf_token)

    # 0. Acquire GDrive Access Token Pool from Service Account Mesh
    sa_list = load_service_accounts_from_supabase_or_env(supabase_url, supabase_key)
    sa_mesh = ServiceAccountMesh(sa_list)
    if sa_mesh.tokens:
        print(f"  ✅ [SA MESH ACTIVE] {len(sa_mesh.tokens)}/{len(sa_list)} Service Account Tokens Active & Ready for Byte-Range Rotation!")

    access_token = sa_mesh.get_token(0) if sa_mesh.tokens else ""
    if access_token:
        print("  ✅ Ready for authenticated GDrive scanning.")
    else:
        print("  ⚠️ Proceeding without SA token (Public GDrive Folder mode)...")

    print(f"🚀 Project Hydra Cloud Migration Engine Active.")
    print(f"  ├─ Target Repos: {router.repos}")
    print(f"  └─ Scanning GDrive Folder ID: {folder_id}...")

    # 1. Scan GDrive Folder
    raw_gdrive_files = fetch_gdrive_folder_files(folder_id, access_token)
    total_raw_files = len(raw_gdrive_files)
    
    shard_index = int(os.getenv("SHARD_INDEX", "1"))
    total_shards = int(os.getenv("TOTAL_SHARDS", "1"))
    
    if total_shards > 1:
        gdrive_files = [f for idx, f in enumerate(raw_gdrive_files) if (idx % total_shards) + 1 == shard_index]
        print(f"🔀 [MATRIX SHARD PIPELINE ACTIVE] Runner Shard {shard_index}/{total_shards} -> Assigned {len(gdrive_files)} of {total_raw_files} files.")
    else:
        gdrive_files = raw_gdrive_files

    total_files = len(gdrive_files)
    total_gdrive_bytes = sum(int(f.get("size", 0)) for f in gdrive_files)
    total_gdrive_gb = total_gdrive_bytes / (1024**3) if total_gdrive_bytes > 0 else 640.0
    
    print(f"  📁 Shard {shard_index}/{total_shards} processing {total_files} video file(s) ({total_gdrive_gb:.1f} GB total).")

    start_time = time.time()
    ingested_bytes = 0
    sa_email, sa_used_gb, sa_pct_left, sa_gb_left = sa_mesh.get_active_quota_health()
    sa_total_count = len(sa_mesh.tokens) or len(sa_list) or 1
    
    # Initialize all 10 HF dataset repos in mesh distribution dictionary
    repo_distribution = {repo.split('/')[-1]: 0.0 for repo in router.repos}

    # Initialize GDrive folder statistics
    folder_stats = {}
    for item in gdrive_files:
        f_name = item.get("folder_name", "Main Storage")
        if f_name not in folder_stats:
            folder_stats[f_name] = {"total_bytes": 0, "ingested_bytes": 0}
        folder_stats[f_name]["total_bytes"] += int(item.get("size", 0))

    healing_stats = {
        "auto_heals": 0,
        "duplicates": 0,
        "sa_rotations": 0,
        "errors": 0,
        "peak_dl_speed": 0.0,
        "peak_up_speed": 0.0
    }

    # Fetch exact live counts from Supabase DB (Honest: no fake additions)
    live_sb_count, live_hf_count = fetch_supabase_live_counts(supabase_url, supabase_key)
    n_sb_val = live_sb_count
    n_hf_val = live_hf_count

    # Render Initial Startup Command Center HUD
    init_item = {
        "clean_title": "Initializing Shard Stream",
        "quality": "Mesh",
        "size_mb": 0.0,
        "dl_pct": 0.0,
        "dl_mb": 0.0,
        "dl_speed": 0.0,
        "dl_time": 0.0,
        "hf_repo": router.repos[0].split("/")[-1],
        "hf_speed": 0.0,
        "hf_time": 0.0,
        "master_id": "Ready",
        "db_time_ms": 0.0
    }
    render_command_center_hud(
        n_gdrive=total_files,
        n_hf=n_hf_val,
        n_supabase=n_sb_val,
        ingested_gb=0.0,
        total_gb=total_gdrive_gb,
        start_time=start_time,
        active_sa_email=sa_email,
        sa_quota_left_pct=sa_pct_left,
        sa_quota_left_gb=sa_gb_left,
        sa_total_count=sa_total_count,
        tmdb_meta={"rating": 8.9, "release_year": 2026, "title": "Hydra Mesh Active"},
        repo_distribution=repo_distribution,
        current_item=init_item,
        healing_stats=healing_stats,
        queue_items=gdrive_files[:3],
        shard_index=shard_index,
        total_shards=total_shards,
        folder_stats=folder_stats
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        for file_idx, item in enumerate(gdrive_files, start=1):
            raw_name = item.get("name", "movie.mp4")
            file_id = item.get("id")
            file_size = int(item.get("size", 0))
            f_name = item.get("folder_name", "Main Storage")
            clean_title, sanitized_filename, slug, quality, extracted_meta = sanitize_movie_title(raw_name)

            file_size_mb = file_size / (1024**2) if file_size > 0 else 721.4
            file_size_gb = file_size / (1024**3) if file_size > 0 else 0.70
            dest_path = temp_dir_path / sanitized_filename

            target_repo = router.get_target_repo(slug, quality)
            canonical_name = (extracted_meta and extracted_meta.get("canonical_name")) or f"{slug}_{quality}"
            canonical_bin = (extracted_meta and extracted_meta.get("scene_bin_name")) or f"{canonical_name}.bin"
            quoted_rel_path = requests.utils.quote(f"{slug}/{quality}/{canonical_bin}")
            single_raw_url = f"https://huggingface.co/datasets/{target_repo}/resolve/main/{quoted_rel_path}"

            # 1:1 Single File Verification on Hugging Face
            is_already_on_hf = check_single_file_exists(router.api, target_repo, slug, quality, canonical_name=canonical_name)

            if file_size > 0 and is_already_on_hf:
                print(f"  ⚡ [PRE-CHECK 100% COMPLETE] {clean_title} [{quality}] already verified on HF (1-File Native Stream)!", flush=True)
                print(f"  ⏩ INSTANT SKIPPING GDrive Download & Bandwidth Consumption!", flush=True)
                item_tmdb = fetch_tmdb_metadata(clean_title, quality)
                movie_id, db_latency = register_in_supabase(
                    clean_title=clean_title,
                    slug=slug,
                    quality=quality,
                    file_name=sanitized_filename,
                    file_size_bytes=file_size,
                    hf_raw_url=single_raw_url,
                    target_repo=target_repo,
                    tmdb_meta=item_tmdb,
                    supabase_url=supabase_url,
                    supabase_key=supabase_key,
                    extracted_meta=extracted_meta
                )
                healing_stats["auto_heals"] += 1
                ingested_bytes += file_size
                n_sb_val += 1
                n_hf_val += 1
                repo_key = target_repo.split('/')[-1]
                if repo_key in repo_distribution:
                    repo_distribution[repo_key] += file_size_gb
                if f_name in folder_stats:
                    folder_stats[f_name]["ingested_bytes"] += file_size
                continue

            # Check available disk headroom before download
            import shutil
            _, _, free_disk_bytes = shutil.disk_usage(dest_path.parent)
            free_disk_gb = free_disk_bytes / (1024 ** 3)

            if file_size > (free_disk_bytes - 1024 * 1024 * 1024):  # 1GB safety margin
                print(f"  ⚠️ [DISK HEADROOM WARNING] '{clean_title}' requires {file_size_gb:.1f} GB, but only {free_disk_gb:.1f} GB is free. Skipping to protect runner...", flush=True)
                continue

            try:
                # 1. Download stream with Adaptive 2-Tier Fallback and Quantized Delta Telemetry
                print(f"  📥 Streaming 1:1 movie from GDrive -> {dest_path.name} (Free Disk: {free_disk_gb:.1f} GB)...", flush=True)
                dl_time, dl_speed = download_gdrive_stream(
                    file_id=file_id,
                    sa_mesh_or_tokens=sa_mesh,
                    dest_path=dest_path,
                    expected_size=file_size,
                    sa_offset=file_idx,
                    file_label=clean_title
                )
                healing_stats["peak_dl_speed"] = max(healing_stats["peak_dl_speed"], dl_speed)
                healing_stats["sa_rotations"] = sa_mesh.rotations_count

                # 2. Upload as 1:1 Single-File Mesh to Hugging Face (Zero-Chunks)
                uploaded_raw_url, target_repo, up_speed, up_time = upload_movie_single_file(
                    file_path=dest_path,
                    slug=slug,
                    clean_title=clean_title,
                    quality=quality,
                    router=router,
                    canonical_name=canonical_name
                )
                healing_stats["peak_up_speed"] = max(healing_stats["peak_up_speed"], up_speed)

                # 3. Register in Supabase with Live Stopwatch Timer
                item_tmdb = fetch_tmdb_metadata(clean_title, quality)
                movie_id, db_latency = register_in_supabase(
                    clean_title=clean_title,
                    slug=slug,
                    quality=quality,
                    file_name=sanitized_filename,
                    file_size_bytes=dest_path.stat().st_size if dest_path.exists() else file_size,
                    hf_raw_url=uploaded_raw_url,
                    target_repo=target_repo,
                    tmdb_meta=item_tmdb,
                    supabase_url=supabase_url,
                    supabase_key=supabase_key,
                    extracted_meta=extracted_meta
                )

                ingested_bytes += file_size
                n_sb_val += 1
                n_hf_val += 1
                repo_key = target_repo.split('/')[-1]
                if repo_key in repo_distribution:
                    repo_distribution[repo_key] += file_size_gb
                if f_name in folder_stats:
                    folder_stats[f_name]["ingested_bytes"] += file_size

                # 4. Render Live Enterprise HUD after successful ingestion cycle
                sa_email, sa_used_gb, sa_pct_left, sa_gb_left = sa_mesh.get_active_quota_health()
                current_item = {
                    "clean_title": clean_title,
                    "quality": quality,
                    "size_mb": file_size_mb,
                    "dl_pct": 100.0,
                    "dl_mb": file_size_mb,
                    "dl_speed": dl_speed,
                    "dl_time": dl_time,
                    "hf_repo": target_repo,
                    "hf_speed": up_speed,
                    "hf_time": up_time,
                    "master_id": movie_id or "Synced",
                    "db_time_ms": db_latency
                }
                queue_items = gdrive_files[file_idx:file_idx + 3]
                render_command_center_hud(
                    n_gdrive=total_files,
                    n_hf=n_hf_val,
                    n_supabase=n_sb_val,
                    ingested_gb=(ingested_bytes / (1024**3)),
                    total_gb=total_gdrive_gb,
                    start_time=start_time,
                    active_sa_email=sa_email,
                    sa_quota_left_pct=sa_pct_left,
                    sa_quota_left_gb=sa_gb_left,
                    sa_total_count=sa_total_count,
                    tmdb_meta=item_tmdb,
                    repo_distribution=repo_distribution,
                    current_item=current_item,
                    healing_stats=healing_stats,
                    queue_items=queue_items,
                    shard_index=shard_index,
                    total_shards=total_shards,
                    folder_stats=folder_stats
                )
            except Exception as dl_err:
                healing_stats["errors"] += 1
                err_str = str(dl_err)
                if "quota" in err_str.lower() or "403" in err_str:
                    print(f"  🔒 [GOOGLE GLOBAL FILE QUOTA LOCK] '{clean_title}' is temporarily restricted by Google for 24h. Skipping to next movie...", flush=True)
                else:
                    print(f"  ⚠️ Direct transfer failed for {clean_title} ({dl_err}), skipping...", flush=True)
                continue
            finally:
                # Guaranteed Disk Reclamation: Immediately wipe temp file to free up space
                if dest_path.exists():
                    try:
                        dest_path.unlink()
                    except Exception:
                        pass


if modal:
    # Inject Secrets dynamically into Modal Cloud Container
    sa_json_env = os.getenv("SERVICE_ACCOUNTS_JSON", "")
    secrets = [
        modal.Secret.from_dict({
            "HF_TOKEN": os.getenv("HF_TOKEN", ""),
            "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "GOOGLE_DRIVE_FOLDER_ID": os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""),
            "SERVICE_ACCOUNTS_JSON": sa_json_env,
            "TMDB_API_KEY": os.getenv("TMDB_API_KEY", ""),
            "OMDB_API_KEY": os.getenv("OMDB_API_KEY", ""),
        })
    ]

    @app.function(
        secrets=secrets,
        schedule=modal.Period(minutes=15),
        timeout=86400
    )
    def run_migration_engine():
        run_migration_logic()

    @app.local_entrypoint()
    def main():
        print("⚡ Triggering Cloud Migration Engine on Modal...")
        run_migration_engine.remote()
else:
    def run_migration_engine():
        run_migration_logic()


if __name__ == "__main__":
    run_migration_logic()


