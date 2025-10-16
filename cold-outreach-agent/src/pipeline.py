"""
Lead Pipeline using LangGraph and DeepSeek.
"""

import json
import os
import asyncio
from typing import TypedDict, Annotated
from operator import add

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from src.tools import BrightDataClient, load_leads_from_csv, save_results_to_json
from src.prompts import get_classification_prompt, get_custom_analysis_prompt


class State(TypedDict):
    """State for the lead pipeline."""
    raw_leads: list[dict]
    enriched_leads: list[dict]
    relevant_leads: list[dict]
    analyzed_top20: list[dict]
    csv_path: str
    output_path: str
    custom_prompt: str
    bright_data_client: BrightDataClient


def load_csv_node(state: State) -> dict:
    """Load leads from CSV file."""
    print(f"\n=== Loading leads from {state['csv_path']} ===")
    raw_leads = load_leads_from_csv(state["csv_path"])
    print(f"Loaded {len(raw_leads)} leads")
    return {"raw_leads": raw_leads}


async def enrich_linkedin_node(state: State) -> dict:
    """Enrich leads with LinkedIn data via Bright Data."""
    print("\n=== Enriching LinkedIn profiles ===")
    client = state.get("bright_data_client")

    if not client:
        raise RuntimeError("BrightDataClient not initialized in state")

    enriched_leads = await client.enrich_batch(
        state["raw_leads"],
        batch_size=10,
        delay_seconds=2.0
    )

    print(f"Enriched {len(enriched_leads)} profiles")
    return {"enriched_leads": enriched_leads}


async def classify_single_lead(lead: dict, llm: ChatOpenAI) -> dict:
    """
    Classify a single lead using DeepSeek LLM.

    Args:
        lead: Lead dictionary with enriched data
        llm: ChatOpenAI instance

    Returns:
        Classification result dictionary
    """
    enriched_data = lead.get("enriched_data", {})
    prompt = get_classification_prompt(lead, enriched_data)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result_text = response.content

        # Parse JSON response
        result = json.loads(result_text)
        return {
            "lead": lead,
            "classification": result,
            "error": None
        }
    except Exception as e:
        return {
            "lead": lead,
            "classification": {"relevant": False, "reason": f"Error: {str(e)}"},
            "error": str(e)
        }


async def classify_node(state: State) -> dict:
    """Classify leads using DeepSeek LLM with batching."""
    print("\n=== Classifying leads ===")

    # Get model and batch size from environment or use defaults
    classification_model = os.getenv("DEEPSEEK_CLASSIFICATION_MODEL", "deepseek-chat")
    batch_size = int(os.getenv("CLASSIFICATION_BATCH_SIZE", "5"))
    print(f"Using model: {classification_model}")
    print(f"Batch size: {batch_size}")

    # Initialize DeepSeek LLM with JSON mode
    llm = ChatOpenAI(
        model=classification_model,
        temperature=0,
        base_url="https://api.deepseek.com",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}}
    )

    relevant_leads = []
    total_leads = len(state["enriched_leads"])
    relevant_count = 0
    not_relevant_count = 0
    error_count = 0
    total_batches = (total_leads + batch_size - 1) // batch_size

    # Process leads in batches
    for batch_idx in range(0, total_leads, batch_size):
        batch = state["enriched_leads"][batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        print(f"\n[DeepSeek] Batch {batch_num}/{total_batches} | Processing {len(batch)} leads...")

        # Create coroutines for batch
        coroutines = [classify_single_lead(lead, llm) for lead in batch]

        # Execute batch in parallel and wait for all results
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Process results
        for i, result in enumerate(results):
            lead_num = batch_idx + i + 1

            # Handle gather exceptions
            if isinstance(result, Exception):
                lead = batch[i]
                error_count += 1
                print(f"\n[DeepSeek] [{lead_num}/{total_leads}] {lead.get('name', 'N/A')}")
                print(f"  ⚠ ERROR | {str(result)}")
                lead["classification"] = {
                    "relevant": False,
                    "reason": f"Error: {str(result)}"
                }
                continue

            # Unpack result
            lead = result["lead"]
            classification = result["classification"]
            error = result["error"]

            print(f"\n[DeepSeek] [{lead_num}/{total_leads}] Classifying: {lead.get('name', 'N/A')}")

            # Add classification to lead
            lead["classification"] = classification

            # Handle errors
            if error:
                error_count += 1
                print(f"  ⚠ ERROR | {error}")
            # Check relevance
            elif classification.get("relevant", False):
                relevant_leads.append(lead)
                relevant_count += 1
                print(f"  ✓ RELEVANT | Reason: {classification.get('reason', 'N/A')[:80]}...")
            else:
                not_relevant_count += 1
                print(f"  ✗ Not relevant | Reason: {classification.get('reason', 'N/A')[:80]}...")

        # Show batch progress
        print(f"\n  Batch {batch_num} complete: {relevant_count} relevant | {not_relevant_count} not relevant | {error_count} errors")

        # Small delay between batches to avoid rate limiting
        if batch_idx + batch_size < total_leads:
            await asyncio.sleep(0.5)

    print(f"\n[DeepSeek] Classification complete:")
    print(f"  ✓ Relevant: {relevant_count}/{total_leads} ({relevant_count/total_leads*100:.1f}%)")
    print(f"  ✗ Not relevant: {not_relevant_count}/{total_leads}")
    print(f"  ⚠ Errors: {error_count}/{total_leads}")

    return {"relevant_leads": relevant_leads}


def filter_relevant_node(state: State) -> dict:
    """Filter to keep only relevant leads (already done in classify_node)."""
    print("\n=== Filtering relevant leads ===")
    print(f"Relevant leads: {len(state['relevant_leads'])}")
    return {}


async def analyze_top20_node(state: State) -> dict:
    """Analyze top 20 relevant leads with custom prompt."""
    print("\n=== Analyzing top 20 leads ===")

    # Get top 20 relevant leads
    top20 = state["relevant_leads"][:20]
    total = len(top20)

    # Get model from environment or use default
    analysis_model = os.getenv("DEEPSEEK_ANALYSIS_MODEL", "deepseek-chat")
    print(f"Analyzing top {total} leads with DeepSeek {analysis_model}\n")

    # Initialize DeepSeek LLM with JSON mode
    llm = ChatOpenAI(
        model=analysis_model,
        temperature=0.3,
        base_url="https://api.deepseek.com",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}}
    )

    analyzed_leads = []
    success_count = 0
    error_count = 0

    for i, lead in enumerate(top20):
        lead_num = i + 1
        print(f"[DeepSeek Analysis] [{lead_num}/{total}] {lead.get('name', 'N/A')}")

        # Get enriched data
        enriched_data = lead.get("enriched_data", {})

        # Create custom analysis prompt
        prompt = get_custom_analysis_prompt(
            lead,
            enriched_data,
            state["custom_prompt"]
        )

        # Call DeepSeek
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            result_text = response.content

            # Try to parse as JSON, otherwise keep as text
            try:
                analysis = json.loads(result_text)
            except json.JSONDecodeError:
                analysis = {"analysis": result_text}

            # Add analysis to lead
            lead["analysis"] = analysis
            analyzed_leads.append(lead)
            success_count += 1
            print(f"  ✓ Analysis complete")

        except Exception as e:
            error_count += 1
            print(f"  ⚠ Error: {str(e)}")
            lead["analysis"] = {"error": str(e)}
            analyzed_leads.append(lead)

        # Show progress
        print(f"  Progress: {success_count} success | {error_count} errors\n")

    print(f"[DeepSeek Analysis] Complete: {success_count}/{total} successful")
    return {"analyzed_top20": analyzed_leads}


def save_node(state: State) -> dict:
    """Save results to JSON file."""
    print("\n=== Saving results ===")

    # Prepare output data - save ALL enriched leads with classification
    output = []

    # Create a set of analyzed lead emails for quick lookup
    analyzed_emails = {lead.get("email") for lead in state["analyzed_top20"]}

    # Process all enriched leads
    for lead in state["enriched_leads"]:
        lead_email = lead.get("email")
        is_relevant = lead.get("classification", {}).get("relevant", False)

        # Check if this lead was analyzed (in top 20 relevant)
        analysis = None
        if lead_email in analyzed_emails:
            # Find the analyzed version to get the analysis
            for analyzed_lead in state["analyzed_top20"]:
                if analyzed_lead.get("email") == lead_email:
                    analysis = analyzed_lead.get("analysis")
                    break

        output.append({
            "email": lead_email,
            "name": lead.get("name"),
            "company": lead.get("company"),
            "job_title": lead.get("job_title"),
            "linkedin_url": lead.get("linkedin_url"),
            "is_relevant": is_relevant,
            "classification_reason": lead.get("classification", {}).get("reason"),
            "analysis": analysis,
            "enriched_data": lead.get("enriched_data"),
        })

    # Sort: relevant first, then by name
    output.sort(key=lambda x: (not x["is_relevant"], x.get("name", "")))

    # Save to file
    save_results_to_json(output, state["output_path"])

    # Print summary
    relevant_count = sum(1 for lead in output if lead["is_relevant"])
    not_relevant_count = len(output) - relevant_count
    analyzed_count = sum(1 for lead in output if lead["analysis"] is not None)

    print(f"Saved {len(output)} total leads:")
    print(f"  ✓ Relevant: {relevant_count} ({analyzed_count} analyzed)")
    print(f"  ✗ Not relevant: {not_relevant_count}")

    return {}


def create_pipeline() -> StateGraph:
    """Create the lead pipeline graph."""
    workflow = StateGraph(State)

    # Add nodes
    workflow.add_node("load_csv", load_csv_node)
    workflow.add_node("enrich_linkedin", enrich_linkedin_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("filter_relevant", filter_relevant_node)
    workflow.add_node("analyze_top20", analyze_top20_node)
    workflow.add_node("save", save_node)

    # Add edges
    workflow.set_entry_point("load_csv")
    workflow.add_edge("load_csv", "enrich_linkedin")
    workflow.add_edge("enrich_linkedin", "classify")
    workflow.add_edge("classify", "filter_relevant")
    workflow.add_edge("filter_relevant", "analyze_top20")
    workflow.add_edge("analyze_top20", "save")
    workflow.add_edge("save", END)

    return workflow.compile()


async def run_pipeline(
    csv_path: str,
    output_path: str,
    custom_prompt: str
) -> dict:
    """
    Run the complete lead pipeline.

    Args:
        csv_path: Path to input CSV file
        output_path: Path to output JSON file
        custom_prompt: Custom prompt for analyzing top 20 leads

    Returns:
        Final state dictionary
    """
    print("=" * 60)
    print("LEAD PIPELINE - Starting")
    print("=" * 60)

    # Create pipeline
    pipeline = create_pipeline()

    # Use BrightDataClient as async context manager
    async with BrightDataClient() as client:
        # Initialize state with connected client
        initial_state = {
            "raw_leads": [],
            "enriched_leads": [],
            "relevant_leads": [],
            "analyzed_top20": [],
            "csv_path": csv_path,
            "output_path": output_path,
            "custom_prompt": custom_prompt,
            "bright_data_client": client,
        }

        # Run pipeline
        final_state = await pipeline.ainvoke(initial_state)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETED")
    print("=" * 60)

    return final_state
