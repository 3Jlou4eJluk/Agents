"""State definitions for the POV Email Generator workflow."""

from typing import TypedDict, Optional, List, Dict, Any


class ProfileData(TypedDict, total=False):
    """Profile data for the target prospect."""
    company: str
    company_size: Optional[int]
    industry: Optional[str]
    recent_news: Optional[str]
    person_name: str
    person_title: str
    person_background: Optional[str]

    # Optional enriched fields from new format
    talking_points: Optional[List[str]]
    pain_points: Optional[List[str]]
    personalization_notes: Optional[List[str]]
    outreach_approach: Optional[str]


class EmailState(TypedDict):
    """State for the email generation workflow."""
    # Input
    profile_data: ProfileData

    # Generated content
    email_draft: str

    # Scores
    gtm_score: float
    pov_score: float

    # Feedback
    gtm_feedback: str
    pov_feedback: str

    # Control
    iteration: int

    # Optional: history tracking
    history: List[Dict[str, Any]]


def create_initial_state(profile_data: ProfileData) -> EmailState:
    """Create initial state from profile data."""
    return EmailState(
        profile_data=profile_data,
        email_draft="",
        gtm_score=0.0,
        pov_score=0.0,
        gtm_feedback="",
        pov_feedback="",
        iteration=0,
        history=[]
    )


def aggregate_feedback(gtm_feedback: str, pov_feedback: str,
                       gtm_score: float, pov_score: float) -> str:
    """Combine feedback from both agents."""

    # Determine which aspect needs more attention
    priority = "ICP/GTM fit" if gtm_score < pov_score else "POV framework adherence"
    if gtm_score == pov_score:
        priority = "both dimensions equally"

    feedback = f"""Previous attempt scores: GTM {gtm_score}/10, POV {pov_score}/10

ICP Validation Issues:
{gtm_feedback}

POV Framework Issues:
{pov_feedback}

Please revise the email to address both sets of concerns.
Priority: Focus on {priority}.
Maintain what's working while fixing the issues identified above.
"""
    return feedback
