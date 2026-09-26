#!/usr/bin/env python3
"""
Thumbnail Optimization Script for PUBLIC bucket.

Tasks:
1. List all *-320.webp files in the PUBLIC bucket.
2. Check file sizes.
3. If size > 10 KiB, compress the image to target 5-8 KiB.

Usage:
    python optimize_thumbnails.py --dry-run
    python optimize_thumbnails.py
"""

import os
import sys
import boto3
import argparse
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

# R2 Configuration
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
PUBLIC_BUCKET = os.getenv("PUBLIC_BUCKET", "your_public_bucket")

TEMP_DIR = "optimization_temp"
TARGET_MAX_SIZE_KB = 10.0
IDEAL_TARGET_SIZE_BYTES = 8192  # 8 KiB

def format_size(size_bytes):
    return f"{size_bytes / 1024:.2f} KiB"

def optimize_webp(file_path, target_bytes=8192):
    """Use cwebp to compress WebP to fit target size precisely."""
    current_size = os.path.getsize(file_path)
    if current_size <= target_bytes:
        return False, current_size / 1024.0

    output_path = file_path + ".tmp.webp"
    
    try:
        # cwebp command: 
        # -size: target size in bytes
        # -m 6: best compression method
        # -pass 10: more analysis for better results
        # -quiet: no output
        cmd = [
            "cwebp",
            "-size", str(target_bytes),
            "-m", "6",
            "-pass", "10",
            "-quiet",
            file_path,
            "-o", output_path
        ]
        
        subprocess.run(cmd, check=True)
        
        if os.path.exists(output_path):
            new_size = os.path.getsize(output_path)
            # Replace original with optimized
            os.replace(output_path, file_path)
            return True, new_size / 1024.0
            
    except Exception as e:
        print(f"Error during cwebp compression: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
            
    return False, current_size / 1024.0

def main():
    parser = argparse.ArgumentParser(description="Optimize WebP thumbnails")
    parser.add_argument("--dry-run", action="store_true", help="Report sizes without compressing")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of files to check")
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

    print(f"[{datetime.now().isoformat()}] Listing *-320.webp files in {PUBLIC_BUCKET}...")
    
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=PUBLIC_BUCKET)

    thumbnails = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("-320.webp"):
                thumbnails.append({
                    "key": key,
                    "size": obj["Size"],
                })

    if args.limit:
        thumbnails = thumbnails[:args.limit]

    print(f"Found {len(thumbnails)} thumbnails.")
    
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    oversized_count = 0
    total_saved = 0

    print(f"\n{'Filename':<50} | {'Original Size':<15} | {'Status':<15}")
    print("-" * 85)

    for thumb in thumbnails:
        key = thumb["key"]
        size_kb = thumb["size"] / 1024.0
        
        if size_kb > TARGET_MAX_SIZE_KB:
            oversized_count += 1
            if args.dry_run:
                print(f"{key:<50} | {size_kb:>11.2f} KiB | [OVERSIZED]")
                continue
            
            # Download and optimize
            local_path = os.path.join(TEMP_DIR, os.path.basename(key))
            s3.download_file(PUBLIC_BUCKET, key, local_path)
            
            success, new_size_kb = optimize_webp(local_path, target_bytes=IDEAL_TARGET_SIZE_BYTES)
            
            if success:
                s3.upload_file(local_path, PUBLIC_BUCKET, key)
                saved = size_kb - new_size_kb
                total_saved += saved
                print(f"{key:<50} | {size_kb:>11.2f} KiB | Optimized to {new_size_kb:.2f} KiB")
            else:
                print(f"{key:<50} | {size_kb:>11.2f} KiB | [SKIPPED - Already Optimal]")
            
            if os.path.exists(local_path):
                os.remove(local_path)
            
            time.sleep(0.05) # Small delay
        else:
            # Uncomment if you want to see all files
            # print(f"{key:<50} | {size_kb:>11.2f} KiB | [OK]")
            pass

    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Total thumbnails checked: {len(thumbnails)}")
    print(f"  Oversized thumbnails (>10KiB): {oversized_count}")
    if not args.dry_run:
        print(f"  Total space saved: {total_saved:.2f} KiB")
    print("=" * 60)

if __name__ == "__main__":
    main()
