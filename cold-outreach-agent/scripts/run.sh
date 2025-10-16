#!/bin/bash
# Lead Pipeline Runner Script

# Load .env file if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env"
    export $(grep -v '^#' .env | xargs)
fi

# Default values
INPUT_FILE="data/leads.csv"
OUTPUT_FILE="data/results.json"
PROMPT_FILE=""
CUSTOM_PROMPT=""

# Show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -i, --input FILE          Input CSV file (default: data/leads.csv)"
    echo "  -o, --output FILE         Output JSON file (default: data/results.json)"
    echo "  -p, --prompt TEXT         Custom prompt text"
    echo "  -f, --prompt-file FILE    File containing custom prompt"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Environment variables required:"
    echo "  DEEPSEEK_API_KEY         DeepSeek API key"
    echo "  BRIGHT_DATA_API_KEY      Bright Data API key"
    echo ""
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--input)
            INPUT_FILE="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -p|--prompt)
            CUSTOM_PROMPT="$2"
            shift 2
            ;;
        -f|--prompt-file)
            PROMPT_FILE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Check environment variables
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "Error: DEEPSEEK_API_KEY environment variable is not set"
    exit 1
fi

if [ -z "$BRIGHT_DATA_API_KEY" ]; then
    echo "Error: BRIGHT_DATA_API_KEY environment variable is not set"
    exit 1
fi

# Check input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file not found: $INPUT_FILE"
    exit 1
fi

# Build Python command
CMD="python src/run.py --input \"$INPUT_FILE\" --output \"$OUTPUT_FILE\""

if [ -n "$PROMPT_FILE" ]; then
    CMD="$CMD --prompt-file \"$PROMPT_FILE\""
elif [ -n "$CUSTOM_PROMPT" ]; then
    CMD="$CMD --prompt \"$CUSTOM_PROMPT\""
fi

# Run the pipeline
echo "Starting Lead Pipeline..."
echo "Input: $INPUT_FILE"
echo "Output: $OUTPUT_FILE"
echo ""

eval $CMD
