#!/bin/bash

# POV Email Generator - Batch Processing Script

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INPUT_FILE="${1:-leads.json}"
OUTPUT_DIR="${2:-output}"
SUMMARY_FILE="${3:-batch_summary.json}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Set DeepSeek API Key
export DEEPSEEK_API_KEY="sk-808dea4151454f5f86385e7c2d4988bd"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}POV Email Generator - Batch Processor${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
    uv venv
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source .venv/bin/activate

# Install/update dependencies
echo -e "${BLUE}Checking dependencies...${NC}"
uv pip install -e . > /dev/null 2>&1 || {
    echo -e "${RED}✗ Failed to install dependencies${NC}"
    exit 1
}

# Check if input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo -e "${RED}✗ Input file '$INPUT_FILE' not found${NC}"
    echo ""
    echo "Usage: $0 [input_file] [output_dir] [summary_file]"
    echo ""
    echo "Example:"
    echo "  $0 leads.json output batch_summary.json"
    echo ""
    exit 1
fi

# Run batch processor
echo -e "${GREEN}✓ Starting batch processing...${NC}"
echo ""

python batch_main.py "$INPUT_FILE" \
    --output-dir "$OUTPUT_DIR" \
    --summary-file "$SUMMARY_FILE"

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Batch processing completed successfully${NC}"
    echo -e "${GREEN}✓ Results saved to: $OUTPUT_DIR${NC}"
    echo -e "${GREEN}✓ Summary saved to: $SUMMARY_FILE${NC}"
else
    echo ""
    echo -e "${RED}✗ Batch processing completed with errors${NC}"
    exit 1
fi
