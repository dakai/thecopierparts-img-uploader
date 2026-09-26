#!/bin/bash
# Quick optimization execution script

set -e  # Exit on error

echo "========================================="
echo "  Thumbnail Optimization - Quick Start"
echo "========================================="
echo ""

# Check environment
if [ ! -f .env ]; then
    echo "✗ .env file not found"
    exit 1
fi

source .env

if [ -z "$CF_ENDPOINT" ] || [ -z "$CF_ACCESS_KEY" ] || [ -z "$CF_SECRET_KEY" ]; then
    echo "✗ Missing CF_ENDPOINT, CF_ACCESS_KEY, or CF_SECRET_KEY"
    exit 1
fi
echo "✓ Environment variables configured"

echo ""
echo "========================================="
echo "  Select Optimization Mode"
echo "========================================="
echo ""
echo "1) Dry Run (List oversized files without changes)"
echo "2) Full Optimization (Compress files > 10 KiB)"
echo ""
read -p "Enter choice [1-2]: " choice

case $choice in
    1)
        echo ""
        echo "Running DRY RUN..."
        python3 optimize_thumbnails.py --dry-run
        ;;
    2)
        echo ""
        echo "⚠ WARNING: This will modify files in the PUBLIC bucket!"
        read -p "Are you sure? Type 'YES' to continue: " confirm
        if [ "$confirm" = "YES" ]; then
            echo ""
            echo "Starting optimization..."
            python3 optimize_thumbnails.py
        else
            echo "Cancelled."
        fi
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "========================================="
echo "  Task Complete"
echo "========================================="
