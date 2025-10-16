"""GTMAgent for validating ICP fit and GTM alignment."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    GTM_MANIFEST,
)
from ..state import EmailState


class GTMAgent:
    """Agent responsible for validating ICP fit and GTM alignment."""

    def __init__(self):
        """Initialize the GTMAgent with DeepSeek model."""
        self.llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=0.3,  # Lower temperature for evaluation
        )

        self.system_prompt = f"""You are an ICP validator. Evaluate email against go_to_market_manifest.md criteria.

{GTM_MANIFEST}

Evaluate the email holistically and provide a score from 1 to 10 based on how well it aligns with the ICP and GTM criteria.

Output format (EXACTLY this structure):
Score: X/10
Issues:
- [list specific mismatches, one per line]
Fix:
- [concrete changes needed, one per line]

Be critical but fair. A score of 8+ means strong ICP match."""

    def validate(self, state: EmailState) -> EmailState:
        """Validate the email against ICP criteria."""
        email_draft = state["email_draft"]
        profile = state["profile_data"]

        # Build the validation prompt
        profile_text = self._format_profile(profile)
        user_prompt = f"""Evaluate this email against ICP criteria:

Email:
{email_draft}

Profile:
{profile_text}

Provide score and feedback following the exact format specified."""

        # Get validation
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        feedback = response.content.strip()

        # Parse score
        score = self._parse_score(feedback)

        # Update state
        state["gtm_score"] = score
        state["gtm_feedback"] = feedback

        return state

    def _format_profile(self, profile: dict) -> str:
        """Format profile data into a readable string."""
        lines = []
        lines.append(f"Person: {profile['person_name']} - {profile['person_title']}")
        lines.append(f"Company: {profile['company']}")

        if profile.get("company_size"):
            lines.append(f"Size: {profile['company_size']} employees")

        if profile.get("industry"):
            lines.append(f"Industry: {profile['industry']}")

        if profile.get("recent_news"):
            lines.append(f"Context: {profile['recent_news']}")

        return "\n".join(lines)

    def _parse_score(self, feedback: str) -> float:
        """Parse score from feedback text."""
        try:
            # Look for "Score: X/10" or "Score: X.X/10"
            lines = feedback.split("\n")
            for line in lines:
                if line.strip().lower().startswith("score:"):
                    # Extract the number before "/10"
                    score_part = line.split(":")[1].strip()
                    score_str = score_part.split("/")[0].strip()
                    return float(score_str)
        except Exception as e:
            print(f"Warning: Could not parse score from GTM feedback: {e}")
            return 0.0

        return 0.0
