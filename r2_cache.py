"""Cache-Control for objects written to the R2 public bucket.

R2 objects are stored without a `Cache-Control` header unless the upload sets
one. Without it a browser falls back to heuristic caching, so a freshly uploaded
image (Last-Modified = now) is re-requested on every page view.

Every upload must go through `extra_args()`; `set_cache_control.py` backfills the
objects that were stored before this existed.

Upload names are immutable in practice ("IH7iA8.jpg", "IH7iA8-320.webp") and get
one year. Fixed names that can be replaced in place ("favicon.png",
"nophoto.png") get one day.
"""

import re

YEAR = "public, max-age=31536000"
DAY = "public, max-age=86400"

UPLOAD_NAME = re.compile(
    r"^[A-Za-z0-9]{6}(?:-\d{3,4})?(?:\.[a-z]{3,4})?\.(?:jpg|jpeg|png|webp|avif)$",
    re.IGNORECASE,
)


def cache_control_for(key: str) -> str:
    """Return the Cache-Control value for an object key."""
    return YEAR if UPLOAD_NAME.search(key) else DAY


def extra_args(key: str) -> dict:
    """ExtraArgs for boto3 upload_file / upload_fileobj."""
    return {"CacheControl": cache_control_for(key)}


def upload_with_cache(s3, local_path, bucket, key):
    """s3.upload_file with the Cache-Control header for `key`."""
    s3.upload_file(local_path, bucket, key, ExtraArgs=extra_args(key))
