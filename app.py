import os
from typing import List
from dotenv import load_dotenv
from cloudflare import Cloudflare

load_dotenv()

CF_API_TOKEN = os.getenv("CF_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_ACCESS_KEY = os.getenv("CF_ACCESS_KEY")
CF_SECRET_KEY = os.getenv("CF_SECRET_KEY")
CF_ENDPOINT = os.getenv("CF_ENDPOINT")
# BUCKET_NAME = os.getenv("BUCKET_NAME")

# R2 bucket details
BUCKET_NAME = "your_public_bucket"


# def upload_files_to_r2(file_paths: List[str]):
#    """Uploads a list of files to Cloudflare R2 storage.
#
#    Args:
#        file_paths: A list of absolute paths to the files to upload.
#    """
#
#    cf = Cloudflare(token=CF_API_TOKEN)
#
#    for file_path in file_paths:
#        try:
#            with open(file_path, "rb") as f:
#                file_content = f.read()
#
#            file_name = os.path.basename(file_path)
#            response = cf.accounts.r2.namespaces.objects.put(
#                account_id=CF_ACCOUNT_ID,
#                namespace_id=BUCKET_NAME,
#                name=file_name,
#                data=file_content,
#            )
#
#            print(f"Uploaded '{file_name}' successfully. Response: {response}")
#
#        except Exception as e:
#            print(f"Error uploading '{file_name}': {e}")
#
#
# if __name__ == "__main__":
#    # Example usage:
#    files_to_upload = [
#        j"/path/to/file1.txt",
#        "/path/to/file2.jpg",
#        "/path/to/file3.pdf",
#    ]
#
#    upload_files_to_r2(files_to_upload)

# https://gist.github.com/Pymmdrza/3e3f30b16f4009503e7572b914fd200d
# install package's from requirements.txt
# Windows : pip install -r requirements.txt
# Linux : pip3 install -r requirements.txt
import os
import boto3
from tqdm import tqdm
from colorthon import Colors as Fore


def get_user_input(prompt, example=""):
    user_input = input(
        f"{Fore.GREEN}{prompt}{Fore.RESET} [{Fore.GREY}e.x: {example}{Fore.RESET}]: "
    ).strip()
    return user_input


def validate_input(input_value, expected_length, message):
    if not input_value or len(input_value) != expected_length:
        print(f"\n{Fore.RED}{message} Exiting...{Fore.RESET}")
        exit(1)


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

    upload_to_r2_cloudflare(
        endpoint_url, access_key, secret_key, reg_name, remote_folder, file_path
    )


if __name__ == "__main__":
    main()
