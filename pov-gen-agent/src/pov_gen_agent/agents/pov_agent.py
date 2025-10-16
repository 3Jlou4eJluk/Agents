"""POVAgent for validating POV framework adherence."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    POV_FRAMEWORK,
    EXAMPLE,
)
from ..state import EmailState


class POVAgent:
    """Agent responsible for validating POV framework adherence."""

    def __init__(self):
        """Initialize the POVAgent with DeepSeek model."""
        self.llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=0.3,  # Lower temperature for evaluation
        )

        self.system_prompt = f"""You are a POV framework validator. Evaluate email structure against pov_framework.md and example.md.

{POV_FRAMEWORK}

{EXAMPLE}

Evaluate the email holistically and provide a score from 1 to 10 based on how well it follows the POV framework structure and principles.

Output format (EXACTLY this structure):
Score: X/10
Issues:
- [structural gaps, one per line]
Fix:
- [specific improvements, one per line]

Be critical about specificity and value. A score of 8+ means strong framework adherence."""

    def validate(self, state: EmailState) -> EmailState:
        """Validate the email against POV framework."""
        email_draft = state["email_draft"]

        # Build the validation prompt
        user_prompt = f"""Evaluate this email against the POV framework:

Email:
{email_draft}

Assess each component:
- Context: Is it specific and personalized?
- Observation: Is there a unique, valuable insight?
- Problem: Is it clearly articulated and relevant?
- CTA: Is it soft and non-pushy?

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
        state["pov_score"] = score
        state["pov_feedback"] = feedback

        return state

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
            print(f"Warning: Could not parse score from POV feedback: {e}")
            return 0.0

        return 0.0
