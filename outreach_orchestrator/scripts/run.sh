#!/bin/bash

# Outreach Orchestrator - Simple wrapper script
# Usage: ./scripts/run.sh [options]

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
