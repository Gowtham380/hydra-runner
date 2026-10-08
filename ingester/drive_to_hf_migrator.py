#!/usr/bin/env python3
"""
================================================================================
SMD PRIME / PROJECT HYDRA - GOOGLE DRIVE TO HUGGING FACE AUTOMATED MIGRATOR
================================================================================
Features:
1. Google Drive / Local Directory Batch Scanning with Regex Title Sanitization.
2. Deduplication Engine (skips files already present in Supabase `public.movies` table).
3. Automatic Hugging Face Repository Sharding / Rotation when a repo gets full.
4. XOR 0x5F Header Obfuscation + 100MB Parallel Chunking.
5. OMDB High-Res Poster Auto-Fetch & Supabase Metadata Upsert (`onConflict: slug`).
"""

import os
import sys
import re
import math
import argparse
import tempfile
import requests
from pathlib import Path
from dotenv import load_dotenv

try:
    from huggingface_hub import HfApi
    from tqdm import tqdm
except ImportError:
    print("❌ Missing required dependencies! Run: pip install huggingface_hub tqdm requests python-dotenv")
    sys.exit(1)


XOR_KEY = 0x5F
DEFAULT_CHUNK_SIZE = 100 * 1024 * 1024  # 100MB
HEADER_MASK_LIMIT = 1024
MAX_REPO_CHUNKS = 100  # Auto-rotate repo every 100 chunks (~10GB)


def sanitize_movie_title(raw_filename: str) -> tuple[str, str, str, str]:
    """
    SMD PRIME Regex Title Sanitization & Deduplication Normalizer
    Strips website tags (@MoviezTamizha, www.1TamilMV.cz, Copy of), quality details, release year.
    Returns: (clean_title, sanitized_filename, slug, quality)
    """
    name = Path(raw_filename).stem
    ext = Path(raw_filename).suffix.lower()

    # Strip Google Drive 'Copy of', 'Copy (1) of'
    name = re.sub(r'^Copy\s*(\(\d+\))?\s*of\s+', '', name, flags=re.IGNORECASE)

    # Strip website tags, pirate groups, telegram handles using multi-pass loop
    prefix_patterns = [
        r'^(?:https?://)?(?:www\.)?[\w\.-]+\.(?:com|org|net|cz|in|me|cc|info|tv|xyz|vip|mobi|app|link|site|work|top|club|fun|online|store|tech|pro)\b[-_ ]*',
        r'^(?:www|ww1|ww2|ww3)\.[\w\.-]+\b[-_ ]*',
        r'^(?:Movieztamizha|moviez[ _-]*tamizha)\b[-_ ]*',
        r'^(?:Sam[ _-]*Dub[ _-]*Lezha|samdublezha|lezha)\b[-_ ]*',
        r'^(?:Omgxmovies|omg[ _-]*x[ _-]*movies)\b[-_ ]*',
        r'^(?:Tamilmv|tamilblasters|tamilrockers|tamilyogi|isaimini|kuttymovies|moviesda|cinemavilla|bolly4u|worldfree4u|9xmovies|katmoviehd|filmyzilla|desiremovies|mkvcinemas|hdhub4u)\b[-_ ]*',
        r'^(?:crazymoviescmc|smd|gtm|tgstream|tglezha|blura)\b[-_ ]*',
        r'^@[\w_]+\b[-_ ]*',
        r'^\([\w\.-]+\.(?:com|cz|org|net|in|me)\)[-_ ]*',
        r'^\[[\w\.-]+\.(?:com|cz|org|net|in|me)\][-_ ]*',
    ]
    for _ in range(5):
        prev = name
        for pattern in prefix_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
        name = re.sub(r'^[-\.\_\s:=|]+', '', name).strip()
        if name == prev:
            break

    name = re.sub(r'\[.*?\]', '', name)

    # Extract 4-Digit Release Year
    year_match = re.search(r'\(?(\d{4})\)?', name)
    year = year_match.group(1) if year_match else ""

    # Quality Detection
    quality = "1080p"
    if "2160p" in name.lower() or "4k" in name.lower():
        quality = "2160p"
    elif "720p" in name.lower():
        quality = "720p"
    elif "480p" in name.lower():
        quality = "480p"

    # Core Title Isolation
    core_title = re.split(r'hq|hdrip|web-dl|bluray|x264|x265|hevc|dd\+|aac|esub|720p|1080p|2160p|480p', name, flags=re.IGNORECASE)[0]
    core_title = core_title.replace('.', ' ').replace('_', ' ').strip('- ').strip()

    clean_title = f"{core_title} ({year})" if (year and year not in core_title) else core_title
    
    # Generate canonical slug for deduplication
    slug_base = re.sub(r'[^\w\s-]', '', clean_title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug_base).strip('-')
    sanitized_filename = f"{slug.replace('-', '.')}.{quality}{ext}"

    return clean_title, sanitized_filename, slug, quality


import urllib.parse


def generate_dynamic_svg_poster(title: str, year: str = "2026", quality: str = "1080p") -> str:
    """Generate high-contrast, dark-mode SVG poster as data URI for missing posters."""
    clean_title = re.sub(r'\(.*?\)', '', title).strip()
    import html
    escaped_title = html.escape(clean_title)
    words = escaped_title.split()
    if len(words) > 3:
        line1 = " ".join(words[:2])
        line2 = " ".join(words[2:])
        title_svg = f'<tspan x="300" dy="-20">{line1}</tspan><tspan x="300" dy="65">{line2}</tspan>'
    else:
        title_svg = f'<tspan x="300" dy="15">{escaped_title}</tspan>'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 900" width="600" height="900">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="50%" stop-color="#1e1b4b"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#6366f1"/>
      <stop offset="100%" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="600" height="900" fill="url(#bg)"/>
  <circle cx="300" cy="400" r="280" fill="#6366f1" opacity="0.05"/>
  <rect x="40" y="40" width="520" height="820" rx="24" fill="none" stroke="url(#accent)" stroke-width="2" stroke-dasharray="8 8" opacity="0.4"/>
  <text x="300" y="200" font-family="system-ui, sans-serif" font-weight="900" font-size="28" fill="#a855f7" text-anchor="middle" letter-spacing="6">SMD CINEMA</text>
  <text x="300" y="420" font-family="system-ui, sans-serif" font-weight="800" font-size="44" fill="#ffffff" text-anchor="middle">{title_svg}</text>
  <rect x="230" y="700" width="140" height="40" rx="20" fill="url(#accent)"/>
  <text x="300" y="726" font-family="system-ui, sans-serif" font-weight="700" font-size="18" fill="#ffffff" text-anchor="middle">{quality} • {year}</text>
</svg>'''
    encoded = urllib.parse.quote(svg)
    return f"data:image/svg+xml;charset=utf-8,{encoded}"


def fetch_tmdb_metadata(clean_title: str) -> dict:
    """3-Tier Metadata Engine: OMDB -> TMDB -> Dynamic SVG Poster"""
    omdb_key = os.getenv("OMDB_API_KEY", "b97e597f")
    tmdb_key = os.getenv("TMDB_API_KEY", "5e2c34f4d7b79e9f3a4071f5d9f25b6d")
    default_backdrop = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=80"

    year_match = re.search(r'\((\d{4})\)', clean_title)
    year_str = year_match.group(1) if year_match else "2026"
    raw_query = re.sub(r'\s*\(\d{4}\)', '', clean_title).strip()

    # Tier 1: OMDB API
    if omdb_key:
        try:
            url = f"http://www.omdbapi.com/?apikey={omdb_key}&t={requests.utils.quote(raw_query)}&y={year_str}"
            res = requests.get(url, timeout=5)
            if res.ok:
                data = res.json()
                if data.get("Response") == "True" and data.get("Poster") and data.get("Poster") != "N/A":
                    try:
                        rating = round(float(data.get("imdbRating", 8.5)), 1)
                    except ValueError:
                        rating = 8.5
                    print(f"  🎬 Tier-1 OMDB Match: '{data.get('Title')}' (Rating: {rating})")
                    return {
                        "poster_url": data.get("Poster"),
                        "backdrop_url": default_backdrop,
                        "description": data.get("Plot") or f"Direct Cinema Stream for {clean_title}",
                        "rating": rating,
                        "release_year": int(year_str) if year_str.isdigit() else 2026
                    }
        except Exception as e:
            print(f"  ⚠️ OMDB API Exception: {e}")

    # Tier 2: TMDB API
    if tmdb_key:
        try:
            url = f"https://api.themoviedb.org/3/search/movie?api_key={tmdb_key}&query={requests.utils.quote(raw_query)}&include_adult=false"
            res = requests.get(url, timeout=5)
            if res.ok:
                data = res.json()
                results = data.get("results", [])
                if results:
                    best = results[0]
                    poster_path = best.get("poster_path")
                    backdrop_path = best.get("backdrop_path")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                    backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else default_backdrop
                    if poster_url:
                        print(f"  🎬 Tier-2 TMDB Match: '{best.get('title')}'")
                        return {
                            "poster_url": poster_url,
                            "backdrop_url": backdrop_url,
                            "description": best.get("overview") or f"Direct Cinema Stream for {clean_title}",
                            "rating": round(float(best.get("vote_average", 8.5)), 1),
                            "release_year": int(year_str) if year_str.isdigit() else 2026
                        }
        except Exception as e:
            print(f"  ⚠️ TMDB API Exception: {e}")

    # Tier 3: Dynamic SVG Poster
    print(f"  🎨 Tier-3 Generated Dynamic SVG Poster for '{clean_title}'")
    dynamic_poster = generate_dynamic_svg_poster(clean_title, year=year_str)
    return {
        "poster_url": dynamic_poster,
        "backdrop_url": default_backdrop,
        "description": f"Direct Cinema Stream for {clean_title}",
        "rating": 8.5,
        "release_year": int(year_str) if year_str.isdigit() else 2026
    }



def check_already_ingested(slug: str, supabase_url: str, supabase_key: str) -> bool:
    """Check if movie slug already exists in Supabase database to prevent duplicate ingestion"""
    if not supabase_url or not supabase_key:
        return False
    try:
        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies?slug=eq.{slug}&select=id"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        res = requests.get(endpoint, headers=headers, timeout=5)
        if res.ok:
            data = res.json()
            return len(data) > 0
    except Exception:
        pass
    return False


def obfuscate_header(chunk_bytes: bytearray) -> bytearray:
    """XOR mask the first 1024 bytes of chunk container header"""
    limit = min(HEADER_MASK_LIMIT, len(chunk_bytes))
    for i in range(limit):
        chunk_bytes[i] ^= XOR_KEY
    return chunk_bytes


MAX_VAULT_BYTES = 90 * 1024 * 1024 * 1024  # 90 GB Safe Soft Cap (Rotates before 100GB limit)
NUM_ACTIVE_VAULTS = 3  # 3 Active Parallel Vault Repositories


class VaultSlot:
    """Represents an active Hugging Face storage repository vault."""
    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.current_bytes = 0


class AtomicMultiRepoMesh:
    """
    Atomic Multi-Vault Rotation & Parallel Ingestion Engine.
    Rules:
    1. 90 GB Cap: Automatically pre-spawns/rotates vault when projected size exceeds 90 GB.
    2. Zero-Split File Guarantee: 100% of a movie's chunks are assigned to a SINGLE vault.
    3. 3-Vault Active Mesh: Manages 3 parallel active vaults for maximum throughput.
    """
    def __init__(self, base_repo: str, hf_token: str):
        self.base_repo = base_repo  # e.g. "akthereddragon/hydra-movies"
        self.hf_token = hf_token
        self.api = HfApi(token=hf_token)
        self.next_index = 1
        self.active_vaults = []

        # Pre-spawn 3 Active Parallel Repositories
        print("⚡ Initializing 3-Vault Parallel Active Storage Mesh...")
        for _ in range(NUM_ACTIVE_VAULTS):
            vault = self._spawn_next_vault()
            self.active_vaults.append(vault)

    def _spawn_next_vault(self) -> VaultSlot:
        if "/" in self.base_repo:
            owner, repo_name = self.base_repo.split("/", 1)
        else:
            owner, repo_name = "user", self.base_repo

        if self.next_index == 1:
            active_id = f"{owner}/{repo_name}"
        else:
            active_id = f"{owner}/{repo_name}-{self.next_index:03d}"

        self.next_index += 1

        try:
            self.api.create_repo(
                repo_id=active_id,
                repo_type="dataset",
                private=True,
                exist_ok=True
            )
            print(f"  └─ 📦 Verified/Pre-spawned HF Vault: {active_id}")
        except Exception as e:
            print(f"  └─ ⚠️ Vault init warning ({active_id}): {e}")

        return VaultSlot(active_id)

    def select_vault_for_movie(self, movie_size_bytes: int) -> VaultSlot:
        """
        ATOMIC SELECTION RULE:
        Selects a vault where (current_bytes + movie_size_bytes) <= 90GB.
        Guarantees all chunks of the movie are stored in ONE single vault.
        """
        movie_gb = movie_size_bytes / (1024 ** 3)

        # 1. Check if movie fits in any of the 3 active vaults
        for vault in self.active_vaults:
            if vault.current_bytes + movie_size_bytes <= MAX_VAULT_BYTES:
                vault.current_bytes += movie_size_bytes
                print(f"🎯 Assigned Movie ({movie_gb:.2f} GB) atomically to Vault: {vault.repo_id} (Vault Usage: {vault.current_bytes / (1024**3):.2f} / 90 GB)")
                return vault

        # 2. If no active vault has space under 90GB, rotate out the fullest vault and spawn a new one
        self.active_vaults.sort(key=lambda v: v.current_bytes, reverse=True)
        fullest = self.active_vaults.pop(0)
        print(f"🔄 Vault '{fullest.repo_id}' reached 90GB capacity limit ({fullest.current_bytes / (1024**3):.2f} GB). Pre-spawning next Vault...")

        new_vault = self._spawn_next_vault()
        new_vault.current_bytes += movie_size_bytes
        self.active_vaults.append(new_vault)

        print(f"🎯 Assigned Movie ({movie_gb:.2f} GB) atomically to NEW Vault: {new_vault.repo_id} (Vault Usage: {new_vault.current_bytes / (1024**3):.2f} / 90 GB)")
        return new_vault


from concurrent.futures import ThreadPoolExecutor, as_completed


def upload_single_chunk(api, tmp_path, chunk_filename, active_repo_id, part, total_parts, slug):
    """Parallel upload worker for a single 100MB chunk."""
    try:
        res_url = api.upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo=chunk_filename,
            repo_id=active_repo_id,
            repo_type="dataset",
            commit_message=f"Add {slug} part {part}/{total_parts}"
        )
        return part, res_url, None
    except Exception as e:
        return part, None, str(e)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


import json
import base64
import time
import glob
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed


def extract_gdrive_folder_id(input_str: str) -> str:
    """Extracts clean Google Drive Folder ID from full URL or raw ID string."""
    if not input_str:
        return ""
    input_str = input_str.strip()
    match = re.search(r'folders/([a-zA-Z0-9_-]+)', input_str)
    if match:
        return match.group(1)
    if re.match(r'^[a-zA-Z0-9_-]{20,}$', input_str) and not os.path.exists(input_str):
        return input_str
    return ""


def load_all_service_accounts(supabase_url: str = "", supabase_key: str = "") -> list:
    """Loads Service Accounts from local keys/ directory, .env, and Supabase."""
    sa_list = []
    
    # 1. Load from local keys/ folder
    keys_dir = Path(__file__).resolve().parent.parent / "keys"
    if keys_dir.exists():
        for json_file in keys_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    email = data.get("client_email") or data.get("email")
                    key = data.get("private_key") or data.get("privateKey")
                    if email and key and not any(s["email"] == email for s in sa_list):
                        sa_list.append({"email": email, "private_key": key.replace('\\n', '\n')})
            except Exception:
                pass

    # 2. Load from Supabase
    if supabase_url and supabase_key:
        try:
            endpoint = f"{supabase_url.rstrip('/')}/rest/v1/drive_service_accounts?is_active=eq.true&select=*"
            headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
            res = requests.get(endpoint, headers=headers, timeout=5)
            if res.ok:
                for r in res.json():
                    email = r.get("sa_email") or r.get("client_email")
                    raw_key = r.get("private_key") or r.get("privateKey") or ""
                    if email and raw_key and not any(s["email"] == email for s in sa_list):
                        sa_list.append({"email": email, "private_key": raw_key.replace('\\n', '\n')})
        except Exception:
            pass

    # 3. Load from .env
    email_single = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
    key_single = os.getenv("GOOGLE_PRIVATE_KEY", "")
    if email_single and key_single and not any(s["email"] == email_single for s in sa_list):
        sa_list.append({"email": email_single, "private_key": key_single.replace('\\n', '\n')})

    return sa_list


def get_gdrive_access_token(sa: dict) -> str:
    """Generates OAuth Access Token from Service Account credentials."""
    if not sa or not sa.get("email") or not sa.get("private_key"):
        return ""
    email = sa["email"]
    raw_key = sa["private_key"].strip()
    if not raw_key.startswith("-----BEGIN PRIVATE KEY-----"):
        raw_key = f"-----BEGIN PRIVATE KEY-----\n{raw_key}\n-----END PRIVATE KEY-----\n"

    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request

        sa_info = {
            "type": "service_account",
            "client_email": email,
            "private_key": raw_key,
            "token_uri": "https://oauth2.googleapis.com/token"
        }
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=['https://www.googleapis.com/auth/drive']
        )
        creds.refresh(Request())
        return creds.token or ""
    except Exception as e:
        print(f"  ⚠️ SA Token Auth warning for [{email}]: {e}")
        return ""


def fetch_gdrive_folder_files(folder_id: str, access_token: str, parent_name: str = "Root") -> list:
    """Recursively fetches video files from Google Drive Folder ID."""
    if not folder_id:
        return []
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    query = f"'{folder_id}' in parents and trashed = false"
    url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(query)}&fields=files(id,name,size,mimeType)&pageSize=1000"

    all_videos = []
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if not res.ok:
            print(f"  ❌ GDrive API HTTP Error ({res.status_code}): {res.text}")
            return []
        items = res.json().get("files", [])
        print(f"  📂 Folder [{parent_name}] (ID: {folder_id}): Found {len(items)} item(s).")

        video_exts = ('.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v')
        for item in items:
            mime = item.get("mimeType", "")
            name = item.get("name", "")
            if mime == "application/vnd.google-apps.folder":
                sub_files = fetch_gdrive_folder_files(item["id"], access_token, parent_name=name)
                all_videos.extend(sub_files)
            elif name.lower().endswith(video_exts) or mime.startswith("video/"):
                size_mb = int(item.get('size', 0)) / (1024 * 1024)
                print(f"  ├── 🎬 Found Video: '{name}' ({size_mb:.1f} MB)")
                all_videos.append(item)
    except Exception as e:
        print(f"  ❌ GDrive Fetch Error: {e}")

    return all_videos


def download_gdrive_file_stream(file_id: str, access_token: str, dest_path: str, file_size_bytes: int = 0):
    """Downloads Google Drive file stream with live progress bar."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        downloaded = 0
        total_mb = file_size_bytes / (1024 * 1024) if file_size_bytes else 0
        last_print = time.time()
        start_time = time.time()

        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_print >= 1.5 or (file_size_bytes and downloaded >= file_size_bytes):
                        last_print = now
                        dl_mb = downloaded / (1024 * 1024)
                        speed = dl_mb / max(now - start_time, 0.1)
                        pct = min(100.0, (downloaded / file_size_bytes) * 100) if total_mb else 0
                        print(f"\r  │  📥 Streaming GDrive File: {dl_mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%) [{speed:.1f} MB/s]", end="", flush=True)
            print()


def process_batch_ingestion(source_input: str, base_repo_id: str, hf_token: str, supabase_url: str, supabase_key: str):
    folder_id = extract_gdrive_folder_id(source_input)
    sa_pool = load_all_service_accounts(supabase_url, supabase_key)

    video_items = []
    if folder_id:
        print(f"🌐 Google Drive Link/Folder ID Detected: {folder_id}")
        print(f"🔑 Loaded {len(sa_pool)} Service Account(s) in Mesh Pool.")
        access_token = ""
        for sa in sa_pool:
            access_token = get_gdrive_access_token(sa)
            if access_token:
                print(f"  🔑 SA OAuth Active: {sa['email']}")
                break
        
        gdrive_files = fetch_gdrive_folder_files(folder_id, access_token)
        for gf in gdrive_files:
            video_items.append({
                "type": "gdrive",
                "id": gf["id"],
                "name": gf["name"],
                "size": int(gf.get("size", 0))
            })
    else:
        source_path = Path(source_input).resolve()
        if not source_path.exists():
            print(f"❌ Source path does not exist: {source_path}")
            return
        video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v'}
        local_files = [f for f in source_path.rglob('*') if f.suffix.lower() in video_extensions]
        for f in local_files:
            video_items.append({
                "type": "local",
                "path": f,
                "name": f.name,
                "size": f.stat().st_size
            })

    if not video_items:
        print(f"⚠️ No video files found for: {source_input}")
        return

    print("==================================================================")
    print("🚀 SMD PRIME - ATOMIC MULTI-VAULT (90GB CAP) MIGRATOR & DEDUPLICATOR")
    print("==================================================================")
    print(f"📂 Source:           {source_input}")
    print(f"🎯 Base HF Repo:     {base_repo_id}")
    print(f"🎬 Total Media Files: {len(video_items)}")
    print("==================================================================\n")

    mesh = AtomicMultiRepoMesh(base_repo_id, hf_token)

    for idx, item in enumerate(video_items, 1):
        raw_filename = item["name"]
        clean_title, sanitized_filename, slug, quality = sanitize_movie_title(raw_filename)

        print(f"\n[{idx}/{len(video_items)}] Processing: {clean_title}")
        print(f"  ├─ Original File: {raw_filename}")
        print(f"  ├─ Canonical Slug: {slug}")

        # 1. DEDUPLICATION CHECK
        if check_already_ingested(slug, supabase_url, supabase_key):
            print(f"  └─ ⏩ [DUPLICATE SKIPPED] Movie '{clean_title}' already exists in Supabase!")
            continue

        temp_gdrive_path = None
        if item["type"] == "gdrive":
            print("  ├─ 📥 Downloading GDrive file stream for processing...")
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(raw_filename).suffix)
            temp_gdrive_path = temp_file.name
            temp_file.close()

            token = ""
            for sa in sa_pool:
                token = get_gdrive_access_token(sa)
                if token:
                    break

            try:
                download_gdrive_file_stream(item["id"], token, temp_gdrive_path, file_size_bytes=item["size"])
                file_path = Path(temp_gdrive_path)
                file_size_bytes = file_path.stat().st_size
            except Exception as e:
                print(f"  └─ ❌ GDrive Download Stream Failed: {e}")
                if temp_gdrive_path and os.path.exists(temp_gdrive_path):
                    os.remove(temp_gdrive_path)
                continue
        else:
            file_path = item["path"]
            file_size_bytes = item["size"]

        file_size_gb = file_size_bytes / (1024 ** 3)
        tmdb_meta = fetch_tmdb_metadata(clean_title)

        total_parts = math.ceil(file_size_bytes / DEFAULT_CHUNK_SIZE)
        print(f"📦 Source File Size: {file_size_gb:.2f} GB -> {total_parts} x 100MB Chunks")

        # 2. ATOMIC VAULT SELECTION (Zero-Split Guarantee)
        selected_vault = mesh.select_vault_for_movie(file_size_bytes)
        target_repo_id = selected_vault.repo_id

        # 3. CHUNKING + XOR OBFUSCATION PREPARATION
        upload_tasks = []
        with open(file_path, 'rb') as f:
            part = 1
            while True:
                chunk_data = f.read(DEFAULT_CHUNK_SIZE)
                if not chunk_data:
                    break

                obfuscated_data = obfuscate_header(bytearray(chunk_data))

                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
                tmp_path = tmp_file.name
                tmp_file.write(obfuscated_data)
                tmp_file.close()

                chunk_filename = f"{slug}/{slug}_part{part:03d}.bin"
                upload_tasks.append((tmp_path, chunk_filename, part))
                part += 1

        # Clean temp download file if from GDrive
        if temp_gdrive_path and os.path.exists(temp_gdrive_path):
            try:
                os.remove(temp_gdrive_path)
            except Exception:
                pass

        # 4. HIGH-SPEED PARALLEL CHUNK UPLOADS INTO TARGET VAULT
        print(f"  ├─ 📤 Parallel Uploading {total_parts} parts to Vault '{target_repo_id}'...")
        chunk_results = [None] * total_parts
        upload_failed = False

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_part = {
                executor.submit(
                    upload_single_chunk,
                    mesh.api,
                    tmp_path,
                    chunk_filename,
                    target_repo_id,
                    part_num,
                    total_parts,
                    slug
                ): part_num
                for tmp_path, chunk_filename, part_num in upload_tasks
            }

            for future in as_completed(future_to_part):
                p_num, res_url, err = future.result()
                if err:
                    print(f"  ❌ Failed upload for part {p_num}/{total_parts}: {err}")
                    upload_failed = True
                else:
                    chunk_results[p_num - 1] = res_url
                    print(f"  ├─ ✅ Part {p_num}/{total_parts} uploaded -> {target_repo_id}")

        if upload_failed or any(url is None for url in chunk_results):
            print(f"  └─ ❌ Ingestion incomplete for {clean_title}. Skipping DB registration.")
            continue

        chunk_urls = chunk_results

        # 5. SUPABASE DB REGISTRATION
        if supabase_url and supabase_key:
            endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies"
            ext_lower = Path(raw_filename).suffix.lower()
            mime_type = "video/mp4" if ext_lower == ".mp4" else "video/x-matroska"

            payload = {
                "title": clean_title,
                "slug": slug,
                "file_name": sanitized_filename,
                "mime_type": mime_type,
                "file_size_bytes": file_size_bytes,
                "hf_raw_url": chunk_urls[0],
                "chunk_urls": chunk_urls,
                "poster_url": tmdb_meta.get("poster_url"),
                "backdrop_url": tmdb_meta.get("backdrop_url"),
                "description": tmdb_meta.get("description"),
                "rating": tmdb_meta.get("rating"),
                "release_year": tmdb_meta.get("release_year"),
                "obfuscated": True,
                "chunk_size_mb": 100
            }

            try:
                headers = {
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                }
                res = requests.post(endpoint, json=payload, headers=headers)
                if res.status_code in (200, 201):
                    print(f"  └─ ✅ Registered in Supabase successfully!")
                else:
                    print(f"  └─ ⚠️ Supabase returned {res.status_code}: {res.text}")
            except Exception as e:
                print(f"  └─ ❌ Supabase registration failed: {e}")

    print("\n==================================================================")
    print("🎉 ALL GOOGLE DRIVE / FOLDER MIGRATIONS COMPLETED!")
    print("==================================================================")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="SMD PRIME - Google Drive to HF Automated Migrator & Deduplicator")
    parser.add_argument("--dir", "-d", help="Google Drive Folder URL, Folder ID, or local movie folder path")
    parser.add_argument("--folder-id", "-f", default="", help="Google Drive Folder ID or URL")
    parser.add_argument("--repo", "-r", default="", help="Hugging Face Dataset Repo ID (e.g. 'akthereddragon/smd-vault-2026')")

    args = parser.parse_args()

    source_input = args.folder_id or args.dir
    if not source_input:
        print("❌ Error: Must specify --dir or --folder-id (can be local path or Google Drive link/ID)")
        sys.exit(1)

    hf_token = (os.getenv("HF_TOKEN") or "").strip().strip('"').strip("'")
    repo_id = (args.repo or os.getenv("HF_REPO_ID") or "").strip()
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()

    if not repo_id or not hf_token:
        print("❌ Error: HF_REPO_ID and HF_TOKEN are required in .env or via arguments.")
        sys.exit(1)

    process_batch_ingestion(source_input, repo_id, hf_token, supabase_url, supabase_key)


if __name__ == "__main__":
    main()

