"""
Configuration loader for the orchestrator.
"""

import json
from pathlib import Path
from typing import Dict, Any


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file. If None, uses default.

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        # Default: config.json in project root
        project_root = Path(__file__).parent.parent
        config_path = project_root / "config.json"

    path = Path(config_path)

    if not path.exists():
        # Return defaults if config doesn't exist
        return get_default_config()

    with open(path, 'r') as f:
        config = json.load(f)

    return config


def get_default_config() -> Dict[str, Any]:
    """
    Get default configuration if config file doesn't exist.

    Returns:
        Default configuration dictionary
    """
    return {
        "models": {
            "classification": {
                "model": "deepseek-chat",
                "temperature": 0
            },
            "letter_generation": {
                "model": "deepseek-chat",
                "temperature": 0.7
            }
        },
        "worker_pool": {
            "num_workers": 5,
            "max_agent_iterations": 30
        }
    }


def get_classification_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get classification model configuration."""
    return config.get("models", {}).get("classification", {
        "model": "deepseek-chat",
        "temperature": 0
    })


def get_letter_generation_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get letter generation model configuration."""
    return config.get("models", {}).get("letter_generation", {
        "model": "deepseek-chat",
        "temperature": 0.7
    })
