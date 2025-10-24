#!/usr/bin/env bash
set -euo pipefail

# Simple script to run the agent with a query
# Usage:
#   ./scripts/run.sh "Your query here"
#   ./scripts/run.sh path/to/query.txt
#
# Flags via env:
#   USE_MCP=1 ./scripts/run.sh "..."   # enable MCP loading (disabled by default)
#   DEFAULT_MODEL=provider:model ./scripts/run.sh "..."

# Check if query is provided
if [ "${1-}" = "" ]; then
  echo "Usage: $0 \"Your query here\" OR $0 path/to/query.txt"
  echo "Example: $0 \"Search for AI news and summarize it\""
  echo "Example: $0 tasks/my_task.txt"
  exit 1
fi

# Get the script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load .env if present
if [ -f .env ]; then
  set +o allexport
  set -o allexport
  # shellcheck disable=SC1091
  source .env || true
  set +o allexport
fi

# Determine Python to use: prefer local venv, else uv, else system python
if [ -x .venv/bin/python ]; then
  PYTHON=".venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  PYTHON="uv run python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

# Resolve query: file content or raw string
if [ -f "$1" ]; then
  echo "📄 Reading query from file: $1"
  QUERY=$(cat "$1")
  if [ -z "$QUERY" ]; then
    echo "Error: File is empty"
    exit 1
  fi
else
  QUERY="$1"
fi

# Create a temporary Python script to run the agent (safer defaults)
TMP_SCRIPT="/tmp/run_agent_temp_$$.py"
cat > "$TMP_SCRIPT" << 'EOF'
import asyncio
import os
import sys
from dotenv import load_dotenv
from plan_mcp_agent.agent import PlanMCPAgent
from plan_mcp_agent.mcp.client import load_mcp_config_from_file


async def main():
    load_dotenv()

    # Get query from command line
    query = sys.argv[1] if len(sys.argv) > 1 else "Hello, what can you do?"

    # Respect env model or default
    model = os.getenv("DEFAULT_MODEL", "anthropic:claude-3-5-sonnet-20241022")

    # Load MCP only if explicitly enabled
    use_mcp = os.getenv("USE_MCP", "0").lower() in {"1", "true", "yes"}
    mcp_config = {}
    if use_mcp:
        try:
            mcp_config = load_mcp_config_from_file("mcp_config.json")
            print(f"✓ Loaded {len(mcp_config)} MCP servers")
        except Exception as e:
            print(f"⚠ Could not load MCP config: {e}")

    # Create agent
    agent = PlanMCPAgent(
        model=model,
        mcp_config=mcp_config if use_mcp else None,
        max_iterations=20,
        executor_max_iterations=40,
    )

    try:
        print("Initializing agent...")
        await asyncio.wait_for(agent.initialize(), timeout=60)

        print(f"\n🎯 Query: {query}")
        print("=" * 80 + "\n")

        # Run the query with a guard timeout to avoid hanging
        result = await asyncio.wait_for(agent.run(query), timeout=300)

        print("\n" + "=" * 80)
        print("📊 Results:")
        print("=" * 80)

        if result.get("plan"):
            for step in result["plan"].steps:
                print(f"\n✓ Step {step.id}: {step.description}")
                if step.status == "completed" and step.result:
                    preview = step.result[:200] + "..." if len(step.result) > 200 else step.result
                    print(f"  → {preview}")

        if result.get("final_result"):
            print(f"\n✅ Final Result:\n{result['final_result']}")

    except asyncio.TimeoutError:
        print("\n✗ Operation timed out. Consider enabling fewer MCP servers or checking API keys/network.")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise SystemExit(1)
    finally:
        try:
            await agent.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
EOF

# Run the temporary script with the query
eval "$PYTHON" "$TMP_SCRIPT" "$QUERY"

# Clean up
rm -f "$TMP_SCRIPT"
