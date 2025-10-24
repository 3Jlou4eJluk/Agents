"""
Lead classification functionality (from cold-outreach-agent).
"""

import json
from typing import Dict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage


CLASSIFICATION_PROMPT = """You are an expert ICP researcher analyzing if this person matches our target profile.

## Target ICP Context:
{gtm_context}

## Profile to Analyze:
Email: {email}
Name: {name}
Company: {company}
Job Title: {job_title}
LinkedIn URL: {linkedin_url}

## Your Analysis Task:
Based on the provided ICP context, analyze if this lead matches the target profile.

Consider:
1. **Role & Seniority**: Does their position match decision-making criteria?
2. **Company Context**: Company size, industry, growth stage
3. **Pain Points**: Do they likely face the problems we solve?
4. **Decision Authority**: Can they influence purchasing decisions?

Return ONLY valid JSON:
{{
  "relevant": true,
  "reason": "Specific signals found (role context, pain points, company size, decision authority)"
}}

or

{{
  "relevant": false,
  "reason": "Why they don't match (wrong seniority, company size, or function)"
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
