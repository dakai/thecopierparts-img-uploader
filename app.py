import os
import boto3
import random
import string
import json
import gc
from tqdm import tqdm
from wand.image import Image
from wand.color import Color
from wand.resource import limits
from dotenv import load_dotenv
from wand.drawing import Drawing
from colorthon import Colors as Fore
from PIL import Image as PILImage
from get_jpg_quality import get_jpg_quality
from flask import Flask, request, jsonify, render_template
from botocore.exceptions import ClientError
import traceback
import subprocess
from flask import Response
from werkzeug.utils import secure_filename
from flask_cors import CORS  # Import CORS

# Set ImageMagick resource limits to prevent OOM
limits["memory"] = 512 * 1024 * 1024  # 512MB
limits["map"] = 1024 * 1024 * 1024  # 1GB

load_dotenv()

CF_API_TOKEN = os.getenv("CF_API_TOKEN")
ALLOW_HOSTS = os.getenv("ALLOW_HOSTS", "*").split(
    ","
)  # Get allowed origins from env, default to all
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
# PUBLIC_BUCKET = os.getenv("PUBLIC_BUCKET")
API_KEY = os.getenv("SECRET_KEY")
# R2 bucket details
PUBLIC_BUCKET = "your_public_bucket"
PRIVATE_BUCKET = "your_private_bucket"

app = Flask(__name__)
cors = CORS(
    app, origins=ALLOW_HOSTS, supports_credentials=True
)  # Initialize CORS with allowed origins

UPLOAD_FOLDER = "uploads"  # Folder to store uploaded files
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "tif", "avif"}  # Allowed image extensions


@app.route("/image/<path:image_path>")
def serve_image(image_path):
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    # data = request.get_json()
    # file = data.get("filename")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    """Serves images from R2 storage."""
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=CF_ENDPOINT,
            aws_access_key_id=CF_ACCESS_KEY,
            aws_secret_access_key=CF_SECRET_KEY,
            region_name="auto",
        )

        bucket_name = PRIVATE_BUCKET
        # Fetch the image from R2
        response = s3.get_object(Bucket=bucket_name, Key=image_path)
        image_data = response["Body"].read()

        # Determine content type based on the file extension (you can expand this)
        content_type = "image/jpeg"  # Default
        if image_path.endswith(".png"):
            content_type = "image/png"
        elif image_path.endswith(".webp"):
            content_type = "image/webp"

        return Response(image_data, content_type=content_type)

    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return (
                jsonify({"error": "Image not found"}),
                404,
            )  # Return 404 if image not found
        else:
            return jsonify({"error": f"Error fetching image: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


def generate_random_filename(length, extension):
    """Generates a random filename with random placement of letters and numbers."""
    characters = string.ascii_letters + string.digits
    random_part = "".join(random.choice(characters) for _ in range(length))
    return f"{random_part}.{extension}"


def allowed_file(filename):
    """Checks if the file extension is allowed."""
    if not filename:
        return False
    _, file_extension = os.path.splitext(filename)
    return file_extension[1:].lower() in ALLOWED_EXTENSIONS


def check_if_file_exists(file_path):
    """Checks if a file exists at the given path.

    Args:
      file_path: The path to the file, including the filename.

    Returns:
      True if the file exists, False otherwise.
    """
    return os.path.exists(file_path)


def generate_unique_filename(filename):
    extension = filename.rsplit(".", 1)[1].lower()
    unique_filename = generate_random_filename(6, extension)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
    while check_if_file_exists(file_path):
        unique_filename = generate_random_filename(6, extension)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
    return unique_filename


def generate_unique_document_filename(filename):
    extension = filename.rsplit(".", 1)[1].lower()
    filename_without_extension = os.path.splitext(filename)[0]
    unique_filename = generate_random_filename(4, extension)
    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"], filename_without_extension + "_" + unique_filename
    )
    while check_if_file_exists(file_path):
        unique_filename = generate_random_filename(4, extension)
        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename_without_extension + "_" + unique_filename,
        )
    return filename_without_extension + "_" + unique_filename


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)


@app.route("/upload", methods=["POST"])
def upload():
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    # data = request.get_json()
    # file = data.get("filename")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    # bucket_name = data.get("bucket")
    bucket_name = request.form.get("bucket")
    print(f"--- Upload Start ---")
    print(f"Bucket Name: {bucket_name}")
    print(f"Files in request: {request.files}")

    if bucket_name == "your_public_bucket":
        try:
            uploaded_files = []
            files = request.files.getlist("file")
            if not files:
                print("Error: No file part in the request")
                return jsonify({"error": "No file part in the request"}), 400

            for file in files:
                if file.filename == "":
                    print("Error: No selected file")
                    return jsonify({"error": "No selected file"}), 400

                if file and allowed_file(file.filename):
                    filename = file.filename
                    print(f"Processing file: {filename}")
                    if not filename == None:
                        unique_filename = generate_unique_filename(filename)
                        # file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))
                        image_path = os.path.join(
                            app.config["UPLOAD_FOLDER"], unique_filename
                        )
                        file.save(image_path)
                        # convert_webp(image_path)
                        uploaded_files.append(unique_filename)
                        print(f"Uploading original to R2: {PRIVATE_BUCKET}/{unique_filename}")
                        upload_to_r2_cloudflare(
                            CF_ENDPOINT,
                            CF_ACCESS_KEY,
                            CF_SECRET_KEY,
                            "auto",
                            PRIVATE_BUCKET,  # Save as a none watermarked backup
                            image_path,
                        )
                        print(f"Adding watermark and converting: {image_path}")
                        add_watermark_and_convert(image_path)
                        print(f"Uploading watermarked to R2: {PUBLIC_BUCKET}")
                        upload_watermark(unique_filename)
                        delete_file(image_path)
                        gc.collect()  # Force garbage collection
                else:
                    print(f"Error: File type not allowed for {file.filename}")
                    return jsonify({"error": "File type not allowed"}), 400

        except Exception as e:
            traceback.print_exc()
            return (jsonify({"error": f"Error uploading files: {str(e)}"}), 500)
        return (
            jsonify(
                {"message": "All files uploaded successfully", "files": uploaded_files}
            ),
            201,
        )
    elif bucket_name == "your_private_bucket":
        try:
            uploaded_files = []
            files = request.files.getlist("file")
            if not files:
                print("Error: No file part in the request (private)")
                return jsonify({"error": "No file part in the request"}), 400

            for file in files:
                if file.filename == "":
                    print("Error: No selected file (private)")
                    return jsonify({"error": "No selected file"}), 400

                if file and allowed_file(file.filename):
                    filename = file.filename
                    print(f"Processing private file: {filename}")
                    if not filename == None:
                        unique_filename = generate_unique_filename(filename)
                        # file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))
                        image_path = os.path.join(
                            app.config["UPLOAD_FOLDER"], unique_filename
                        )
                        file.save(image_path)
                        # convert_webp(image_path)
                        uploaded_files.append(unique_filename)
                        print(f"Uploading to private R2: {bucket_name}/{unique_filename}")
                        upload_to_r2_cloudflare(
                            CF_ENDPOINT,
                            CF_ACCESS_KEY,
                            CF_SECRET_KEY,
                            "auto",
                            bucket_name,
                            image_path,
                        )
                        delete_file(image_path)

        except Exception as e:
            traceback.print_exc()
            return (jsonify({"error": f"Error uploading files: {str(e)}"}), 500)
        return (
            jsonify(
                {"message": "All files uploaded successfully", "files": uploaded_files}
            ),
            201,
        )
    else:
        try:
            print(f"Processing other bucket: {bucket_name}")
            uploaded_files = []
            files = request.files.getlist("file")
            if not files:
                print("Error: No file part in the request (other)")
                return jsonify({"error": "No file part in the request"}), 400

            for file in files:
                if file.filename == "":
                    print("Error: No selected file (other)")
                    return jsonify({"error": "No selected file"}), 400

                filename = file.filename
                print(f"Processing other file: {filename}")
                if not filename == None:
                    unique_filename = generate_unique_document_filename(filename)
                    image_path = os.path.join(
                        app.config["UPLOAD_FOLDER"], unique_filename
                    )
                    file.save(image_path)
                    # convert_webp(image_path)
                    uploaded_files.append(unique_filename)
                    print(f"Uploading to R2: {bucket_name}/{unique_filename}")
                    upload_to_r2_cloudflare(
                        CF_ENDPOINT,
                        CF_ACCESS_KEY,
                        CF_SECRET_KEY,
                        "auto",
                        bucket_name,
                        image_path,
                    )
                    delete_file(image_path)
            return (
                jsonify(
                    {
                        "message": "All files uploaded successfully",
                        "files": uploaded_files,
                    }
                ),
                201,
            )
        except Exception as e:
            traceback.print_exc()
            return (jsonify({"error": f"Error uploading files: {str(e)}"}), 500)


@app.route("/delete", methods=["POST"])
def delete():
    # Auth validation
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        file = data.get("filename")
        bucket = data.get("bucket")

        # Validate required fields
        if not file or not bucket:
            return (
                jsonify({"error": "Missing required fields: filename and bucket"}),
                400,
            )

        # Attempt deletion
        result = delete_from_r2_cloudflare(
            CF_ENDPOINT,
            CF_ACCESS_KEY,
            CF_SECRET_KEY,
            "auto",
            bucket,
            file,
        )

        # Handle deletion result
        if result["success"]:
            return (
                jsonify(
                    {"message": result["message"], "filename": file, "bucket": bucket}
                ),
                200,
            )
        else:
            return jsonify(
                {"error": result["message"], "filename": file, "bucket": bucket}
            ), (404 if "not found" in result["message"].lower() else 500)

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "error": f"Unexpected error: {str(e)}",
                    "details": traceback.format_exc(),
                }
            ),
            500,
        )


@app.route("/delete/<path:key>", methods=["DELETE"])
def delete_bucket_file(key):
    # Auth validation
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    try:
        # You might want to add validation for the key format
        if not key:
            return jsonify({"error": "No file key provided"}), 400

        # If you need to extract bucket and filename from the key
        # Assuming default bucket, modify as needed
        bucket = "your-default-bucket"
        file = key
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        bucket = data.get("bucket")

        # Attempt deletion
        result = delete_from_r2_cloudflare(
            CF_ENDPOINT,
            CF_ACCESS_KEY,
            CF_SECRET_KEY,
            "auto",
            bucket,
            file,
        )

        # Handle deletion result
        if result["success"]:
            return (
                jsonify({"message": result["message"], "key": key, "bucket": bucket}),
                200,
            )
        else:
            return jsonify(
                {"error": result["message"], "key": key, "bucket": bucket}
            ), (404 if "not found" in result["message"].lower() else 500)

    except Exception as e:
        return (
            jsonify(
                {
                    "error": f"Unexpected error: {str(e)}",
                    "details": traceback.format_exc(),
                    "key": key,
                }
            ),
            500,
        )


@app.route("/fetch", methods=["POST"])
def fetch_file():
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    bucket_name = data.get("bucket")
    file_path = data.get("filename")

    if not bucket_name or not file_path:
        return jsonify({"error": "Missing bucket or filename"}), 400

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=CF_ENDPOINT,
            aws_access_key_id=CF_ACCESS_KEY,
            aws_secret_access_key=CF_SECRET_KEY,
            region_name="auto",
        )

        # Fetch the file from R2
        response = s3.get_object(Bucket=bucket_name, Key=file_path)
        file_data = response["Body"].read()

        # Get content type from response or fallback
        content_type = response.get("ContentType", "application/octet-stream")

        return Response(file_data, content_type=content_type)

    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return jsonify({"error": "File not found"}), 404
        return jsonify({"error": f"Error fetching file: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route("/list", methods=["POST"])
def list():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    try:
        data = request.get_json()
        bucket = data.get("bucket")
        prefix = data.get("prefix", "")  # Get optional prefix
        result = get_bucket_contents(
            bucket,
            CF_ENDPOINT,
            CF_ACCESS_KEY,
            CF_SECRET_KEY,
            "auto",
            prefix=prefix,
        )

    except Exception as e:
        return jsonify({"error": f"Error listing files: {str(e)}"}), 500

    return jsonify(result), 200


def get_bucket_contents(
    bucket_name,
    endpoint_url,
    access_key_id,
    secret_key,
    region_name,
    prefix="",
):
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_key,
        region_name=region_name,
    )
    objects_list = []

    try:
        paginator = s3.get_paginator("list_objects_v2")
        # Add prefix to pagination
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

        for page in pages:
            for obj in page.get("Contents", []):
                # Convert datetime to string for JSON serialization
                obj["LastModified"] = obj["LastModified"].isoformat()

                # Create a clean dictionary with desired fields
                object_dict = {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                    "etag": obj["ETag"].strip('"'),
                    "storage_class": obj["StorageClass"],
                }
                objects_list.append(object_dict)

        # Convert to JSON string if needed
        json_data = json.dumps(objects_list, indent=2)

        return {
            "objects": objects_list,  # Python list of dictionaries
            "json_string": json_data,  # JSON string format
        }

    except Exception as e:
        print(f"Error: {e}")
        return None


## Usage example
# bucket_name = 'your-bucket-name'
# result = get_bucket_contents(bucket_name)
#
# if result:
#    # Work with Python list of dictionaries
#    for item in result['objects']:
#        print(f"Processing file: {item['key']}")
#        # Do something with the item...
#
#    # Or work with JSON string
#    print(result['json_string'])
#
#    # Save to file if needed
#    with open('bucket_contents.json', 'w') as f:
#        json.dump(result['objects'], f, indent=2)
#
#    # Filter objects programmatically
#    # Example: Get all .jpg files larger than 1MB
#    large_images = [
#        obj for obj in result['objects']
#        if obj['key'].endswith('.jpg') and obj['size'] > 1000000
#    ]


@app.route("/upload_original", methods=["POST"])
def upload_original():
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    bucket_name = request.form.get("bucket")
    try:
        uploaded_files = []
        files = request.files.getlist("file")
        if not files:
            return jsonify({"error": "No file part in the request"}), 400

        for file in files:
            if file.filename == "" or file.filename == None:
                return jsonify({"error": "No selected file"}), 400

            filename = secure_filename(file.filename)

            if not filename == None:
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(file_path)
                # convert_webp(image_path)
                uploaded_files.append(filename)
                upload_to_r2_cloudflare(
                    CF_ENDPOINT,
                    CF_ACCESS_KEY,
                    CF_SECRET_KEY,
                    "auto",
                    bucket_name,
                    file_path,
                )
                delete_file(file_path)
    except Exception as e:
        return (jsonify({"error": f"Error uploading files: {str(e)}"}), 500)
    return (
        jsonify(
            {"message": "All files uploaded successfully", "files": uploaded_files}
        ),
        201,
    )


@app.route("/upload_custom", methods=["POST"])
def upload_custom():
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    bucket_name = request.form.get("bucket")
    custom_path = request.form.get("path", "").strip("/")

    if not bucket_name:
        return jsonify({"error": "Bucket name is required"}), 400

    try:
        uploaded_files = []
        files = request.files.getlist("file")
        if not files:
            return jsonify({"error": "No file part in the request"}), 400

        for file in files:
            if file.filename == "" or file.filename == None:
                continue

            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            # Construct the S3 key (path + filename)
            remote_key = f"{custom_path}/{filename}" if custom_path else filename

            upload_to_r2_cloudflare(
                CF_ENDPOINT,
                CF_ACCESS_KEY,
                CF_SECRET_KEY,
                "auto",
                bucket_name,
                file_path,
                remote_key=remote_key,
            )
            delete_file(file_path)
            uploaded_files.append(
                {"filename": filename, "key": remote_key, "bucket": bucket_name}
            )

    except Exception as e:
        return (
            jsonify(
                {
                    "error": f"Error uploading files: {str(e)}",
                    "details": traceback.format_exc(),
                }
            ),
            500,
        )

    return (
        jsonify({"message": "Files uploaded successfully", "files": uploaded_files}),
        201,
    )


def upload_watermark(image_path):
    """Uploads watermarked images and thumbnails to public bucket.

    Generates and uploads:
    - Original size watermarked image (JPG/PNG/etc)
    - Original size watermarked WebP
    - 320px thumbnail (JPG/PNG/etc + WebP) - NO watermark
    - 640px thumbnail (JPG/PNG/etc + WebP) - NO watermark
    """
    try:
        basename = os.path.basename(image_path)
        name_without_extension = os.path.splitext(basename)[0]
        extension = image_path.rsplit(".", 1)[1].lower()

        # Paths for watermarked full-size images
        path = "output/" + basename
        webp_path = f"output/{basename}.webp"

        # Upload full-size watermarked images
        upload_to_r2_cloudflare(
            CF_ENDPOINT,
            CF_ACCESS_KEY,
            CF_SECRET_KEY,
            "auto",
            PUBLIC_BUCKET,
            webp_path,
        )
        upload_to_r2_cloudflare(
            CF_ENDPOINT,
            CF_ACCESS_KEY,
            CF_SECRET_KEY,
            "auto",
            PUBLIC_BUCKET,
            path,
        )

        # Generate and upload thumbnails (without watermarks)
        thumbnail_paths = generate_thumbnails("uploads/" + basename, sizes=[320, 640])

        for thumb_path in thumbnail_paths:
            upload_to_r2_cloudflare(
                CF_ENDPOINT,
                CF_ACCESS_KEY,
                CF_SECRET_KEY,
                "auto",
                PUBLIC_BUCKET,
                thumb_path,
            )
            delete_file(thumb_path)

        # Clean up watermarked files
        delete_file(path)
        delete_file(webp_path)

    except Exception as e:
        print(f"Error processing {image_path}: {e}")


def resize_image(img, compressed_rate):
    """Resizes an image if it exceeds 1920px in height or width,
    preserving aspect ratio.

    Args:
        image_data (bytes): Image data (e.g., from `open(image_path, 'rb').read()`)

    Returns:
        bytes: Resized image data or original data if no resizing was needed.
    """
    img.auto_orient()

    width, height = img.width, img.height

    if width > height and width > 800:  # Landscape/Horizontal
        img.transform(resize="800x")
    elif height >= width and height > 800:  # Portrait/Vertical
        img.transform(resize="x800")

    if compressed_rate > 80:
        img.compression_quality = 80

    return img  # Return resized or original image data


def generate_thumbnails(image_path, sizes=[320, 640]):
    """Generates thumbnail variants without watermarks.

    Args:
        image_path: Path to the original image in uploads folder
        sizes: List of thumbnail widths to generate (default: [320, 640])

    Returns:
        List of generated thumbnail file paths
    """
    try:
        thumbnail_paths = []
        basename = os.path.basename(image_path)
        name_without_extension = os.path.splitext(basename)[0]
        extension = image_path.rsplit(".", 1)[1].lower()

        with Image(filename=image_path) as img:
            # Get quality for JPEG images
            if img.format == "jpeg":
                pim = PILImage.open(image_path)
                quality = get_jpg_quality(pim)
            else:
                quality = 100

            img.auto_orient()

            # Set compression quality
            if quality > 80:
                img.compression_quality = 80
            else:
                img.compression_quality = quality

            # Generate each thumbnail size
            for size in sizes:
                # Clone the image for each size
                with img.clone() as thumb:
                    # Resize to target width, maintaining aspect ratio
                    thumb.transform(resize=f"{size}x")

                    # Save as original format with size suffix
                    output_filename = f"{name_without_extension}-{size}.{extension}"
                    output_path = f"output/{output_filename}"
                    thumb.save(filename=output_path)
                    thumbnail_paths.append(output_path)
                    print(f"Generated thumbnail: {output_filename}")

                    # Also save as WebP with size suffix
                    webp_output_filename = f"{name_without_extension}-{size}.webp"
                    webp_output_path = f"output/{webp_output_filename}"
                    
                    try:
                        # Use cwebp for better compression
                        # For 320px, we target 8KB (8192 bytes)
                        # For others, we use high quality settings
                        cwebp_cmd = [
                            "cwebp",
                            "-m", "6",
                            "-pass", "10",
                            "-quiet",
                            output_path,
                            "-o", webp_output_path
                        ]
                        
                        if size == 320:
                            cwebp_cmd.extend(["-size", "8192"])
                        
                        subprocess.run(cwebp_cmd, check=True)
                        thumbnail_paths.append(webp_output_path)
                        print(f"Generated WebP thumbnail (cwebp): {webp_output_filename}")
                    except Exception as e:
                        print(f"cwebp failed for {webp_output_filename}, falling back to Wand: {e}")
                        with thumb.clone() as webp_thumb:
                            webp_thumb.format = "webp"
                            webp_thumb.save(filename=webp_output_path)
                            thumbnail_paths.append(webp_output_path)
                            print(f"Generated WebP thumbnail (Wand fallback): {webp_output_filename}")

        return thumbnail_paths

    except Exception as e:
        print(f"Error generating thumbnails for {image_path}: {e}")
        return []


def delete_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)


def convert_webp(image_path):
    try:
        with Image(filename=image_path) as img:
            print(f"file path: {image_path}")
            basename = os.path.basename(image_path)
            name_without_extension = os.path.splitext(basename)[0]

            print(f"File Name: {basename}")
            if img.format == "jpeg":
                pim = PILImage.open(image_path)
                quality = get_jpg_quality(pim)
                print(f"Quality: {quality}")
            else:
                quality = 100
            img = resize_image(img, quality)
            ## Get image dimensions
            img.format = "webp"
            img.save(filename="output/" + name_without_extension + ".webp")

            print(f"Processed: {image_path}")

    except Exception as e:
        print(f"Error processing {image_path}: {e}")


def add_watermark_and_convert(image_path):
    try:
        with Image(filename=image_path) as img:
            print(f"file path: {image_path}")
            basename = os.path.basename(image_path)
            name_without_extension = os.path.splitext(basename)[0]
            extension = image_path.rsplit(".", 1)[1].lower()

            print(f"File Name: {basename}")
            if img.format == "jpeg":
                pim = PILImage.open(image_path)
                quality = get_jpg_quality(pim)
                print(f"Quality: {quality}")
            else:
                quality = 100
            img = resize_image(img, quality)
            ## Get image dimensions
            pic_width = img.width
            pic_height = img.height

            # Calculate watermark dimensions (adjust as needed)
            watermark_height = int(0.05 * pic_width)
            watermark_width = int(5 * pic_width / 15)

            # Create watermark
            with Drawing() as draw:
                draw.fill_color = Color("white")
                draw.font_size = int(
                    watermark_height / 1.5
                )  # Adjust font size if needed
                draw.text_alignment = "center"
                draw.gravity = "center"  # Center the watermark
                draw.text(
                    int(watermark_width / 2),
                    int(watermark_height / 1.4),
                    "TheCopierParts.com",
                )
                with Image(
                    width=watermark_width,
                    height=watermark_height,
                    background=Color("#0006"),
                ) as watermark:
                    draw(watermark)
                    img.composite(
                        watermark,
                        left=int((pic_width - watermark_width) / 2),
                        top=int((pic_height - watermark_height) / 2),
                    )
            # img.format = "jpg"
            # img.save(filename="output/" + name_without_extension + ".jpg")
            img.save(filename="output/" + name_without_extension + "." + extension)
            img.format = "webp"
            img.save(
                filename="output/" + name_without_extension + "." + extension + ".webp"
            )

            print(f"Processed: {image_path}")

    except Exception as e:
        print(f"Error processing {image_path}: {e}")


def upload_to_r2_cloudflare(
    endpoint_url,
    access_key_id,
    secret_key,
    region_name,
    remote_folder,
    local_file,
    remote_key=None,
):
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_key,
        region_name=region_name,
    )

    file_name = os.path.basename(local_file)
    if remote_key is None:
        remote_key = file_name

    file_size = os.path.getsize(local_file)
    print(f"File Name: {Fore.GREY}{file_name}{Fore.RESET}")
    print(
        f"File Size: {Fore.MAGENTA}{round(file_size / 1024 / 1024, 2)} MB{Fore.RESET}"
    )

    with tqdm(
        total=file_size,
        unit="B",
        unit_scale=True,
        desc=f"Uploading {file_name} to R2",
        ascii=True,
    ) as pbar:
        with open(local_file, "rb") as f:
            s3.upload_fileobj(
                f, remote_folder, remote_key, Callback=lambda x: pbar.update(x)
            )


def delete_from_r2_cloudflare(
    endpoint_url, access_key_id, secret_key, region_name, remote_folder, file_name
):
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_key,
            region_name=region_name,
        )

        # Check if file exists first
        try:
            s3.head_object(Bucket=remote_folder, Key=file_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return {
                    "success": False,
                    "message": f"File '{file_name}' not found in bucket '{remote_folder}'",
                }
            else:
                return {"success": False, "message": f"Error checking file: {str(e)}"}

        # If file exists, delete it
        s3.delete_object(Bucket=remote_folder, Key=file_name)
        return {
            "success": True,
            "message": f"Successfully deleted '{file_name}' from bucket '{remote_folder}'",
        }

    except ClientError as e:
        return {"success": False, "message": f"AWS Error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}


# Usage example:
# result = delete_from_r2_cloudflare(
#    endpoint_url="https://your-endpoint.r2.cloudflarestorage.com",
#    access_key_id="your_access_key",
#    secret_key="your_secret_key",
#    region_name="auto",
#    remote_folder="your-bucket",
#    file_name="path/to/file.txt"
# )
#
# if result['success']:
#    print(result['message'])
# else:
#    print(f"Error: {result['message']}")


@app.route("/check_file_exists", methods=["GET"])
def check_file_exists():
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    # data = request.get_json()
    # file = data.get("filename")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    """
    Check if a file exists in a specified bucket.
    
    Query Parameters:
    - filename: Name of the file to check
    - bucket: Name of the bucket to check (optional, defaults to PUBLIC_BUCKET)
    
    Returns:
    JSON response with file existence status
    """
    # Get query parameters
    filename = request.args.get("filename")
    bucket = request.args.get("bucket", PUBLIC_BUCKET)

    # Validate input
    if not filename:
        return jsonify({"error": "Filename is required"}), 400

    try:
        # Create S3 client
        s3_client = boto3.client(
            "s3",
            endpoint_url=CF_ENDPOINT,
            aws_access_key_id=CF_ACCESS_KEY,
            aws_secret_access_key=CF_SECRET_KEY,
        )

        # Check if file exists
        try:
            s3_client.head_object(Bucket=bucket, Key=filename)
            return (
                jsonify({"exists": True, "filename": filename, "bucket": bucket}),
                200,
            )
        except s3_client.exceptions.ClientError as e:
            # If a 404 error is raised, the file does not exist
            if e.response["Error"]["Code"] == "404":
                return (
                    jsonify({"exists": False, "filename": filename, "bucket": bucket}),
                    404,
                )
            # If it's another type of error, raise it
            raise

    except Exception as e:
        # Log the error for debugging
        print(f"Error checking file existence: {str(e)}")
        return (
            jsonify({"error": "Failed to check file existence", "details": str(e)}),
            500,
        )


if __name__ == "__main__":
    app.run(debug=True)
