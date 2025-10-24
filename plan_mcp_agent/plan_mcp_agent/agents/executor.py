"""
Executor Agent - Executes individual steps using available tools.
"""

from typing import List, Dict, Any
from langchain_core.tools import BaseTool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import ToolNode


class ExecutorAgent:
    """
    Agent responsible for executing individual plan steps.
    Uses ReAct pattern with tool calling.
    """

    def __init__(self, llm, tools: List[BaseTool], max_iterations: int = 30):
        """
        Initialize the executor agent.

        Args:
            llm: Language model with tool calling capability
            tools: List of available tools
            max_iterations: Maximum number of tool call iterations per step (default: 30)
        """
        self.llm = llm
        self.tools = tools
        self.tool_node = ToolNode(tools)
        self.llm_with_tools = llm.bind_tools(tools)
        self.max_iterations = max_iterations

    async def execute_step(
        self,
        step_description: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single step from the plan.

        Args:
            step_description: What needs to be done
            context: Context from previous steps and overall objective

        Returns:
            Dictionary with 'success' (bool), 'result' (str), and 'error' (optional str)
        """
        system_prompt = """You are an execution agent. Your job is to complete the given step using available tools.

Guidelines:
1. Use tools when necessary to accomplish the task
2. Be thorough but efficient
3. Report results clearly
4. If you encounter errors, explain what went wrong
5. You can use multiple tools in sequence if needed

After using tools, provide a clear summary of what was accomplished."""

        context_str = f"""
Objective: {context.get('objective', 'N/A')}
Current Step: {step_description}

Previous Results:
{context.get('previous_results', 'None')}
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context_str)
        ]

        iteration = 0

        try:
            while iteration < self.max_iterations:
                iteration += 1

                # Get LLM response
                response = await self.llm_with_tools.ainvoke(messages)
                messages.append(response)

                # Check if LLM wants to use tools
                if not response.tool_calls:
                    # No more tools to call, we're done
                    final_response = response.content
                    return {
                        "success": True,
                        "result": final_response,
                        "iterations": iteration
                    }

                # Execute tools
                tool_messages = []
                for tool_call in response.tool_calls:
                    tool_result = await self._execute_tool_call(tool_call)
                    tool_messages.append(tool_result)

                messages.extend(tool_messages)

            # Max iterations reached
            return {
                "success": False,
                "result": "Max iterations reached",
                "error": "Agent exceeded maximum number of tool calls"
            }

        except Exception as e:
            return {
                "success": False,
                "result": "",
                "error": f"Error during execution: {str(e)}"
            }

    async def _execute_tool_call(self, tool_call) -> ToolMessage:
        """Execute a single tool call and return the result."""
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # Find the tool
        tool = next((t for t in self.tools if t.name == tool_name), None)

        if not tool:
            return ToolMessage(
                content=f"Error: Tool '{tool_name}' not found",
                tool_call_id=tool_call["id"]
            )

        try:
            # Check if this is an MCP tool (not OS tool)
            os_tools = ['read_file', 'write_file', 'list_directory', 'execute_command', 'get_current_time']
            is_mcp_tool = tool_name not in os_tools

            if is_mcp_tool:
                print(f"🔧 Calling MCP: {tool_name}")

            # Execute the tool
            if hasattr(tool, "ainvoke"):
                result = await tool.ainvoke(tool_args)
            else:
                result = tool.invoke(tool_args)

            return ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            )
        except Exception as e:
            return ToolMessage(
                content=f"Error executing tool: {str(e)}",
                tool_call_id=tool_call["id"]
            )
