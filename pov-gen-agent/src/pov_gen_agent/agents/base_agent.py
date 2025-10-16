"""BaseAgent for generating POV-based cold emails."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    TEMPERATURE,
    POV_FRAMEWORK,
    EXAMPLE,
    GTM_MANIFEST,
    WORKFLOW,
)
from ..state import EmailState


class BaseAgent:
    """Agent responsible for generating POV-based email drafts."""

    def __init__(self):
        """Initialize the BaseAgent with DeepSeek model."""
        self.llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=TEMPERATURE,
        )

        self.system_prompt = f"""You are my cold email writer assistant. We want high reply rate in emails. Yet we neither sell our product in first email, nor even trying to hard book a meeting. Instead we are using POV FRAMEWORK. Ultra think on how you connect the dots about Context + Observation/Insight. The thought must be logical as output i expect a markdown document. My name is Almas btw, for email signature.

## POV Framework
{POV_FRAMEWORK}

## Example of Great Email
{EXAMPLE}

## Go-to-Market Context
{GTM_MANIFEST}

## Workflow
{WORKFLOW}

Your task is to generate a compelling, POV-based cold email that:
1. Uses specific context from the prospect's profile
2. Demonstrates a unique, valuable insight
3. Articulates a relevant problem/opportunity
4. Ends with a soft, non-pushy CTA
5. Is 80-120 words
6. Feels peer-to-peer, not salesy

Output ONLY the email body in markdown format. Do not include subject line headers unless specifically needed.
"""

    def generate(self, state: EmailState) -> EmailState:
        """Generate an email draft based on profile data and optional feedback."""
        profile = state["profile_data"]
        feedback = ""

        # If this is a regeneration, include feedback
        if state["iteration"] > 0:
            from ..state import aggregate_feedback
            feedback = aggregate_feedback(
                state["gtm_feedback"],
                state["pov_feedback"],
                state["gtm_score"],
                state["pov_score"],
            )

        # Build the user prompt
        profile_text = self._format_profile(profile)

        if feedback:
            user_prompt = f"""Regenerate the email based on this feedback:

{feedback}

---

Profile Data:
{profile_text}

Previous Draft:
{state['email_draft']}

---

Please generate an improved version addressing the feedback while maintaining the POV framework."""
        else:
            user_prompt = f"""Generate a POV-based cold email for this prospect:

{profile_text}

Remember: Context → Observation → Problem → Soft CTA
Keep it 80-120 words.
Be specific, valuable, and non-pushy."""

        # Generate the email
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm.invoke(messages)
        email_draft = response.content.strip()

        # Update state
        state["email_draft"] = email_draft
        state["iteration"] += 1

        # Track history
        state["history"].append({
            "iteration": state["iteration"],
            "draft": email_draft,
            "gtm_score": state["gtm_score"],
            "pov_score": state["pov_score"],
        })

        return state

    def _format_profile(self, profile: dict) -> str:
        """Format profile data into a readable string."""
        lines = []
        lines.append(f"**Person:** {profile['person_name']}")
        lines.append(f"**Title:** {profile['person_title']}")

        if profile.get("person_background"):
            lines.append(f"**Background:** {profile['person_background']}")

        lines.append(f"\n**Company:** {profile['company']}")

        if profile.get("company_size"):
            lines.append(f"**Size:** {profile['company_size']} employees")

        if profile.get("industry"):
            lines.append(f"**Industry:** {profile['industry']}")

        if profile.get("recent_news"):
            lines.append(f"**Recent News:** {profile['recent_news']}")

        return "\n".join(lines)
