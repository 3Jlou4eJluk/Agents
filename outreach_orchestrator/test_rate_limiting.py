"""
Test script to verify rate limiting works correctly.
"""

import asyncio
import time
from src.config_loader import load_config, create_llm
from langchain_core.messages import HumanMessage


async def test_rate_limiting():
    """Test that rate limiting prevents 429 errors."""
    print("🧪 Testing Rate Limiting\n")

    # Load config
    config = load_config()

    # Get classification model config
    model_config = config['models']['classification']

    print(f"Provider: {model_config.get('provider', 'unknown')}")
    print(f"Model: {model_config['model']}")
    print(f"Rate limiting: {config.get('rate_limiting', {}).get('enabled', False)}\n")

    # Create LLM (should be wrapped with rate limiter)
    llm = create_llm(config, model_config)

    print(f"LLM type: {type(llm).__name__}")
    print(f"Has rate limiter: {hasattr(llm, '_rate_limiter')}")

    if hasattr(llm, '_rate_limiter') and llm._rate_limiter:
        print(f"Rate limiter config: {llm._rate_limiter.rate} req/sec, burst={llm._rate_limiter.burst}\n")

    # Test with multiple rapid requests
    print("🚀 Sending 10 rapid requests...")
    start = time.time()

    tasks = []
    for i in range(10):
        # Simple prompt to minimize cost
        task = llm.ainvoke([HumanMessage(content=f"Say 'Hello {i}'")])
        tasks.append(task)

    # Wait for all requests
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start

    print(f"\n✓ Completed in {elapsed:.2f}s")
    print(f"Average: {elapsed/10:.2f}s per request")

    # Check for errors
    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        print(f"\n❌ Found {len(errors)} errors:")
        for err in errors[:3]:  # Show first 3
            print(f"  - {type(err).__name__}: {str(err)[:100]}")
    else:
        print(f"\n✓ All requests succeeded (no 429 errors!)")

    # Calculate expected time
    rate_limit = config.get('rate_limiting', {}).get(
        model_config.get('provider', 'openai'), {}
    ).get('requests_per_second', 10)

    expected_min_time = 10 / rate_limit if rate_limit else 0
    print(f"\nExpected minimum time: {expected_min_time:.2f}s (at {rate_limit} req/s)")
    print(f"Actual time: {elapsed:.2f}s")

    if elapsed >= expected_min_time * 0.8:  # 80% threshold
        print("✓ Rate limiting is working!")
    else:
        print("⚠ Rate limiting may not be active (too fast)")


if __name__ == "__main__":
    asyncio.run(test_rate_limiting())
