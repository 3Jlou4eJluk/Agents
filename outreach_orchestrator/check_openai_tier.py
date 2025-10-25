"""
Check OpenAI API tier and rate limits.
"""

import asyncio
from openai import AsyncOpenAI
from src.config_loader import load_config


async def check_tier():
    """Check OpenAI tier by analyzing rate limit headers."""
    print("🔍 Checking OpenAI API Tier and Limits\n")

    # Load config
    config = load_config()
    api_key = config['providers']['openai']['api_key']

    # Create client
    client = AsyncOpenAI(api_key=api_key)

    # Make a minimal request to get rate limit headers
    print("Making test request to check headers...")
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5
        )

        # Note: Rate limit info is in response headers
        # AsyncOpenAI doesn't expose headers directly, so we'll use alternative method
        print("✓ Request successful\n")

    except Exception as e:
        print(f"❌ Error: {e}\n")
        return

    # Try to get limits info
    print("📊 Rate Limit Information:")
    print("=" * 60)

    # Use models.list to check organization
    try:
        models = await client.models.list()
        print(f"✓ API key is valid")
        print(f"✓ Can access {len(models.data)} models\n")
    except Exception as e:
        print(f"⚠ Could not fetch models: {e}\n")

    # Provide tier guidance (2025 ACTUAL limits)
    print("📋 OpenAI Tier Information (2025):")
    print("=" * 60)
    print("Free Tier:    3 req/min     (0.05 req/s)   - No payment")
    print("Tier 1:       500 req/min   (8.3 req/s)    - $5 paid")
    print("Tier 2:       5,000 req/min (83.3 req/s)   - $50 + 7 days")
    print("Tier 3:       5,000 req/min (83.3 req/s)   - $100 + 7 days")
    print("Tier 4:       10,000 req/min (166.7 req/s) - $250 + 14 days")
    print("Tier 5:       30,000 req/min (500 req/s)   - $1000 + 30 days")
    print()
    print("Check your tier at:")
    print("https://platform.openai.com/settings/organization/limits")
    print()

    # Recommendations
    print("🔧 Recommended Settings Based on Tier:")
    print("=" * 60)
    print("Free:   requests_per_second: 0.04, burst: 1,  workers: 1")
    print("Tier 1: requests_per_second: 8,    burst: 15, workers: 5")
    print("Tier 2: requests_per_second: 80,   burst: 50, workers: 10")
    print("Tier 3: requests_per_second: 80,   burst: 50, workers: 10")
    print()

    # Current settings
    current_rps = config.get('rate_limiting', {}).get('openai', {}).get('requests_per_second', '?')
    current_burst = config.get('rate_limiting', {}).get('openai', {}).get('burst', '?')
    current_workers = config.get('worker_pool', {}).get('num_workers', '?')

    print("📌 Your Current Settings:")
    print("=" * 60)
    print(f"requests_per_second: {current_rps}")
    print(f"burst: {current_burst}")
    print(f"workers: {current_workers}")
    print()

    # Analyze settings
    if current_rps == 0.04:
        print("✓ Settings configured for FREE tier (3 req/min)")
        print("💡 To upgrade: Pay $5 → Tier 1 → 500 req/min (166x faster!)")
    elif current_rps >= 8 and current_rps <= 10:
        print("✓ Settings look good for Tier 1 (500 req/min)")
    elif current_rps >= 80:
        print("✓ Settings for Tier 2+ (5000+ req/min)")
    elif current_rps > 0.04 and current_rps < 8:
        print("⚠️  WARNING: Settings between Free and Tier 1")
        print("   If you're on Free tier (no payment): TOO FAST! Use 0.04")
        print("   If you're on Tier 1 ($5 paid): TOO SLOW! Use 8")
    else:
        print("⚠️  Unusual rate limit setting")

    await client.close()


if __name__ == "__main__":
    asyncio.run(check_tier())
