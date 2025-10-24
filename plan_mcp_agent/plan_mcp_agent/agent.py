"""
Main Agent class - brings together MCP, tools, and planning graph.
"""

import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool

from .mcp.client import MCPClientManager
from .tools.os_tools import get_all_os_tools
from .graph import PlanExecuteGraph


class PlanMCPAgent:
    """
    Main agent class combining planning, tools, and MCP.
    Similar to Claude Desktop but with explicit planning.
    """

    def __init__(
        self,
        model: str = "anthropic:claude-3-5-sonnet-20241022",
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        api_key: Optional[str] = None,
        max_iterations: int = 20,
        enable_os_tools: bool = True
    ):
        """
        Initialize the agent.

        Args:
            model: Model identifier (format: "provider:model-name")
                   Supported providers:
                   - anthropic: claude-3-5-sonnet-20241022, etc.
                   - openai: gpt-4, gpt-3.5-turbo, etc.
                   - deepseek: deepseek-chat, deepseek-coder, etc.
            mcp_config: MCP server configuration
            api_key: API key (or set via environment variables)
            max_iterations: Maximum execution iterations
            enable_os_tools: Whether to enable OS tools
        """
        load_dotenv()

        self.model_name = model
        self.mcp_config = mcp_config
        self.max_iterations = max_iterations
        self.enable_os_tools = enable_os_tools

        # Initialize LLM
        self.llm = self._initialize_llm(model, api_key)

        # Initialize components
        self.mcp_manager = MCPClientManager(mcp_config)
        self.tools: List[BaseTool] = []
        self.graph: Optional[PlanExecuteGraph] = None

    def _initialize_llm(self, model: str, api_key: Optional[str]):
        """Initialize the language model."""
        provider, model_id = model.split(":", 1) if ":" in model else ("anthropic", model)

        if provider == "anthropic":
            api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            return ChatAnthropic(
                model=model_id,
                api_key=api_key,
                temperature=0
            )
        elif provider == "openai":
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            return ChatOpenAI(
                model=model_id,
                api_key=api_key,
                temperature=0
            )
        elif provider == "deepseek":
            api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
            return ChatOpenAI(
                model=model_id,
                api_key=api_key,
                base_url="https://api.deepseek.com",
                temperature=0
            )
        else:
            raise ValueError(f"Unsupported model provider: {provider}. Use 'anthropic', 'openai', or 'deepseek'")

    async def initialize(self):
        """Initialize the agent - must be called before use."""
        print("🔧 Initializing PlanMCP Agent...")

        # Get OS tools
        if self.enable_os_tools:
            self.tools.extend(get_all_os_tools())
            print(f"✓ Loaded {len(self.tools)} OS tools")

        # Initialize MCP
        await self.mcp_manager.initialize()
        mcp_tools = await self.mcp_manager.get_tools()
        self.tools.extend(mcp_tools)

        if mcp_tools:
            print(f"✓ Loaded {len(mcp_tools)} MCP tools")

        # Create planning graph
        self.graph = PlanExecuteGraph(
            self.llm,
            self.tools,
            max_iterations=self.max_iterations
        )

        print(f"✓ Agent initialized with {len(self.tools)} total tools")
        print(f"  Model: {self.model_name}")
        print(f"  Max iterations: {self.max_iterations}")

    async def run(self, objective: str) -> dict:
        """
        Execute a task using plan-and-execute approach.

        Args:
            objective: The task description

        Returns:
            Execution results
        """
        if not self.graph:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        return await self.graph.run(objective)

    async def close(self):
        """Clean up resources."""
        await self.mcp_manager.close()

    def list_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self.tools]

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
