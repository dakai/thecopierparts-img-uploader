# thecopierparts-img-uploader

## Usage

### Upload images and files

- The file name will be altted according to different bucket name:

1. Bucket name: `PUBLIC_BUCKET`, image files only

   - The file will be renamed to 7 random characters name and stored in converted jpg and web format with watermarked
   - the file will be stored in `PRIVATE_BUCKET` bucket with same alterd filename but without watermark and in original format

2. Bucket name: `PRIVATE_BUCKET`, image files only

   - The file will be renamed to 7 random characters name and stored in its original format and size

3. Bucket name: others
   - The file will be renamed to additioanal 4 random characters to avoid replacing the files with the same name

```
curl -X POST https://url/upload \
  -F "file=@file_name" \
-F "bucket=bucket_name" -H "Authorization: Bearer token"

```

### Delete a file

```
curl -X POST -H "Content-Type: application/json" \
-H "Authorization: Bearer token" \
-d '{"filename": "filename", "bucket":"bucketname"}' http://url/delete

```

### List files

```
curl -H "Authorization: Bearer token" https://url/list \
-H "Content-Type: application/json" \
-d '{"bucket":"bucketname"}'
```

### Fetch a file

```
curl -X POST -H "Authorization: Bearer token" \
-H "Content-Type: application/json" \
-d '{"bucket": "bucketname", "filename": "filename"}' \
https://url/fetch --output downloaded_file.jpg
```

### Upload files without altering any names

```
curl -X POST https://url/upload_original \
  -F "file=@file_name" \
-F "bucket=bucket_name" -H "Authorization: Bearer token"

`
```
