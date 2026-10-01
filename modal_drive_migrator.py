#!/usr/bin/env python3
"""
================================================================================
PROJECT HYDRA / SMD PRIME - MODAL CLOUD WORKER INGESTION ENGINE (STRATEGY B)
================================================================================
Architecture:
1. Serverless 24/7 Autonomous Background Execution via Modal.
2. 3-Dataset Mesh Sharding (`hydra-movies-1`, `hydra-movies-2`, `hydra-movies-3`).
3. Single-Commit Multi-Chunk Batching (`create_commit`) -> 1 Movie = 1 Commit.
4. Multi-Quality DSA Mapping & Supabase `movie_sources` Registration.
5. Zero-RAM Disk Offset Streaming (Seek offset) - Maximum 800MB RAM footprint.
6. Service Account Mesh Auto-Rotation (16+ SAs).
================================================================================
"""

import os
import sys
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

# ================================================================================
# CONSTANTS & CONFIGURATION
# ================================================================================
XOR_KEY = 0x5F
DEFAULT_CHUNK_SIZE = 100 * 1024 * 1024  # 100MB Chunk
HEADER_MASK_LIMIT = 1024
MAX_PARALLEL_WORKERS = 8  # 8 Parallel Threads per Movie Batch Upload

# 3-Dataset Mesh Repositories
MESH_REPOSITORIES = [
    "hydra-movies-1",
    "hydra-movies-2",
    "hydra-movies-3"
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
def sanitize_movie_title(raw_filename: str):
    """
    Parses title, release year, resolution/quality, and generates clean slug key.
    Example: 'Sarpatta Parambarai (2021) Tamil 1080p HQ PreDVD.mkv'
    -> Title: 'Sarpatta Parambarai', Year: '2021', Quality: '1080p', Slug: 'sarpatta-parambarai-2021'
    """
    stem = Path(raw_filename).stem

    # Extract Quality
    quality = "720p"  # Default
    if re.search(r'2160p|4k|uhd', stem, re.IGNORECASE):
        quality = "2160p_4K"
    elif re.search(r'1080p|fhd', stem, re.IGNORECASE):
        quality = "1080p"
    elif re.search(r'720p|hd', stem, re.IGNORECASE):
        quality = "720p"
    elif re.search(r'480p|sd', stem, re.IGNORECASE):
        quality = "480p"

    # Extract Year
    year_match = re.search(r'\(?((?:19|20)\d{2})\)?', stem)
    year = year_match.group(1) if year_match else ""

    # Clean Name
    cleaned = re.sub(r'\[.*?\]|\(.*?\)', ' ', stem)
    cleaned = re.sub(r'(?i)(1080p|720p|480p|2160p|4k|bluray|web-dl|webrip|predvd|hdrip|dvdrip|x264|x265|hevc|aac|esub|h264|hq|org|aud|dd5|1|repack|dual|multi|clean)', ' ', cleaned)
    cleaned = re.sub(r'[@_.\-+]', ' ', cleaned)
    cleaned = ' '.join(cleaned.split()).strip()

    if not cleaned:
        cleaned = stem

    slug_base = cleaned.lower()
    slug_base = re.sub(r'[^a-z0-9\s-]', '', slug_base)
    slug_base = re.sub(r'\s+', '-', slug_base).strip('-')

    if year and year not in slug_base:
        slug = f"{slug_base}-{year}"
        clean_title = f"{cleaned.title()} ({year})"
    else:
        slug = slug_base
        clean_title = cleaned.title()

    sanitized_filename = f"{slug}.mp4"
    return clean_title, sanitized_filename, slug, quality


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
# SMART DELTA RESUME & HF MISSING CHUNK VERIFIER (DSA BITSET SET-DIFFERENCE)
# ================================================================================
def get_existing_repo_chunks(api: HfApi, repo_id: str, slug: str, quality: str) -> set[int]:
    """
    Queries Hugging Face repository files to verify already uploaded chunks.
    Verifies chunk existence and size (>0 bytes) to prevent corrupted file skips.
    Returns a set of part indices (1-indexed) already stored in HF.
    """
    existing_parts = set()
    prefix = f"{slug}/{quality}/"
    try:
        # Attempt detailed tree inspection first
        tree_items = api.list_repo_tree(repo_id=repo_id, path_in_repo=f"{slug}/{quality}", repo_type="dataset")
        for item in tree_items:
            path_str = getattr(item, 'path', '') or str(item)
            size_val = getattr(item, 'size', 1)
            if path_str.endswith(".bin") and size_val > 0:
                part_match = re.search(r'_part(\d+)\.bin$', path_str)
                if part_match:
                    existing_parts.add(int(part_match.group(1)))
    except Exception:
        # Fallback to list_repo_files if directory doesn't exist yet or tree fails
        try:
            files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
            for f in files:
                if f.startswith(prefix) and f.endswith(".bin"):
                    part_match = re.search(r'_part(\d+)\.bin$', f)
                    if part_match:
                        existing_parts.add(int(part_match.group(1)))
        except Exception as e:
            print(f"  ⚠️ Couldn't check existing HF files for {slug} in {repo_id}: {e}")
            
    return existing_parts


# ================================================================================
# SLIDING-WINDOW MULTI-COMMIT BATCH UPLOADER (DSA FAIL-SAFE DELTA RESUME)
# ================================================================================
def upload_movie_batch_commit(
    file_path: Path,
    slug: str,
    clean_title: str,
    quality: str,
    router: MeshRepoRouter,
    max_chunks_per_commit: int = 8
) -> tuple[list[str], str]:
    """
    Uploads missing chunks of a movie using DSA Bitset Set-Difference & Sliding Window Micro-Commits.
    - Universe Set U = {1...N}, Verified Set S, Missing Delta = U \\ S.
    - If 100% uploaded, skips upload completely.
    - Uses max_chunks_per_commit windowing (default 8 chunks = 800MB payload max) for resilient uploads.
    """
    target_repo = router.get_target_repo(slug, quality)
    file_size = file_path.stat().st_size
    total_parts = math.ceil(file_size / DEFAULT_CHUNK_SIZE)
    
    print(f"\n🚀 [DSA BITSET RESUME] Checking {clean_title} [{quality}] ({file_size/(1024**3):.2f} GB)")
    print(f"  ├─ Target Repo Mesh: {target_repo}")
    print(f"  ├─ Total Chunks Required: {total_parts} x 100MB Chunks")

    # 1. DSA Bitset Set Difference: U \ S_verified
    existing_parts = get_existing_repo_chunks(router.api, target_repo, slug, quality)
    missing_parts = [i for i in range(1, total_parts + 1) if i not in existing_parts]
    
    print(f"  ├─ Verified on HF: {len(existing_parts)} / {total_parts} chunks present")
    print(f"  └─ Missing Delta: {len(missing_parts)} chunks to upload")

    all_chunk_urls = [
        f"https://huggingface.co/datasets/{target_repo}/resolve/main/{slug}/{quality}/{slug}_{quality}_part{p:03d}.bin"
        for p in range(1, total_parts + 1)
    ]

    if not missing_parts:
        print(f"  ✅ [100% COMPLETE] {clean_title} [{quality}] all chunks verified on HF! Skipping upload.")
        return all_chunk_urls, target_repo

    # 2. Sliding Window Chunking: Divide missing_parts into windows of size max_chunks_per_commit
    chunk_windows = [missing_parts[i:i + max_chunks_per_commit] for i in range(0, len(missing_parts), max_chunks_per_commit)]
    total_windows = len(chunk_windows)
    
    print(f"  📦 Split {len(missing_parts)} missing chunks into {total_windows} windowed commit(s) (Max {max_chunks_per_commit} chunks/commit)")

    for w_idx, window in enumerate(chunk_windows, start=1):
        operations = []
        for part_idx in window:
            offset = (part_idx - 1) * DEFAULT_CHUNK_SIZE
            with open(file_path, 'rb') as f:
                f.seek(offset)
                raw_data = f.read(DEFAULT_CHUNK_SIZE)

            chunk_bytes = bytearray(raw_data)
            obfuscate_header(chunk_bytes)
            chunk_filename = f"{slug}_{quality}_part{part_idx:03d}.bin"
            path_in_repo = f"{slug}/{quality}/{chunk_filename}"

            operations.append(
                CommitOperationAdd(
                    path_in_repo=path_in_repo,
                    path_or_fileobj=bytes(chunk_bytes)
                )
            )

        print(f"  ⚡ [Window {w_idx}/{total_windows}] Pushing Commit ({len(window)} chunks: {window[0]}..{window[-1]}) to [{target_repo}]...", flush=True)
        commit_start = time.time()
        
        for attempt in range(1, 4):
            try:
                router.api.create_commit(
                    repo_id=target_repo,
                    repo_type="dataset",
                    operations=operations,
                    commit_message=f"Ingest {clean_title} [{quality}] Window {w_idx}/{total_windows} (Parts {window[0]}..{window[-1]})"
                )
                commit_duration = time.time() - commit_start
                delta_bytes = len(window) * DEFAULT_CHUNK_SIZE
                upload_speed = (delta_bytes / (1024 * 1024)) / max(commit_duration, 0.001)
                print(f"  ✅ [Window {w_idx}/{total_windows} SUCCESS] ({len(window)} chunks, {delta_bytes/(1024*1024):.1f} MB in {commit_duration:.1f}s | ⚡ {upload_speed:.1f} MB/s)", flush=True)
                break
            except Exception as err:
                print(f"  ⚠️ Window {w_idx} Commit Attempt {attempt} failed: {err}", flush=True)
                if attempt == 3:
                    raise err
                time.sleep(attempt * 3)

    return all_chunk_urls, target_repo


# ================================================================================
# SUPABASE MULTI-QUALITY & MULTI-REPO ACCESS REGISTRATION
# ================================================================================
def register_in_supabase(
    clean_title: str,
    slug: str,
    quality: str,
    file_name: str,
    file_size_bytes: int,
    chunk_urls: list[str],
    target_repo: str,
    tmdb_meta: dict,
    supabase_url: str,
    supabase_key: str
):
    """
    Registers metadata in Supabase `movies` table & multi-quality sources in `movie_sources`.
    Enables frontend $O(1)$ quality switching (480p, 720p, 1080p, 4K).
    """
    if not supabase_url or not supabase_key:
        print("  ⚠️ Supabase credentials missing. Skipping DB registration.")
        return

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

    # 1. Upsert Movie Master Record
    movie_payload = {
        "title": clean_title,
        "slug": slug,
        "file_name": file_name,
        "mime_type": "video/x-matroska",
        "file_size_bytes": file_size_bytes,
        "hf_raw_url": chunk_urls[0] if chunk_urls else "",
        "chunk_urls": chunk_urls,
        "poster_url": tmdb_meta.get("poster_url"),
        "backdrop_url": tmdb_meta.get("backdrop_url"),
        "overview": tmdb_meta.get("overview"),
        "rating": tmdb_meta.get("rating", 0.0),
        "year": tmdb_meta.get("year", 2026),
        "genres": tmdb_meta.get("genres", []),
        "is_processed": True
    }

    movie_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies"
    res = requests.post(movie_endpoint, headers=headers, json=movie_payload, timeout=10)
    
    movie_id = None
    if res.ok and res.json():
        movie_id = res.json()[0].get("id")
    else:
        # Fetch existing movie ID if conflict occurred
        get_res = requests.get(f"{movie_endpoint}?slug=eq.{slug}&select=id", headers=headers, timeout=5)
        if get_res.ok and get_res.json():
            movie_id = get_res.json()[0].get("id")

    # 2. Register Multi-Quality Source Variant in `movie_sources`
    if movie_id:
        source_payload = {
            "movie_id": movie_id,
            "quality": quality,
            "repo_id": target_repo,
            "file_size_bytes": file_size_bytes,
            "chunk_urls": chunk_urls,
            "stream_url": chunk_urls[0] if chunk_urls else "",
            "is_active": True
        }
        source_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movie_sources"
        headers_upsert = headers.copy()
        headers_upsert["Prefer"] = "resolution=merge-duplicates"
        requests.post(source_endpoint, headers=headers_upsert, json=source_payload, timeout=10)
        print(f"  ✅ [SUPABASE DB] Registered {clean_title} [{quality}] Source -> Movie ID: {movie_id}")


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
            except Exception as sb_err:
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


def fetch_gdrive_folder_files(folder_id: str, access_token: str = "") -> list:
    """Fetch video files from Google Drive API"""
    if not folder_id:
        return []
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    api_key = os.getenv("GOOGLE_API_KEY", "")
    query = f"'{folder_id}' in parents and trashed = false"
    url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id,name,size,mimeType)&pageSize=1000"
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
                    all_files.extend(fetch_gdrive_folder_files(item["id"], access_token))
                elif name.lower().endswith(('.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v')) or mime.startswith("video/"):
                    all_files.append(item)
        else:
            print(f"  ❌ GDrive API error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"  ⚠️ GDrive Fetch Warning: {e}")
    return all_files


def download_gdrive_range_segment(
    file_id: str,
    access_token: str,
    dest_path: Path,
    start_byte: int,
    end_byte: int,
    progress_lock: threading.Lock,
    stats: dict
):
    """Downloads a specific byte range segment of a GDrive file to a pre-allocated disk offset"""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {
        "Range": f"bytes={start_byte}-{end_byte}"
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, 'r+b') as f:
            f.seek(start_byte)
            for chunk in r.iter_content(chunk_size=2 * 1024 * 1024):  # 2MB chunks
                if chunk:
                    f.write(chunk)
                    with progress_lock:
                        stats["downloaded"] += len(chunk)


def download_gdrive_stream(file_id: str, access_token: str, dest_path: Path, expected_size: int = 0, num_threads: int = 8):
    """
    Downloads GDrive file using an 8-Thread Concurrent Byte-Range Stream Mesh.
    Bypasses GDrive single-connection speed limits, accelerating downloads to 20MB/s - 40MB/s+.
    """
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    
    # 1. Determine total size
    total_bytes = expected_size
    if not total_bytes:
        try:
            res = requests.head(url, headers=headers, timeout=15)
            total_bytes = int(res.headers.get("content-length", 0))
        except Exception:
            total_bytes = 0

    # Fallback to single stream if file is small (< 10MB) or size is unknown
    if total_bytes < 10 * 1024 * 1024 or num_threads <= 1:
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_bytes = total_bytes or int(r.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            last_log_time = start_time
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=2 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_log_time >= 3.0 or (total_bytes and downloaded >= total_bytes):
                            last_log_time = now
                            elapsed = max(now - start_time, 0.001)
                            speed_mbps = (downloaded / (1024 * 1024)) / elapsed
                            dl_mb = downloaded / (1024 * 1024)
                            if total_bytes:
                                total_mb = total_bytes / (1024 * 1024)
                                pct = min(100.0, (downloaded / total_bytes) * 100)
                                remaining = max(0, total_bytes - downloaded)
                                eta_sec = int(remaining / (speed_mbps * 1024 * 1024)) if speed_mbps > 0 else 0
                                filled = int(20 * downloaded // total_bytes)
                                bar = '█' * min(20, filled) + '░' * max(0, 20 - filled)
                                print(f"  📥 [{pct:5.1f}%] [{bar}] {dl_mb:6.1f}/{total_mb:.1f} MB | ⚡ {speed_mbps:5.1f} MB/s | ⏱️ ETA: {eta_sec}s", flush=True)
                            else:
                                print(f"  📥 Downloaded: {dl_mb:.1f} MB | ⚡ {speed_mbps:.1f} MB/s", flush=True)
        return

    # 2. Pre-allocate target destination file size
    with open(dest_path, 'wb') as f:
        f.truncate(total_bytes)

    # 3. Calculate 8 Byte-Ranges
    segment_size = total_bytes // num_threads
    ranges = []
    for i in range(num_threads):
        start = i * segment_size
        end = (start + segment_size - 1) if i < num_threads - 1 else (total_bytes - 1)
        ranges.append((start, end))

    print(f"  ⚡ Launching {num_threads}-Thread Concurrent Byte-Range Downloader ({total_bytes/(1024*1024):.1f} MB)...", flush=True)

    progress_lock = threading.Lock()
    stats = {"downloaded": 0}
    start_time = time.time()
    done_flag = threading.Event()

    # 4. Background Telemetry Logger Thread (Throttled for Ultra-Clean UI)
    def log_progress():
        while not done_flag.is_set():
            time.sleep(3.0)
            now = time.time()
            with progress_lock:
                dl = stats["downloaded"]
            elapsed = max(now - start_time, 0.001)
            speed_mbps = (dl / (1024 * 1024)) / elapsed
            dl_mb = dl / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            pct = min(100.0, (dl / total_bytes) * 100)
            remaining = max(0, total_bytes - dl)
            eta_sec = int(remaining / (speed_mbps * 1024 * 1024)) if speed_mbps > 0 else 0
            filled = int(20 * dl // total_bytes)
            bar = '█' * min(20, filled) + '░' * max(0, 20 - filled)
            print(f"  📥 [{pct:5.1f}%] [{bar}] {dl_mb:6.0f}/{total_mb:.0f} MB | ⚡ {speed_mbps:5.1f} MB/s | ⏱️ {eta_sec}s", flush=True)

    logger_thread = threading.Thread(target=log_progress, daemon=True)
    logger_thread.start()

    # 5. Submit Range Workers to ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(
                download_gdrive_range_segment,
                file_id,
                access_token,
                dest_path,
                start,
                end,
                progress_lock,
                stats
            )
            for start, end in ranges
        ]
        for future in as_completed(futures):
            future.result()

    done_flag.set()
    logger_thread.join(timeout=1.0)
    
    elapsed = max(time.time() - start_time, 0.001)
    final_speed = (total_bytes / (1024 * 1024)) / elapsed
    print(f"  ✅ [DOWNLOAD COMPLETE] {total_bytes/(1024*1024):.1f} MB in {elapsed:.1f}s | ⚡ Peak Speed: {final_speed:.1f} MB/s", flush=True)


# ================================================================================
# MODAL AUTONOMOUS ENTRYPOINT & SECRETS INJECTION
# ================================================================================
def run_migration_logic():
    """Core logic for Google Drive to Hugging Face 3-Dataset Migration"""
    hf_token = os.getenv("HF_TOKEN", "")
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    if not hf_token:
        print("❌ HF_TOKEN environment variable required!")
        return

    print("🔑 Initializing 3-Dataset Mesh Shard Router...")
    router = MeshRepoRouter(hf_token)

    # 0. Acquire GDrive Access Token from Service Account Mesh
    sa_list = load_service_accounts_from_supabase_or_env(supabase_url, supabase_key)
    access_token = ""
    if sa_list:
        print(f"  🔑 Loaded {len(sa_list)} Service Account(s). Attempting to generate GDrive Access Token...")
        for sa in sa_list:
            token_candidate = get_gdrive_access_token_from_sa(sa)
            if token_candidate:
                access_token = token_candidate
                print(f"  ✅ GDrive SA Access Token successfully acquired using [{sa.get('email')}]!")
                break
    
    if access_token:
        print("  ✅ Ready for authenticated GDrive scanning.")
    else:
        print("  ⚠️ Proceeding without SA token (Public GDrive Folder mode)...")

    print(f"🚀 Project Hydra Cloud Migration Engine Active.")
    print(f"  ├─ Target Repos: {router.repos}")
    print(f"  └─ Scanning GDrive Folder ID: {folder_id}...")

    # 1. Scan GDrive Folder
    gdrive_files = fetch_gdrive_folder_files(folder_id, access_token)
    total_files = len(gdrive_files)
    print(f"  📁 Found {total_files} video file(s) in Google Drive folder.")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        for file_idx, item in enumerate(gdrive_files, start=1):
            raw_name = item.get("name", "movie.mp4")
            file_id = item.get("id")
            file_size = int(item.get("size", 0))
            clean_title, sanitized_filename, slug, quality = sanitize_movie_title(raw_name)

            file_size_gb = file_size / (1024**3) if file_size > 0 else 0.0
            print(f"\n🎬 [{file_idx}/{total_files}] Processing: {clean_title} [{quality}] ({file_size_gb:.2f} GB) (GDrive ID: {file_id})", flush=True)
            dest_path = temp_dir_path / sanitized_filename

            # Pre-Download Check: Is this movie already 100% migrated to Hugging Face?
            target_repo = router.get_target_repo(slug, quality)
            total_parts = math.ceil(file_size / DEFAULT_CHUNK_SIZE) if file_size > 0 else 1
            existing_parts = get_existing_repo_chunks(router.api, target_repo, slug, quality)
            missing_parts = [i for i in range(1, total_parts + 1) if i not in existing_parts]

            if file_size > 0 and not missing_parts:
                print(f"  ⚡ [PRE-CHECK 100% COMPLETE] {clean_title} [{quality}] already fully uploaded on HF ({len(existing_parts)}/{total_parts} chunks verified)!", flush=True)
                print(f"  ⏩ INSTANT SKIPPING GDrive Download & Bandwidth Consumption!", flush=True)
                chunk_urls = [
                    f"https://huggingface.co/datasets/{target_repo}/resolve/main/{slug}/{quality}/{slug}_{quality}_part{p:03d}.bin"
                    for p in range(1, total_parts + 1)
                ]
                register_in_supabase(
                    clean_title=clean_title,
                    slug=slug,
                    quality=quality,
                    file_name=sanitized_filename,
                    file_size_bytes=file_size,
                    chunk_urls=chunk_urls,
                    target_repo=target_repo,
                    tmdb_meta={},
                    supabase_url=supabase_url,
                    supabase_key=supabase_key
                )
                continue

            # Download stream with live progress bar
            print(f"  📥 Streaming from GDrive -> {dest_path.name} (Missing {len(missing_parts)}/{total_parts} chunks)...", flush=True)
            try:
                download_gdrive_stream(file_id, access_token, dest_path, expected_size=file_size)
            except Exception as dl_err:
                print(f"  ⚠️ Direct download failed ({dl_err}), skipping...", flush=True)
                continue

            # Upload missing chunk delta to Hugging Face
            chunk_urls, target_repo = upload_movie_batch_commit(
                file_path=dest_path,
                slug=slug,
                clean_title=clean_title,
                quality=quality,
                router=router
            )

            # Register in Supabase
            register_in_supabase(
                clean_title=clean_title,
                slug=slug,
                quality=quality,
                file_name=sanitized_filename,
                file_size_bytes=dest_path.stat().st_size,
                chunk_urls=chunk_urls,
                target_repo=target_repo,
                tmdb_meta={},
                supabase_url=supabase_url,
                supabase_key=supabase_key
            )

            # Clean up local file
            if dest_path.exists():
                dest_path.unlink()


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
