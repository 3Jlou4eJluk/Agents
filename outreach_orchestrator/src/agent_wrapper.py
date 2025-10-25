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
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from .config_loader import create_llm
from .logger import get_logger

logger = get_logger(__name__)


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
        self.logger = get_logger(__name__)

    async def initialize(self, timeout_per_server: int = 10):
        """Initialize MCP servers."""
        if not self.server_configs:
            self.logger.info("No MCP servers configured.")
            return

        try:
            # Create client directly without testing individual servers
            self.client = MultiServerMCPClient(self.server_configs)

            # Get tools with timeout
            self._tools = await asyncio.wait_for(
                self.client.get_tools(),
                timeout=timeout_per_server * len(self.server_configs)
            )

            self.logger.info(f"✓ Connected to {len(self.server_configs)} MCP server(s)")
            self.logger.info(f"✓ Loaded {len(self._tools)} MCP tools")

        except asyncio.TimeoutError:
            self.logger.warning(f"⚠ MCP initialization timed out")
            self._tools = []
        except Exception as e:
            self.logger.warning(f"⚠ MCP initialization failed: {str(e)[:100]}")
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
        shared_mcp_manager: Optional["MCPClientManager"] = None,
        temperature: float = 0.7,
        config: Optional[Dict[str, Any]] = None,
        model_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize SimplePlanMCPAgent.

        Args:
            model: Legacy format "provider:model" (deprecated, use model_config instead)
            mcp_config: MCP server configuration
            max_iterations: Maximum agent iterations
            shared_mcp_manager: Shared MCP manager instance
            temperature: LLM temperature
            config: Full application config (for provider settings)
            model_config: Model-specific config (provider, model, temperature)
        """
        load_dotenv()

        self.model_name = model
        self.mcp_config = mcp_config
        self.max_iterations = max_iterations
        self.owns_mcp_manager = shared_mcp_manager is None
        self.temperature = temperature
        self.config = config  # Store config for later use (e.g., compression)

        # Initialize LLM
        if config and model_config:
            # New way: use config-based initialization (with rate limiting)
            self.llm = create_llm(config, model_config)
        else:
            # Legacy way: parse model string (backward compatibility)
            # WARNING: This path won't have rate limiting!
            provider, model_id = model.split(":", 1) if ":" in model else ("deepseek", model)

            if provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                base_url = "https://api.openai.com/v1"
            else:  # deepseek
                api_key = os.getenv("DEEPSEEK_API_KEY")
                base_url = "https://api.deepseek.com"

            # Create LLM without rate limiting (legacy mode)
            self.llm = ChatOpenAI(
                model=model_id,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature
            )

            logger.warning("LLM created in legacy mode without rate limiting. Use config + model_config for rate limiting.")

        # Use shared MCP manager or create new one
        if shared_mcp_manager:
            self.mcp_manager = shared_mcp_manager
        else:
            self.mcp_manager = MCPClientManager(mcp_config)

        self.tools: List[BaseTool] = []

        # Auto-compact settings
        if config:
            compact_config = config.get('auto_compact', {})
            self.auto_compact_enabled = compact_config.get('enabled', True)
            self.compact_trigger = compact_config.get('trigger_at_messages', 15)
            self.compact_preserve_last = compact_config.get('preserve_last_messages', 5)
            self.compact_model = compact_config.get('summarization_model', 'gpt-4o-mini')
        else:
            # Defaults if no config
            self.auto_compact_enabled = True
            self.compact_trigger = 15
            self.compact_preserve_last = 5
            self.compact_model = 'gpt-4o-mini'

        # Compression stats
        self.compression_count = 0
        self.messages_before_compression = 0
        self.messages_after_compression = 0

    async def initialize(self):
        """Initialize the agent."""
        # Only initialize MCP if we own it
        if self.owns_mcp_manager:
            logger.info("🔧 Initializing agent...")
            await self.mcp_manager.initialize()

        self.tools = await self.mcp_manager.get_tools()

        if self.owns_mcp_manager:
            logger.info(f"✓ Agent ready with {len(self.tools)} tools")

    async def _compress_context(self, messages: List) -> List:
        """
        Compress middle messages to save context window.

        Preserves:
        - First message (system prompt with task/instructions)
        - Last N messages (current context)

        Compresses:
        - Everything in between (research results, thinking)

        Args:
            messages: Current message list

        Returns:
            Compressed message list
        """
        if len(messages) <= (1 + self.compact_preserve_last):
            # Not enough messages to compress
            return messages

        # Extract parts
        first_msg = messages[0]

        # Calculate split point for last messages
        split_point = -self.compact_preserve_last

        # Check if first message in last_msgs is a ToolMessage
        # If so, we need to include the preceding AIMessage with tool_calls
        last_msgs = messages[split_point:]
        if last_msgs and isinstance(last_msgs[0], ToolMessage):
            # Find the preceding AIMessage with tool_calls
            # Expand the window to include it
            for i in range(len(messages) + split_point - 1, 0, -1):
                if isinstance(messages[i], AIMessage) and hasattr(messages[i], 'tool_calls') and messages[i].tool_calls:
                    # Found the AIMessage with tool_calls, include it
                    split_point = -(len(messages) - i)
                    last_msgs = messages[split_point:]
                    logger.debug(f"Adjusted compression to include AIMessage at position {i} (has tool_calls)")
                    break

        middle_msgs = messages[1:len(messages) + split_point]

        # Build summary prompt
        summary_parts = []
        for msg in middle_msgs:
            if isinstance(msg, ToolMessage):
                # Extract tool name from content or use generic
                tool_name = "tool"
                content_preview = str(msg.content)[:500] if msg.content else "N/A"
                summary_parts.append(f"Tool Result: {content_preview}")
            elif isinstance(msg, AIMessage):
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    tool_names = [tc.get('name', 'unknown') for tc in msg.tool_calls]
                    summary_parts.append(f"AI called: {', '.join(tool_names)}")
                elif msg.content:
                    summary_parts.append(f"AI: {str(msg.content)[:300]}")

        summary_text = "\n\n".join(summary_parts)

        # Create summarization prompt
        summarization_prompt = f"""You are summarizing research and analysis results for context compression.

Extract and preserve ONLY the key findings that are relevant for writing a personalized cold email:

{summary_text}

Provide a concise summary (max 500 words) focusing on:
1. Key facts about the person (recent activities, role, interests)
2. Key facts about the company (stage, challenges, news)
3. Important insights or patterns identified
4. Any rejection signals or red flags

Be specific and preserve actionable details. Remove verbose explanations and redundant information."""

        # Call summarization LLM
        try:
            # Create config for summarization model (uses same provider config)
            summarization_config = {
                'provider': 'openai',
                'model': self.compact_model,
                'temperature': 0
            }

            # Use stored config or fallback
            if self.config:
                # Preferred: use config-based initialization (with rate limiting)
                summarizer = create_llm(self.config, summarization_config)
            else:
                # Fallback for legacy initialization (WITHOUT rate limiting)
                logger.warning("Compression LLM created without rate limiting (no config available)")
                summarizer = ChatOpenAI(
                    model=self.compact_model,
                    temperature=0,
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url="https://api.openai.com/v1"
                )

            response = await summarizer.ainvoke([HumanMessage(content=summarization_prompt)])
            summary_content = response.content

            # Create compressed summary message
            summary_msg = SystemMessage(
                content=f"[COMPRESSED RESEARCH SUMMARY]\n\n{summary_content}"
            )

            # Update stats
            self.messages_before_compression += len(messages)
            compressed = [first_msg, summary_msg] + last_msgs

            # Validate: remove orphaned ToolMessages (without preceding AIMessage with tool_calls)
            validated = []
            last_had_tool_calls = False

            for msg in compressed:
                if isinstance(msg, ToolMessage):
                    if not last_had_tool_calls:
                        # Orphaned ToolMessage - skip it
                        logger.warning(f"Skipping orphaned ToolMessage in compressed context")
                        continue
                    # Valid ToolMessage following AIMessage with tool_calls
                    validated.append(msg)
                    last_had_tool_calls = False  # Reset after consuming
                elif isinstance(msg, AIMessage):
                    validated.append(msg)
                    # Check if this AIMessage has tool_calls
                    last_had_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls and len(msg.tool_calls) > 0
                else:
                    # HumanMessage, SystemMessage, etc
                    validated.append(msg)
                    last_had_tool_calls = False

            compressed = validated
            self.messages_after_compression += len(compressed)
            self.compression_count += 1

            logger.info(f"🗜️  Context compressed: {len(messages)} → {len(compressed)} messages")

            return compressed

        except Exception as e:
            logger.warning(f"⚠️  Compression failed: {e}, keeping original context")
            return messages

    async def run(self, task: str) -> Dict[str, Any]:
        """
        Execute a task using the LLM with tools.

        Args:
            task: Task description

        Returns:
            Result dictionary with token usage stats
        """
        try:
            # Bind tools to LLM
            llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm

            logger.debug(f"Agent starting with {len(self.tools)} tools, max_iterations={self.max_iterations}")
            logger.debug(f"Task length: {len(task)} chars")

            messages = [HumanMessage(content=task)]
            iteration = 0

            # Token tracking
            total_input_tokens = 0
            total_output_tokens = 0
            total_cached_tokens = 0

            while iteration < self.max_iterations:
                iteration += 1
                logger.debug(f"[Iteration {iteration}/{self.max_iterations}] messages={len(messages)}")

                # Check if we need to compress context
                if self.auto_compact_enabled and len(messages) >= self.compact_trigger:
                    messages = await self._compress_context(messages)

                # Get LLM response
                try:
                    logger.debug(f"Calling LLM with {len(messages)} messages...")
                    response = await llm_with_tools.ainvoke(messages)
                    logger.debug("LLM call completed")
                except Exception as e:
                    logger.error(f"LLM call failed: {e}")
                    raise

                messages.append(response)

                # Log what happened
                has_tool_calls = hasattr(response, 'tool_calls') and response.tool_calls

                if has_tool_calls:
                    tool_names = [tc.get('name', '?') for tc in response.tool_calls]
                    logger.debug(f"LLM requested tools: {', '.join(tool_names)}")
                else:
                    content_len = len(response.content) if response.content else 0
                    logger.debug(f"LLM returned final response ({content_len} chars)")

                # Track tokens from this response
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    usage = response.usage_metadata
                    total_input_tokens += usage.get('input_tokens', 0)
                    total_output_tokens += usage.get('output_tokens', 0)

                    # Track cached tokens if available
                    if 'input_token_details' in usage and usage['input_token_details']:
                        total_cached_tokens += usage['input_token_details'].get('cached_tokens', 0)

                # Check if LLM wants to use tools
                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                    # No more tools to call, we're done
                    # Extract content from response (handle different formats)
                    final_content = response.content

                    # Debug: if content is empty, log the full response structure
                    if not final_content or final_content.strip() == "":
                        logger.warning(f"Empty response.content at iteration {iteration}!")
                        logger.debug(f"Response type: {type(response)}")
                        logger.debug(f"Has tool_calls attr: {hasattr(response, 'tool_calls')}")
                        logger.debug(f"tool_calls value: {response.tool_calls if hasattr(response, 'tool_calls') else 'N/A'}")

                        # Check for structured output in additional_kwargs
                        if hasattr(response, 'additional_kwargs'):
                            logger.debug(f"additional_kwargs keys: {list(response.additional_kwargs.keys())}")
                            logger.debug(f"additional_kwargs content: {response.additional_kwargs}")

                            # Try to extract from function_call or other fields
                            if 'function_call' in response.additional_kwargs:
                                final_content = response.additional_kwargs['function_call'].get('arguments', '')
                                logger.debug(f"Extracted from function_call: {final_content[:200]}")

                        # Check if this is actually a finish_reason issue
                        if hasattr(response, 'response_metadata'):
                            logger.debug(f"response_metadata: {response.response_metadata}")

                        # Last resort: convert entire response to string
                        if not final_content:
                            final_content = str(response)
                            logger.debug(f"Using str(response): {final_content[:300]}...")

                        # Still empty? This is bad - return error instead of empty string
                        if not final_content or final_content.strip() == "":
                            logger.error("CRITICAL: All extraction methods failed!")
                            logger.debug(f"Full response object: {vars(response)}")

                            # Return error result instead of success with empty content
                            return {
                                "final_result": json.dumps({
                                    "rejected": True,
                                    "reason": "LLM returned empty response - all extraction methods failed",
                                    "letter": None,
                                    "relevance_assessment": "ERROR",
                                    "notes": f"Iteration {iteration}/{self.max_iterations}, response type: {type(response).__name__}"
                                }),
                                "status": "error",
                                "error": "Empty LLM response",
                                "token_usage": {
                                    "input_tokens": total_input_tokens,
                                    "output_tokens": total_output_tokens,
                                    "cached_tokens": total_cached_tokens,
                                    "total_tokens": total_input_tokens + total_output_tokens
                                },
                                "compression_stats": {
                                    "count": self.compression_count,
                                    "messages_before": self.messages_before_compression,
                                    "messages_after": self.messages_after_compression
                                }
                            }

                    return {
                        "final_result": final_content,
                        "status": "success",
                        "token_usage": {
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens,
                            "cached_tokens": total_cached_tokens,
                            "total_tokens": total_input_tokens + total_output_tokens
                        },
                        "compression_stats": {
                            "count": self.compression_count,
                            "messages_before": self.messages_before_compression,
                            "messages_after": self.messages_after_compression
                        }
                    }

                # Execute tools
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    # Log MCP call
                    logger.debug(f"Calling MCP tool: {tool_name}")

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
            logger.warning(f"Agent reached max iterations ({self.max_iterations})")
            logger.debug(f"Total messages in context: {len(messages)}")
            logger.debug(f"Last message type: {type(messages[-1]).__name__ if messages else 'None'}")
            if messages and hasattr(messages[-1], 'content'):
                logger.debug(f"Last message content preview: {str(messages[-1].content)[:200]}")

            return {
                "final_result": "Max iterations reached - agent did not produce final output",
                "status": "partial",
                "error": "Agent exceeded maximum iterations without completing task",
                "token_usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cached_tokens": total_cached_tokens,
                    "total_tokens": total_input_tokens + total_output_tokens
                },
                "compression_stats": {
                    "count": self.compression_count,
                    "messages_before": self.messages_before_compression,
                    "messages_after": self.messages_after_compression
                }
            }

        except Exception as e:
            return {
                "final_result": "",
                "status": "error",
                "error": str(e),
                "token_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "total_tokens": 0
                },
                "compression_stats": {
                    "count": self.compression_count,
                    "messages_before": self.messages_before_compression,
                    "messages_after": self.messages_after_compression
                }
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
