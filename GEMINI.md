# Project Overview: thecopierparts-img-uploader

A specialized Flask-based microservice for managing image uploads, processing, and storage for **TheCopierParts.com**. This service handles image resizing, watermarking, WebP conversion, and thumbnail generation, storing all assets in Cloudflare R2 (S3-compatible storage).

## Core Functionalities

### 1. Image Upload & Processing (`/upload`)
- **Bucket: `PUBLIC_BUCKET` (Public)**
  - Generates 7-character random filename.
  - Creates a watermarked version ("TheCopierParts.com").
  - Converts to WebP.
  - Generates thumbnails (320px, 640px) in both original format and WebP.
  - Backs up the **original, unwatermarked** file to the private bucket.
- **Bucket: `PRIVATE_BUCKET` (Private)**
  - Stores the original file with a 7-character random filename without alterations.
- **Other Buckets**
  - Appends 4 random characters to the original filename to avoid collisions.

### 2. File Management
- **`/fetch`**: Downloads a file from a specified bucket (Public or Private) via `POST` request with JSON parameters: `{"bucket": "bucketname", "filename": "path/filename"}`.
- **`/delete`**: Deletes a specific file from a specified bucket.
- **`/list`**: Lists all objects in a specified bucket with metadata (size, last modified, etag).
- **`/upload_original`**: Uploads a file without any processing or renaming.
- **`/image/<path>`**: Serves images from the private R2 bucket (requires authentication).

### 3. Migration Tools
- **`migrate_images.py`**: A robust, resumable script to process existing images in the public bucket (resize oversized images, generate missing thumbnails).
- **`get_jpg_quality.py`**: Implements ImageMagick's heuristic for detecting JPEG quality from quantization tables.

## Tech Stack

- **Backend**: Python 3.11, Flask
- **WSGI Server**: Gunicorn (using `gevent` workers)
- **Image Processing**: 
  - `Wand` (ImageMagick binding) for watermarking and resizing.
  - `Pillow` for JPEG quality detection.
- **Storage**: `boto3` for Cloudflare R2 integration.
- **Deployment**: Docker (Debian-based with `libmagickwand-dev`).

## Building and Running

### Environment Configuration
Copy `.env.example` to `.env` and fill in:
- `CF_ACCESS_KEY`, `CF_SECRET_KEY`, `CF_ENDPOINT` (Cloudflare R2 S3 credentials)
- `SECRET_KEY` (Used as the Bearer Token for API auth)
- `PUBLIC_BUCKET`, `PRIVATE_BUCKET` (required bucket names)
- `ALLOW_HOSTS` (CORS configuration)

### Local Development
```bash
# Install dependencies (requires ImageMagick development headers)
pip install -r requirements.txt

# Run the Flask development server
python app.py
```

### Docker
```bash
# Build the image
docker build -t img-uploader .

# Run the container
docker run -p 5002:5002 --env-file .env img-uploader
```

## Development Conventions

- **Authentication**: All API endpoints (except `/`) require a `Authorization: Bearer <SECRET_KEY>` header.
- **Storage**:
  - `PUBLIC_BUCKET`: Public-facing bucket for watermarked images and thumbnails.
  - `PRIVATE_BUCKET`: Private storage for original, unwatermarked high-quality assets.
- **Image Specs**:
  - Default max dimension for public images: 800px.
  - Watermark: Centered with "TheCopierParts.com" text on a semi-transparent black background.
  - WebP conversion is preferred for all public assets to optimize delivery.
- **Error Handling**: Uses `traceback` for detailed error reporting in API responses (mostly during development/debug).

## Key Files
- `app.py`: Main entry point and API route definitions.
- `migrate_images.py`: CLI tool for batch processing and repair of existing assets.
- `gunicorn.py`: Production server configuration (10 gevent workers).
- `get_jpg_quality.py`: Low-level image analysis for optimal compression.
