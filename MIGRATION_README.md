# Image Migration Script

## Overview

This script performs a **one-time migration** to:
1. **Resize** oversized images (>800px) in PUBLIC bucket
2. **Generate** missing thumbnails (320px, 640px) from PRIVATE bucket originals
3. **Upload** clean thumbnails (without watermarks) to PUBLIC bucket

## Safety Features

✅ **Dry-run mode** (default) - test without changes  
✅ **State tracking** - resumable if interrupted  
✅ **Comprehensive logging** - full audit trail  
✅ **Batch processing** - checkpoints every 50 files  
✅ **Rate limiting** - avoids API throttling  

## Pre-Flight Checklist

Before running the migration:

- [ ] **Backup**: Create snapshot of PUBLIC bucket metadata
  ```bash
  python -c "
  import boto3, json, os
  from dotenv import load_dotenv
  load_dotenv()
  s3 = boto3.client('s3', 
      endpoint_url=os.getenv('CF_ENDPOINT'),
      aws_access_key_id=os.getenv('CF_ACCESS_KEY'),
      aws_secret_access_key=os.getenv('CF_SECRET_KEY'),
      region_name='auto')
  
  objects = []
  paginator = s3.get_paginator('list_objects_v2')
  for page in paginator.paginate(Bucket=os.getenv('PUBLIC_BUCKET')):
      for obj in page.get('Contents', []):
          objects.append({'key': obj['Key'], 'size': obj['Size']})
  
  with open('pre_migration_snapshot.json', 'w') as f:
      json.dump(objects, f, indent=2)
  print(f'Saved {len(objects)} files to pre_migration_snapshot.json')
  "
  ```

- [ ] **Disk space**: Ensure 20GB+ free space
  ```bash
  df -h .
  ```

- [ ] **Environment**: Verify .env has required variables
  ```bash
  grep -E "CF_ENDPOINT|CF_ACCESS_KEY|CF_SECRET_KEY" .env
  ```

- [ ] **Dependencies**: Install required packages
  ```bash
  pip install boto3 python-dotenv wand pillow
  ```

## Execution Plan

### Phase 1: Dry Run (MANDATORY)

Test the migration without making changes:

```bash
python migrate_images.py --dry-run
```

**Review outputs:**
- `migration_YYYYMMDD_HHMMSS.log` - All operations logged
- Console output - What would be processed

**Validation:**
- ✅ No errors in log
- ✅ File counts look reasonable
- ✅ No credential issues

---

### Phase 2: Pilot Run (RECOMMENDED)

Process first 10 files to verify:

```bash
python migrate_images.py --limit 10
```

**Manual verification:**
1. Check PUBLIC bucket for new thumbnails:
   - `{filename}-320.jpg`
   - `{filename}-320.webp`
   - `{filename}-640.jpg`
   - `{filename}-640.webp`

2. Verify thumbnail quality:
   - Download a few thumbnails
   - Check dimensions (320px or 640px width)
   - Verify no watermarks on thumbnails
   - Confirm clean, sharp images

3. Review logs:
   ```bash
   tail -50 migration_*.log
   ```

**If pilot fails:**
- ❌ Do NOT proceed to full migration
- Review error logs
- Fix issues in script or environment
- Delete `migration_state.json` and retry

---

### Phase 3: Full Migration

**Only proceed if pilot was 100% successful.**

```bash
# Run in screen/tmux session (recommended)
screen -S migration
python migrate_images.py

# Detach: Ctrl+A, D
# Reattach: screen -r migration
```

**Monitor progress:**
- Watch log file in real-time:
  ```bash
  tail -f migration_*.log
  ```

- Check state file for progress:
  ```bash
  cat migration_state.json | jq '.stats'
  ```

**Expected duration:**
- ~2 seconds per file (with rate limiting)
- 1000 files ≈ 35 minutes

---

## Script Behavior

### What it does:

1. **Lists** all master files in PUBLIC bucket (excludes existing thumbnails)
2. **For each file:**
   - Checks if thumbnails already exist → skips if yes
   - Downloads from PUBLIC bucket
   - Checks dimensions → resizes if >800px
   - Re-uploads resized version to PUBLIC
   - Fetches clean original from PRIVATE bucket (if exists)
   - Generates 4 thumbnails (320.jpg, 320.webp, 640.jpg, 640.webp)
   - Uploads thumbnails to PUBLIC bucket
   - Cleans up temp files

### What it does NOT do:

- ❌ Modify PRIVATE bucket (read-only)
- ❌ Delete any files
- ❌ Process already-complete files (idempotent)

### Resumability:

If the script crashes or is interrupted:

```bash
# Just re-run - it will skip already-processed files
python migrate_images.py
```

State is saved in `migration_state.json`:
- `processed`: Files completed successfully
- `failed`: Files that had errors
- `skipped`: Files that didn't need processing

---

## Output Files

**migration_state.json:**
```json
{
  "processed": ["file1.jpg", "file2.jpg"],
  "skipped": [...],
  "failed": [...],
  "stats": {
    "total_files": 1000,
    "processed_count": 850,
    "skipped_count": 100,
    "failed_count": 50,
    "resized_count": 200,
    "thumbnails_generated": 3400
  }
}
```

**migration_YYYYMMDD_HHMMSS.log:**
- Structured JSON logs
- Every operation timestamped
- Errors with full tracebacks

---

## Troubleshooting

### "Missing environment variables"
```bash
# Check .env file exists and has values
cat .env | grep CF_
```

### "Failed to initialize S3 client"
- Verify credentials are correct
- Check network connectivity
- Test endpoint URL

### "Disk space full"
- Free up space in current directory
- Script downloads files to `migration_temp/`

### High failure rate (>10%)
- **STOP the migration**
- Review failed files in `migration_state.json`
- Check error patterns in log file
- Fix underlying issue before continuing

### Script hangs
- Check network connectivity
- Look for large files (may take time to download)
- Verify R2 API is responding

---

## Post-Migration Verification

**1. Count check:**
```bash
# Master files should have 4 thumbnails each
# If 1000 master files → expect ~4000 new thumbnails
```

**2. Spot check (manual):**
- Download 10 random thumbnails
- Verify dimensions: 320px or 640px width
- Confirm no watermarks
- Check image quality

**3. Review report:**
```bash
# Script generates summary at end
# Also check:
cat migration_state.json | jq '.stats'
```

**4. Test in production:**
- Update frontend to use new thumbnail URLs
- Verify responsive images load correctly
- Check browser network tab for proper srcset selection

---

## Rollback Plan

If migration causes issues:

**Thumbnails only (safe):**
- Delete generated thumbnails from PUBLIC bucket
- Original full-size images unchanged
- No rollback needed for originals

**If resized images have issues:**
- Use `pre_migration_snapshot.json` to identify affected files
- Fetch originals from PRIVATE bucket
- Re-process through normal upload flow

---

## Cost Estimate

**Assumptions:**
- 1000 files
- Average 2MB per file
- R2 pricing: $0.36/GB egress (if outside Cloudflare)

**Bandwidth:**
- Download from PUBLIC: 1000 × 2MB = 2GB
- Download from PRIVATE: 1000 × 2MB = 2GB  
- Upload thumbnails: 1000 × 4 × 0.3MB = 1.2GB
- **Total: ~5.2GB**

**Cost:**
- If within Cloudflare network: **$0** (free)
- If external: ~$1.87 (5.2GB × $0.36/GB)

**API Operations:**
- ~15,000 operations (mostly free tier)

---

## Support

**Before asking for help:**
1. Read error messages in log file
2. Check `migration_state.json` for details
3. Review this README troubleshooting section

**Include when reporting issues:**
- Error messages from log file
- `migration_state.json` stats
- Command you ran
- Environment (OS, Python version)

---

## After Successful Migration

- [ ] Verify thumbnails work in production
- [ ] Archive migration logs: `migration_*.log`, `migration_state.json`
- [ ] Delete temp directory: `rm -rf migration_temp/`
- [ ] Keep `pre_migration_snapshot.json` as backup reference
- [ ] Update documentation with new image naming scheme
- [ ] **Do NOT run this script again** (one-time use only)

---

## Quick Reference

```bash
# Test without changes
python migrate_images.py --dry-run

# Process first 10 files
python migrate_images.py --limit 10

# Full migration
python migrate_images.py

# Resume after interruption (automatically skips processed files)
python migrate_images.py

# View progress
tail -f migration_*.log
cat migration_state.json | jq '.stats'

# Check final results
cat migration_state.json | jq
```

---

**Last Updated:** 2026-01-24  
**Script Version:** 1.0  
**Author:** Migration Script Generator
