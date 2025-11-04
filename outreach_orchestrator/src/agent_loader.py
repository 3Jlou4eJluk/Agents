"""
Agent Loader - loads and parses declarative agents from markdown files.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a declarative agent loaded from markdown."""

    name: str
    description: str
    role: str
    tools: List[str]
    model: str
    provider: str
    temperature: float
    max_iterations: int
    instructions: str  # Markdown content after frontmatter
    file_path: str

    # Optional metadata
    color: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'role': self.role,
            'tools': self.tools,
            'model': self.model,
            'provider': self.provider,
            'temperature': self.temperature,
            'max_iterations': self.max_iterations,
            'color': self.color,
            'file_path': self.file_path
        }


class AgentLoader:
    """Loads declarative agents from markdown files (Claude Code style)."""

    def __init__(self, agents_dir: str = "agents"):
        """
        Initialize agent loader.

        Args:
            agents_dir: Directory containing agent markdown files
        """
        self.agents_dir = Path(agents_dir)
        if not self.agents_dir.exists():
            raise FileNotFoundError(f"Agents directory not found: {self.agents_dir}")

        self._cache: Dict[str, AgentConfig] = {}

    def load_agent(self, agent_name: str) -> AgentConfig:
        """
        Load an agent from markdown file.

        Args:
            agent_name: Name of the agent (without .md extension)

        Returns:
            AgentConfig object

        Raises:
            FileNotFoundError: If agent file doesn't exist
            ValueError: If agent file is malformed
        """
        # Check cache first
        if agent_name in self._cache:
            logger.debug(f"Loading agent '{agent_name}' from cache")
            return self._cache[agent_name]

        # Find agent file
        agent_file = self.agents_dir / f"{agent_name}.md"
        if not agent_file.exists():
            raise FileNotFoundError(f"Agent file not found: {agent_file}")

        logger.debug(f"Loading agent from: {agent_file}")

        # Read file content
        with open(agent_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter and markdown
        config = self._parse_agent_file(content, str(agent_file))

        # Cache and return
        self._cache[agent_name] = config
        return config

    def load_all_agents(self) -> Dict[str, AgentConfig]:
        """
        Load all agents from the agents directory.

        Returns:
            Dictionary mapping agent names to AgentConfig objects
        """
        agents = {}

        for agent_file in self.agents_dir.glob("*.md"):
            agent_name = agent_file.stem
            try:
                config = self.load_agent(agent_name)
                agents[agent_name] = config
                logger.info(f"✓ Loaded agent: {agent_name}")
            except Exception as e:
                logger.error(f"✗ Failed to load agent {agent_name}: {e}")

        return agents

    def _parse_agent_file(self, content: str, file_path: str) -> AgentConfig:
        """
        Parse agent markdown file with YAML frontmatter.

        Format:
        ---
        name: agent-name
        description: Agent description
        role: research|writing|review
        tools: [tool1, tool2]
        model: model-name
        provider: openai|deepseek|claude
        temperature: 0.7
        max_iterations: 20
        ---

        # Agent instructions in markdown
        ...

        Args:
            content: File content
            file_path: Path to file (for error messages)

        Returns:
            AgentConfig object

        Raises:
            ValueError: If file is malformed or missing required fields
        """
        # Extract YAML frontmatter
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)

        if not frontmatter_match:
            raise ValueError(f"Agent file missing YAML frontmatter: {file_path}")

        frontmatter_str = frontmatter_match.group(1)
        markdown_content = frontmatter_match.group(2).strip()

        # Parse YAML
        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter in {file_path}: {e}")

        # Validate required fields
        required_fields = ['name', 'description', 'role', 'model', 'provider', 'temperature', 'max_iterations']
        missing_fields = [f for f in required_fields if f not in frontmatter]

        if missing_fields:
            raise ValueError(f"Missing required fields in {file_path}: {missing_fields}")

        # Parse tools (can be list or single string)
        tools = frontmatter.get('tools', [])
        if isinstance(tools, str):
            tools = [tools]
        elif tools is None:
            tools = []

        # Create AgentConfig
        config = AgentConfig(
            name=frontmatter['name'],
            description=frontmatter['description'],
            role=frontmatter['role'],
            tools=tools,
            model=frontmatter['model'],
            provider=frontmatter['provider'],
            temperature=float(frontmatter['temperature']),
            max_iterations=int(frontmatter['max_iterations']),
            instructions=markdown_content,
            file_path=file_path,
            color=frontmatter.get('color'),
            metadata={k: v for k, v in frontmatter.items()
                     if k not in required_fields + ['tools', 'color']}
        )

        return config

    def get_agent_summary(self, agent_name: str) -> str:
        """
        Get a brief summary of an agent (for logging/debugging).

        Args:
            agent_name: Name of the agent

        Returns:
            Human-readable summary string
        """
        config = self.load_agent(agent_name)

        tools_str = ', '.join(config.tools) if config.tools else 'none'

        return (
            f"Agent: {config.name}\n"
            f"  Role: {config.role}\n"
            f"  Model: {config.provider}/{config.model} (temp={config.temperature})\n"
            f"  Tools: {tools_str}\n"
            f"  Max iterations: {config.max_iterations}\n"
            f"  Description: {config.description}"
        )

    def clear_cache(self):
        """Clear the agent cache (useful for reloading during development)."""
        self._cache.clear()
        logger.debug("Agent cache cleared")


# Convenience function for quick agent loading
def load_agent(agent_name: str, agents_dir: str = "agents") -> AgentConfig:
    """
    Convenience function to load a single agent.

    Args:
        agent_name: Name of the agent
        agents_dir: Directory containing agent files

    Returns:
        AgentConfig object
    """
    loader = AgentLoader(agents_dir)
    return loader.load_agent(agent_name)


# Example usage
if __name__ == "__main__":
    import sys

    # Test loading agents
    try:
        loader = AgentLoader("agents")

        # Load all agents
        print("Loading all agents...")
        agents = loader.load_all_agents()
        print(f"\n✓ Loaded {len(agents)} agents\n")

        # Print summaries
        for name, config in agents.items():
            print("=" * 60)
            print(loader.get_agent_summary(name))
            print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
