"""
Replanner Agent - Adjusts plans based on execution results.
"""

from typing import List, Optional
from .planner import Plan, Step


class ReplannerAgent:
    """
    Agent that adjusts plans based on execution feedback.
    Decides whether to continue, replan, or finish.
    """

    def __init__(self, llm):
        """
        Initialize the replanner agent.

        Args:
            llm: Language model for decision making
        """
        self.llm = llm

    async def should_replan(
        self,
        plan: Plan,
        step_id: int,
        execution_result: dict
    ) -> bool:
        """
        Decide if replanning is needed based on execution result.

        Args:
            plan: Current plan
            step_id: ID of the step that was just executed
            execution_result: Result from executor

        Returns:
            True if replanning is needed
        """
        # Simple heuristic: replan if execution failed
        if not execution_result.get("success", False):
            return True

        # Check if this was the last step
        remaining_steps = [s for s in plan.steps if s.status == "pending"]
        if not remaining_steps:
            return False

        return False

    async def adjust_plan(
        self,
        plan: Plan,
        completed_step_id: int,
        execution_result: dict
    ) -> Plan:
        """
        Adjust the plan based on execution results.

        Args:
            plan: Current plan
            completed_step_id: ID of completed step
            execution_result: Execution result

        Returns:
            Updated plan
        """
        # Update the completed step
        for step in plan.steps:
            if step.id == completed_step_id:
                if execution_result.get("success"):
                    step.status = "completed"
                    step.result = execution_result.get("result", "")
                else:
                    step.status = "failed"
                    step.result = execution_result.get("error", "Unknown error")

        # If there was a failure, might need to add recovery steps
        if not execution_result.get("success"):
            # Add a recovery step or modify remaining steps
            error_info = execution_result.get("error", "")

            # Simple recovery: mark dependent steps as pending for retry
            for step in plan.steps:
                if completed_step_id in step.dependencies:
                    step.status = "pending"

        return plan

    def get_next_executable_step(self, plan: Plan) -> Optional[Step]:
        """
        Find the next step that can be executed (all dependencies met).

        Args:
            plan: Current plan

        Returns:
            Next executable step or None if no steps are ready
        """
        for step in plan.steps:
            if step.status != "pending":
                continue

            # Check if all dependencies are completed
            dependencies_met = all(
                any(s.id == dep_id and s.status == "completed" for s in plan.steps)
                for dep_id in step.dependencies
            )

            if dependencies_met:
                return step

        return None

    def is_plan_complete(self, plan: Plan) -> bool:
        """Check if all steps in the plan are completed."""
        return all(step.status == "completed" for step in plan.steps)

    def has_failed_steps(self, plan: Plan) -> bool:
        """Check if any steps have failed."""
        return any(step.status == "failed" for step in plan.steps)
