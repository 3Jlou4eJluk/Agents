#!/bin/bash

# Simple script to run the agent with a query
# Usage: ./scripts/run.sh "Your query here"

# Check if query is provided
if [ -z "$1" ]; then
    echo "Usage: $0 \"Your query here\""
    echo "Example: $0 \"Search for AI news and summarize it\""
    exit 1
fi

# Get the query from the first argument
QUERY="$1"

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Create a temporary Python script to run the agent
cat > /tmp/run_agent_temp.py << EOF
import asyncio
import sys
from plan_mcp_agent.agent import PlanMCPAgent
from plan_mcp_agent.mcp.client import load_mcp_config_from_file


async def main():
    # Get query from command line
    query = sys.argv[1] if len(sys.argv) > 1 else "Hello, what can you do?"

    # Load MCP configuration
    try:
        mcp_config = load_mcp_config_from_file("mcp_config.json")
        print(f"✓ Loaded {len(mcp_config)} MCP servers")
    except Exception as e:
        print(f"⚠ Could not load MCP config: {e}")
        mcp_config = {}

    # Create agent
    agent = PlanMCPAgent(
        model="deepseek:deepseek-chat",
        mcp_config=mcp_config,
        max_iterations=30
    )

    # Initialize
    print("Initializing agent...")
    await agent.initialize()

    print(f"\n🎯 Query: {query}")
    print("="*80 + "\n")

    # Run the query
    result = await agent.run(query)

    # Display results
    print("\n" + "="*80)
    print("📊 Results:")
    print("="*80)

    if result.get("plan"):
        for step in result["plan"].steps:
            print(f"\n✓ Step {step.id}: {step.description}")
            if step.status == "completed" and step.result:
                preview = step.result[:200] + "..." if len(step.result) > 200 else step.result
                print(f"  → {preview}")

    if result.get("final_result"):
        print(f"\n✅ Final Result:\n{result['final_result']}")

    # Cleanup
    await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
EOF

# Run the temporary script with the query
python /tmp/run_agent_temp.py "$QUERY"

# Clean up
rm /tmp/run_agent_temp.py
