"""
Configuration loader for the orchestrator.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from .rate_limiter import TokenBucketRateLimiter, RateLimitedLLM
from .logger import get_logger

logger = get_logger(__name__)

# Global rate limiters (one per provider)
_RATE_LIMITERS: Dict[str, TokenBucketRateLimiter] = {}


def get_rate_limiter(provider: str, config: Dict[str, Any]) -> Optional[TokenBucketRateLimiter]:
    """
    Get or create a rate limiter for a provider.

    Args:
        provider: Provider name (e.g., 'openai', 'deepseek')
        config: Configuration dictionary

    Returns:
        Rate limiter instance or None if disabled
    """
    # Check if rate limiting is enabled
    rate_limiting_config = config.get('rate_limiting', {})
    if not rate_limiting_config.get('enabled', False):
        return None

    # Check if provider has rate limiting config
    provider_config = rate_limiting_config.get(provider)
    if not provider_config:
        logger.warning(f"No rate limiting config for provider '{provider}', rate limiting disabled")
        return None

    # Return existing rate limiter if available (singleton)
    if provider in _RATE_LIMITERS:
        return _RATE_LIMITERS[provider]

    # Create new rate limiter
    # Prefer RPM (requests_per_minute) if provided, fall back to RPS
    rpm = None
    if 'requests_per_minute' in provider_config:
        rpm = float(provider_config.get('requests_per_minute') or 0)
    elif 'rpm' in provider_config:
        rpm = float(provider_config.get('rpm') or 0)

    if rpm is not None and rpm > 0:
        rate = rpm / 60.0
    else:
        rate = float(provider_config.get('requests_per_second', 10))

    burst = int(provider_config.get('burst', 20))

    rate_limiter = TokenBucketRateLimiter(rate=rate, burst=burst)
    _RATE_LIMITERS[provider] = rate_limiter

    # Log both RPM and RPS for clarity
    logger.info(
        f"✓ Rate limiter for '{provider}': {rate*60:.2f} req/min ({rate:.3f} req/sec), burst={burst}"
    )

    return rate_limiter


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


def create_llm(config: Dict[str, Any], model_config: Dict[str, Any], **kwargs) -> Union[ChatOpenAI, ChatAnthropic]:
    """
    Create LLM client based on provider configuration.

    Args:
        config: Full configuration dictionary
        model_config: Model-specific config (from classification or letter_generation)
        **kwargs: Additional arguments to pass to ChatOpenAI or ChatAnthropic

    Returns:
        ChatOpenAI or ChatAnthropic instance configured for the specified provider
    """
    provider = model_config.get("provider", "deepseek")
    model = model_config.get("model", "deepseek-chat")
    temperature = model_config.get("temperature", 0.7)

    # Get provider config
    providers = config.get("providers", {})
    provider_config = providers.get(provider, {})

    # Get API key
    if "api_key" in provider_config:
        # Direct API key in config
        api_key = provider_config["api_key"]
    elif "api_key_env" in provider_config:
        # API key from environment variable
        api_key = os.getenv(provider_config["api_key_env"])
    else:
        # Fallback to default env vars
        if provider == "claude":
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        else:
            api_key = os.getenv("DEEPSEEK_API_KEY")

    # Create LLM based on provider
    if provider == "claude":
        # Use ChatAnthropic for Claude
        llm = ChatAnthropic(
            model=model,
            api_key=api_key,
            temperature=temperature,
            **kwargs
        )
        logger.debug(f"Created ChatAnthropic with model={model}")
    else:
        # Use ChatOpenAI for OpenAI and DeepSeek
        # Get base URL
        base_url = provider_config.get("base_url", "https://api.openai.com/v1")

        # Handle JSON mode (optional, controlled by config)
        # Note: JSON mode is incompatible with tool calling in most providers
        # Only enable if explicitly requested via use_json_mode flag
        model_kwargs = kwargs.get('model_kwargs', {})

        # Check for existing response_format in kwargs (might come from classification stage)
        has_existing_format = 'model_kwargs' in kwargs and 'response_format' in kwargs['model_kwargs']

        if model_config.get('use_json_mode', False) and not has_existing_format:
            # Enable JSON mode (OpenAI, DeepSeek support)
            # WARNING: This will prevent tool calling!
            model_kwargs['response_format'] = {"type": "json_object"}
            kwargs['model_kwargs'] = model_kwargs
        elif 'response_format' in model_config and not has_existing_format:
            # Legacy: support old response_format config
            response_format = model_config['response_format']
            if response_format == 'json_object':
                model_kwargs['response_format'] = {"type": "json_object"}
            kwargs['model_kwargs'] = model_kwargs

        # Create LLM
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            **kwargs
        )
        logger.debug(f"Created ChatOpenAI with model={model}, base_url={base_url}")

    # Wrap with rate limiter if enabled
    rate_limiter = get_rate_limiter(provider, config)
    if rate_limiter:
        llm = RateLimitedLLM(llm, rate_limiter)
        logger.debug(f"LLM wrapped with rate limiter for provider '{provider}'")

    return llm
