"""
Planner Agent - Creates step-by-step plans for complex tasks.
"""

import json
from typing import List, Optional
from pydantic import BaseModel, Field


class Step(BaseModel):
    """A single step in a plan."""

    id: int = Field(description="Step ID")
    description: str = Field(description="What needs to be done")
    dependencies: List[int] = Field(default_factory=list, description="IDs of steps this depends on")
    status: str = Field(default="pending", description="pending, in_progress, completed, failed")
    result: Optional[str] = Field(default=None, description="Result of executing this step")


class Plan(BaseModel):
    """A plan consisting of multiple steps."""

    objective: str = Field(description="The overall objective")
    steps: List[Step] = Field(description="List of steps to complete the objective")


class PlannerAgent:
    """
    Agent responsible for creating plans from user objectives.
    Uses LLM to break down complex tasks into manageable steps.
    """

    def __init__(self, llm):
        """
        Initialize the planner agent.

        Args:
            llm: Language model to use for planning
        """
        self.llm = llm
        self.supports_structured_output = None  # Will be determined on first use

    async def _get_structured_plan(self, messages: List) -> Plan:
        """
        Get a structured plan from the LLM with fallback for unsupported models.

        Args:
            messages: List of chat messages

        Returns:
            Parsed Plan object
        """
        # Try structured output first (if not already known to fail)
        if self.supports_structured_output != False:
            try:
                llm_with_structure = self.llm.with_structured_output(Plan)
                plan = await llm_with_structure.ainvoke(messages)
                self.supports_structured_output = True
                return plan
            except Exception as e:
                error_msg = str(e)
                if "response_format" in error_msg or "unavailable" in error_msg:
                    print("⚠ Model doesn't support structured output, using JSON mode fallback")
                    self.supports_structured_output = False
                else:
                    raise

        # Fallback: Use regular LLM and parse JSON manually
        # Add instruction to ensure JSON output
        from langchain_core.messages import SystemMessage, HumanMessage

        enhanced_messages = messages.copy()
        # Add explicit JSON instruction to the last message
        if isinstance(enhanced_messages[-1], HumanMessage):
            enhanced_messages[-1].content += "\n\nIMPORTANT: Respond with ONLY valid JSON matching the schema described above. No other text."

        response = await self.llm.ainvoke(enhanced_messages)
        content = response.content

        # Try to extract JSON from the response
        try:
            # First, try to parse the entire content as JSON
            plan_data = json.loads(content)
        except json.JSONDecodeError:
            # If that fails, try to find JSON in code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group(1))
            else:
                # Last resort: find any JSON object
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    plan_data = json.loads(json_match.group(0))
                else:
                    raise ValueError(f"Could not extract valid JSON from response: {content[:200]}")

        return Plan(**plan_data)

    async def create_plan(self, objective: str, context: Optional[str] = None) -> Plan:
        """
        Create a plan to achieve the given objective.

        Args:
            objective: The user's goal
            context: Optional additional context

        Returns:
            A Plan object with steps
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        system_prompt = """You are an expert planning agent. Your job is to break down complex objectives into clear, actionable steps.

For each step:
1. Be specific and concrete
2. Identify dependencies on previous steps
3. Ensure steps are in logical order
4. Make steps achievable with available tools

Available tool categories:
- File operations (read, write, list)
- Shell commands
- Search operations
- MCP tools (if configured)

Return a plan in this JSON format:
{
    "objective": "the user's objective",
    "steps": [
        {
            "id": 1,
            "description": "First step description",
            "dependencies": [],
            "status": "pending"
        },
        {
            "id": 2,
            "description": "Second step description",
            "dependencies": [1],
            "status": "pending"
        }
    ]
}"""

        user_message = f"Objective: {objective}"
        if context:
            user_message += f"\n\nContext: {context}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]

        plan = await self._get_structured_plan(messages)
        return plan

    async def replan(self, original_plan: Plan, completed_steps: List[int], error_info: Optional[str] = None) -> Plan:
        """
        Modify the plan based on execution results.

        Args:
            original_plan: The original plan
            completed_steps: IDs of successfully completed steps
            error_info: Information about any errors encountered

        Returns:
            Updated Plan
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        system_prompt = """You are a replanning agent. Based on the progress and any errors, update the plan.

You can:
1. Mark steps as completed
2. Add new steps if needed
3. Modify remaining steps
4. Remove unnecessary steps
5. Adjust dependencies

Maintain the same JSON format for the plan."""

        context = f"""Original Objective: {original_plan.objective}

Original Plan:
{original_plan.model_dump_json(indent=2)}

Completed Steps: {completed_steps}
"""

        if error_info:
            context += f"\n\nError Information:\n{error_info}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context)
        ]

        new_plan = await self._get_structured_plan(messages)
        return new_plan
