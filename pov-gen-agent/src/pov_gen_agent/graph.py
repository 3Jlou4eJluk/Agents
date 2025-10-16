"""LangGraph workflow for POV Email Generator."""

from typing import Literal
from langgraph.graph import StateGraph, END

from .state import EmailState, ProfileData, create_initial_state
from .agents import BaseAgent, GTMAgent, POVAgent
from .config import MAX_ITERATIONS, SCORE_THRESHOLD


def create_pov_graph():
    """Create the POV email generation graph."""

    # Initialize agents
    base_agent = BaseAgent()
    gtm_agent = GTMAgent()
    pov_agent = POVAgent()

    # Define node functions
    def generate_node(state: EmailState) -> EmailState:
        """Generate email draft."""
        print(f"\n[Iteration {state['iteration'] + 1}] Generating email draft...")
        return base_agent.generate(state)

    def validate_gtm_node(state: EmailState) -> EmailState:
        """Validate ICP/GTM fit."""
        print(f"[Iteration {state['iteration']}] Validating ICP/GTM fit...")
        return gtm_agent.validate(state)

    def validate_pov_node(state: EmailState) -> EmailState:
        """Validate POV framework."""
        print(f"[Iteration {state['iteration']}] Validating POV framework...")
        return pov_agent.validate(state)

    def check_scores_node(state: EmailState) -> EmailState:
        """Check scores and prepare for next iteration or end."""
        gtm = state["gtm_score"]
        pov = state["pov_score"]
        iteration = state["iteration"]

        print(f"[Iteration {iteration}] Scores: GTM {gtm:.1f}/10, POV {pov:.1f}/10")

        if gtm >= SCORE_THRESHOLD and pov >= SCORE_THRESHOLD:
            print(f"✓ Success! Both scores meet threshold ({SCORE_THRESHOLD})")
        elif iteration >= MAX_ITERATIONS:
            print(f"⚠ Max iterations ({MAX_ITERATIONS}) reached")
        else:
            print(f"→ Regenerating based on feedback...")

        return state

    # Define conditional logic
    def should_continue(state: EmailState) -> Literal["generate", "end"]:
        """Determine whether to continue iterating or end."""
        # Check if max iterations reached
        if state["iteration"] >= MAX_ITERATIONS:
            return "end"

        # Check if both scores meet threshold
        if (state["gtm_score"] >= SCORE_THRESHOLD and
            state["pov_score"] >= SCORE_THRESHOLD):
            return "end"

        # Continue iterating
        return "generate"

    # Build the graph
    workflow = StateGraph(EmailState)

    # Add nodes
    workflow.add_node("generate", generate_node)
    workflow.add_node("validate_gtm", validate_gtm_node)
    workflow.add_node("validate_pov", validate_pov_node)
    workflow.add_node("check_scores", check_scores_node)

    # Add edges
    workflow.set_entry_point("generate")
    workflow.add_edge("generate", "validate_gtm")
    workflow.add_edge("validate_gtm", "validate_pov")
    workflow.add_edge("validate_pov", "check_scores")

    # Add conditional edge
    workflow.add_conditional_edges(
        "check_scores",
        should_continue,
        {
            "generate": "generate",
            "end": END,
        }
    )

    return workflow.compile()


def generate_email(profile_data: ProfileData, verbose: bool = True) -> dict:
    """
    Generate a POV-based email for the given profile.

    Args:
        profile_data: Dictionary containing prospect information
        verbose: Whether to print progress

    Returns:
        Dictionary with email, scores, and metadata
    """
    # Create initial state
    initial_state = create_initial_state(profile_data)

    # Create and run the graph
    graph = create_pov_graph()

    if verbose:
        print("=" * 60)
        print("POV Email Generator")
        print("=" * 60)

    # Run the workflow
    final_state = graph.invoke(initial_state)

    # Determine status
    if (final_state["gtm_score"] >= SCORE_THRESHOLD and
        final_state["pov_score"] >= SCORE_THRESHOLD):
        status = "success"
        warnings = []
    else:
        status = "max_iterations"
        warnings = [
            "Could not achieve target scores",
            "Consider reviewing profile data quality or adjusting thresholds"
        ]

    if verbose:
        print("\n" + "=" * 60)
        print("Final Result")
        print("=" * 60)
        print(f"\nStatus: {status}")
        print(f"GTM Score: {final_state['gtm_score']:.1f}/10")
        print(f"POV Score: {final_state['pov_score']:.1f}/10")
        print(f"Iterations: {final_state['iteration']}")
        if warnings:
            print("\nWarnings:")
            for warning in warnings:
                print(f"  - {warning}")
        print("\n" + "=" * 60)
        print("Generated Email")
        print("=" * 60)
        print(f"\n{final_state['email_draft']}\n")
        print("=" * 60)

    # Return result
    return {
        "status": status,
        "email": final_state["email_draft"],
        "gtm_score": final_state["gtm_score"],
        "pov_score": final_state["pov_score"],
        "iterations": final_state["iteration"],
        "gtm_feedback": final_state["gtm_feedback"],
        "pov_feedback": final_state["pov_feedback"],
        "warnings": warnings if warnings else None,
        "history": final_state["history"],
    }
