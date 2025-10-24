"""
Main LangGraph implementation - Plan and Execute pattern.
"""

from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from .agents.planner import PlannerAgent, Plan
from .agents.executor import ExecutorAgent
from .agents.replanner import ReplannerAgent


class AgentState(TypedDict):
    """State of the planning and execution agent."""

    messages: Annotated[List[BaseMessage], add_messages]
    objective: str
    plan: Plan | None
    current_step_id: int | None
    step_results: dict
    iteration: int
    max_iterations: int
    is_complete: bool
    error: str | None


class PlanExecuteGraph:
    """
    LangGraph implementation of Plan-and-Execute pattern.

    Workflow:
    1. Plan: Create initial plan from objective
    2. Execute: Execute next available step
    3. Replan: Check if replanning is needed
    4. Repeat until complete or max iterations
    """

    def __init__(self, llm, tools, max_iterations: int = 20):
        """
        Initialize the planning graph.

        Args:
            llm: Language model for agents
            tools: List of available tools
            max_iterations: Maximum number of execution iterations
        """
        self.planner = PlannerAgent(llm)
        self.executor = ExecutorAgent(llm, tools)
        self.replanner = ReplannerAgent(llm)
        self.max_iterations = max_iterations
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""

        # Create the graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("execute", self._execute_node)
        workflow.add_node("replan", self._replan_node)

        # Add edges
        workflow.add_edge(START, "plan")
        workflow.add_edge("plan", "execute")
        workflow.add_edge("execute", "replan")

        # Conditional edge from replan
        workflow.add_conditional_edges(
            "replan",
            self._should_continue,
            {
                "continue": "execute",
                "end": END
            }
        )

        return workflow.compile()

    async def _plan_node(self, state: AgentState) -> AgentState:
        """Create the initial plan."""
        objective = state["objective"]

        print(f"\n📋 Creating plan for: {objective}")

        plan = await self.planner.create_plan(objective)

        print(f"✓ Created plan with {len(plan.steps)} steps:")
        for step in plan.steps:
            print(f"  {step.id}. {step.description}")

        return {
            **state,
            "plan": plan,
            "step_results": {},
            "iteration": 0,
            "is_complete": False
        }

    async def _execute_node(self, state: AgentState) -> AgentState:
        """Execute the next available step."""
        plan = state["plan"]
        iteration = state.get("iteration", 0) + 1

        # Find next executable step
        next_step = self.replanner.get_next_executable_step(plan)

        if not next_step:
            print("⚠️  No executable steps found")
            return {
                **state,
                "is_complete": True,
                "iteration": iteration
            }

        print(f"\n🔧 Executing step {next_step.id}: {next_step.description}")

        # Mark step as in progress
        next_step.status = "in_progress"

        # Prepare context
        context = {
            "objective": plan.objective,
            "previous_results": state.get("step_results", {}),
            "step": next_step
        }

        # Execute the step
        result = await self.executor.execute_step(
            next_step.description,
            context
        )

        # Store result
        step_results = state.get("step_results", {})
        step_results[next_step.id] = result

        if result["success"]:
            print(f"✓ Step {next_step.id} completed successfully")
        else:
            print(f"✗ Step {next_step.id} failed: {result.get('error', 'Unknown error')}")

        return {
            **state,
            "current_step_id": next_step.id,
            "step_results": step_results,
            "iteration": iteration
        }

    async def _replan_node(self, state: AgentState) -> AgentState:
        """Decide if replanning is needed and update the plan."""
        plan = state["plan"]
        current_step_id = state["current_step_id"]
        step_results = state["step_results"]

        if current_step_id is None:
            return state

        execution_result = step_results.get(current_step_id, {})

        # Update plan with execution results
        updated_plan = await self.replanner.adjust_plan(
            plan,
            current_step_id,
            execution_result
        )

        # Check if plan is complete
        is_complete = self.replanner.is_plan_complete(updated_plan)
        has_failed = self.replanner.has_failed_steps(updated_plan)

        if is_complete:
            print("\n✓ All steps completed successfully!")
        elif has_failed:
            print("\n⚠️  Some steps failed")

        return {
            **state,
            "plan": updated_plan,
            "is_complete": is_complete or has_failed
        }

    def _should_continue(self, state: AgentState) -> str:
        """Determine if execution should continue."""
        if state.get("is_complete", False):
            return "end"

        if state.get("iteration", 0) >= self.max_iterations:
            print(f"\n⚠️  Max iterations ({self.max_iterations}) reached")
            return "end"

        return "continue"

    async def run(self, objective: str) -> dict:
        """
        Run the planning agent for a given objective.

        Args:
            objective: The goal to achieve

        Returns:
            Final state with results
        """
        initial_state = {
            "messages": [],
            "objective": objective,
            "plan": None,
            "current_step_id": None,
            "step_results": {},
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "is_complete": False,
            "error": None
        }

        print(f"\n{'='*60}")
        print(f"🚀 Starting Plan-Execute Agent")
        print(f"{'='*60}")

        final_state = await self.graph.ainvoke(initial_state)

        print(f"\n{'='*60}")
        print(f"📊 Execution Summary")
        print(f"{'='*60}")

        if final_state["plan"]:
            completed = sum(1 for s in final_state["plan"].steps if s.status == "completed")
            total = len(final_state["plan"].steps)
            print(f"Steps completed: {completed}/{total}")
            print(f"Iterations: {final_state['iteration']}")

        return final_state
