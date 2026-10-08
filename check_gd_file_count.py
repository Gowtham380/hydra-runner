#!/usr/bin/env python3
"""
================================================================================
RED-HAT ARCHITECTURE - DUAL GDRIVE FOLDER PARALLEL AUDIT ENGINE
================================================================================
Master Features:
1. Dynamic Folder Name & ID Resolution (SMD Paid Client Files & SMD Own Files)
2. Multi-Folder Parallel Deep Scanning (Folder 1 + Folder 2)
3. Individual Folder Audit Summaries (Separate Counts & Storage Metrics)
4. Combined Master Audit Summary (Merged Metrics with Unique Deduplication)
5. Consistent SA Token Binding per Folder (Zero nextPageToken 400 Bad Request)
6. 16-Worker Parallel BFS Queue Traversal across All Subfolders
================================================================================
"""

import os
import sys
import time
import json
import requests
import threading
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load .env file from project root
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Force UTF-8 encoding for Windows terminal output
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

VIDEO_EXTENSIONS = (
    '.mp4', '.mkv', '.avi', '.mov', '.webm', 
    '.flv', '.ts', '.m2ts', '.m4v', '.3gp', '.wmv',
    '.vob', '.iso', '.mpg', '.mpeg', '.m2v'
)

CHUNK_100MB = 100 * 1024 * 1024  # 104,857,600 bytes
MAX_WORKERS = 16

# Default Dual Folder Configuration
FOLDER_1_ID = "10uguj8gnoCx1j2t2-885MwH8YMj1OvQ7"
FOLDER_2_ID = "13QLJomTi-5IA4Jjz7TOMSEKwalE6mSCt"

_sa_tokens = []
_token_lock = threading.Lock()
_sa_counter = 0


def load_all_service_accounts() -> list:
    """Loads all service account keys from keys/ directory or .env"""
    sa_list = []
    keys_dir = Path(__file__).parent / "keys"
    
    if keys_dir.exists():
        json_files = sorted(list(keys_dir.glob("*.json")))
        for jf in json_files:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("client_email") and data.get("private_key"):
                        sa_list.append(data)
            except Exception:
                pass

    raw_env_sa = os.getenv("SERVICE_ACCOUNTS_JSON", "")
    if raw_env_sa:
        clean_sa = raw_env_sa.strip().strip("'").strip('"')
        try:
            parsed = json.loads(clean_sa)
            items = parsed if isinstance(parsed, list) else [parsed]
            for item in items:
                email = item.get("email") or item.get("client_email")
                key = item.get("privateKey") or item.get("private_key")
                if email and key and not any(s.get("client_email") == email for s in sa_list):
                    sa_list.append({"client_email": email, "private_key": key})
        except Exception:
            pass

    return sa_list


def filter_authorized_tokens(sa_list: list, folder_ids: list) -> list:
    """Validates and filters SA tokens that have read permissions to the target folders."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    valid_tokens = []

    def check_sa(sa):
        email = sa.get("client_email")
        raw_key = sa.get("private_key", "").replace('\\n', '\n').strip()
        if not email or not raw_key:
            return None
        if not raw_key.startswith("-----BEGIN PRIVATE KEY-----"):
            raw_key = f"-----BEGIN PRIVATE KEY-----\n{raw_key}\n-----END PRIVATE KEY-----\n"

        try:
            sa_info = {
                "type": "service_account",
                "client_email": email,
                "private_key": raw_key,
                "token_uri": "https://oauth2.googleapis.com/token"
            }
            creds = service_account.Credentials.from_service_account_info(
                sa_info, 
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            creds.refresh(Request())
            tok = creds.token
            
            # Check access to first folder ID
            test_fid = folder_ids[0]
            url = f"https://www.googleapis.com/drive/v3/files/{test_fid}?supportsAllDrives=true"
            res = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=5)
            if res.ok:
                return tok
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=min(20, max(1, len(sa_list)))) as executor:
        futures = [executor.submit(check_sa, sa) for sa in sa_list]
        for fut in as_completed(futures):
            tok = fut.result()
            if tok:
                valid_tokens.append(tok)

    return valid_tokens


def get_next_token() -> str:
    """Thread-safe round-robin token rotation across authorized Service Accounts"""
    global _sa_counter, _sa_tokens
    with _token_lock:
        if not _sa_tokens:
            return ""
        token = _sa_tokens[_sa_counter % len(_sa_tokens)]
        _sa_counter += 1
        return token


def fetch_folder_name(folder_id: str) -> str:
    """Fetches the display name of a Google Drive folder by ID"""
    tok = get_next_token()
    if not tok:
        return "Unknown Folder"
    url = f"https://www.googleapis.com/drive/v3/files/{folder_id}?supportsAllDrives=true&fields=name"
    try:
        res = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        if res.ok:
            return res.json().get("name", "Unknown Folder")
    except Exception:
        pass
    return "Unknown Folder"


def fetch_folder_items_single_level(folder_id: str, folder_name: str = "Folder", assigned_token: str = None) -> tuple[list, list]:
    """
    Fetches all items in a single folder with pagination support, shortcut resolution,
    and consistent token binding per folder.
    Returns: (file_list, subfolder_list)
    """
    if not folder_id:
        return [], []

    files = []
    subfolders = []
    page_token = None
    page_count = 0

    tok = assigned_token if assigned_token else get_next_token()
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}

    while True:
        page_count += 1
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,size,mimeType,shortcutDetails)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true"
        }
        if page_token:
            params["pageToken"] = page_token

        resp_data = None
        for attempt in range(3):
            try:
                res = requests.get("https://www.googleapis.com/drive/v3/files", params=params, headers=headers, timeout=25)
                if res.ok:
                    resp_data = res.json()
                    break
                else:
                    time.sleep(0.5)
            except Exception:
                time.sleep(0.5)

        if not resp_data:
            break

        items = resp_data.get("files", [])
        for item in items:
            mime = item.get("mimeType", "")

            # Handle Google Drive Shortcuts
            if mime == "application/vnd.google-apps.shortcut":
                sdetails = item.get("shortcutDetails", {})
                target_mime = sdetails.get("targetMimeType", "")
                target_id = sdetails.get("targetId")
                target_name = item.get("name", "")

                if target_id:
                    if target_mime == "application/vnd.google-apps.folder":
                        subfolders.append({"id": target_id, "name": target_name})
                    else:
                        files.append({
                            "id": target_id,
                            "name": target_name,
                            "size": item.get("size", 0),
                            "mimeType": target_mime
                        })
            elif mime == "application/vnd.google-apps.folder":
                subfolders.append(item)
            else:
                files.append(item)

        page_token = resp_data.get("nextPageToken")
        if not page_token:
            break

    print(f" 📂 [{folder_name[:35]:<35}] -> {len(files):>5} file(s), {len(subfolders):>3} subfolder(s) ({page_count} pgs)", flush=True)
    return files, subfolders


def parallel_deep_scan(root_folder_id: str, label: str = "Folder") -> list:
    """
    Master 16-Worker Parallel BFS Queue Traversal Engine across all subfolders.
    """
    all_files = []
    folders_queue = [(label, root_folder_id)]
    visited_ids = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while folders_queue:
            current_batch = list(folders_queue)
            folders_queue.clear()

            futures = {}
            for name, fid in current_batch:
                if fid not in visited_ids:
                    visited_ids.add(fid)
                    assigned_tok = get_next_token()
                    fut = executor.submit(fetch_folder_items_single_level, fid, name, assigned_tok)
                    futures[fut] = (name, fid)

            for fut in as_completed(futures):
                fname, fid = futures[fut]
                try:
                    flist, sflist = fut.result()
                    all_files.extend(flist)
                    for sf in sflist:
                        sf_id = sf.get("id")
                        sf_name = sf.get("name", "Subfolder")
                        if sf_id and sf_id not in visited_ids:
                            folders_queue.append((sf_name, sf_id))
                except Exception:
                    pass

    return all_files


def format_size(bytes_val: int) -> str:
    """Formats bytes to human readable string (GB / TB)"""
    gb = bytes_val / (1024 * 1024 * 1024)
    if gb >= 1024:
        return f"{gb:.2f} GB ({gb / 1024:.2f} TB)"
    elif bytes_val >= 1024 * 1024:
        return f"{gb:.2f} GB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.2f} KB"
    return f"{bytes_val} Bytes"


def compute_folder_metrics(audited_files: list) -> dict:
    """Computes total, video, >100MB, <=100MB, and non-video metrics for a list of files."""
    seen_ids = set()
    unique_files = []
    for f in audited_files:
        fid = f.get("id")
        if fid:
            if fid not in seen_ids:
                seen_ids.add(fid)
                unique_files.append(f)
        else:
            unique_files.append(f)

    total_bytes = 0
    video_bytes = 0
    video_files = []
    other_files = []
    video_gt_100mb_count = 0
    video_gt_100mb_bytes = 0
    video_lte_100mb_count = 0

    for f in unique_files:
        fname = f.get("name", "")
        fsize = int(f.get("size", 0))
        fmime = f.get("mimeType", "")

        total_bytes += fsize
        is_video = fname.lower().endswith(VIDEO_EXTENSIONS) or fmime.startswith("video/")

        if is_video:
            video_files.append(f)
            video_bytes += fsize
            if fsize > CHUNK_100MB:
                video_gt_100mb_count += 1
                video_gt_100mb_bytes += fsize
            else:
                video_lte_100mb_count += 1
        else:
            other_files.append(f)

    return {
        "unique_files": unique_files,
        "total_files": len(unique_files),
        "total_bytes": total_bytes,
        "video_files": video_files,
        "video_files_count": len(video_files),
        "video_bytes": video_bytes,
        "video_gt_100mb_count": video_gt_100mb_count,
        "video_gt_100mb_bytes": video_gt_100mb_bytes,
        "video_lte_100mb_count": video_lte_100mb_count,
        "video_lte_100mb_bytes": video_bytes - video_gt_100mb_bytes,
        "other_files_count": len(other_files)
    }


def print_metrics_summary(title: str, m: dict):
    """Prints formatted audit metrics summary."""
    print("\n" + "=" * 75)
    print(f" {title}")
    print("=" * 75)
    print(f"  1. Total Files Available       : {m['total_files']:,} files ({format_size(m['total_bytes'])})")
    print(f"  2. Total Video Format Files     : {m['video_files_count']:,} files ({format_size(m['video_bytes'])})")
    print(f"  3. Video Files > 100 MB         : {m['video_gt_100mb_count']:,} files ({format_size(m['video_gt_100mb_bytes'])})")
    print(f"  4. Video Files <= 100 MB        : {m['video_lte_100mb_count']:,} files ({format_size(m['video_lte_100mb_bytes'])})")
    print(f"  5. Non-Video / Other Files      : {m['other_files_count']:,} files")
    print("=" * 75)


def main():
    global _sa_tokens
    start_time = time.time()

    f1_raw = os.getenv("GOOGLE_DRIVE_FOLDER_1_ID") or os.getenv("GOOGLE_DRIVE_FOLDER_ID", FOLDER_1_ID)
    f1_id = f1_raw.split(",")[0].strip()
    f2_id = os.getenv("GOOGLE_DRIVE_FOLDER_2_ID", FOLDER_2_ID).strip()

    print("=" * 75)
    print(" 🚀 RED-HAT ARCHITECTURE: DUAL GDRIVE AUDIT ENGINE")
    print("=" * 75)

    sa_list = load_all_service_accounts()
    print(f" 🔑 Service Accounts : Loaded {len(sa_list)} SAs from local pool")

    _sa_tokens = filter_authorized_tokens(sa_list, [f1_id, f2_id])
    print(f" ⚡ Authorized SAs   : {len(_sa_tokens)} Active OAuth Tokens Initialized")

    f1_name = fetch_folder_name(f1_id)
    f2_name = fetch_folder_name(f2_id)

    print(f" 📁 Folder 1 Name : [{f1_name}] (ID: {f1_id})")
    print(f" 📁 Folder 2 Name : [{f2_name}] (ID: {f2_id})")
    print("-" * 75)

    # 1. AUDIT FOLDER 1
    print(f"\n ⏳ [1/2] Scanning Folder 1: [{f1_name}] (ID: {f1_id})...", flush=True)
    files_f1 = parallel_deep_scan(f1_id, label=f1_name)
    m1 = compute_folder_metrics(files_f1)

    # 2. AUDIT FOLDER 2
    print(f"\n ⏳ [2/2] Scanning Folder 2: [{f2_name}] (ID: {f2_id})...", flush=True)
    files_f2 = parallel_deep_scan(f2_id, label=f2_name)
    m2 = compute_folder_metrics(files_f2)

    # 3. COMBINED MASTER AUDIT
    combined_raw_files = files_f1 + files_f2
    m_combined = compute_folder_metrics(combined_raw_files)
    total_scan_duration = time.time() - start_time

    # Print Final Summary Tables for All 3 Cases
    print_metrics_summary(f"📊 FOLDER 1: [{f1_name}] (ID: {f1_id})", m1)
    print_metrics_summary(f"📊 FOLDER 2: [{f2_name}] (ID: {f2_id})", m2)
    print_metrics_summary("🔥 COMBINED MASTER AUDIT RESULTS SUMMARY (ALL FOLDERS MERGED)", m_combined)

    print(f"\n ⏱️ Total Dual Scan Execution Time : {total_scan_duration:.2f} SECONDS ⚡")
    print("=" * 75)

    if m_combined["video_gt_100mb_count"] > 0:
        print("\n TOP VIDEO FILES (> 100 MB COMBINED SAMPLE):")
        print("-" * 75)
        sorted_videos = sorted(m_combined["video_files"], key=lambda x: int(x.get("size", 0)), reverse=True)
        for i, vf in enumerate(sorted_videos[:10], 1):
            name = vf.get("name", "Unknown")
            sz = int(vf.get("size", 0))
            print(f"   [{i:02d}] {name[:55]:<55} | {format_size(sz)}")
        print("-" * 75)


if __name__ == "__main__":
    main()
