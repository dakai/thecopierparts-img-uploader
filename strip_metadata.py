#!/usr/bin/env python3
"""
Metadata Stripping Script for PUBLIC bucket.

Tasks:
1. List all image files in the PUBLIC bucket.
2. Download each file.
3. Remove all metadata (EXIF, XMP, ICC, etc.) using ImageMagick 'strip'.
4. Upload back to R2.

Usage:
    python strip_metadata.py --dry-run
    python strip_metadata.py
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

import boto3
from dotenv import load_dotenv

from r2_cache import upload_with_cache

# Load environment
load_dotenv()

# R2 Configuration
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
PUBLIC_BUCKET = os.environ["PUBLIC_BUCKET"]

TEMP_DIR = "strip_temp"
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff')

def check_metadata(file_path):
    """Check if the image has any profiles or comments using identify."""
    try:
        # identify -format "%[profiles]%[comment]" returns names of profiles/comments
        cmd = ["identify", "-format", "%[profiles]%[comment]", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return len(result.stdout.strip()) > 0
    except Exception:
        return True # Fallback to true if identify fails

def strip_metadata(file_path):
    """Remove all metadata from the image using ImageMagick mogrify."""
    try:
        size_before = os.path.getsize(file_path)
        cmd = ["mogrify", "-strip", file_path]
        subprocess.run(cmd, check=True)
        size_after = os.path.getsize(file_path)
        return True, size_before, size_after
    except Exception as e:
        print(f"Error stripping {file_path}: {e}")
        return False, 0, 0

def main():
    # ... rest of setup ...
    parser = argparse.ArgumentParser(description="Strip metadata from all images in public bucket")
    parser.add_argument("--dry-run", action="store_true", help="Report files without modifying")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of files to process")
    parser.add_argument("--prefix", type=str, default="", help="Only process files with this prefix")
    args = parser.parse_args()

    if not all([CF_ENDPOINT, CF_ACCESS_KEY, CF_SECRET_KEY]):
        print("Error: Missing R2 environment variables.")
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=CF_ENDPOINT,
        aws_access_key_id=CF_ACCESS_KEY,
        aws_secret_access_key=CF_SECRET_KEY,
        region_name="auto",
    )

    print(
        f"[{datetime.now(UTC).isoformat()}] Listing all files in {PUBLIC_BUCKET}..."
    )

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=PUBLIC_BUCKET, Prefix=args.prefix)

    files_to_process = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(IMAGE_EXTENSIONS):
                files_to_process.append({
                    "key": key,
                    "size": obj["Size"],
                })

    if args.limit:
        files_to_process = files_to_process[:args.limit]

    print(f"Found {len(files_to_process)} image files.")

    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    total_files = len(files_to_process)
    processed_count = 0
    total_saved_bytes = 0

    print(f"\n{'Filename':<50} | {'Saved Size':<15} | {'Status':<15}")
    print("-" * 85)

    for i, file_info in enumerate(files_to_process):
        key = file_info["key"]

        if args.dry_run:
            print(f"[{i+1}/{total_files}] {key:<42} | -- | [PENDING]")
            continue

        # Download
        local_path = os.path.join(TEMP_DIR, os.path.basename(key))
        # Handle subdirectories in keys
        if "/" in key:
            os.makedirs(os.path.join(TEMP_DIR, os.path.dirname(key)), exist_ok=True)
            local_path = os.path.join(TEMP_DIR, key)

        try:
            s3.download_file(PUBLIC_BUCKET, key, local_path)

            # 1. Check if metadata exists first
            if check_metadata(local_path):
                # 2. Strip it
                success, before, after = strip_metadata(local_path)

                if success:
                    saved = before - after
                    # 3. Upload only if modified
                    upload_with_cache(s3, local_path, PUBLIC_BUCKET, key)
                    total_saved_bytes += saved
                    print(f"[{i+1}/{total_files}] {key:<42} | {saved/1024:>7.2f} KiB | [STRIPPED]")
                else:
                    print(f"[{i+1}/{total_files}] {key:<42} |    -- KiB | [ERROR]")
            else:
                # No metadata found, skip upload
                print(f"[{i+1}/{total_files}] {key:<42} |    0.00 KiB | [CLEAN]")

            processed_count += 1

        except Exception as e:
            print(f"Error processing {key}: {e}")
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

        # Small rate limiting to be nice to the API
        if i % 10 == 0:
            time.sleep(0.05)

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total images found: {total_files}")
    if not args.dry_run:
        print(f"  Total space saved: {total_saved_bytes / 1024 / 1024:.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    main()
