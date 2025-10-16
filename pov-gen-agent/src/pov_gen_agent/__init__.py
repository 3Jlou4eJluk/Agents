"""POV Email Generator - A LangGraph-based cold email generator using DeepSeek-V3."""

from .graph import create_pov_graph, generate_email

__version__ = "0.1.0"
__all__ = ["create_pov_graph", "generate_email"]
