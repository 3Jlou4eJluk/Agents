"""
Basic usage example of PlanMCP Agent.
Demonstrates simple task execution without MCP.
"""

import asyncio
from plan_mcp_agent.agent import PlanMCPAgent


async def main():
    """Run basic example."""

    # Create agent (no MCP servers, just OS tools)
    agent = PlanMCPAgent(
        model="anthropic:claude-3-5-sonnet-20241022",
        max_iterations=15
    )

    # Initialize
    await agent.initialize()

    # List available tools
    print("\n📦 Available tools:")
    for tool_name in agent.list_tools():
        print(f"  - {tool_name}")

    # Run a simple task
    objective = """
    Create a Python script called hello.py that prints 'Hello from PlanMCP Agent!'
    and then execute it to verify it works.
    """

    result = await agent.run(objective)

    # Show results
    print("\n" + "="*60)
    print("Final Results:")
    print("="*60)

    if result["plan"]:
        for step in result["plan"].steps:
            status_emoji = "✓" if step.status == "completed" else "✗"
            print(f"{status_emoji} Step {step.id}: {step.description}")
            if step.result:
                print(f"  Result: {step.result[:100]}...")

    # Cleanup
    await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
