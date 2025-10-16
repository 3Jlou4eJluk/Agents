"""Test MCP connection directly."""
import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_mcp():
    """Test connecting to Bright Data MCP server."""
    api_token = os.getenv("API_TOKEN") or "31fa7760465a064bd08bec7c86424078128942e4a77b1e61d007aa6d5f4bd443"

    print(f"Testing MCP connection with API_TOKEN: {api_token[:20]}...")

    env = os.environ.copy()
    env["API_TOKEN"] = api_token

    server_params = StdioServerParameters(
        command="npx",
        args=["@brightdata/mcp"],
        env=env
    )

    print("Creating stdio_client...")

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            print("✓ stdio_client connected")

            print("Creating ClientSession...")
            session = ClientSession(read_stream, write_stream)

            print("Initializing session...")
            await session.initialize()

            print("✓ Session initialized!")

            # List available tools
            print("\nListing available tools...")
            tools = await session.list_tools()
            print(f"Available tools: {tools}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_mcp())
