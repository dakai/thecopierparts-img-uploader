import os
import boto3
import random
import string
from tqdm import tqdm
from wand.image import Image
from wand.color import Color
from dotenv import load_dotenv
from wand.drawing import Drawing
from colorthon import Colors as Fore
from PIL import Image as PILImage
from get_jpg_quality import get_jpg_quality
from flask import Flask, request, jsonify

load_dotenv()

CF_API_TOKEN = os.getenv("CF_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
# BUCKET_NAME = os.getenv("BUCKET_NAME")
API_KEY = os.getenv("SECRET_KEY")
# R2 bucket details
BUCKET_NAME = "your_public_bucket"

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"  # Folder to store uploaded files
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "tiff"}  # Allowed image extensions


def generate_random_filename(length, extension):
    """Generates a random filename with random placement of letters and numbers."""
    characters = string.ascii_letters + string.digits
    random_part = "".join(random.choice(characters) for _ in range(length))
    return f"{random_part}.{extension}"


def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    while check_if_file_exists(file_path):
        unique_filename = generate_random_filename(6, extension)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    return unique_filename


@app.route("/public", methods=["POST"])
def upload_public_photo():
    # 1. Authentication Check
    # auth_header = request.headers.get("Authorization")
    # if not auth_header or not auth_header.startswith("Bearer "):
    #    return jsonify({"error": "Authentication required"}), 401

    # api_key = auth_header.split("Bearer ")[1]
    # print(api_key)
    # print(API_KEY)
    # if api_key != API_KEY:
    #    return jsonify({"error": "Invalid API key"}), 401

    # try

    files = request.files.getlist("file")
    uploaded_files = []
    if not files:
        return jsonify({"error": "No file part in the request"}), 400

    for file in files:
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        if file and allowed_file(file.filename):
            filename = file.filename
            if not filename == None:
                unique_filename = generate_unique_filename(filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))
                uploaded_files.append(unique_filename)
        else:
            return jsonify({"error": "File type not allowed"}), 400

    return (
        jsonify(
            {"message": "All files uploaded successfully", "files": uploaded_files}
        ),
        201,
    )


@app.route("/private", methods=["POST"])
def upload_private_photo():
    # 1. Authentication Check
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Authentication required"}), 401

    api_key = auth_header.split("Bearer ")[1]
    print(api_key)
    print(API_KEY)
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    # try
    return jsonify({"message": "All files uploaded successfully"}), 201


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

    if width > height and width > 1920:  # Landscape/Horizontal
        img.transform(resize="1920x")
    elif height >= width and height > 1920:  # Portrait/Vertical
        img.transform(resize="x1920")

    if compressed_rate > 80:
        img.compression_quality = 80

    return img  # Return resized or original image data


def add_watermark_and_convert(image_path):
    try:
        with Image(filename=image_path) as img:

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
            img.format = "jpg"
            img.save(filename="output/" + os.path.splitext(image_path)[0] + ".jpg")
            img.format = "webp"
            img.save(filename="output/" + os.path.splitext(image_path)[0] + ".jpg.webp")

            print(f"Processed: {image_path}")

    except Exception as e:
        print(f"Error processing {image_path}: {e}")


# def get_user_input(prompt, example=""):
#    user_input = input(
#        f"{Fore.GREEN}{prompt}{Fore.RESET} [{Fore.GREY}e.x: {example}{Fore.RESET}]: "
#    ).strip()
#    return user_input
#
#
# def validate_input(input_value, expected_length, message):
#    if not input_value or len(input_value) != expected_length:
#        print(f"\n{Fore.RED}{message} Exiting...{Fore.RESET}")
#        exit(1)


def upload_to_r2_cloudflare(
    endpoint_url, access_key_id, secret_key, region_name, remote_folder, local_file
):
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_key,
        region_name=region_name,
    )

    file_name = os.path.basename(local_file)
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
                f, remote_folder, file_name, Callback=lambda x: pbar.update(x)
            )


def main():
    # account_id = CF_ACCOUNT_ID
    access_key = CF_ACCESS_KEY
    secret_key = CF_SECRET_KEY
    # reg_name = get_user_input("REGION NAME (Default: auto)", "auto")
    reg_name = "auto"

    endpoint_url = CF_ENDPOINT

    remote_folder = BUCKET_NAME

    file_path = "test.webp"

    # upload_to_r2_cloudflare(
    #    endpoint_url, access_key, secret_key, reg_name, remote_folder, file_path
    # )

    # Example usage (process a single image):
    image_path = "test.png"  # Replace with your image path
    add_watermark_and_convert(image_path)


if __name__ == "__main__":
    # main()
    app.run(debug=True)
