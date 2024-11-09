# thecopierparts-img-uploader

## Usage

### Upload images

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
