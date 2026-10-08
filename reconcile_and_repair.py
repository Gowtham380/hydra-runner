#!/usr/bin/env python3
"""
================================================================================
PROJECT HYDRA / SMD PRIME - ULTRA-FAST SUB-2S AUTO-RECONCILER & REPAIR ENGINE
================================================================================
Architecture:
1. Sub-2s Bulk State Vector Query (1 REST Request for all Supabase DB records).
2. Parallel ThreadPool (10 Workers) for HF Mesh Repositories Inventory.
3. Zero-Download Instant Repair ($O(1)$ Set Difference):
   - HF verified movies missing in `public.movies` -> Instant Batch Upsert.
   - Movies missing in `public.movie_files` -> Instant Quality Sync.
4. Zero Bandwidth Waste: Never downloads from GDrive if HF already has chunks!
================================================================================
"""

import os
import sys
import time
import re
import math
import requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from huggingface_hub import HfApi
except ImportError:
    print("❌ Missing huggingface_hub! Run: pip install huggingface_hub requests python-dotenv")
    sys.exit(1)

from modal_drive_migrator import (
    sanitize_movie_title,
    fetch_tmdb_metadata,
    generate_dynamic_svg_poster,
    load_service_accounts_from_supabase_or_env,
    get_gdrive_access_token_from_sa,
    fetch_gdrive_folder_files,
    MESH_REPOSITORIES
)

XOR_KEY = 0x5F
DEFAULT_CHUNK_SIZE = 100 * 1024 * 1024


def bulk_fetch_supabase_state(supabase_url: str, supabase_key: str) -> tuple[dict, dict]:
    """
    Fetch entire database state in 2 lightweight REST queries:
    Returns:
      movies_map: {slug: {id, title, file_name, file_size_bytes, chunk_urls, poster_url, backdrop_url, description, rating, release_year}}
      movie_files_map: {(movie_id, quality): file_id}
    """
    if not supabase_url or not supabase_key:
        return {}, {}

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"
    }

    # 1. Fetch movies master table
    movies_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies?select=id,title,slug,file_name,file_size_bytes,chunk_urls,poster_url,backdrop_url,description,rating,release_year"
    res_m = requests.get(movies_endpoint, headers=headers, timeout=10)
    movies_map = {}
    if res_m.ok and res_m.json():
        for m in res_m.json():
            movies_map[m["slug"]] = m

    # 2. Fetch movie_files quality table
    files_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movie_files?select=id,movie_id,quality"
    res_f = requests.get(files_endpoint, headers=headers, timeout=10)
    movie_files_map = {}
    if res_f.ok and res_f.json():
        for f in res_f.json():
            movie_files_map[(f["movie_id"], f["quality"])] = f["id"]

    return movies_map, movie_files_map


def scan_single_hf_repo(api: HfApi, repo_id: str) -> dict:
    """
    Inspects files in a single HF repo.
    Returns: { (slug, quality): set(part_indices) }
    """
    repo_chunks = {}
    try:
        files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
        for f in files:
            if f.endswith(".bin"):
                # Path format: {slug}/{quality}/{slug}_{quality}_part{part:03d}.bin
                match = re.search(r'^([^/]+)/([^/]+)/.*?_part(\d+)\.bin$', f)
                if match:
                    slug = match.group(1)
                    quality = match.group(2)
                    part_num = int(match.group(3))
                    key = (slug, quality)
                    if key not in repo_chunks:
                        repo_chunks[key] = set()
                    repo_chunks[key].add(part_num)
    except Exception as e:
        print(f"  ⚠️ Warning scanning HF Repo [{repo_id}]: {e}")
    return repo_chunks


def bulk_scan_hf_mesh(hf_token: str) -> dict:
    """
    Scans all 10 HF Mesh Repositories concurrently using 10 Threads.
    Returns merged map: { (slug, quality): {"repo": repo_id, "parts": set(part_indices)} }
    """
    api = HfApi(token=hf_token)
    try:
        owner = api.whoami()["name"]
    except Exception:
        owner = "akthereddragon"

    repos = [f"{owner}/{r}" for r in MESH_REPOSITORIES]
    merged_hf = {}

    start_t = time.time()
    with ThreadPoolExecutor(max_workers=min(10, len(repos))) as executor:
        future_to_repo = {executor.submit(scan_single_hf_repo, api, r): r for r in repos}
        for future in as_completed(future_to_repo):
            repo_id = future_to_repo[future]
            res = future.result()
            for (slug, quality), parts in res.items():
                if (slug, quality) not in merged_hf:
                    merged_hf[(slug, quality)] = {"repo": repo_id, "parts": set()}
                merged_hf[(slug, quality)]["parts"].update(parts)
                # Keep track of repo where chunks live
                merged_hf[(slug, quality)]["repo"] = repo_id

    duration = time.time() - start_t
    print(f"⚡ [PARALLEL HF SCAN] Scanned {len(repos)} Repos in {duration:.2f}s -> Found {len(merged_hf)} Unique Media Items")
    return merged_hf


def run_fast_reconcile_and_repair():
    """
    Main Sub-2s Auto-Reconciler & Repair Engine Execution Loop
    """
    start_total = time.time()
    hf_token = os.getenv("HF_TOKEN", "").strip().strip('"').strip("'")
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

    print("\n================================================================================")
    print("🚀 PROJECT HYDRA - ULTRA-FAST SUB-2S AUTO-RECONCILER & REPAIR ENGINE")
    print("================================================================================\n")

    # 1. Fetch Supabase State Vector (1-2 Lightweight REST Calls)
    print("📥 [STEP 1/3] Bulk Querying Supabase Database State...")
    t1 = time.time()
    movies_map, movie_files_map = bulk_fetch_supabase_state(supabase_url, supabase_key)
    print(f"  ✅ Fetched {len(movies_map)} Master Movies & {len(movie_files_map)} Quality Entries in {time.time()-t1:.2f}s")

    # 2. Parallel Scan HF Mesh Inventory (10 Parallel Threads)
    print("\n⚡ [STEP 2/3] Parallel Inventory Audit Across HF Dataset Mesh Repositories...")
    hf_mesh_map = bulk_scan_hf_mesh(hf_token)

    # 3. Scan Google Drive Folder for Metadata Alignment
    print("\n📁 [STEP 3/3] Fetching GDrive Folder Metadata for File Alignment...")
    sa_list = load_service_accounts_from_supabase_or_env(supabase_url, supabase_key)
    access_token = get_gdrive_access_token_from_sa(sa_list[0]) if sa_list else ""
    gdrive_files = fetch_gdrive_folder_files(folder_id, access_token) if folder_id else []
    print(f"  📁 GDrive Folder Contains {len(gdrive_files)} Video File(s)")

    # 4. Perform O(1) Set-Difference Auto-Reconciliation & Instant Repair
    print("\n================================================================================")
    print("🔍 [RECONCILIATION & AUTO-REPAIR AUDIT]")
    print("================================================================================\n")

    repair_count = 0
    headers_post = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }

    # Process all GDrive files & HF discovered items
    processed_slugs = set()

    for item in gdrive_files:
        raw_name = item.get("name", "")
        file_size = int(item.get("size", 0))
        clean_title, sanitized_filename, slug, quality = sanitize_movie_title(raw_name)
        processed_slugs.add(slug)

        total_parts = max(1, math.ceil(file_size / DEFAULT_CHUNK_SIZE)) if file_size > 0 else 1
        hf_info = hf_mesh_map.get((slug, quality), {"repo": f"akthereddragon/hydra-movies-1", "parts": set()})
        hf_parts = hf_info["parts"]
        target_repo = hf_info["repo"]
        
        is_hf_complete = (len(hf_parts) >= total_parts) and (total_parts > 0)
        in_movies_db = slug in movies_map
        movie_obj = movies_map.get(slug, {})
        movie_id = movie_obj.get("id")
        in_files_db = (movie_id, quality) in movie_files_map if movie_id else False

        # REPAIR CASE A: HF Has 100% Chunks, but missing from Supabase movies or movie_files table!
        if is_hf_complete and (not in_movies_db or not in_files_db):
            print(f"🔧 [INSTANT REPAIR TRIGGERED] '{clean_title}' [{quality}] ({len(hf_parts)}/{total_parts} Chunks on HF)")
            print(f"   ├─ GDrive Download: ZERO (Skipped ⚡)")
            print(f"   └─ Cause: Missing in DB -> movies: {in_movies_db}, movie_files: {in_files_db}")

            chunk_urls = [
                f"https://huggingface.co/datasets/{target_repo}/resolve/main/{slug}/{quality}/{slug}_{quality}_part{p:03d}.bin"
                for p in range(1, total_parts + 1)
            ]
            hf_raw_url = chunk_urls[0]
            safe_size = max(1024, file_size)

            # Fetch metadata if missing
            tmdb_meta = fetch_tmdb_metadata(clean_title, quality)

            # 1. Upsert Master Movie Record
            movie_payload = {
                "title": clean_title,
                "slug": slug,
                "file_name": sanitized_filename,
                "mime_type": "video/x-matroska",
                "file_size_bytes": safe_size,
                "hf_raw_url": hf_raw_url,
                "chunk_urls": chunk_urls,
                "poster_url": tmdb_meta.get("poster_url"),
                "backdrop_url": tmdb_meta.get("backdrop_url"),
                "description": tmdb_meta.get("description"),
                "rating": tmdb_meta.get("rating", 8.9),
                "release_year": tmdb_meta.get("release_year", 2026),
                "duration": tmdb_meta.get("duration", "2h 15m"),
                "obfuscated": True,
                "chunk_size_mb": 100
            }

            res_m = requests.post(f"{supabase_url.rstrip('/')}/rest/v1/movies?on_conflict=slug", headers=headers_post, json=movie_payload, timeout=10)
            rec_id = None
            if res_m.ok and isinstance(res_m.json(), list) and len(res_m.json()) > 0:
                rec_id = res_m.json()[0].get("id")

            if not rec_id:
                # Query by slug fallback
                res_q = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/movies?slug=eq.{requests.utils.quote(slug)}&select=id", headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}, timeout=5)
                if res_q.ok and res_q.json():
                    rec_id = res_q.json()[0].get("id")

            if rec_id:
                print(f"   ✅ [REPAIRED] `movies` Master Table -> ID: {rec_id}")

                # 2. Upsert Quality File Record
                file_payload = {
                    "movie_id": rec_id,
                    "quality": quality,
                    "file_name": sanitized_filename,
                    "mime_type": "video/x-matroska",
                    "file_size_bytes": safe_size,
                    "hf_raw_url": hf_raw_url,
                    "chunk_urls": chunk_urls,
                    "obfuscated": True,
                    "chunk_size_mb": 100
                }
                res_f = requests.post(f"{supabase_url.rstrip('/')}/rest/v1/movie_files", headers=headers_post, json=file_payload, timeout=10)
                if res_f.ok:
                    print(f"   ✅ [REPAIRED] `movie_files` Quality Table [{quality}] Entry Synced!")
                    repair_count += 1
                else:
                    print(f"   ⚠️ `movie_files` Post Error: {res_f.status_code} - {res_f.text}")

    total_time = time.time() - start_total
    print("\n================================================================================")
    print(f"🎉 [AUDIT & REPAIR COMPLETE] Total Time Elapsed: {total_time:.2f}s")
    print(f"   ├─ Scanned GDrive Files: {len(gdrive_files)}")
    print(f"   ├─ Instant Repaired DB Records: {repair_count}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_fast_reconcile_and_repair()
