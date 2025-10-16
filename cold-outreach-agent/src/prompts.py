"""
Prompt templates for the lead pipeline.
"""

CLASSIFICATION_PROMPT = """You are an expert ICP researcher analyzing if this person matches our target profile.

## Target ICP Context:
ResolveOnce helps teams (50-1,500 employees) struggling with:
- Incomplete ticket closures ("resolution horror")
- Knowledge loss from 40% annual agent turnover
- Ticket bouncing (customers explaining problems multiple times)
- Agents wasting time re-solving already-solved problems

Target decision-makers face operational chaos in support/IT/customer success operations.

## Profile to Analyze:
Email: {email}
Name: {name}
Company: {company}
Job Title: {job_title}
LinkedIn URL: {linkedin_url}

Full LinkedIn Profile Data:
{profile_data}

## Your Analysis Task:
Study their ENTIRE profile (not just job title) to identify:

1. **Workflow Signals**: Do they manage support operations, IT teams, customer success, service desks, or operational processes where tickets/requests are handled?

2. **Pain Point Indicators**: Any mentions of team management, process improvement, knowledge management, turnover challenges, operational efficiency, or scaling support operations?

3. **Decision-Making Authority**: Are they in a position to influence or decide on tools/processes for their team (manager, director, head of, VP, founder, operations lead)?

4. **Company Context**: Company size 50-1,500 employees? Growing company with scaling challenges? B2B/SaaS environment? Industries with heavy support operations?

5. **Experience Patterns**: Past roles showing progression in support/IT/operations leadership? Experience with team challenges, process optimization, or tool evaluation?

**Don't just match keywords - look for authentic signals that this person deals with operational chaos in handling support/requests/tickets.**

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

CUSTOM_ANALYSIS_PROMPT = """You are analyzing a highly relevant lead for a B2B SaaS outreach campaign.

Profile Information:
Email: {email}
Name: {name}
Company: {company}
Job Title: {job_title}
LinkedIn URL: {linkedin_url}

Enriched Profile Data:
{profile_data}

{custom_prompt}

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no text outside the JSON object.
Return your analysis as a valid JSON object.
"""


def get_classification_prompt(lead: dict, enriched_data: dict) -> str:
    """
    Format the classification prompt with lead data.

    Uses enriched_data from Bright Data as primary source,
    falls back to CSV raw_data if enrichment failed.
    """
    # Check if enrichment failed
    has_error = enriched_data.get("error") is not None
    raw = lead.get("raw_data", {})

    # Merge data: prioritize enriched, fallback to CSV
    if has_error or not enriched_data:
        # Use CSV data as fallback
        profile_data = {
            "headline": raw.get("headline", "N/A"),
            "job_level": raw.get("jobLevel", "N/A"),
            "industry": raw.get("industry", "N/A"),
            "company_size": raw.get("companyHeadCount", "N/A"),
            "company_description": raw.get("companyDescription", "N/A"),
            "location": raw.get("location", "N/A"),
            "source": "CSV (Bright Data enrichment failed)"
        }
    else:
        # Use Bright Data enriched data
        profile_data = enriched_data
        profile_data["source"] = "Bright Data (fresh)"

    return CLASSIFICATION_PROMPT.format(
        email=lead.get("email", "N/A"),
        name=lead.get("name", "N/A"),
        company=lead.get("company", "N/A"),
        job_title=lead.get("job_title", "N/A"),
        linkedin_url=lead.get("linkedin_url", "N/A"),
        profile_data=profile_data
    )


def get_custom_analysis_prompt(lead: dict, enriched_data: dict, custom_prompt: str) -> str:
    """
    Format the custom analysis prompt with lead data.

    Uses enriched_data from Bright Data as primary source,
    falls back to CSV raw_data if enrichment failed.
    """
    # Check if enrichment failed
    has_error = enriched_data.get("error") is not None
    raw = lead.get("raw_data", {})

    # Merge data: prioritize enriched, fallback to CSV
    if has_error or not enriched_data:
        # Use CSV data as fallback
        profile_data = {
            "headline": raw.get("headline", "N/A"),
            "job_level": raw.get("jobLevel", "N/A"),
            "industry": raw.get("industry", "N/A"),
            "company_size": raw.get("companyHeadCount", "N/A"),
            "company_website": raw.get("companyWebsite", "N/A"),
            "company_description": raw.get("companyDescription", "N/A"),
            "location": raw.get("location", "N/A"),
            "connections": raw.get("connectionCount", "N/A"),
        }
    else:
        # Use Bright Data enriched data
        profile_data = enriched_data

    return CUSTOM_ANALYSIS_PROMPT.format(
        email=lead.get("email", "N/A"),
        name=lead.get("name", "N/A"),
        company=lead.get("company", "N/A"),
        job_title=lead.get("job_title", "N/A"),
        linkedin_url=lead.get("linkedin_url", "N/A"),
        profile_data=profile_data,
        custom_prompt=custom_prompt
    )
