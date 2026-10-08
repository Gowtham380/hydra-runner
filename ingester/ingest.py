#!/usr/bin/env python3
"""
PROJECT HYDRA - AUTO-INGESTION ENGINE (LAYER 5)

Automated CLI tool to:
1. Obfuscate large video files (.mkv/.mp4) as AI weight binaries (.bin)
2. Upload assets to Hugging Face Git LFS Dataset storage via 10Gbps AWS CDN
3. Automatically register movie metadata into Supabase PostgreSQL database
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
except ImportError:
    HfApi = None


def slugify(text: str) -> str:
    """Convert string to URL-friendly slug"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def main():
    parser = argparse.ArgumentParser(
        description="Project Hydra - Auto-Ingestion CLI for HuggingFace Git LFS & Supabase"
    )
    parser.add_argument("--file", "-f", required=True, help="Path to local video file (.mkv, .mp4, etc.)")
    parser.add_argument("--title", "-t", required=True, help="Movie Title (e.g. 'Avatar: The Way of Water')")
    parser.add_argument("--poster", "-p", default="", help="Optional poster image URL")
    parser.add_argument("--desc", "-d", default="", help="Optional movie description")
    parser.add_argument("--repo", "-r", default="", help="Hugging Face repo ID (e.g. 'username/hydra-vault'). Overrides .env")
    parser.add_argument("--ext", default="bin", help="Extension to obfuscate file as (default: 'bin')")
    
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    
    hf_token = os.getenv("HF_TOKEN")
    hf_repo_id = args.repo or os.getenv("HF_REPO_ID")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    # Validation
    file_path = Path(args.file).resolve()
    if not file_path.exists() or not file_path.is_file():
        print(f"❌ Error: Local file not found: {file_path}")
        sys.exit(1)

    file_size_bytes = file_path.stat().st_size
    file_size_gb = file_size_bytes / (1024 ** 3)
    original_filename = file_path.name
    
    title = args.title.strip()
    slug = slugify(title)
    obfuscated_filename = f"{slug}.{args.ext.lstrip('.')}"

    print("==================================================================")
    print("🚀 PROJECT HYDRA - AUTO-INGESTION PIPELINE")
    print("==================================================================")
    print(f"🎬 Title:             {title}")
    print(f"📁 Source File:        {original_filename}")
    print(f"📦 Obfuscated File:    {obfuscated_filename}")
    print(f"📊 Size:               {file_size_gb:.2f} GB ({file_size_bytes:,} bytes)")
    print(f"🎯 Target Repo:        {hf_repo_id or 'NOT CONFIGURED'}")
    print("------------------------------------------------------------------")

    # Step 1: Upload to Hugging Face Git LFS
    hf_raw_url = None
    if hf_token and hf_repo_id:
        if HfApi is None:
            print("❌ Error: 'huggingface_hub' library missing. Install via: pip install huggingface_hub")
            sys.exit(1)

        print(f"⏳ Uploading {obfuscated_filename} to Hugging Face Dataset [{hf_repo_id}] via Git LFS...")
        try:
            api = HfApi(token=hf_token)
            api.upload_file(
                path_or_fileobj=str(file_path),
                path_in_repo=obfuscated_filename,
                repo_id=hf_repo_id,
                repo_type="dataset",
                commit_message=f"Ingest asset: {title} ({file_size_gb:.2f}GB)"
            )
            hf_raw_url = f"https://huggingface.co/datasets/{hf_repo_id}/resolve/main/{obfuscated_filename}"
            print(f"✅ Hugging Face Upload Complete!")
            print(f"🔗 Raw CDN URL: {hf_raw_url}")
        except Exception as e:
            print(f"❌ Hugging Face Upload Failed: {e}")
            sys.exit(1)
    else:
        print("⚠️ Warning: HF_TOKEN or HF_REPO_ID not set. Generating placeholder HF CDN URL...")
        hf_raw_url = f"https://huggingface.co/datasets/placeholder-org/hydra-vault/resolve/main/{obfuscated_filename}"

    # Step 2: Register Record in Supabase Database
    if supabase_url and supabase_key:
        print(f"\n⏳ Registering movie record in Supabase Database...")
        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/movies"
        
        # Determine mime type based on original extension
        ext_lower = file_path.suffix.lower()
        mime_type = "video/mp4" if ext_lower == ".mp4" else "video/x-matroska"

        payload = {
            "title": title,
            "slug": slug,
            "file_name": original_filename,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
            "hf_raw_url": hf_raw_url,
            "poster_url": args.poster or None,
            "description": args.desc or f"High-speed 10Gbps DDL for {title} ({file_size_gb:.2f} GB)"
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
                inserted_data = res.json()
                print(f"✅ Registered in Supabase! Movie ID: {inserted_data[0]['id']}")
            else:
                print(f"⚠️ Supabase registration returned status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"❌ Failed to post to Supabase: {e}")
    else:
        print("⚠️ Warning: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured. Skipping DB insertion.")

    print("\n==================================================================")
    print("🎉 INGESTION PIPELINE COMPLETE!")
    print("==================================================================")


if __name__ == "__main__":
    main()
