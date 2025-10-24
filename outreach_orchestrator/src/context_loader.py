"""
Context Loader - loads agent personality from context directory.
"""

from pathlib import Path
from typing import Dict


class ContextLoader:
    """
    Loads context files (GTM.md, guides, instructions) for agent personality.
    """

    def __init__(self, context_dir: str = "context"):
        """
        Initialize context loader.

        Args:
            context_dir: Path to context directory
        """
        self.context_dir = Path(context_dir)

        if not self.context_dir.exists():
            raise FileNotFoundError(
                f"Context directory not found: {context_dir}\n"
                f"Please create it and add:\n"
                f"  - GTM.md (copy from GTM.md.example)\n"
                f"  - agent_instruction.md (copy from agent_instruction.md.example)\n"
                f"  - guides/ (copy examples and customize)"
            )

    def load_context(self) -> Dict[str, str]:
        """
        Load all context files.

        Returns:
            Dictionary with loaded context
        """
        context = {
            'gtm': self._load_gtm(),
            'instruction': self._load_instruction(),
            'guides': self._load_guides()
        }

        return context

    def _load_gtm(self) -> str:
        """Load GTM.md file."""
        gtm_path = self.context_dir / "GTM.md"

        if not gtm_path.exists():
            raise FileNotFoundError(
                f"GTM.md not found in {self.context_dir}\n"
                f"Please copy GTM.md.example to GTM.md and fill it out."
            )

        with open(gtm_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_instruction(self) -> str:
        """Load agent_instruction.md file."""
        instruction_path = self.context_dir / "agent_instruction.md"

        if not instruction_path.exists():
            raise FileNotFoundError(
                f"agent_instruction.md not found in {self.context_dir}\n"
                f"Please copy agent_instruction.md.example to agent_instruction.md"
            )

        with open(instruction_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_guides(self) -> str:
        """Load all guide files from guides/ directory."""
        guides_dir = self.context_dir / "guides"

        if not guides_dir.exists():
            print(f"⚠ Warning: guides/ directory not found in {self.context_dir}")
            return ""

        guides_content = []

        # Load all .md files from guides/
        for guide_file in sorted(guides_dir.glob("*.md")):
            with open(guide_file, 'r', encoding='utf-8') as f:
                guides_content.append(f"# {guide_file.stem}\n\n{f.read()}")

        if not guides_content:
            print(f"⚠ Warning: No guide files found in {guides_dir}")
            return ""

        return "\n\n---\n\n".join(guides_content)

    def format_for_agent(self, context: Dict[str, str]) -> str:
        """
        Format context for inclusion in agent task.

        Args:
            context: Loaded context dictionary

        Returns:
            Formatted context string
        """
        return f"""
# PROJECT CONTEXT

## Go-To-Market Strategy
{context['gtm']}

---

## Writing Guides
{context['guides']}

---

## Task Instructions
{context['instruction']}
"""
