#!/usr/bin/env python3
"""
================================================================================
GOOGLE DRIVE ULTRA-FAST VIDEO NAME INDEXER & EXPORTER
================================================================================
Author: Advanced Systems & Cloud Automation Engine
Target: Google Drive API v3 (Direct MIME Query Protocol)

Technical Specifications:
- 0-Folder Traversal: Direct MIME Query: `mimeType contains 'video/' and trashed = false`
- Payload Minimization: `fields="nextPageToken, files(name)"`
- Batch Window: `pageSize=1000` (Google API Maximum Limit)
- Corpus Scope: Supports My Drive + All Shared Drives (supportsAllDrives=True)
- Output: UTF-8 Encoded .txt file in the script's execution directory
================================================================================
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path

# Auto-load .env if available
try:
    from dotenv import load_dotenv
    # Check current directory and parent directory for .env
    script_dir = Path(__file__).resolve().parent
    env_curr = script_dir / '.env'
    env_parent = script_dir.parent / '.env'
    if env_curr.exists():
        load_dotenv(dotenv_path=env_curr)
    elif env_parent.exists():
        load_dotenv(dotenv_path=env_parent)
    else:
        load_dotenv()
except ImportError:
    pass

# Google API client dependencies
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except ImportError:
    print("❌ Missing required Google API libraries!")
    print("👉 Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def resolve_google_credentials(custom_creds_path: str = None):
    """
    Production-grade multi-tier credential resolver:
    Tier 1: Explicit CLI path (--credentials)
    Tier 2: Environment variable (GOOGLE_APPLICATION_CREDENTIALS or SERVICE_ACCOUNTS_JSON)
    Tier 3: Local JSON files in script directory (service_account.json, sa.json, token.json, credentials.json)
    Tier 4: Interactive OAuth User Flow (InstalledAppFlow for Personal Google Accounts)
    """
    script_dir = Path(__file__).resolve().parent

    # 1. Explicit path from argument
    if custom_creds_path:
        p = Path(custom_creds_path).resolve()
        if p.exists():
            return load_credentials_from_path(p)
        else:
            print(f"⚠️ Warning: Specified credentials file not found: {custom_creds_path}")

    # 2. GOOGLE_APPLICATION_CREDENTIALS environment variable
    gac_env = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if gac_env and Path(gac_env).exists():
        return load_credentials_from_path(Path(gac_env))

    # 3. SERVICE_ACCOUNTS_JSON (JSON string in .env as array or object)
    sa_json_env = os.getenv("SERVICE_ACCOUNTS_JSON")
    if sa_json_env:
        try:
            parsed = json.loads(sa_json_env)
            sa_data = parsed[0] if isinstance(parsed, list) and len(parsed) > 0 else parsed
            if isinstance(sa_data, dict):
                # Format to standard Google service account info if needed
                client_email = sa_data.get("client_email") or sa_data.get("email")
                private_key = sa_data.get("private_key") or sa_data.get("privateKey")
                if client_email and private_key:
                    sa_info = {
                        "type": "service_account",
                        "client_email": client_email,
                        "private_key": private_key.replace('\\n', '\n'),
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
                    print(f"🔑 Authenticated via .env SERVICE_ACCOUNTS_JSON [{client_email}]")
                    return creds
        except Exception as e:
            print(f"⚠️ Failed to parse SERVICE_ACCOUNTS_JSON from .env: {e}")

    # 4. Local candidate files in the script directory
    candidate_files = [
        "service_account.json",
        "sa.json",
        "credentials.json",
        "token.json",
        "client_secret.json"
    ]
    for filename in candidate_files:
        candidate_path = script_dir / filename
        if candidate_path.exists():
            creds = load_credentials_from_path(candidate_path)
            if creds:
                return creds

    # 5. User OAuth Desktop Flow if credentials.json is an OAuth Client ID file
    oauth_client_file = script_dir / "credentials.json"
    token_file = script_dir / "token.json"
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if creds and creds.valid:
                print(f"🔑 Authenticated via User OAuth Token [{token_file.name}]")
                return creds
        except Exception as e:
            print(f"⚠️ token.json refresh failed: {e}")

    if oauth_client_file.exists():
        try:
            with open(oauth_client_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "installed" in data or "web" in data:
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(str(oauth_client_file), SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_file, 'w', encoding='utf-8') as token:
                    token.write(creds.to_json())
                print(f"🔑 User OAuth Successful! Saved session to {token_file.name}")
                return creds
        except Exception as e:
            print(f"⚠️ OAuth Flow initialization failed: {e}")

    return None


def load_credentials_from_path(file_path: Path):
    """Loads either Service Account or OAuth credentials from a file path"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check if Service Account JSON
        if data.get("type") == "service_account" or ("client_email" in data and "private_key" in data):
            creds = service_account.Credentials.from_service_account_file(str(file_path), scopes=SCOPES)
            print(f"🔑 Authenticated via Service Account: {file_path.name} [{data.get('client_email')}]")
            return creds

        # Check if saved User OAuth Token JSON
        if "token" in data or "refresh_token" in data:
            creds = Credentials.from_authorized_user_file(str(file_path), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            print(f"🔑 Authenticated via User Token: {file_path.name}")
            return creds

    except Exception as e:
        print(f"❌ Error loading credentials from {file_path}: {e}")

    return None


def extract_all_video_names(service, output_file_path: Path, folder_id: str = None):
    """
    Executes Ultra-Fast Video Indexing using Google Drive API v3.
    MIME Direct Query + fields payload minimization + pageSize=1000 batching.
    """
    # Base query as per specification:
    # q = "mimeType contains 'video/' and trashed = false"
    query_parts = ["mimeType contains 'video/'", "trashed = false"]
    
    if folder_id:
        query_parts.append(f"'{folder_id}' in parents")
        print(f"🎯 Target Scope: Sub-folder ID [{folder_id}]")
    else:
        print("🌐 Target Scope: Entire Google Drive (All Accessible Folders & Shared Drives)")

    query = " and ".join(query_parts)
    print(f"⚡ Search Query: `{query}`")

    page_token = None
    page_number = 0
    total_videos = 0
    start_time = time.time()

    # Open target .txt file for streaming append with strict UTF-8
    with open(output_file_path, 'w', encoding='utf-8', errors='replace') as out_f:
        while True:
            page_number += 1
            request_params = {
                'q': query,
                'fields': "nextPageToken, files(name)",
                'pageSize': 1000,
                'supportsAllDrives': True,
                'includeItemsFromAllDrives': True,
                'pageToken': page_token
            }

            # Exponential backoff retry loop for API rate limits / network hiccups
            items = []
            for attempt in range(1, 5):
                try:
                    response = service.files().list(**request_params).execute()
                    items = response.get('files', [])
                    page_token = response.get('nextPageToken', None)
                    break
                except HttpError as err:
                    if err.resp.status in [429, 500, 503] and attempt < 4:
                        sleep_sec = attempt * 2
                        print(f"\n⚠️ API Rate Limit / Transient error ({err.resp.status}). Retrying in {sleep_sec}s...")
                        time.sleep(sleep_sec)
                    else:
                        print(f"\n❌ Google Drive API Fatal Error: {err}")
                        raise err
                except Exception as ex:
                    if attempt < 4:
                        time.sleep(attempt * 2)
                    else:
                        raise ex

            # Write raw names directly without any regex/formatting/alteration
            for file_item in items:
                raw_name = file_item.get('name', '')
                if raw_name:
                    out_f.write(f"{raw_name}\n")
                    total_videos += 1

            out_f.flush()  # Immediate disk flush to preserve data

            elapsed = max(time.time() - start_time, 0.001)
            rate = total_videos / elapsed
            print(f"\r🚀 Batch #{page_number:02d} | Fetched: {len(items):4d} videos | Total Indexed: {total_videos:5d} | Speed: {rate:.1f} files/sec", end="", flush=True)

            if not page_token:
                break

    print()  # Newline after progress bar
    total_time = time.time() - start_time
    return total_videos, page_number, total_time


def main():
    script_dir = Path(__file__).resolve().parent
    default_output = script_dir / "gdrive_all_video_names.txt"

    parser = argparse.ArgumentParser(
        description="Ultra-Fast Google Drive Video Name Indexer & TXT Exporter (Production Ready)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python export_gdrive_video_names.py
  python export_gdrive_video_names.py --credentials ./my_service_account.json
  python export_gdrive_video_names.py --folder-id 10uguj8gnoCx1j2t2-885MwH8YMj1OvQ7
  python export_gdrive_video_names.py --output ./all_my_videos.txt
        """
    )
    parser.add_argument("-c", "--credentials", default=None, help="Path to Service Account JSON or OAuth credentials file")
    parser.add_argument("-f", "--folder-id", default=None, help="Optional: Restrict search to specific Folder ID")
    parser.add_argument("-o", "--output", default=str(default_output), help="Output .txt file path (Defaults to gdrive_all_video_names.txt in script dir)")

    args = parser.parse_args()
    output_path = Path(args.output).resolve()

    print("================================================================================")
    print("🎬 GOOGLE DRIVE ULTRA-FAST VIDEO INDEXER (PRODUCTION RUNNER)")
    print("================================================================================")
    print(f"📁 Script Directory : {script_dir}")
    print(f"📄 Output File Path : {output_path}")

    # Step 1: Resolve Authentication
    creds = resolve_google_credentials(args.credentials)
    if not creds:
        print("\n❌ AUTHENTICATION ERROR: No valid Google Drive credentials detected!")
        print("👉 Please provide one of the following:")
        print("   1. Place 'service_account.json' or 'credentials.json' in this folder:")
        print(f"      {script_dir}")
        print("   2. Or set SERVICE_ACCOUNTS_JSON in your .env file.")
        print("   3. Or run with CLI argument: python export_gdrive_video_names.py --credentials /path/to/sa.json")
        sys.exit(1)

    # Step 2: Build Google Drive API v3 Service
    try:
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"❌ Failed to construct Google Drive API service: {e}")
        sys.exit(1)

    # Step 3: Run Extraction
    try:
        count, pages, duration = extract_all_video_names(service, output_path, folder_id=args.folder_id)

        print("================================================================================")
        print("🎉 EXTRACTION COMPLETED SUCCESSFULLY!")
        print(f"📊 Total Video Files Found : {count}")
        print(f"📄 Total API Pages Queried : {pages} (pageSize=1000)")
        print(f"⏱️ Total Execution Time     : {duration:.2f} seconds")
        if count > 0:
            print(f"⚡ Extraction Speed         : {count / max(duration, 0.001):.1f} video names/sec")
        print(f"💾 Output File Saved At    : {output_path}")
        print(f"📦 File Size                : {output_path.stat().st_size / 1024:.2f} KB")
        print("================================================================================")

    except KeyboardInterrupt:
        print("\n🛑 Process interrupted by user. Partial data saved.")
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
