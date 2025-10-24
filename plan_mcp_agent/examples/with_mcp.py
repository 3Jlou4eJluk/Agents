"""
Example with MCP server integration.
Demonstrates connecting to MCP servers for extended functionality.
"""

import asyncio
from plan_mcp_agent.agent import PlanMCPAgent


async def main():
    """Run example with MCP servers."""

    # Configure MCP servers
    # Example: filesystem server for accessing files
    mcp_config = {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "transport": "stdio"
        }
        # Add more MCP servers here as needed
        # "weather": {
        #     "url": "http://localhost:8000/mcp",
        #     "transport": "streamable_http"
        # }
    }

    # Create agent with MCP
    agent = PlanMCPAgent(
        model="anthropic:claude-3-5-sonnet-20241022",
        mcp_config=mcp_config,
        max_iterations=20
    )

    # Initialize
    await agent.initialize()

    # Run task that uses both OS and MCP tools
    objective = """
    List all Python files in the current directory,
    read one of them, and create a summary of what it does.
    """

    result = await agent.run(objective)

    # Display results
    print("\n📊 Execution Results:")
    if result["plan"]:
        for step in result["plan"].steps:
            print(f"\nStep {step.id}: {step.description}")
            print(f"Status: {step.status}")
            if step.result:
                print(f"Result: {step.result[:200]}...")

    # Cleanup
    await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
