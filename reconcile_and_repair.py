#!/usr/bin/env python3
"""
================================================================================
PROJECT HYDRA / SMD PRIME - 2026 HIGH-ROI 4-TABLE RECONCILER & REPAIR ENGINE
================================================================================
Architecture:
1. 4-Table Dual-Domain Support:
   - Movies Domain: `public.movies` (Master) + `public.movie_files` (Quality)
   - Series Domain: `public.series` (Master) + `public.series_files` (Episodes/Batches)
2. Native 1-File Streaming (Zero-Chunk Overhead, Instant HTTP 206 Range Passthrough).
3. Sub-2s Bulk State Vector Query (1 REST Request per table).
4. Parallel ThreadPool (10 Workers) across Hugging Face Dataset Mesh Repositories.
5. Zero Download Bandwidth Waste: Reconciles verified files directly into DB.
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

from ingester.title_sanitizer import (
    sanitize_movie_title,
    parse_video_line,
    extract_tech_specs
)

from modal_drive_migrator import (
    fetch_tmdb_metadata,
    generate_dynamic_svg_poster,
    load_service_accounts_from_supabase_or_env,
    get_gdrive_access_token_from_sa,
    fetch_gdrive_folder_files,
    MESH_REPOSITORIES
)

XOR_KEY = 0x5F
HEADER_MASK_LIMIT = 1024


def bulk_fetch_supabase_state_4table(supabase_url: str, supabase_key: str) -> tuple[dict, dict, dict, dict]:
    """
    Fetch entire database state across all 4 tables in parallel:
    Returns:
      movies_map: {slug: movie_obj}
      movie_files_map: {(movie_id, quality): file_id}
      series_map: {slug: series_obj}
      series_files_map: {(series_id, season, ep_start, ep_end, quality): file_id}
    """
    if not supabase_url or not supabase_key:
        return {}, {}, {}, {}

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"
    }

    movies_map = {}
    movie_files_map = {}
    series_map = {}
    series_files_map = {}

    try:
        # 1. Fetch movies master
        res_m = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/movies?select=id,title,slug,poster_url,backdrop_url,description,rating,release_year", headers=headers, timeout=10)
        if res_m.ok and res_m.json():
            for m in res_m.json():
                movies_map[m["slug"]] = m

        # 2. Fetch movie_files
        res_mf = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/movie_files?select=id,movie_id,quality", headers=headers, timeout=10)
        if res_mf.ok and res_mf.json():
            for f in res_mf.json():
                movie_files_map[(f["movie_id"], f["quality"])] = f["id"]

        # 3. Fetch series master
        res_s = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/series?select=id,title,slug,poster_url,backdrop_url,description,rating,release_year", headers=headers, timeout=10)
        if res_s.ok and res_s.json():
            for s in res_s.json():
                series_map[s["slug"]] = s

        # 4. Fetch series_files
        res_sf = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/series_files?select=id,series_id,season_number,episode_number,episode_end,quality", headers=headers, timeout=10)
        if res_sf.ok and res_sf.json():
            for sf in res_sf.json():
                key = (sf["series_id"], sf["season_number"], sf["episode_number"], sf.get("episode_end", sf["episode_number"]), sf["quality"])
                series_files_map[key] = sf["id"]
    except Exception as e:
        print(f"⚠️ Error fetching Supabase state: {e}")

    return movies_map, movie_files_map, series_map, series_files_map


def scan_single_hf_repo(api: HfApi, repo_id: str) -> dict:
    """
    Inspects files in a single HF repo.
    Returns: { (slug, quality): {"repo": repo_id, "single_file": True, "bin_path": str} }
    """
    repo_inventory = {}
    try:
        files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
        for f in files:
            if f.endswith(".bin"):
                # Single-File Mesh: {slug}/{quality}/{canonical_scene_name}.bin
                single_match = re.search(r'^([^/]+)/([^/]+)/([^/]+)\.bin$', f)
                if single_match and "_part" not in f:
                    slug = single_match.group(1)
                    quality = single_match.group(2)
                    key = (slug, quality)
                    repo_inventory[key] = {
                        "repo": repo_id,
                        "single_file": True,
                        "bin_path": f
                    }
    except Exception as e:
        err_str = str(e)
        if "404" in err_str or "Repository Not Found" in err_str:
            try:
                api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)
                print(f"  🆕 [AUTO-CREATE] HF Repo '{repo_id}' created successfully!")
            except Exception as ce:
                print(f"  ❌ Could not create repo {repo_id}: {ce}")
        else:
            print(f"  ⚠️ Warning scanning {repo_id}: {e}")
    return repo_inventory


def bulk_scan_hf_mesh_parallel(hf_token: str) -> dict:
    """Parallel inventory audit of all 10 HF dataset repos in ~1-2 seconds."""
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
            for (slug, quality), data in res.items():
                merged_hf[(slug, quality)] = data

    duration = time.time() - start_t
    print(f"⚡ [PARALLEL HF MESH AUDIT] Scanned {len(repos)} Repos in {duration:.2f}s -> Found {len(merged_hf)} Variants")
    return merged_hf


def run_fast_reconcile_and_repair():
    start_total = time.time()
    hf_token = os.getenv("HF_TOKEN", "").strip().strip('"').strip("'")
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

    print("\n================================================================================")
    print("🚀 SMD PRIME - 2026 HIGH-ROI 4-TABLE RECONCILER & REPAIR ENGINE")
    print("================================================================================\n")

    # 1. Fetch Supabase Bulk State across 4 tables
    print("📥 [1/3] Querying Supabase 4-Table Master State...")
    t1 = time.time()
    movies_map, movie_files_map, series_map, series_files_map = bulk_fetch_supabase_state_4table(supabase_url, supabase_key)
    print(f"  ✅ Movies: {len(movies_map)} | Movie Files: {len(movie_files_map)} | Series: {len(series_map)} | Series Files: {len(series_files_map)} ({time.time()-t1:.2f}s)")

    # 2. Parallel Scan HF Repositories
    print("\n⚡ [2/3] Parallel Inventory Audit Across 10 HF Dataset Mesh Repos...")
    hf_mesh_map = bulk_scan_hf_mesh_parallel(hf_token)

    # 3. GDrive Metadata Fetching
    print("\n📁 [3/3] Fetching Google Drive Video Catalog...")
    sa_list = load_service_accounts_from_supabase_or_env(supabase_url, supabase_key)
    access_token = get_gdrive_access_token_from_sa(sa_list[0]) if sa_list else ""
    gdrive_files = fetch_gdrive_folder_files(folder_id, access_token) if folder_id else []
    print(f"  📁 GDrive Folder Contains {len(gdrive_files)} Video File(s)")

    # 4. Perform O(1) Set-Difference Auto-Reconciliation & Instant Repair
    print("\n================================================================================")
    print("🔍 [RECONCILIATION & 4-TABLE REPAIR EXECUTION]")
    print("================================================================================\n")

    repaired_movies = 0
    repaired_series = 0

    headers_post = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }

    for item in gdrive_files:
        raw_name = item.get("name", "")
        file_size = int(item.get("size", 0))
        parsed = parse_video_line(raw_name)
        if not parsed:
            continue

        category = parsed.get("category", "MOVIE")
        clean_title = parsed["clean_title"]
        sanitized_filename = parsed["sanitized_filename"]
        slug = parsed["slug"]
        quality = parsed["quality"]
        hf_info = hf_mesh_map.get((slug, quality), {"repo": "akthereddragon/hydra-movies-1", "single_file": False})
        is_single_file = hf_info.get("single_file", False)

        if not is_single_file:
            continue

        safe_size = max(1024, file_size)

        # 1-File Native Stream URL & Multi-Mirror CDN
        target_repo = hf_info.get("repo", "akthereddragon/hydra-movies-1")
        canonical_bin = parsed.get("scene_bin_name") or f"{slug}_{quality}.bin"
        actual_bin_path = hf_info.get("bin_path") or f"{slug}/{quality}/{canonical_bin}"
        quoted_bin_path = requests.utils.quote(actual_bin_path)
        single_url = f"https://huggingface.co/datasets/{target_repo}/resolve/main/{quoted_bin_path}"
        mirror_repos = [f"akthereddragon/{r}" for r in MESH_REPOSITORIES if f"akthereddragon/{r}" != target_repo][:3]
        mirror_urls = [
            f"https://huggingface.co/datasets/{m}/resolve/main/{quoted_bin_path}"
            for m in mirror_repos
        ]

        # ----------------------------------------------------------------------
        # CASE A: MOVIE DOMAIN (movies & movie_files)
        # ----------------------------------------------------------------------
        if category == "MOVIE":
            in_movies_db = slug in movies_map
            movie_obj = movies_map.get(slug, {})
            movie_id = movie_obj.get("id")
            in_files_db = (movie_id, quality) in movie_files_map if movie_id else False

            if not in_movies_db or not in_files_db:
                print(f"🎬 [MOVIE REPAIR] '{clean_title}' [{quality}] (1-File Native on HF)")
                tmdb_meta = fetch_tmdb_metadata(clean_title, quality)

                # Upsert Master Movie Record
                movie_payload = {
                    "title": clean_title,
                    "slug": slug,
                    "file_name": sanitized_filename,
                    "clean_filename": parsed.get("clean_filename") or f"{clean_title} [{quality}].mkv",
                    "mime_type": "video/x-matroska",
                    "file_size_bytes": safe_size,
                    "total_bytes": safe_size,
                    "storage_type": "single_file_mesh",
                    "hf_raw_url": single_url,
                    "mirrors": mirror_urls,
                    "poster_url": tmdb_meta.get("poster_url"),
                    "backdrop_url": tmdb_meta.get("backdrop_url"),
                    "description": tmdb_meta.get("description"),
                    "rating": tmdb_meta.get("rating", 8.5),
                    "release_year": parsed.get("year") or tmdb_meta.get("release_year", 2026),
                    "duration": tmdb_meta.get("duration", "2h 15m"),
                    "default_quality_label": parsed.get("quality_label", "1080P FULL HD"),
                    "is_theater_print": parsed.get("is_theater_print", False)
                }

                res_m = requests.post(f"{supabase_url.rstrip('/')}/rest/v1/movies?on_conflict=slug", headers=headers_post, json=movie_payload, timeout=10)
                rec_id = None
                if res_m.ok and isinstance(res_m.json(), list) and len(res_m.json()) > 0:
                    rec_id = res_m.json()[0].get("id")
                if not rec_id:
                    res_q = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/movies?slug=eq.{requests.utils.quote(slug)}&select=id", headers=headers_post, timeout=5)
                    if res_q.ok and res_q.json():
                        rec_id = res_q.json()[0].get("id")

                if rec_id:
                    movies_map[slug] = {"id": rec_id, "title": clean_title}
                    # Upsert Quality File Record
                    file_payload = {
                        "movie_id": rec_id,
                        "quality": quality,
                        "quality_label": parsed.get("quality_label", f"{quality.upper()} HD"),
                        "file_name": sanitized_filename,
                        "clean_filename": parsed.get("clean_filename") or f"{clean_title} [{quality}].mkv",
                        "mime_type": "video/x-matroska",
                        "file_size_bytes": safe_size,
                        "total_bytes": safe_size,
                        "storage_type": "single_file_mesh",
                        "hf_raw_url": single_url,
                        "mirrors": mirror_urls,
                        "rip_type": parsed.get("rip_type", "WEB-DL"),
                        "codec": parsed.get("codec", "x264"),
                        "audio_languages": ", ".join(parsed.get("audio_languages", ["Tamil"])),
                        "is_theater_print": parsed.get("is_theater_print", False)
                    }
                    res_f = requests.post(f"{supabase_url.rstrip('/')}/rest/v1/movie_files?on_conflict=movie_id,quality", headers=headers_post, json=file_payload, timeout=10)
                    if res_f.ok:
                        movie_files_map[(rec_id, quality)] = True
                        repaired_movies += 1
                        print(f"   ✅ [SYNCED] `movies` & `movie_files` -> '{clean_title}' [{quality}]")

        # ----------------------------------------------------------------------
        # CASE B: SERIES DOMAIN (series & series_files)
        # ----------------------------------------------------------------------
        elif category in ("SERIES_SINGLE", "SERIES_BATCH"):
            series_title = parsed["series_title"]
            series_slug = parsed.get("series_slug") or re.sub(r'[^a-z0-9]', '', series_title.lower())
            season_num = parsed.get("season", 1)
            ep_start = parsed.get("episode", 1)
            ep_end = parsed.get("episode_end", ep_start)
            is_batch = parsed.get("is_batch", False)
            batch_range = parsed.get("batch_range")

            in_series_db = series_slug in series_map
            series_obj = series_map.get(series_slug, {})
            series_id = series_obj.get("id")
            file_key = (series_id, season_num, ep_start, ep_end, quality) if series_id else None
            in_sfiles_db = file_key in series_files_map if file_key else False

            if not in_series_db or not in_sfiles_db:
                print(f"📺 [SERIES REPAIR] '{series_title}' S{season_num:02d}E{ep_start:02d} [{quality}] (1-File Native on HF)")
                tmdb_meta = fetch_tmdb_metadata(series_title, quality)

                # Upsert Master Series Record
                series_payload = {
                    "title": series_title,
                    "slug": series_slug,
                    "poster_url": tmdb_meta.get("poster_url"),
                    "backdrop_url": tmdb_meta.get("backdrop_url"),
                    "description": tmdb_meta.get("description") or f"Watch all seasons and episodes of {series_title} in Full HD.",
                    "release_year": tmdb_meta.get("release_year", 2026),
                    "rating": tmdb_meta.get("rating", 8.8),
                    "total_seasons": max(1, season_num),
                    "total_episodes": max(1, ep_end),
                    "status": "Returning Series"
                }

                res_s = requests.post(f"{supabase_url.rstrip('/')}/rest/v1/series?on_conflict=slug", headers=headers_post, json=series_payload, timeout=10)
                s_id = None
                if res_s.ok and isinstance(res_s.json(), list) and len(res_s.json()) > 0:
                    s_id = res_s.json()[0].get("id")
                if not s_id:
                    res_sq = requests.get(f"{supabase_url.rstrip('/')}/rest/v1/series?slug=eq.{requests.utils.quote(series_slug)}&select=id", headers=headers_post, timeout=5)
                    if res_sq.ok and res_sq.json():
                        s_id = res_sq.json()[0].get("id")

                if s_id:
                    series_map[series_slug] = {"id": s_id, "title": series_title}
                    # Upsert Series File (Episode / Batch Variant)
                    sfile_payload = {
                        "series_id": s_id,
                        "season_number": season_num,
                        "episode_number": ep_start,
                        "episode_end": ep_end,
                        "is_batch": is_batch,
                        "batch_range": batch_range,
                        "episode_title": batch_range if is_batch else f"Episode {ep_start}",
                        "quality": quality,
                        "quality_label": parsed.get("quality_label", f"{quality.upper()} HD"),
                        "file_name": sanitized_filename,
                        "clean_filename": parsed.get("clean_filename") or f"{series_title} S{season_num:02d}E{ep_start:02d} [{quality}].mkv",
                        "mime_type": "video/x-matroska",
                        "file_size_bytes": safe_size,
                        "total_bytes": safe_size,
                        "storage_type": "single_file_mesh",
                        "hf_raw_url": single_url,
                        "mirrors": mirror_urls,
                        "rip_type": parsed.get("rip_type", "WEB-DL"),
                        "codec": parsed.get("codec", "x264"),
                        "audio_languages": ", ".join(parsed.get("audio_languages", ["Tamil"])),
                        "tech_metadata": parsed
                    }
                    res_sf = requests.post(f"{supabase_url.rstrip('/')}/rest/v1/series_files?on_conflict=series_id,season_number,episode_number,episode_end,quality", headers=headers_post, json=sfile_payload, timeout=10)
                    if res_sf.ok:
                        series_files_map[(s_id, season_num, ep_start, ep_end, quality)] = True
                        repaired_series += 1
                        print(f"   ✅ [SYNCED] `series` & `series_files` -> '{series_title}' S{season_num:02d} Ep {ep_start}-{ep_end}")

    total_time = time.time() - start_total
    print("\n================================================================================")
    print(f"🎉 [4-TABLE RECONCILIATION & REPAIR COMPLETE] Elapsed: {total_time:.2f}s")
    print(f"   ├─ GDrive Scanned Files       : {len(gdrive_files)}")
    print(f"   ├─ Repaired Movies Ingested   : {repaired_movies}")
    print(f"   ├─ Repaired Series Ingested   : {repaired_series}")
    print(f"   └─ Total Verified Stream Items : {repaired_movies + repaired_series}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_fast_reconcile_and_repair()
