"""
Agent wrapper - minimal implementation of plan_mcp_agent functionality.
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


def load_mcp_config_from_file(config_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Load MCP server configuration from a JSON file.

    Args:
        config_path: Path to JSON configuration file

    Returns:
        Dictionary of server configurations
    """
    path = Path(config_path)
    if not path.exists():
        return {}

    with open(path, 'r') as f:
        config = json.load(f)

    return config.get('mcpServers', {})


class MCPClientManager:
    """Manages MCP connections."""

    def __init__(self, server_configs: Optional[Dict[str, Dict[str, Any]]] = None):
        self.server_configs = server_configs or {}
        self.client: Optional[MultiServerMCPClient] = None
        self._tools: List[BaseTool] = []

    async def initialize(self, timeout_per_server: int = 10):
        """Initialize MCP servers."""
        if not self.server_configs:
            print("No MCP servers configured.")
            return

        try:
            # Create client directly without testing individual servers
            self.client = MultiServerMCPClient(self.server_configs)

            # Get tools with timeout
            self._tools = await asyncio.wait_for(
                self.client.get_tools(),
                timeout=timeout_per_server * len(self.server_configs)
            )

            print(f"✓ Connected to {len(self.server_configs)} MCP server(s)")
            print(f"✓ Loaded {len(self._tools)} MCP tools")

        except asyncio.TimeoutError:
            print(f"⚠ MCP initialization timed out")
            self._tools = []
        except Exception as e:
            print(f"⚠ MCP initialization failed: {str(e)[:100]}")
            self._tools = []

    async def get_tools(self) -> List[BaseTool]:
        """Get all MCP tools."""
        if not self._tools and self.client:
            self._tools = await self.client.get_tools()
        return self._tools

    async def close(self):
        """Close connections."""
        if self.client:
            try:
                # As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient
                # no longer supports context manager protocol.
                # The client manages sessions internally, so we just clear references.
                await asyncio.sleep(0.1)
            except:
                pass
            finally:
                self.client = None
                self._tools = []


class SimplePlanMCPAgent:
    """
    Simplified agent for letter generation.
    Uses LLM + MCP tools without complex planning graph.
    """

    def __init__(
        self,
        model: str = "deepseek:deepseek-chat",
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        max_iterations: int = 10,
        shared_mcp_manager: Optional["MCPClientManager"] = None
    ):
        load_dotenv()

        self.model_name = model
        self.mcp_config = mcp_config
        self.max_iterations = max_iterations
        self.owns_mcp_manager = shared_mcp_manager is None

        # Initialize LLM
        provider, model_id = model.split(":", 1) if ":" in model else ("deepseek", model)
        api_key = os.getenv("DEEPSEEK_API_KEY")

        self.llm = ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url="https://api.deepseek.com",
            temperature=0.3
        )

        # Use shared MCP manager or create new one
        if shared_mcp_manager:
            self.mcp_manager = shared_mcp_manager
        else:
            self.mcp_manager = MCPClientManager(mcp_config)

        self.tools: List[BaseTool] = []

    async def initialize(self):
        """Initialize the agent."""
        # Only initialize MCP if we own it
        if self.owns_mcp_manager:
            print("🔧 Initializing agent...")
            await self.mcp_manager.initialize()

        self.tools = await self.mcp_manager.get_tools()

        if self.owns_mcp_manager:
            print(f"✓ Agent ready with {len(self.tools)} tools")

    async def run(self, task: str) -> Dict[str, Any]:
        """
        Execute a task using the LLM with tools.

        Args:
            task: Task description

        Returns:
            Result dictionary
        """
        try:
            from langchain_core.messages import HumanMessage, ToolMessage

            # Bind tools to LLM
            llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm

            messages = [HumanMessage(content=task)]
            iteration = 0

            while iteration < self.max_iterations:
                iteration += 1

                # Get LLM response
                response = await llm_with_tools.ainvoke(messages)
                messages.append(response)

                # Check if LLM wants to use tools
                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                    # No more tools to call, we're done
                    return {
                        "final_result": response.content,
                        "status": "success"
                    }

                # Execute tools
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    # Log MCP call
                    print(f"🔧 Calling MCP: {tool_name}")

                    # Find and execute tool
                    tool = next((t for t in self.tools if t.name == tool_name), None)

                    if not tool:
                        tool_result = f"Error: Tool '{tool_name}' not found"
                    else:
                        try:
                            if hasattr(tool, "ainvoke"):
                                tool_result = await tool.ainvoke(tool_args)
                            else:
                                tool_result = tool.invoke(tool_args)
                        except Exception as e:
                            tool_result = f"Error executing tool: {str(e)}"

                    messages.append(ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"]
                    ))

            # Max iterations reached
            return {
                "final_result": "Max iterations reached",
                "status": "partial",
                "error": "Agent exceeded maximum iterations"
            }

        except Exception as e:
            return {
                "final_result": "",
                "status": "error",
                "error": str(e)
            }

    async def close(self):
        """Clean up resources. Only closes MCP if we own it."""
        if self.owns_mcp_manager:
            await self.mcp_manager.close()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
