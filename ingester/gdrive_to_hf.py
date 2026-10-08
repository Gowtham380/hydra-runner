#!/usr/bin/env python3
"""
PROJECT HYDRA - BATCH GOOGLE DRIVE / FOLDER TO HUGGING FACE TRANSFER ENGINE
Scans an entire directory (Google Drive or Local Folder), automatically cleans release tags,
obfuscates video files to .bin, uploads to Hugging Face Git LFS via 10Gbps CDN,
and registers all metadata cleanly into Supabase PostgreSQL.
"""

import os
import sys
import re
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

try:
    from huggingface_hub import HfApi
    from tqdm import tqdm
except ImportError:
    print("❌ Missing dependencies! Install via: pip install huggingface_hub tqdm requests python-dotenv")
    sys.exit(1)


def clean_movie_title(raw_filename: str) -> tuple[str, str, str]:
    """
    Cleans junk release tags like 'www.1TamilMV.meme -', codec details, site names.
    Returns (clean_title, sanitized_filename, slug)
    Example input: 'www.1TamilMV.meme - Hushar Pittalu (2026) Telugu HQ HDRip - 720p - x264.mkv'
    Returns: ('Hushar Pittalu (2026)', 'Hushar.Pittalu.2026.720p.mkv', 'hushar-pittalu-2026')
    """
    name = Path(raw_filename).stem
    ext = Path(raw_filename).suffix.lower()

    # Remove site tags like www.1TamilMV.wwe -, www.TamilRockers.net -, etc.
    name = re.sub(r'^(www\.[a-zA-Z0-9\.-]+\s*[-_]?\s*)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[.*?\]', '', name) # Remove [1TamilMV] tags
    
    # Extract Year if present (e.g. 2026, 2025, 2024...)
    year_match = re.search(r'\(?(\d{4})\)?', name)
    year = year_match.group(1) if year_match else ""

    # Extract quality if present
    quality = "1080p"
    if "2160p" in name.lower() or "4k" in name.lower():
        quality = "2160p"
    elif "720p" in name.lower():
        quality = "720p"

    # Extract core title before codec junk
    core_title = re.split(r'hq|hdrip|web-dl|bluray|x264|x265|hevc|dd\+|aac|esub|720p|1080p|2160p', name, flags=re.IGNORECASE)[0]
    core_title = core_title.replace('.', ' ').replace('_', ' ').strip('- ').strip()

    if year and year not in core_title:
        clean_title = f"{core_title} ({year})"
    else:
        clean_title = core_title

    # Construct clean sanitized file name
    slug_base = re.sub(r'[^\w\s-]', '', clean_title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug_base).strip('-')
    
    sanitized_filename = f"{slug.replace('-', '.')}.{quality}{ext}"

    return clean_title, sanitized_filename, slug


def batch_transfer(source_dir: str, repo_id: str, hf_token: str, supabase_url: str, supabase_key: str):
    source_path = Path(source_dir).resolve()
    if not source_path.exists():
        print(f"❌ Source directory does not exist: {source_path}")
        return

    # Scan for video files
    video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.webm', '.m4v'}
    video_files = [f for f in source_path.rglob('*') if f.suffix.lower() in video_extensions]

    if not video_files:
        print(f"⚠️ No video files found in {source_path}")
        return

    print("==================================================================")
    print("🚀 PROJECT HYDRA - BATCH INGESTION ENGINE")
    print("==================================================================")
    print(f"📂 Source Directory: {source_path}")
    print(f"🎯 Hugging Face Repo: {repo_id}")
    print(f"🎬 Total Movies Found: {len(video_files)}")
    print("==================================================================\n")

    api = HfApi(token=hf_token)

    for idx, file_path in enumerate(video_files, 1):
        raw_name = file_path.name
        file_size_bytes = file_path.stat().st_size
        file_size_gb = file_size_bytes / (1024 ** 3)

        clean_title, sanitized_filename, slug = clean_movie_title(raw_name)
        obfuscated_filename = f"{slug}.bin"

        print(f"\n[{idx}/{len(video_files)}] Ingesting: {clean_title}")
        print(f"  ├─ Original File:   {raw_name}")
        print(f"  ├─ Target Storage:  {obfuscated_filename} ({file_size_gb:.2f} GB)")

        # 1. Upload to Hugging Face Git LFS
        hf_raw_url = f"https://huggingface.co/datasets/{repo_id}/resolve/main/{obfuscated_filename}"
        
        try:
            print(f"  ├─ ⏳ Uploading to Hugging Face 10Gbps CDN...")
            api.upload_file(
                path_or_fileobj=str(file_path),
                path_in_repo=obfuscated_filename,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"Batch ingest: {clean_title} ({file_size_gb:.2f}GB)"
            )
            print(f"  ├─ ✅ Uploaded! Raw URL: {hf_raw_url}")
        except Exception as e:
            print(f"  ├─ ❌ HF Upload Error: {e}")
            continue

        # 2. Register in Supabase Database
        if supabase_url and supabase_key:
            endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies"
            ext_lower = file_path.suffix.lower()
            mime_type = "video/mp4" if ext_lower == ".mp4" else "video/x-matroska"

            payload = {
                "title": clean_title,
                "slug": slug,
                "file_name": sanitized_filename,
                "mime_type": mime_type,
                "file_size_bytes": file_size_bytes,
                "hf_raw_url": hf_raw_url,
                "description": f"High-speed 10Gbps direct download for {clean_title} ({file_size_gb:.2f} GB)"
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
                    print(f"  └─ ✅ Registered in Supabase!")
                else:
                    print(f"  └─ ⚠️ Supabase returned {res.status_code}: {res.text}")
            except Exception as e:
                print(f"  └─ ❌ Supabase registration error: {e}")

    print("\n==================================================================")
    print("🎉 ALL BATCH TRANSFERS COMPLETED!")
    print("==================================================================")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Project Hydra - Batch Folder / GDrive to HF Transfer Engine")
    parser.add_argument("--dir", "-d", required=True, help="Path to folder containing movie files (e.g. /content/drive/MyDrive/Movies)")
    parser.add_argument("--repo", "-r", default="", help="Hugging Face Dataset Repo ID (e.g. 'akthereddragon/hydra-movies')")
    
    args = parser.parse_args()

    hf_token = os.getenv("HF_TOKEN")
    repo_id = args.repo or os.getenv("HF_REPO_ID")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not repo_id:
        print("❌ Error: HF_REPO_ID must be provided via --repo argument or .env file.")
        sys.exit(1)

    if not hf_token:
        print("❌ Error: HF_TOKEN is missing in .env file.")
        sys.exit(1)

    batch_transfer(args.dir, repo_id, hf_token, supabase_url, supabase_key)


if __name__ == "__main__":
    main()
