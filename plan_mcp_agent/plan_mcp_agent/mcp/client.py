"""
MCP Client Manager for connecting to multiple MCP servers.
Based on langchain-mcp-adapters.
"""

import asyncio
from typing import Dict, List, Optional, Any
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool


class MCPClientManager:
    """
    Manages connections to multiple MCP servers and provides unified tool access.

    Example:
        >>> config = {
        ...     "filesystem": {
        ...         "command": "npx",
        ...         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        ...         "transport": "stdio"
        ...     }
        ... }
        >>> manager = MCPClientManager(config)
        >>> await manager.initialize()
        >>> tools = await manager.get_tools()
    """

    def __init__(self, server_configs: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize MCP Client Manager.

        Args:
            server_configs: Dictionary of server configurations.
                Each key is the server name, value is config dict with:
                - command: Command to run the server
                - args: List of arguments
                - transport: "stdio" or "streamable_http"
                - url: (for HTTP) Server URL
        """
        self.server_configs = server_configs or {}
        self.client: Optional[MultiServerMCPClient] = None
        self._tools: List[BaseTool] = []

    async def initialize(self, timeout_per_server: int = 10):
        """
        Initialize connection to all configured MCP servers.

        Args:
            timeout_per_server: Timeout in seconds for each server initialization
        """
        if not self.server_configs:
            print("No MCP servers configured. Running without MCP tools.")
            return

        # Try to initialize servers individually to isolate failures
        working_servers = {}
        failed_servers = []

        for server_name, server_config in self.server_configs.items():
            try:
                # Test each server individually with timeout
                async def test_server():
                    test_client = MultiServerMCPClient({server_name: server_config})
                    await test_client.get_tools()
                    return True

                await asyncio.wait_for(test_server(), timeout=timeout_per_server)
                working_servers[server_name] = server_config
                print(f"✓ Successfully connected to {server_name}")
            except asyncio.TimeoutError:
                failed_servers.append(server_name)
                print(f"✗ Failed to connect to {server_name}: timeout after {timeout_per_server}s")
            except Exception as e:
                failed_servers.append(server_name)
                print(f"✗ Failed to connect to {server_name}: {str(e)[:100]}")

        # Initialize with working servers only
        if working_servers:
            try:
                self.client = MultiServerMCPClient(working_servers)
                self._tools = await self.client.get_tools()
                print(f"\n✓ Successfully connected to {len(working_servers)}/{len(self.server_configs)} MCP server(s)")
                print(f"✓ Loaded {len(self._tools)} tools from MCP servers")

                if failed_servers:
                    print(f"\n⚠ Failed servers ({len(failed_servers)}): {', '.join(failed_servers)}")
            except Exception as e:
                print(f"Error initializing working servers: {e}")
                self._tools = []
        else:
            print("⚠ No MCP servers could be initialized")
            self._tools = []

    async def get_tools(self) -> List[BaseTool]:
        """
        Get all available tools from connected MCP servers.

        Returns:
            List of LangChain tools
        """
        if not self._tools and self.client:
            self._tools = await self.client.get_tools()
        return self._tools

    def get_tool_names(self) -> List[str]:
        """Get names of all available MCP tools."""
        return [tool.name for tool in self._tools]

    async def close(self):
        """Close all MCP server connections."""
        if self.client:
            # MultiServerMCPClient handles cleanup automatically
            self.client = None
            self._tools = []


def load_mcp_config_from_file(config_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load MCP server configuration from a JSON file.

    Args:
        config_path: Path to JSON configuration file

    Returns:
        Dictionary of server configurations
    """
    import json
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        return {}

    with open(path, 'r') as f:
        config = json.load(f)

    return config.get('mcpServers', {})
