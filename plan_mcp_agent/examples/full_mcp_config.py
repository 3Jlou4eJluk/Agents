"""
Example with full MCP server configuration.
Demonstrates connecting to multiple MCP servers with all available integrations.
"""

import asyncio
from plan_mcp_agent.agent import PlanMCPAgent
from plan_mcp_agent.mcp.client import load_mcp_config_from_file


async def main():
    """Run example with full MCP server configuration."""

    # Load MCP configuration from file
    mcp_config = load_mcp_config_from_file("mcp_config.json")

    print(f"Loaded {len(mcp_config)} MCP servers:")
    for server_name in mcp_config.keys():
        print(f"  - {server_name}")

    # Create agent with MCP
    agent = PlanMCPAgent(
        model="deepseek:deepseek-chat",  # Using DeepSeek model
        mcp_config=mcp_config,
        max_iterations=30
    )

    # Initialize
    print("\nInitializing agent and connecting to MCP servers...")
    await agent.initialize()

    # Example task that can use various MCP tools
    objective = """
    Search for recent news about AI agents using Brave Search,
    then summarize the top 3 most interesting findings.
    """

    print(f"\n🎯 Objective: {objective}")
    print("\n" + "="*80)

    result = await agent.run(objective)

    # Display results
    print("\n📊 Execution Results:")
    print("="*80)

    if result["plan"]:
        for step in result["plan"].steps:
            print(f"\n📍 Step {step.id}: {step.description}")
            print(f"   Status: {step.status}")
            if step.tool:
                print(f"   Tool: {step.tool}")
            if step.result:
                result_preview = step.result[:300] + "..." if len(step.result) > 300 else step.result
                print(f"   Result: {result_preview}")

    if result.get("final_result"):
        print(f"\n✅ Final Result:\n{result['final_result']}")

    # Cleanup
    await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
