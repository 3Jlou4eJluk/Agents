# DeepSeek Integration Guide

## О DeepSeek

DeepSeek - это китайский провайдер мощных open-source LLM моделей с API совместимым с OpenAI. Модели DeepSeek показывают отличные результаты в coding задачах и стоят значительно дешевле западных аналогов.

## Доступные модели

| Модель | Назначение | Контекст | Стоимость |
|--------|-----------|----------|-----------|
| `deepseek-chat` | Общего назначения | 64K tokens | ~$0.14/1M входных токенов |
| `deepseek-coder` | Специализация на коде | 64K tokens | ~$0.14/1M входных токенов |

## Получение API ключа

1. Зарегистрируйтесь на https://platform.deepseek.com/
2. Перейдите в раздел API Keys
3. Создайте новый ключ
4. Скопируйте ключ в `.env` файл

## Настройка

### 1. Добавьте API ключ

```bash
# .env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Базовое использование

```python
import asyncio
from plan_mcp_agent.agent import PlanMCPAgent

async def main():
    # Используем DeepSeek Chat
    async with PlanMCPAgent(
        model="deepseek:deepseek-chat"
    ) as agent:
        result = await agent.run("Твоя задача здесь")

asyncio.run(main())
```

### 3. CLI использование

```bash
# Экспортируйте API ключ
export DEEPSEEK_API_KEY=sk-xxxx

# Запустите с DeepSeek
uv run python main.py "Создай Python скрипт для парсинга JSON"
```

## Сравнение моделей

### deepseek-chat vs deepseek-coder

**deepseek-chat (общего назначения):**
- ✅ Хорош для: общие задачи, планирование, обсуждения
- ✅ Широкий кругозор
- ⚠️ Может быть менее точным в технических деталях

**deepseek-coder (специализация на коде):**
- ✅ Хорош для: написание кода, рефакторинг, отладка
- ✅ Более точные технические решения
- ✅ Лучше понимает паттерны кода
- ⚠️ Может быть менее гибким в non-coding задачах

### DeepSeek vs Claude vs GPT-4

| Критерий | DeepSeek | Claude Sonnet | GPT-4 |
|----------|----------|---------------|-------|
| **Стоимость** | ⭐⭐⭐⭐⭐ Дешево | ⭐⭐⭐ Средне | ⭐⭐ Дорого |
| **Coding** | ⭐⭐⭐⭐ Отлично | ⭐⭐⭐⭐⭐ Превосходно | ⭐⭐⭐⭐ Отлично |
| **Reasoning** | ⭐⭐⭐⭐ Хорошо | ⭐⭐⭐⭐⭐ Превосходно | ⭐⭐⭐⭐⭐ Превосходно |
| **Русский язык** | ⭐⭐⭐⭐ Хорошо | ⭐⭐⭐⭐⭐ Отлично | ⭐⭐⭐⭐⭐ Отлично |
| **Tool calling** | ⭐⭐⭐⭐ Хорошо | ⭐⭐⭐⭐⭐ Отлично | ⭐⭐⭐⭐⭐ Отлично |

## Примеры использования

### Пример 1: Простая задача

```python
async with PlanMCPAgent(model="deepseek:deepseek-chat") as agent:
    await agent.run("Создай функцию для валидации email адресов")
```

### Пример 2: Анализ кода

```python
async with PlanMCPAgent(model="deepseek:deepseek-coder") as agent:
    await agent.run("""
        Проанализируй структуру проекта:
        1. Найди все Python модули
        2. Определи основные компоненты
        3. Создай диаграмму зависимостей
    """)
```

### Пример 3: С MCP серверами

```python
mcp_config = {
    "git": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-git"],
        "transport": "stdio"
    }
}

async with PlanMCPAgent(
    model="deepseek:deepseek-coder",
    mcp_config=mcp_config
) as agent:
    await agent.run("Покажи последние коммиты и создай changelog")
```

### Пример 4: Смешанное использование

```python
# Для планирования - Claude
planner = PlanMCPAgent(model="anthropic:claude-3-5-sonnet-20241022")

# Для выполнения - DeepSeek (дешевле)
executor = PlanMCPAgent(model="deepseek:deepseek-coder")
```

## Рекомендации

### Когда использовать DeepSeek

✅ **Рекомендуется:**
- Coding задачи
- Большие объемы запросов (экономия)
- Анализ и рефакторинг кода
- Автоматизация разработки
- Обучение и эксперименты

⚠️ **С осторожностью:**
- Критически важные задачи (используйте Claude/GPT-4)
- Сложное reasoning требующее глубокого понимания
- Задачи требующие максимальной точности

### Оптимизация стоимости

```python
# Стратегия 1: Claude для планирования, DeepSeek для выполнения
async with PlanMCPAgent(model="anthropic:claude-3-5-sonnet-20241022") as agent:
    plan = await agent.create_plan(objective)

# Переключаемся на DeepSeek для выполнения
async with PlanMCPAgent(model="deepseek:deepseek-coder") as agent:
    result = await agent.execute_plan(plan)
```

```python
# Стратегия 2: Используем DeepSeek по умолчанию
async with PlanMCPAgent(
    model="deepseek:deepseek-coder",
    max_iterations=30  # Можем позволить больше итераций
) as agent:
    result = await agent.run(objective)
```

## Лимиты и ограничения

- **Rate limits:** Зависят от вашего плана подписки
- **Context window:** 64K tokens для обеих моделей
- **Поддержка function calling:** Да (OpenAI-совместимый)
- **Streaming:** Поддерживается
- **Batch API:** Доступно

## Troubleshooting

### Ошибка: "Invalid API key"

```bash
# Проверьте, что ключ установлен
echo $DEEPSEEK_API_KEY

# Или в .env файле
cat .env | grep DEEPSEEK
```

### Ошибка: "Connection timeout"

DeepSeek API может быть медленнее, увеличьте timeout:

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    timeout=60  # Увеличенный timeout
)
```

### Медленные ответы

DeepSeek серверы находятся в Китае, задержка может быть выше:

```python
# Используйте меньше итераций для DeepSeek
agent = PlanMCPAgent(
    model="deepseek:deepseek-chat",
    max_iterations=10  # Вместо 20
)
```

## Дополнительные ресурсы

- [DeepSeek Platform](https://platform.deepseek.com/)
- [API Documentation](https://platform.deepseek.com/api-docs/)
- [Model Comparison](https://huggingface.co/deepseek-ai)
- [Pricing](https://platform.deepseek.com/pricing)

## Примеры из репозитория

Запустите готовые примеры:

```bash
# Базовое использование
uv run python examples/deepseek_usage.py

# Сравнение моделей
uv run python examples/deepseek_usage.py --compare

# С MCP серверами
uv run python examples/deepseek_usage.py --with-mcp
```
