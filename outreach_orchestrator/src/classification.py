"""
Lead classification functionality (from cold-outreach-agent).
"""

import json
from typing import Dict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


CLASSIFICATION_PROMPT = """You're doing a quick first-pass filter. Your job is BROAD filtering - only reject OBVIOUS mismatches.

## Target ICP Context:
{gtm_context}

## Profile to Analyze:
Email: {email}
Name: {name}
Company: {company}
Job Title: {job_title}
LinkedIn URL: {linkedin_url}

## Your Task: Quick Pre-Screen (NOT deep analysis)

**IMPORTANT: Default to "relevant" unless there are CLEAR red flags.**

This is a PRE-SCREENING stage. Stage 2 will do deep research and make the final decision.
Your goal: filter out ONLY obviously irrelevant leads.

**Mark as relevant (true) if:**
- Job title suggests they work in relevant functions (tech, product, CS, ops, support)
- Company seems like a B2B tech/SaaS company
- Role suggests potential decision influence (manager+, director, VP, C-level, founder)
- You're uncertain → mark as relevant (better safe than sorry)

**Mark as NOT relevant (false) ONLY if:**
- Job title is completely unrelated (HR, finance, legal, sales, marketing)
- Company is clearly not B2B tech/SaaS (retail, manufacturing, etc.)
- Role is clearly junior IC with zero influence (intern, junior dev, etc.)
- OBVIOUS mismatch with ICP

**When in doubt → mark as RELEVANT.** Stage 2 will investigate deeper.

Return ONLY valid JSON:
{{
  "relevant": true,
  "reason": "Brief reason (e.g., 'Tech role in B2B SaaS company')"
}}

or

{{
  "relevant": false,
  "reason": "Clear red flag (e.g., 'Marketing role, not relevant to our ICP')"
}}
"""


def get_classification_prompt(lead: Dict, gtm_context: str) -> str:
    """
    Format the classification prompt with lead data.

    Args:
        lead: Lead dictionary with basic info
        gtm_context: GTM.md content with ICP definition

    Returns:
        Formatted prompt string
    """
    return CLASSIFICATION_PROMPT.format(
        gtm_context=gtm_context,
        email=lead.get("email", "N/A"),
        name=lead.get("name", "N/A"),
        company=lead.get("company", "N/A"),
        job_title=lead.get("job_title", "N/A"),
        linkedin_url=lead.get("linkedin_url", "N/A")
    )


async def classify_single_lead(lead: Dict, llm: ChatOpenAI, gtm_context: str) -> Dict:
    """
    Classify a single lead using LLM.

    Args:
        lead: Lead dictionary with enriched data
        llm: ChatOpenAI instance
        gtm_context: GTM.md content with ICP definition

    Returns:
        Classification result dictionary
    """
    prompt = get_classification_prompt(lead, gtm_context)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result_text = response.content

        # Extract token usage
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            metadata = response.usage_metadata
            usage = {
                'input_tokens': metadata.get('input_tokens', 0),
                'output_tokens': metadata.get('output_tokens', 0),
                'total_tokens': metadata.get('total_tokens', 0)
            }

            # Extract cached tokens if available
            if 'input_token_details' in metadata and metadata['input_token_details']:
                usage['cached_tokens'] = metadata['input_token_details'].get('cached_tokens', 0)
            else:
                usage['cached_tokens'] = 0

        # Parse JSON response
        result = json.loads(result_text)
        return {
            "lead": lead,
            "classification": result,
            "usage": usage,
            "error": None
        }
    except Exception as e:
        return {
            "lead": lead,
            "classification": {"relevant": False, "reason": f"Error: {str(e)}"},
            "usage": {},
            "error": str(e)
        }
