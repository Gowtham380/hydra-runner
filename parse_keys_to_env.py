#!/usr/bin/env python3
import os
import json
from pathlib import Path

keys_dir = Path(__file__).resolve().parent / "keys"
env_file = Path(__file__).resolve().parent / ".env"

sa_list = []

for json_path in sorted(keys_dir.glob("*.json")):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            email = data.get("client_email") or data.get("email") or data.get("sa_email")
            key = data.get("private_key") or data.get("privateKey")
            if email and key:
                sa_list.append({
                    "email": email,
                    "privateKey": key
                })
                print(f"  ✅ Loaded SA key: {json_path.name} -> {email}")
    except Exception as e:
        print(f"  ❌ Error reading {json_path.name}: {e}")

print(f"\n🎉 Successfully parsed {len(sa_list)} Service Account(s) from 'keys/' directory.")

# Format as single-line JSON string for .env
sa_json_str = json.dumps(sa_list)

# Read existing .env
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
else:
    lines = []

# Replace or add SERVICE_ACCOUNTS_JSON line
updated = False
new_lines = []
for line in lines:
    if line.startswith("SERVICE_ACCOUNTS_JSON="):
        new_lines.append(f"SERVICE_ACCOUNTS_JSON='{sa_json_str}'\n")
        updated = True
    else:
        new_lines.append(line)

if not updated:
    new_lines.append(f"\nSERVICE_ACCOUNTS_JSON='{sa_json_str}'\n")

with open(env_file, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✨ Updated master .env file with {len(sa_list)} Service Accounts!")
