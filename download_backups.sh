#!/bin/bash

# Configuration
API_URL="https://your_api_host"
BUCKET="your_backup_bucket"
PREFIX="your/backup/prefix/"
DOWNLOAD_DIR="downloads/${BUCKET}/${PREFIX}"

# Load SECRET_KEY from .env.local
if [ -f .env.local ]; then
    source .env.local
    API_KEY=$SECRET_KEY
else
    echo "Error: .env.local file not found."
    exit 1
fi

if [ -z "$API_KEY" ]; then
    echo "Error: SECRET_KEY not found in .env.local"
    exit 1
fi

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

if [ -z "$FILES" ]; then
    echo "No files found matching that path."
    exit 0
fi

# Count files
FILE_COUNT=$(echo "$FILES" | wc -l)
echo "Found ${FILE_COUNT} files. Starting download..."

# 2. Fetch each file
CURRENT_FILE=1
for FILE in $FILES; do
    # Get just the filename (after the last /)
    LOCAL_FILENAME=$(basename "$FILE")
    LOCAL_PATH="${DOWNLOAD_DIR}${LOCAL_FILENAME}"

    echo "[${CURRENT_FILE}/${FILE_COUNT}] Downloading: ${LOCAL_FILENAME}..."
    
    # We use a POST to /fetch as implemented in the API
    # Using -f to fail on server errors and -o to save to file
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
    
    ((CURRENT_FILE++))
done

echo ""
echo "All downloads completed. Files are located in: ${DOWNLOAD_DIR}"
