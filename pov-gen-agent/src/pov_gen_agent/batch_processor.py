"""Batch processor for generating POV emails from JSON input."""

import json
from typing import List, Dict, Any
from pathlib import Path

from .graph import generate_email
from .state import ProfileData


def extract_profile_from_lead(lead: Dict[str, Any]) -> ProfileData:
    """
    Extract ProfileData from lead JSON.

    Args:
        lead: Dictionary containing lead information

    Returns:
        ProfileData formatted for email generation
    """
    import re

    # Get analysis section
    analysis = lead.get("analysis", {})
    classification_reason = lead.get("classification_reason", "")

    # Extract company size from classification_reason or analysis
    company_size = None
    if analysis and isinstance(analysis, dict) and "company_size" in analysis:
        # Old format
        company_size = analysis.get("company_size")
    else:
        # Try to extract from classification_reason
        size_match = re.search(r'(\d+)[\s\-+]*employees', classification_reason, re.IGNORECASE)
        if size_match:
            company_size = int(size_match.group(1))

    # Extract industry from analysis or classification_reason
    industry = None
    if analysis and isinstance(analysis, dict) and "industry" in analysis:
        # Old format
        industry = analysis.get("industry")
    else:
        # Try to infer from classification_reason
        if "B2B SaaS" in classification_reason or "SaaS" in classification_reason:
            industry = "B2B SaaS"
        elif "financial" in classification_reason.lower() or "fintech" in classification_reason.lower():
            industry = "Financial Technology"
        elif "tech" in classification_reason.lower():
            industry = "Technology"

    # Extract recent news from analysis
    recent_news = None
    if analysis and isinstance(analysis, dict) and "recent_news" in analysis:
        recent_news = analysis.get("recent_news")

    # Build enriched person_background from new format fields
    person_background_parts = []

    # Add classification reason as base context
    if classification_reason:
        person_background_parts.append(f"Background: {classification_reason}")

    # Add talking points if available
    if analysis and isinstance(analysis, dict):
        talking_points = analysis.get("talking_points", [])
        if talking_points:
            person_background_parts.append(f"\nKey Talking Points:\n" + "\n".join(f"- {point}" for point in talking_points))

        # Add pain points
        pain_points = analysis.get("pain_points", [])
        if pain_points:
            person_background_parts.append(f"\nPain Points:\n" + "\n".join(f"- {point}" for point in pain_points))

        # Add personalization notes
        personalization = analysis.get("personalization", [])
        if personalization:
            person_background_parts.append(f"\nPersonalization Notes:\n" + "\n".join(f"- {point}" for point in personalization))

        # Add outreach approach
        outreach_approach = analysis.get("outreach_approach")
        if outreach_approach:
            person_background_parts.append(f"\nRecommended Approach: {outreach_approach}")

    person_background = "\n".join(person_background_parts) if person_background_parts else classification_reason

    # Extract basic info
    profile: ProfileData = {
        "company": lead.get("company", "Unknown Company"),
        "company_size": company_size,
        "industry": industry,
        "recent_news": recent_news,
        "person_name": lead.get("name", ""),
        "person_title": lead.get("job_title", ""),
        "person_background": person_background if person_background else None,
    }

    # Add optional enriched fields if available in new format
    if analysis and isinstance(analysis, dict):
        if analysis.get("talking_points"):
            profile["talking_points"] = analysis.get("talking_points")
        if analysis.get("pain_points"):
            profile["pain_points"] = analysis.get("pain_points")
        if analysis.get("personalization"):
            profile["personalization_notes"] = analysis.get("personalization")
        if analysis.get("outreach_approach"):
            profile["outreach_approach"] = analysis.get("outreach_approach")

    return profile


def process_leads_batch(
    leads: List[Dict[str, Any]],
    output_dir: str = "output",
    filter_relevant: bool = True,
    verbose: bool = True
) -> List[Dict[str, Any]]:
    """
    Process a batch of leads and generate POV emails.

    Args:
        leads: List of lead dictionaries
        output_dir: Directory to save individual email results
        filter_relevant: If True, only process leads where is_relevant=True
        verbose: Whether to print progress

    Returns:
        List of results with email generation outcomes
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    results = []

    # Filter leads if needed
    if filter_relevant:
        leads_to_process = [lead for lead in leads if lead.get("is_relevant", False)]
        if verbose:
            print(f"\nFiltered to {len(leads_to_process)} relevant leads (out of {len(leads)} total)")
    else:
        leads_to_process = leads

    if not leads_to_process:
        print("\n⚠️  No relevant leads to process. Set 'is_relevant': true in your JSON or use filter_relevant=False")
        return []

    # Process each lead
    for idx, lead in enumerate(leads_to_process, 1):
        if verbose:
            print(f"\n{'='*80}")
            print(f"Processing Lead {idx}/{len(leads_to_process)}")
            print(f"{'='*80}")
            print(f"Name: {lead.get('name', 'N/A')}")
            print(f"Company: {lead.get('company', 'N/A')}")
            print(f"Title: {lead.get('job_title', 'N/A')}")
            print(f"{'='*80}")

        try:
            # Extract profile data
            profile_data = extract_profile_from_lead(lead)

            # Generate email
            result = generate_email(profile_data, verbose=verbose)

            # Add lead info to result
            result["lead_info"] = {
                "email": lead.get("email"),
                "name": lead.get("name"),
                "company": lead.get("company"),
                "job_title": lead.get("job_title"),
                "linkedin_url": lead.get("linkedin_url"),
            }

            # Save individual result
            safe_filename = f"{lead.get('name', 'unknown').replace(' ', '_').lower()}_{idx}.json"
            result_file = output_path / safe_filename
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2)

            if verbose:
                print(f"\n✓ Saved to {result_file}")

            results.append(result)

        except Exception as e:
            error_result = {
                "status": "error",
                "error": str(e),
                "lead_info": {
                    "email": lead.get("email"),
                    "name": lead.get("name"),
                    "company": lead.get("company"),
                },
            }
            results.append(error_result)

            if verbose:
                print(f"\n✗ Error processing lead: {e}")

    return results


def save_batch_summary(results: List[Dict[str, Any]], output_file: str = "batch_summary.json"):
    """Save a summary of batch processing results."""
    summary = {
        "total_processed": len(results),
        "successful": sum(1 for r in results if r.get("status") == "success"),
        "max_iterations": sum(1 for r in results if r.get("status") == "max_iterations"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
        "average_gtm_score": sum(r.get("gtm_score", 0) for r in results if "gtm_score" in r) / len(results) if results else 0,
        "average_pov_score": sum(r.get("pov_score", 0) for r in results if "pov_score" in r) / len(results) if results else 0,
        "average_iterations": sum(r.get("iterations", 0) for r in results if "iterations" in r) / len(results) if results else 0,
        "results": results,
    }

    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def process_from_file(
    input_file: str,
    output_dir: str = "output",
    summary_file: str = "batch_summary.json",
    filter_relevant: bool = True,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Process leads from a JSON file.

    Args:
        input_file: Path to input JSON file
        output_dir: Directory to save results
        summary_file: Path to summary output file
        filter_relevant: If True, only process leads where is_relevant=True
        verbose: Whether to print progress

    Returns:
        Summary dictionary
    """
    # Load input JSON
    with open(input_file, "r") as f:
        leads = json.load(f)

    if verbose:
        print(f"\n🚀 POV Email Batch Processor")
        print(f"{'='*80}")
        print(f"Input file: {input_file}")
        print(f"Total leads: {len(leads)}")
        print(f"Output directory: {output_dir}")
        print(f"Filter relevant only: {filter_relevant}")
        print(f"{'='*80}")

    # Process leads
    results = process_leads_batch(leads, output_dir, filter_relevant, verbose)

    # Save summary
    summary = save_batch_summary(results, summary_file)

    if verbose:
        print(f"\n{'='*80}")
        print(f"Batch Processing Complete")
        print(f"{'='*80}")
        print(f"Total processed: {summary['total_processed']}")
        print(f"Successful: {summary['successful']}")
        print(f"Max iterations reached: {summary['max_iterations']}")
        print(f"Errors: {summary['errors']}")
        print(f"Average GTM score: {summary['average_gtm_score']:.2f}/10")
        print(f"Average POV score: {summary['average_pov_score']:.2f}/10")
        print(f"Average iterations: {summary['average_iterations']:.1f}")
        print(f"\nSummary saved to: {summary_file}")
        print(f"{'='*80}\n")

    return summary
