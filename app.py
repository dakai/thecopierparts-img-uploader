import os
import boto3
from tqdm import tqdm
from wand.image import Image
from wand.color import Color
from dotenv import load_dotenv
from wand.drawing import Drawing
from colorthon import Colors as Fore
from PIL import Image as PILImage
from get_jpg_quality import get_jpg_quality

load_dotenv()

CF_API_TOKEN = os.getenv("CF_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
# BUCKET_NAME = os.getenv("BUCKET_NAME")

# R2 bucket details
BUCKET_NAME = "your_public_bucket"


def resize_image(img):
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

    img_buffer = img.make_blob(format="jpeg")  # Or the original format of the image

    # img_compression_quality = get_jpg_quality(img_buffer)
    # print(f"img_compression_quality: {img_compression_quality}")
    img.compression_quality = 80

    return img  # Return resized or original image data


def add_watermark_and_convert(image_path):
    try:
        with Image(filename=image_path) as img:
            pim = PILImage.open(image_path)
            quality = get_jpg_quality(pim)
            print(f"Quality: {quality}")

            img = resize_image(img)
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

            # Save as JPG
            output_filename_jpg = (
                "output/" + image_path
            )  # Keep the original filename for JPG
            img.format = "jpeg"
            img.save(filename=output_filename_jpg)

            # Save as WebP
            output_filename_webp = (
                "output/" + os.path.splitext(image_path)[0] + ".jpg.webp"
            )  # Add .jpg.webp extension
            img.format = "webp"
            img.save(filename=output_filename_webp)

            print(
                f"Processed: {image_path} -> {output_filename_jpg} (JPG), {output_filename_webp} (WebP)"
            )

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
    image_path = "test.jpg"  # Replace with your image path
    add_watermark_and_convert(image_path)


if __name__ == "__main__":
    main()
