#!/bin/bash

# Load configuration from .env
if [ -f .env ]; then
    source .env
else
    echo "Error: .env file not found."
    exit 1
fi

API_URL="${BACKUP_API_URL:?Error: BACKUP_API_URL not set in .env}"
BUCKET="${BACKUP_BUCKET:?Error: BACKUP_BUCKET not set in .env}"
PREFIX="${BACKUP_PREFIX:?Error: BACKUP_PREFIX not set in .env}"
API_KEY="${SECRET_KEY:?Error: SECRET_KEY not set in .env}"
DOWNLOAD_DIR="downloads/${BUCKET}/${PREFIX}"

# Ensure download directory exists
mkdir -p "$DOWNLOAD_DIR"

echo "Connecting to ${API_URL}..."
echo "Listing files in bucket '${BUCKET}' under path '${PREFIX}'..."

# 1. List files with prefix
LIST_RESPONSE=$(curl -s -X POST "${API_URL}/list" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
        \"bucket\": \"${BUCKET}\",
        \"prefix\": \"${PREFIX}\"
    }")

# Check if the list call was successful
if [[ $LIST_RESPONSE == *"error"* ]]; then
    echo "Error from API: $LIST_RESPONSE"
    exit 1
fi

# Extract keys using jq
FILES=$(echo "$LIST_RESPONSE" | jq -r '.objects[].key')

if [ -z "$FILES" ] || [ "$FILES" == "null" ]; then
    echo "No files found matching that path. Skipping synchronization."
    exit 0
fi

# Ensure download directory exists
mkdir -p "$DOWNLOAD_DIR"

# 1. Remove local files that are NOT in the bucket list
echo "Cleaning up local files not present in the bucket..."
# Get list of local filenames
LOCAL_FILES=$(ls "$DOWNLOAD_DIR")

for LOCAL_FILE in $LOCAL_FILES; do
    FOUND=false
    for REMOTE_FILE in $FILES; do
        REMOTE_BASENAME=$(basename "$REMOTE_FILE")
        # Apply the same transformation as we do for downloading
        SAFE_REMOTE_NAME="${REMOTE_BASENAME//:/-}"
        
        if [ "$LOCAL_FILE" == "$SAFE_REMOTE_NAME" ]; then
            FOUND=true
            break
        fi
    done
    
    if [ "$FOUND" = false ]; then
        echo "   Removing outdated local file: ${LOCAL_FILE}"
        rm "${DOWNLOAD_DIR}${LOCAL_FILE}"
    fi
done

# 2. Download missing files
FILE_COUNT=$(echo "$FILES" | wc -l)
echo "Found ${FILE_COUNT} files in bucket. Syncing..."

CURRENT_FILE=1
for FILE in $FILES; do
    REMOTE_BASENAME=$(basename "$FILE")
    # Replace ':' with '-' for the local filename
    LOCAL_FILENAME="${REMOTE_BASENAME//:/-}"
    LOCAL_PATH="${DOWNLOAD_DIR}${LOCAL_FILENAME}"

    if [ -f "$LOCAL_PATH" ]; then
        echo "[${CURRENT_FILE}/${FILE_COUNT}] Skipping: ${LOCAL_FILENAME} (Already exists)"
    else
        echo "[${CURRENT_FILE}/${FILE_COUNT}] Downloading: ${REMOTE_BASENAME} as ${LOCAL_FILENAME}..."
        
        curl -s -f -X POST "${API_URL}/fetch" \
            -H "Authorization: Bearer ${API_KEY}" \
            -H "Content-Type: application/json" \
            -d "{
                \"bucket\": \"${BUCKET}\",
                \"filename\": \"${FILE}\"
            }" \
            -o "$LOCAL_PATH"

        if [ $? -eq 0 ]; then
            echo "   Success: Saved to ${LOCAL_PATH}"
        else
            echo "   Error: Failed to download ${FILE}"
        fi
    fi
    
    ((CURRENT_FILE++))
done

echo ""
echo "All downloads completed. Files are located in: ${DOWNLOAD_DIR}"
