#!/usr/bin/env python3
"""
Cache-Control for the PUBLIC bucket.

R2 objects are served without a `Cache-Control` header, so browsers fall back to
heuristic caching and freshly uploaded images are re-requested on every visit.
This sets the header at the source:

- upload names and their thumbnails (6 random characters, optional -320/-640): 1 year
- every other key (fixed names such as favicon.png or nophoto.png): 1 day

Usage:
    python set_cache_control.py --dry-run
    python set_cache_control.py
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from r2_cache import cache_control_for

load_dotenv(".env.local")
load_dotenv()

CF_ENDPOINT = os.getenv("CF_ENDPOINT")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
PUBLIC_BUCKET = os.environ["PUBLIC_BUCKET"]


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=CF_ENDPOINT,
        aws_access_key_id=CF_ACCESS_KEY,
        aws_secret_access_key=CF_SECRET_KEY,
        region_name="auto",
    )


def main():
    parser = argparse.ArgumentParser(description="Set Cache-Control on every object in the PUBLIC bucket")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change")
    parser.add_argument("--limit", type=int, default=None, help="Stop after this many objects")
    parser.add_argument("--workers", type=int, default=16, help="Concurrent requests")
    args = parser.parse_args()

    if not (CF_ENDPOINT and CF_ACCESS_KEY and CF_SECRET_KEY):
        sys.exit("Missing CF_ENDPOINT / CF_ACCESS_KEY / CF_SECRET_KEY in the environment or .env.local")

    s3 = s3_client()
    print(f"[{datetime.now(UTC).isoformat()}] bucket={PUBLIC_BUCKET} dry-run={args.dry_run} workers={args.workers}")

    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=PUBLIC_BUCKET):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    if args.limit:
        keys = keys[: args.limit]
    print(f"listed {len(keys)} objects")

    seen = changed = skipped = failed = 0
    samples = []

    def process(key):
        head = s3.head_object(Bucket=PUBLIC_BUCKET, Key=key)
        current = head.get("CacheControl")
        wanted = cache_control_for(key)
        if current == wanted:
            return "ok", key, None
        if not args.dry_run:
            try:
                s3.copy_object(
                    Bucket=PUBLIC_BUCKET,
                    Key=key,
                    CopySource={"Bucket": PUBLIC_BUCKET, "Key": key},
                    MetadataDirective="REPLACE",
                    CacheControl=wanted,
                    ContentType=head.get("ContentType", "application/octet-stream"),
                )
            except ClientError as e:
                return "failed", key, e.response["Error"]["Message"]
        return "changed", key, (current, wanted)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for status, key, info in pool.map(process, keys):
            seen += 1
            if status == "ok":
                skipped += 1
            elif status == "failed":
                failed += 1
                print(f"  FAILED {key}: {info}")
            else:
                changed += 1
                if len(samples) < 5:
                    samples.append(f"  {key}: {info[0]} -> {info[1]}")
                if not args.dry_run and changed % 500 == 0:
                    print(f"  ... {changed} updated of {seen} seen")

    for line in samples:
        print(line)
    print("=" * 60)
    print(f"seen={seen} changed={changed} already_ok={skipped} failed={failed} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
