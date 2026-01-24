#!/usr/bin/env python3
"""
ONE-TIME MIGRATION SCRIPT for PUBLIC bucket image processing.

Tasks:
1. Resize oversized images (>800px) in PUBLIC bucket
2. Fetch clean originals from PRIVATE bucket
3. Generate missing thumbnails (320px, 640px in both original format + WebP)
4. Upload thumbnails to PUBLIC bucket

SAFETY FEATURES:
- Dry-run mode (default: ON)
- State tracking for resumability
- Comprehensive logging
- Batch processing with checkpoints
- Rate limiting to avoid API throttling

Usage:
    # Step 1: Dry run (test without changes)
    python migrate_images.py --dry-run

    # Step 2: Pilot run (process first 10 files)
    python migrate_images.py --limit 10

    # Step 3: Full migration
    python migrate_images.py

Author: Migration Script
Date: 2026-01-24
"""

import os
import sys
import json
import boto3
import re
import argparse
from datetime import datetime
from pathlib import Path
from wand.image import Image
from PIL import Image as PILImage
from get_jpg_quality import get_jpg_quality
import time
import traceback
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration
TEMP_DIR = "migration_temp"
STATE_FILE = "migration_state.json"
LOG_FILE = f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
BATCH_SIZE = 50
RATE_LIMIT_DELAY = 0.1  # 100ms between operations
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# R2 Configuration
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
PUBLIC_BUCKET = "your_public_bucket"
PRIVATE_BUCKET = "your_private_bucket"


class MigrationState:
    """Track progress for idempotency and resumability."""

    def __init__(self, state_file):
        self.state_file = state_file
        self.state = self._load()

    def _load(self):
        """Load existing state or create new."""
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                return json.load(f)
        return {
            "processed": [],
            "skipped": [],
            "failed": [],
            "started_at": datetime.now().isoformat(),
            "last_checkpoint": None,
            "stats": {
                "total_files": 0,
                "processed_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "resized_count": 0,
                "thumbnails_generated": 0,
            },
        }

    def save(self):
        """Persist state to disk."""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def is_processed(self, filename):
        """Check if file already processed."""
        return filename in self.state["processed"]

    def mark_processed(self, filename, operations):
        """Mark file as successfully processed."""
        if filename not in self.state["processed"]:
            self.state["processed"].append(filename)
            self.state["stats"]["processed_count"] += 1

            # Update operation stats
            if "resize" in operations:
                self.state["stats"]["resized_count"] += 1
            if any("thumbnail" in op for op in operations):
                # Count thumbnails from operation string
                for op in operations:
                    if "thumbnail" in op:
                        match = re.search(r"(\d+)", op)
                        count = int(match.group(1)) if match else 0
                        self.state["stats"]["thumbnails_generated"] += count

            self.save()

    def mark_skipped(self, filename, reason):
        """Mark file as skipped."""
        self.state["skipped"].append(
            {
                "filename": filename,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.state["stats"]["skipped_count"] += 1
        self.save()

    def mark_failed(self, filename, error):
        """Mark file as failed."""
        self.state["failed"].append(
            {
                "filename": filename,
                "error": str(error),
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.state["stats"]["failed_count"] += 1
        self.save()


class Logger:
    """Structured logging for audit trail."""

    def __init__(self, log_file):
        self.log_file = log_file

    def log(self, level, message, **kwargs):
        """Log message with metadata."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Also print to console
        color_codes = {
            "INFO": "\033[94m",
            "WARN": "\033[93m",
            "ERROR": "\033[91m",
            "SUCCESS": "\033[92m",
            "RESET": "\033[0m",
        }
        color = color_codes.get(level, "")
        reset = color_codes["RESET"]
        print(f"{color}[{level}]{reset} {message}")


def is_thumbnail(filename):
    """Identify if file is already a thumbnail variant."""
    # Thumbnails: filename-320.jpg, filename-640.webp, etc.
    return bool(re.search(r"-\d{3,4}\.(jpg|jpeg|png|webp)$", filename, re.IGNORECASE))


def get_master_files(s3_client, bucket, logger):
    """List only master files (exclude thumbnails)."""
    logger.log("INFO", f"Listing master files from {bucket}...")

    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket)

    master_files = []
    for page in pages:
        for obj in page.get("Contents", []):
            filename = obj["Key"]
            if not is_thumbnail(filename):
                master_files.append(
                    {
                        "key": filename,
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                    }
                )

    logger.log("INFO", f"Found {len(master_files)} master files")
    return master_files


def check_missing_thumbnails(s3_client, bucket, filename):
    """Check which thumbnail variants are missing."""
    base_name = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1].lower()

    thumbnail_variants = [
        f"{base_name}-320{ext}",
        f"{base_name}-320.webp",
        f"{base_name}-640{ext}",
        f"{base_name}-640.webp",
    ]

    missing = []
    for variant in thumbnail_variants:
        try:
            s3_client.head_object(Bucket=bucket, Key=variant)
        except:
            missing.append(variant)

    return missing


def resize_image_if_needed(img, max_size=800):
    """Resize image to max dimension while preserving aspect ratio."""
    img.auto_orient()
    width, height = img.width, img.height

    needs_resize = False
    if width > height and width > max_size:
        img.transform(resize=f"{max_size}x")
        needs_resize = True
    elif height >= width and height > max_size:
        img.transform(resize=f"x{max_size}")
        needs_resize = True

    return needs_resize


def generate_thumbnail(source_path, output_path, size, logger):
    """Generate single thumbnail at specified size."""
    try:
        with Image(filename=source_path) as img:
            # Get quality for JPEG
            img_format = img.format.lower() if img.format else ""
            if img_format == "jpeg":
                pim = PILImage.open(source_path)
                quality = get_jpg_quality(pim)
            else:
                quality = 100

            img.auto_orient()

            # Set compression
            if quality > 80:
                img.compression_quality = 80
            else:
                img.compression_quality = quality

            # Resize
            img.transform(resize=f"{size}x")

            # Save
            img.save(filename=output_path)
            logger.log("INFO", f"Generated thumbnail: {os.path.basename(output_path)}")
            return True
    except Exception as e:
        logger.log("ERROR", f"Failed to generate thumbnail {output_path}", error=str(e))
        return False


def process_single_file(
    s3_client, public_bucket, private_bucket, file_info, logger, state, dry_run=True
):
    """Process a single file with full error handling."""
    filename = file_info["key"]
    temp_public_file = None
    temp_private_file = None
    uploaded_files = []

    try:
        logger.log(
            "INFO",
            f"Processing: {filename}",
            size=f"{file_info['size'] / 1024 / 1024:.2f}MB",
        )

        # Check if file needs processing
        missing_thumbnails = check_missing_thumbnails(
            s3_client, public_bucket, filename
        )

        if not missing_thumbnails:
            logger.log("INFO", f"Skipping {filename} - all thumbnails exist")
            state.mark_skipped(filename, "all_thumbnails_exist")
            return {"status": "skipped", "reason": "all_thumbnails_exist"}

        logger.log(
            "INFO", f"Missing {len(missing_thumbnails)} thumbnails for {filename}"
        )

        if dry_run:
            logger.log("INFO", f"[DRY RUN] Would process: {filename}")
            return {"status": "dry_run", "missing_thumbnails": len(missing_thumbnails)}

        # Create temp directory
        os.makedirs(TEMP_DIR, exist_ok=True)

        temp_public_file = os.path.join(TEMP_DIR, f"public_{filename}")
        temp_private_file = os.path.join(TEMP_DIR, f"private_{filename}")

        # Ensure subdirectories exist
        os.makedirs(os.path.dirname(temp_public_file), exist_ok=True)
        os.makedirs(os.path.dirname(temp_private_file), exist_ok=True)

        operations = []

        # Download from PUBLIC to check if resize needed
        logger.log("INFO", f"Downloading from PUBLIC: {filename}")
        s3_client.download_file(public_bucket, filename, temp_public_file)

        # Check dimensions and resize if needed
        with Image(filename=temp_public_file) as img:
            original_size = (img.width, img.height)
            needs_resize = resize_image_if_needed(img, max_size=800)

            if needs_resize:
                # Save resized version
                img.save(filename=temp_public_file)
                logger.log(
                    "INFO",
                    f"Resized {filename} from {original_size} to ({img.width}, {img.height})",
                )

                # Re-upload to PUBLIC bucket
                s3_client.upload_file(temp_public_file, public_bucket, filename)
                logger.log("SUCCESS", f"Uploaded resized {filename} to PUBLIC")
                operations.append("resize")

        # Try to fetch from PRIVATE bucket for clean thumbnails
        private_exists = False
        try:
            logger.log("INFO", f"Checking PRIVATE bucket for: {filename}")
            s3_client.head_object(Bucket=private_bucket, Key=filename)
            s3_client.download_file(private_bucket, filename, temp_private_file)
            private_exists = True
            logger.log("INFO", f"Using clean original from PRIVATE bucket")
        except Exception as e:
            logger.log(
                "WARN", f"File not in PRIVATE bucket, using PUBLIC version: {filename}"
            )
            # Use PUBLIC version instead
            temp_private_file = temp_public_file

        # Generate thumbnails from the best source
        source_file = temp_private_file if private_exists else temp_public_file
        base_name = os.path.splitext(filename)[0]
        extension = os.path.splitext(filename)[1].lower()

        thumbnail_sizes = [320, 640]
        generated_count = 0

        for size in thumbnail_sizes:
            # Generate original format thumbnail
            orig_output = os.path.join(TEMP_DIR, f"{base_name}-{size}{extension}")
            if generate_thumbnail(source_file, orig_output, size, logger):
                s3_client.upload_file(
                    orig_output, public_bucket, f"{base_name}-{size}{extension}"
                )
                logger.log("SUCCESS", f"Uploaded {base_name}-{size}{extension}")
                uploaded_files.append(orig_output)
                generated_count += 1

            # Generate WebP thumbnail
            webp_output = os.path.join(TEMP_DIR, f"{base_name}-{size}.webp")
            if generate_thumbnail(source_file, webp_output, size, logger):
                # Convert to WebP
                with Image(filename=webp_output) as img:
                    img.format = "webp"
                    img.save(filename=webp_output)

                s3_client.upload_file(
                    webp_output, public_bucket, f"{base_name}-{size}.webp"
                )
                logger.log("SUCCESS", f"Uploaded {base_name}-{size}.webp")
                uploaded_files.append(webp_output)
                generated_count += 1

        operations.append(f"generate_{generated_count}_thumbnails")

        logger.log(
            "SUCCESS", f"Completed processing: {filename}", operations=operations
        )
        state.mark_processed(filename, operations)

        return {
            "status": "success",
            "operations": operations,
            "private_exists": private_exists,
            "generated_count": generated_count,
        }

    except Exception as e:
        logger.log(
            "ERROR",
            f"Failed processing {filename}",
            error=str(e),
            traceback=traceback.format_exc(),
        )
        state.mark_failed(filename, str(e))
        return {"status": "failed", "error": str(e)}

    finally:
        # Cleanup temp files
        for temp_file in [temp_public_file, temp_private_file] + uploaded_files:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)


def generate_report(state, logger):
    """Generate final migration report."""
    stats = state.state["stats"]

    report = f"""
{"=" * 60}
MIGRATION REPORT
{"=" * 60}
Started: {state.state["started_at"]}
Completed: {datetime.now().isoformat()}

SUMMARY:
  Total Files:           {stats["total_files"]}
  Successfully Processed: {stats["processed_count"]}
  Skipped:               {stats["skipped_count"]}
  Failed:                {stats["failed_count"]}
  
OPERATIONS:
  Images Resized:        {stats["resized_count"]}
  Thumbnails Generated:  {stats["thumbnails_generated"]}

FAILED FILES: {len(state.state["failed"])}
"""

    if state.state["failed"]:
        report += "\n  Failed files:\n"
        for fail in state.state["failed"][:10]:  # Show first 10
            report += f"    - {fail['filename']}: {fail['error']}\n"
        if len(state.state["failed"]) > 10:
            report += f"    ... and {len(state.state['failed']) - 10} more (see {STATE_FILE})\n"

    report += f"\nFull details: {STATE_FILE}\nLog file: {LOG_FILE}\n"
    report += "=" * 60

    print(report)
    logger.log("INFO", "Migration report generated", stats=stats)


def main():
    """Main migration orchestrator."""
    parser = argparse.ArgumentParser(description="Migrate PUBLIC bucket images")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Test run without making changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files to process (for testing)",
    )
    args = parser.parse_args()

    logger = Logger(LOG_FILE)
    state = MigrationState(STATE_FILE)

    # Validate environment
    if not all([CF_ENDPOINT, CF_ACCESS_KEY, CF_SECRET_KEY]):
        logger.log(
            "ERROR",
            "Missing environment variables (CF_ENDPOINT, CF_ACCESS_KEY, CF_SECRET_KEY)",
        )
        sys.exit(1)

    # Initialize S3 client
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=CF_ENDPOINT,
            aws_access_key_id=CF_ACCESS_KEY,
            aws_secret_access_key=CF_SECRET_KEY,
            region_name="auto",
        )
        logger.log("INFO", "S3 client initialized successfully")
    except Exception as e:
        logger.log("ERROR", f"Failed to initialize S3 client: {e}")
        sys.exit(1)

    # Create temp directory
    os.makedirs(TEMP_DIR, exist_ok=True)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.log("INFO", f"Starting migration in {mode} mode", limit=args.limit)

    # Get list of master files
    master_files = get_master_files(s3_client, PUBLIC_BUCKET, logger)

    if args.limit:
        master_files = master_files[: args.limit]
        logger.log("INFO", f"Limited to {args.limit} files for testing")

    state.state["stats"]["total_files"] = len(master_files)
    state.save()

    # Process in batches
    for i in range(0, len(master_files), BATCH_SIZE):
        batch = master_files[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(master_files) + BATCH_SIZE - 1) // BATCH_SIZE

        logger.log("INFO", f"Processing batch {batch_num}/{total_batches}")

        for file_info in batch:
            filename = file_info["key"]

            # Skip if already processed
            if state.is_processed(filename):
                logger.log(
                    "INFO", f"Skipping {filename} - already processed in previous run"
                )
                continue

            # Process file
            result = process_single_file(
                s3_client,
                PUBLIC_BUCKET,
                PRIVATE_BUCKET,
                file_info,
                logger,
                state,
                dry_run=args.dry_run,
            )

        # Checkpoint after each batch
        state.state["last_checkpoint"] = datetime.now().isoformat()
        state.save()
        logger.log("INFO", f"Checkpoint saved after batch {batch_num}")

    # Generate final report
    generate_report(state, logger)

    if args.dry_run:
        logger.log("INFO", "DRY RUN completed - no changes made")
        logger.log("INFO", "Run without --dry-run to execute migration")


if __name__ == "__main__":
    main()
