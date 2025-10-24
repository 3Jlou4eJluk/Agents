"""
Example: Using DeepSeek models with PlanMCP Agent.

DeepSeek provides powerful open-source models with OpenAI-compatible API:
- deepseek-chat: General purpose chat model
- deepseek-coder: Specialized for coding tasks

Get your API key from: https://platform.deepseek.com/
"""

import asyncio
from plan_mcp_agent.agent import PlanMCPAgent


async def example_deepseek_chat():
    """Example using DeepSeek Chat model."""

    print("=" * 60)
    print("Example 1: DeepSeek Chat (general purpose)")
    print("=" * 60)

    async with PlanMCPAgent(
        model="deepseek:deepseek-chat",
        max_iterations=10
    ) as agent:
        result = await agent.run(
            "Создай файл greeting.py с функцией, которая принимает имя и возвращает приветствие"
        )


async def example_deepseek_coder():
    """Example using DeepSeek Coder (optimized for code)."""

    print("\n" + "=" * 60)
    print("Example 2: DeepSeek Coder (code-focused)")
    print("=" * 60)

    async with PlanMCPAgent(
        model="deepseek:deepseek-coder",
        max_iterations=15
    ) as agent:
        result = await agent.run(
            """
            Найди все Python файлы в текущей директории,
            проанализируй их структуру и создай краткий отчет.
            """
        )


async def example_deepseek_with_mcp():
    """Example using DeepSeek with MCP servers."""

    print("\n" + "=" * 60)
    print("Example 3: DeepSeek + MCP servers")
    print("=" * 60)

    mcp_config = {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "transport": "stdio"
        }
    }

    async with PlanMCPAgent(
        model="deepseek:deepseek-chat",
        mcp_config=mcp_config,
        max_iterations=10
    ) as agent:
        result = await agent.run(
            "Используй MCP filesystem сервер, чтобы посмотреть содержимое /tmp"
        )


async def compare_models():
    """Compare different models on the same task."""

    print("\n" + "=" * 60)
    print("Example 4: Comparing models")
    print("=" * 60)

    task = "Создай простую функцию для вычисления факториала"

    models = [
        "deepseek:deepseek-chat",
        "deepseek:deepseek-coder",
        # "anthropic:claude-3-5-sonnet-20241022",  # Uncomment if you have API key
        # "openai:gpt-4",  # Uncomment if you have API key
    ]

    for model in models:
        print(f"\n--- Testing {model} ---")
        try:
            async with PlanMCPAgent(model=model, max_iterations=5) as agent:
                await agent.run(task)
        except Exception as e:
            print(f"Error with {model}: {e}")


async def main():
    """Run all examples."""

    print("""
    ╔════════════════════════════════════════════════════════╗
    ║         DeepSeek Integration Examples                  ║
    ║         Мощные open-source модели для кода             ║
    ╚════════════════════════════════════════════════════════╝

    Убедитесь, что в .env файле установлен DEEPSEEK_API_KEY

    """)

    # Выберите примеры для запуска
    await example_deepseek_chat()
    # await example_deepseek_coder()
    # await example_deepseek_with_mcp()
    # await compare_models()


if __name__ == "__main__":
    asyncio.run(main())
