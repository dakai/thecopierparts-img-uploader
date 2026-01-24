#!/bin/bash
# Quick migration execution script

set -e  # Exit on error

echo "========================================="
echo "  Image Migration - Quick Start"
echo "========================================="
echo ""

# Check Python version
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Check dependencies
echo ""
echo "Checking dependencies..."
python -c "import boto3; import wand.image; import PIL; from dotenv import load_dotenv" 2>/dev/null && echo "✓ All dependencies installed" || {
    echo "✗ Missing dependencies. Install with:"
    echo "  pip install boto3 python-dotenv wand pillow"
    exit 1
}

# Check environment
echo ""
echo "Checking environment variables..."
if [ ! -f .env ]; then
    echo "✗ .env file not found"
    exit 1
fi

source .env
if [ -z "$CF_ENDPOINT" ] || [ -z "$CF_ACCESS_KEY" ] || [ -z "$CF_SECRET_KEY" ]; then
    echo "✗ Missing CF_ENDPOINT, CF_ACCESS_KEY, or CF_SECRET_KEY in .env"
    exit 1
fi
echo "✓ Environment variables configured"

# Check disk space
echo ""
echo "Checking disk space..."
available=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$available" -lt 20 ]; then
    echo "⚠ Warning: Less than 20GB free space (${available}GB available)"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ Sufficient disk space (${available}GB available)"
fi

echo ""
echo "========================================="
echo "  Select Migration Mode"
echo "========================================="
echo ""
echo "1) Dry Run (recommended first step)"
echo "2) Pilot Run (process 10 files)"
echo "3) Full Migration"
echo "4) Resume Previous Migration"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "Running DRY RUN..."
        echo "This will scan all files and show what would be processed."
        echo ""
        python migrate_images.py --dry-run
        ;;
    2)
        echo ""
        echo "Running PILOT with 10 files..."
        echo "⚠ This will make actual changes!"
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            python migrate_images.py --limit 10
            echo ""
            echo "✓ Pilot complete. Manually verify results before full migration."
        fi
        ;;
    3)
        echo ""
        echo "⚠ WARNING: Full migration will process ALL files"
        read -p "Are you sure? Type 'YES' to continue: " confirm
        if [ "$confirm" = "YES" ]; then
            echo ""
            echo "Starting full migration..."
            echo "You can safely Ctrl+C and resume later."
            python migrate_images.py
        else
            echo "Cancelled."
        fi
        ;;
    4)
        echo ""
        echo "Resuming previous migration..."
        python migrate_images.py
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "========================================="
echo "  Migration Complete"
echo "========================================="
echo ""
echo "Check logs:"
echo "  - migration_*.log (detailed operation log)"
echo "  - migration_state.json (progress and stats)"
echo ""
