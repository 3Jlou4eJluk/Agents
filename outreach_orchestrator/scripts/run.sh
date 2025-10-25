#!/bin/bash

# Outreach Orchestrator - Simple wrapper script
# Usage: ./scripts/run.sh [options]
#
# Examples:
#
#   # Basic run with default settings (5 workers, clears database)
#   ./scripts/run.sh --input data/input/leads.csv --output data/output/results.csv
#
#   # Run with 3 workers (recommended for testing)
#   ./scripts/run.sh --input data/input/leads.csv --output data/output/results.csv --workers 3
#
#   # Resume previous run (continues from where it stopped, keeps database)
#   ./scripts/run.sh --resume
#
#   # Custom config file
#   ./scripts/run.sh --input data/input/leads.csv --config config.custom.json
#
#   Note: By default, the database in data/progress.db is cleared on each new run.
#   Use --resume to continue from a previous run without clearing the database.
#
#   # Full example with all options
#   ./scripts/run.sh \
#     --input data/input/leads.csv \
#     --output data/output/results.csv \
#     --workers 5 \
#     --context context \
#     --db data/progress.db \
#     --config config.json
#
# Options:
#   --input, -i     Path to input CSV file with leads (required unless --resume)
#   --output, -o    Path to output CSV file (default: data/output/results.csv)
#   --workers, -w   Number of parallel workers (default: 5, recommended: 3-5)
#   --context, -c   Path to context directory (default: context/)
#   --db            Path to SQLite database (default: data/progress.db)
#   --resume, -r    Resume from previous run
#   --config        Path to config.json file (default: config.json in project root)

# Function to print usage examples
print_usage() {
    echo ""
    echo "Usage: ./scripts/run.sh [options]"
    echo ""
    echo "Examples:"
    echo ""
    echo "  # Basic run with default settings (5 workers, clears database)"
    echo "  ./scripts/run.sh --input data/input/leads.csv --output data/output/results.csv"
    echo ""
    echo "  # Run with 3 workers (recommended for testing)"
    echo "  ./scripts/run.sh --input data/input/leads.csv --output data/output/results.csv --workers 3"
    echo ""
    echo "  # Resume previous run (keeps database)"
    echo "  ./scripts/run.sh --resume"
    echo ""
    echo "  # Custom config file"
    echo "  ./scripts/run.sh --input data/input/leads.csv --config config.custom.json"
    echo ""
    echo "Options:"
    echo "  --input, -i     Path to input CSV file with leads (required unless --resume)"
    echo "  --output, -o    Path to output CSV file (default: data/output/results.csv)"
    echo "  --workers, -w   Number of parallel workers (default: 5, recommended: 3-5)"
    echo "  --context, -c   Path to context directory (default: context/)"
    echo "  --db            Path to SQLite database (default: data/progress.db)"
    echo "  --resume, -r    Resume from previous run (keeps database intact)"
    echo "  --config        Path to config.json file (default: config.json)"
    echo "  --help, -h      Show this help message"
    echo ""
    echo "Note: By default, the database is cleared on each new run."
    echo "      Use --resume to continue from a previous run without clearing."
    echo ""
}

# Check for help flag or no arguments
if [ "$1" == "--help" ] || [ "$1" == "-h" ] || [ $# -eq 0 ]; then
    print_usage
    exit 0
fi

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env not found"
    echo ""
    echo "Please set up your .env file:"
    echo ""
    echo "  cp .env.example .env"
    echo "  # Edit .env with your API keys"
    echo ""
    exit 1
fi

# Check if mcp_config.json exists
if [ ! -f "mcp_config.json" ]; then
    echo "⚠ Warning: mcp_config.json not found"
    echo "MCP tools will not be available"
fi

# Check if context is set up
if [ ! -f "context/GTM.md" ]; then
    echo "❌ Error: context/GTM.md not found"
    echo ""
    echo "Please set up context files:"
    echo "  cp context/GTM.md.example context/GTM.md"
    echo "  cp context/agent_instruction.md.example context/agent_instruction.md"
    echo "  cp context/guides/*.example context/guides/ (remove .example)"
    echo ""
    echo "Then fill out GTM.md with your project details"
    exit 1
fi

# Run with Python
python -m src.run "$@"

# Capture exit code
EXIT_CODE=$?

# If failed, show usage examples
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "💡 Need help? Here are some common usage examples:"
    print_usage
    exit $EXIT_CODE
fi
