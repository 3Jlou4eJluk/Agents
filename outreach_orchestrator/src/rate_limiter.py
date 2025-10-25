"""
Rate limiting middleware for LLM API calls.

Prevents 429 (Too Many Requests) errors by controlling request frequency.
"""

import asyncio
import time
from typing import Any, Dict, Optional
from langchain_openai import ChatOpenAI
from .logger import get_logger

logger = get_logger(__name__)


class TokenBucketRateLimiter:
    """
    Token bucket algorithm for rate limiting.

    Allows bursts while maintaining average rate limit.
    Thread-safe for concurrent async operations.
    """

    def __init__(self, rate: float, burst: int):
        """
        Initialize rate limiter.

        Args:
            rate: Requests per second (e.g., 3.0 for 3 req/sec)
            burst: Maximum burst size (e.g., 5 for 5 simultaneous requests)
        """
        self.rate = rate  # tokens per second
        self.burst = burst  # max tokens in bucket
        self.tokens = float(burst)  # current tokens
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """
        Acquire a token (wait if necessary).

        This method will block until a token is available.
        """
        async with self.lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Add tokens based on elapsed time
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now

                # If we have a token, consume it and return
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Calculate wait time
                wait_time = (1.0 - self.tokens) / self.rate

                if wait_time > 0.1:  # Log only significant waits
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")

                # Release lock and wait
                await asyncio.sleep(wait_time)


class RateLimitedLLM:
    """
    Wrapper for ChatOpenAI that applies rate limiting.

    Transparently intercepts all LLM calls and applies rate limiting
    before forwarding to the underlying LLM.
    """

    def __init__(self, llm: ChatOpenAI, rate_limiter: Optional[TokenBucketRateLimiter] = None):
        """
        Initialize rate-limited LLM.

        Args:
            llm: The underlying ChatOpenAI instance
            rate_limiter: Rate limiter to use (None = no limiting)
        """
        self._llm = llm
        self._rate_limiter = rate_limiter

    async def ainvoke(self, *args, **kwargs):
        """
        Async invoke with rate limiting.

        Acquires rate limit token before calling underlying LLM.
        Retries on 429 errors with exponential backoff.
        """
        max_retries = 3
        base_delay = 2.0  # seconds

        for attempt in range(max_retries + 1):
            if self._rate_limiter:
                await self._rate_limiter.acquire()

            try:
                return await self._llm.ainvoke(*args, **kwargs)
            except Exception as e:
                # Check if this is a 429 error
                error_str = str(e).lower()
                is_429 = '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str

                if is_429 and attempt < max_retries:
                    # Exponential backoff: 2s, 4s, 8s
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"429 Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Not a 429 or out of retries
                    raise

    def invoke(self, *args, **kwargs):
        """Sync invoke (delegates to underlying LLM)."""
        # Note: sync invoke doesn't apply rate limiting
        # If needed, convert to async or add sync rate limiting
        return self._llm.invoke(*args, **kwargs)

    def bind_tools(self, tools):
        """
        Bind tools and return a new rate-limited LLM.

        Important: Returns a new RateLimitedLLM wrapping the bound LLM.
        """
        bound_llm = self._llm.bind_tools(tools)
        return RateLimitedLLM(bound_llm, self._rate_limiter)

    def __getattr__(self, name):
        """
        Proxy all other attributes/methods to underlying LLM.

        This makes RateLimitedLLM transparent for most operations.
        """
        return getattr(self._llm, name)
