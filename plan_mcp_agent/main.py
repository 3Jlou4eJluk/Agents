"""
Main entry point for PlanMCP Agent.
Run interactive tasks or use as a CLI tool.
"""

import asyncio
import sys
from plan_mcp_agent.agent import PlanMCPAgent


async def main():
    """Main function."""

    print("""
╔══════════════════════════════════════════════════════════╗
║         PlanMCP Agent - Claude Desktop Alternative       ║
║         LangGraph + Planning + MCP + OS Tools           ║
╚══════════════════════════════════════════════════════════╝
    """)

    # Get objective from command line or use interactive mode
    if len(sys.argv) > 1:
        objective = " ".join(sys.argv[1:])
    else:
        print("Enter your objective (or 'quit' to exit):")
        objective = input("> ").strip()

        if objective.lower() in ['quit', 'exit', 'q']:
            return

    # Create and run agent
    async with PlanMCPAgent(
        model="anthropic:claude-3-5-sonnet-20241022",
        max_iterations=20
    ) as agent:
        await agent.run(objective)


if __name__ == "__main__":
    asyncio.run(main())
