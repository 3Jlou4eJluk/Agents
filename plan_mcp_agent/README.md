# 🤖 PlanMCP Agent

**LangGraph-агент с планированием, инструментами ОС и поддержкой MCP** - Open Source альтернатива Claude Desktop

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)](https://github.com/langchain-ai/langgraph)

---

## 📋 Содержание

- [Возможности](#-возможности)
- [Архитектура](#-архитектура)
- [Установка](#-установка)
- [Быстрый старт](#-быстрый-старт)
- [Конфигурация](#-конфигурация)
- [Примеры использования](#-примеры-использования)
- [Доступные инструменты](#-доступные-инструменты)
- [MCP серверы](#-mcp-серверы)
- [Разработка](#-разработка)
- [Сравнение с аналогами](#-сравнение-с-аналогами)

---

## ✨ Возможности

- 🎯 **Plan-and-Execute паттерн** - Автоматическое разбиение сложных задач на шаги
- 📁 **Инструменты ОС** - Работа с файлами, shell командами, поиском
- 🔌 **Поддержка MCP** - Подключение к любым MCP серверам для расширения функциональности
- 🔄 **LangGraph workflow** - Надежное управление состоянием и потоком выполнения
- 🧠 **Множество LLM** - Anthropic Claude, OpenAI, и другие
- ⚡ **Async/Await** - Полная асинхронная поддержка для высокой производительности
- 🔍 **ReAct паттерн** - Умное использование инструментов через reasoning
- 🛡️ **Обработка ошибок** - Автоматическая корректировка плана при ошибках

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      PlanMCP Agent                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │   Planner    │──▶│   Executor   │──▶│  Replanner   │   │
│  │              │   │              │   │              │   │
│  │ Создает план │   │ Выполняет    │   │ Корректирует │   │
│  │ выполнения   │   │ шаги с       │   │ план по      │   │
│  │              │   │ инструментами│   │ результатам  │   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
│         │                   │                   │          │
│         └───────────────────┼───────────────────┘          │
│                             ▼                              │
│              ┌──────────────────────────────┐             │
│              │   LangGraph State Machine    │             │
│              │  (plan → execute → replan)   │             │
│              └──────────────────────────────┘             │
│                      │              │                      │
│         ┌────────────┴──────┐  ┌───┴────────────┐        │
│         │                   │  │                │        │
│    ┌────▼─────┐      ┌──────▼──▼─────┐   ┌─────▼─────┐  │
│    │OS Tools  │      │  LLM (Claude,  │   │MCP Client │  │
│    │          │      │  OpenAI, etc)  │   │           │  │
│    │• Files   │      └────────────────┘   │• Custom   │  │
│    │• Shell   │                           │  Servers  │  │
│    │• Search  │                           │• Tools    │  │
│    └──────────┘                           └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Принцип работы

1. **Планирование** - LLM анализирует цель и создает пошаговый план
2. **Выполнение** - Каждый шаг выполняется через ReAct цикл с инструментами
3. **Корректировка** - План адаптируется на основе результатов выполнения
4. **Итерация** - Процесс повторяется до завершения или достижения лимита

---

## 📦 Установка

### Вариант 1: Использование uv (рекомендуется)

```bash
# Перейдите в директорию проекта
cd plan_mcp_agent

# Установите зависимости
uv sync

# Скопируйте шаблон переменных окружения
cp .env.example .env

# Отредактируйте .env и добавьте API ключи
nano .env
```

### Вариант 2: Использование pip

```bash
pip install langgraph langchain-anthropic langchain-openai \
    langchain-mcp-adapters python-dotenv rich
```

### Требования

- Python 3.11 или выше
- API ключ от Anthropic или OpenAI
- (Опционально) Node.js для MCP серверов

---

## 🚀 Быстрый старт

### 1️⃣ Базовое использование (без MCP)

```python
import asyncio
from plan_mcp_agent.agent import PlanMCPAgent

async def main():
    # Создаем агента
    async with PlanMCPAgent() as agent:
        # Выполняем задачу
        result = await agent.run(
            "Создай Python скрипт hello.py, который выводит Hello World, и запусти его"
        )

asyncio.run(main())
```

### 2️⃣ Использование с MCP серверами

```python
import asyncio
from plan_mcp_agent.agent import PlanMCPAgent

async def main():
    # Конфигурация MCP серверов
    mcp_config = {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "transport": "stdio"
        }
    }

    # Создаем агента с MCP
    async with PlanMCPAgent(mcp_config=mcp_config) as agent:
        result = await agent.run("Покажи все файлы в /tmp")

asyncio.run(main())
```

### 3️⃣ CLI интерфейс

```bash
# Интерактивный режим
uv run python main.py

# Режим командной строки
uv run python main.py "Найди все Python файлы в текущей директории"

# Простой запуск через скрипт
./scripts/run.sh "Search for AI news and summarize it"

# Запуск с файлом задачи (для многострочных заданий)
./scripts/run.sh tasks/example_task.txt

# Создайте свой файл с заданием
echo "Какие новости сегодня в мире технологий?" > tasks/my_task.txt
./scripts/run.sh tasks/my_task.txt

# Запуск примеров
uv run python examples/basic_usage.py
uv run python examples/with_mcp.py
uv run python examples/full_mcp_config.py  # С полной конфигурацией MCP
```

### 4️⃣ Тестирование

```bash
# Быстрый тест работоспособности
uv run python test_agent.py
```

---

## ⚙️ Конфигурация

### Переменные окружения (.env)

```bash
# Обязательно: хотя бы один API ключ
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxx

# Опционально: LangSmith для трейсинга
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxx
LANGSMITH_PROJECT=plan-mcp-agent

# Выбор модели (по умолчанию)
DEFAULT_MODEL=anthropic:claude-3-5-sonnet-20241022
```

### MCP конфигурация (mcp_config.json)

В проекте включена полная конфигурация с множеством MCP серверов:

```json
{
  "mcpServers": {
    "reddit": {
      "command": "uvx",
      "args": ["mcp-server-reddit"],
      "transport": "stdio"
    },
    "tavily-mcp": {
      "command": "npx",
      "args": ["tavily-mcp@0.1.2"],
      "env": {
        "TAVILY_API_KEY": "your-key-here"
      },
      "transport": "stdio"
    },
    "server-brave-search": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-brave-search", "-y"],
      "env": {
        "BRAVE_API_KEY": "your-key-here"
      },
      "transport": "stdio"
    },
    "firecrawl-mcp": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "your-key-here"
      },
      "transport": "stdio"
    },
    "youtube-mcp": {
      "command": "npx",
      "args": ["youtube-mcp"],
      "transport": "stdio"
    },
    "playwright-mcp-server": {
      "command": "npx",
      "args": ["@executeautomation/playwright-mcp-server"],
      "transport": "stdio"
    },
    "desktop-commander": {
      "command": "npx",
      "args": ["@wonderwhy-er/desktop-commander@latest"],
      "transport": "stdio"
    }
  }
}
```

Файл `mcp_config.json` в корне проекта содержит готовую конфигурацию всех доступных серверов.

### Программная конфигурация

```python
from plan_mcp_agent.agent import PlanMCPAgent
from plan_mcp_agent.mcp.client import load_mcp_config_from_file

# Загрузка MCP из файла
mcp_config = load_mcp_config_from_file("mcp_config.json")

# Создание агента с параметрами
agent = PlanMCPAgent(
    model="anthropic:claude-3-5-sonnet-20241022",  # Выбор модели
    mcp_config=mcp_config,                          # MCP серверы
    max_iterations=20,                              # Максимум итераций
    enable_os_tools=True                            # Включить OS инструменты
)
```

---

## 💡 Примеры использования

### Пример 1: Анализ файлов

```python
objective = """
Найди все Python файлы в директории src,
посчитай количество строк кода в каждом,
и создай отчет в формате Markdown.
"""

async with PlanMCPAgent() as agent:
    result = await agent.run(objective)
```

**Что произойдет:**
1. Агент создаст план из 3-4 шагов
2. Выполнит поиск Python файлов
3. Прочитает каждый файл и посчитает строки
4. Создаст Markdown отчет

### Пример 2: Рефакторинг кода

```python
objective = """
1. Прочитай файл utils.py
2. Добавь type hints ко всем функциям
3. Добавь docstrings в Google style
4. Сохрани улучшенную версию
"""

async with PlanMCPAgent() as agent:
    result = await agent.run(objective)
```

### Пример 3: Работа с Git через MCP

```python
from plan_mcp_agent.mcp.client import load_mcp_config_from_file

mcp_config = load_mcp_config_from_file("examples/mcp_config.json")

async with PlanMCPAgent(mcp_config=mcp_config) as agent:
    result = await agent.run(
        "Покажи последние 5 коммитов и создай краткое резюме изменений"
    )
```

### Пример 4: Комплексная задача

```python
objective = """
Проанализируй структуру проекта:
1. Найди все Python модули
2. Построй граф зависимостей между ними
3. Найди потенциальные циклические зависимости
4. Создай визуализацию в DOT формате
"""

async with PlanMCPAgent(max_iterations=30) as agent:
    result = await agent.run(objective)
```

---

## 🛠️ Доступные инструменты

### OS Tools (встроенные)

| Инструмент | Описание | Пример |
|-----------|----------|--------|
| `execute_shell_command` | Выполнение shell команд | `ls -la`, `git status` |
| `read_file` | Чтение файлов (с диапазоном строк) | Чтение кода, конфигов |
| `write_file` | Запись/добавление в файлы | Создание скриптов, отчетов |
| `list_directory` | Список файлов в директории | Поиск с паттернами `*.py` |
| `search_files` | Поиск текста в файлах | Поиск функций, классов |

### Примеры использования инструментов

```python
# Агент автоматически выберет нужные инструменты
async with PlanMCPAgent() as agent:
    # Использует: list_directory, read_file, execute_shell_command
    await agent.run("Найди все TODO комментарии в Python файлах")

    # Использует: search_files, read_file
    await agent.run("Найди все функции с именем 'process' в проекте")

    # Использует: write_file, execute_shell_command
    await agent.run("Создай requirements.txt из текущего окружения")
```

---

## 🔌 MCP серверы

Агент поддерживает любые MCP серверы. Популярные варианты:

### Официальные серверы

| Сервер | Возможности | Включен |
|--------|-------------|---------|
| `@modelcontextprotocol/server-filesystem` | Работа с файлами | ❌ |
| `@modelcontextprotocol/server-git` | Git операции | ❌ |
| `@modelcontextprotocol/server-brave-search` | Поиск через Brave | ✅ |
| `tavily-mcp` | Поиск через Tavily | ✅ |
| `firecrawl-mcp` | Web scraping | ✅ |
| `youtube-mcp` | YouTube интеграция | ✅ |
| `mcp-server-reddit` | Reddit API | ✅ |
| `playwright-mcp-server` | Браузерная автоматизация | ✅ |
| `desktop-commander` | Управление рабочим столом | ✅ |
| `@anaisbetts/mcp-youtube` | YouTube альтернатива | ✅ |
| `@brightdata/mcp` | Bright Data scraping | ✅ |

Все серверы преднастроены в `mcp_config.json`. Для использования серверов с API ключами необходимо указать их в конфигурации.

### Создание собственного MCP сервера

```python
from mcp.server.fastmcp import FastMCP

# Создаем сервер
mcp = FastMCP("MyServer")

@mcp.tool()
def my_tool(param: str) -> str:
    """Описание инструмента."""
    return f"Результат: {param}"

# Запуск
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Подробнее: [MCP Servers Directory](https://github.com/modelcontextprotocol/servers)

---

## 🔧 Разработка

### Структура проекта

```
plan_mcp_agent/
├── 📄 README.md              # Этот файл
├── 📄 main.py                # CLI точка входа
├── 📄 test_agent.py          # Тестовый файл
├── 📄 pyproject.toml         # Конфигурация проекта
├── 📄 .env.example           # Шаблон переменных окружения
├── 📄 mcp_config.json        # Конфигурация MCP серверов
│
├── 📁 docs/                  # Документация
│   ├── QUICKSTART.md         # Быстрый старт
│   ├── ARCHITECTURE.md       # Техническая документация
│   └── DEEPSEEK.md           # Использование DeepSeek
│
├── 📁 scripts/               # Утилиты
│   └── run.sh                # Скрипт быстрого запуска
│
├── 📁 plan_mcp_agent/        # Основной пакет
│   ├── agent.py              # Главный класс агента
│   ├── graph.py              # LangGraph workflow
│   │
│   ├── 📁 agents/            # Компоненты планирования
│   │   ├── planner.py        # Создание планов
│   │   ├── executor.py       # Выполнение с ReAct
│   │   └── replanner.py      # Корректировка планов
│   │
│   ├── 📁 mcp/               # MCP интеграция
│   │   ├── __init__.py
│   │   └── client.py         # MCP клиент менеджер
│   │
│   └── 📁 tools/             # Инструменты
│       ├── __init__.py
│       └── os_tools.py       # OS операции
│
└── 📁 examples/              # Примеры
    ├── basic_usage.py        # Базовый пример
    ├── with_mcp.py           # С MCP серверами
    ├── full_mcp_config.py    # С полной конфигурацией MCP
    └── deepseek_usage.py     # Использование DeepSeek
```

### Добавление пользовательских инструментов

```python
from langchain_core.tools import tool
from plan_mcp_agent.agent import PlanMCPAgent

# Создаем инструмент
@tool
def calculate_fibonacci(n: int) -> int:
    """Вычисляет n-ное число Фибоначчи."""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

# Добавляем к агенту
async with PlanMCPAgent() as agent:
    agent.tools.append(calculate_fibonacci)
    result = await agent.run("Вычисли 10-е число Фибоначчи")
```

### Запуск тестов

```bash
# Установка dev зависимостей
uv sync --dev

# Запуск тестов
uv run pytest

# С покрытием
uv run pytest --cov=plan_mcp_agent
```

### Расширение функциональности

#### Добавление нового узла в граф

```python
# В graph.py
async def validation_node(self, state: AgentState) -> AgentState:
    """Валидация плана перед выполнением."""
    plan = state["plan"]
    # Ваша логика валидации
    return state

# Добавление в граф
workflow.add_node("validation", self.validation_node)
workflow.add_edge("plan", "validation")
workflow.add_edge("validation", "execute")
```

#### Кастомизация Planner

```python
from plan_mcp_agent.agents.planner import PlannerAgent

class MyPlanner(PlannerAgent):
    async def create_plan(self, objective: str, context=None):
        # Ваша логика планирования
        plan = await super().create_plan(objective, context)
        # Дополнительная обработка
        return plan
```

---

## 📊 Сравнение с аналогами

### vs Claude Desktop

| Функция | PlanMCP Agent | Claude Desktop |
|---------|---------------|----------------|
| **Планирование** | ✅ Явное, прозрачное | ❌ Неявное |
| **MCP Support** | ✅ Полная поддержка | ✅ Полная поддержка |
| **OS Tools** | ✅ Встроенные | ✅ Через MCP |
| **Open Source** | ✅ MIT License | ❌ Закрытый |
| **Кастомизация** | ✅ Полная | ⚠️ Ограниченная |
| **Выбор LLM** | ✅ Любая модель | ❌ Только Claude |
| **Self-hosted** | ✅ Да | ❌ Нет |
| **API доступ** | ✅ Python API | ❌ Только GUI |
| **Стоимость** | ✅ Бесплатно | ⚠️ Требует подписку |

### vs Simple ReAct Agent

| Аспект | PlanMCP Agent | ReAct Agent |
|--------|---------------|-------------|
| **Сложные задачи** | ✅ Отлично | ⚠️ Может зацикливаться |
| **Прозрачность** | ✅ Виден весь план | ❌ Шаг за шагом |
| **Простые задачи** | ⚠️ Медленнее | ✅ Быстрее |
| **Отладка** | ✅ Легко | ⚠️ Сложнее |
| **Адаптивность** | ✅ Перепланирование | ⚠️ Ограниченная |

### vs LangChain Agent Executor

| Функция | PlanMCP Agent | LangChain Agent |
|---------|---------------|-----------------|
| **Workflow** | ✅ LangGraph | ⚠️ Chain-based |
| **State Management** | ✅ Продвинутый | ⚠️ Базовый |
| **Планирование** | ✅ Встроенное | ❌ Нужно добавлять |
| **MCP** | ✅ Нативная поддержка | ⚠️ Через адаптеры |

---

## 🎯 Преимущества Plan-and-Execute

### Почему явное планирование?

1. **Прозрачность** - видите весь план заранее
2. **Эффективность** - можно использовать разные модели для разных шагов
3. **Параллелизм** - независимые шаги выполняются параллельно
4. **Отладка** - легко понять, где возникла проблема
5. **Адаптивность** - план корректируется на основе результатов

### Когда использовать Plan-and-Execute?

✅ **Хорошо подходит для:**
- Многошаговых задач (>3 шагов)
- Задач с зависимостями между шагами
- Комплексного анализа
- Задач требующих планирования

⚠️ **Избыточно для:**
- Простых одношаговых задач
- Задач требующих немедленного ответа
- Чисто информационных запросов

---

## 🤝 Contributing

Приветствуются любые улучшения!

### Области для развития

- [ ] Дополнительные OS инструменты
- [ ] Больше MCP интеграций
- [ ] Web UI / Streamlit интерфейс
- [ ] Поддержка потокового вывода
- [ ] Human-in-the-loop подтверждения
- [ ] Параллельное выполнение шагов
- [ ] Кэширование результатов LLM
- [ ] Больше тестов
- [ ] Документация на английском

### Как контрибьютить

1. Fork репозиторий
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

---

## 📝 Лицензия

MIT License - см. [LICENSE](LICENSE)

---

## 🙏 Благодарности

Проект построен на основе:

- **[LangGraph](https://github.com/langchain-ai/langgraph)** - State machine для агентов
- **[LangChain](https://github.com/langchain-ai/langchain)** - Фреймворк для LLM
- **[MCP](https://modelcontextprotocol.io/)** - Model Context Protocol от Anthropic
- **[Claude Desktop](https://claude.ai/desktop)** - Вдохновение для дизайна

---

## 🔗 Полезные ссылки

- [MCP Documentation](https://modelcontextprotocol.io/docs) - Документация по MCP
- [LangGraph Tutorials](https://langchain-ai.github.io/langgraph/) - Руководства по LangGraph
- [Plan-and-Execute Pattern](https://blog.langchain.com/planning-agents/) - Статья о паттерне
- [MCP Servers Directory](https://github.com/modelcontextprotocol/servers) - Каталог MCP серверов
- [FastMCP](https://github.com/jlowin/fastmcp) - Создание MCP серверов

---

## 📧 Контакты и поддержка

- Вопросы и Issues: [GitHub Issues](https://github.com/your-repo/issues)
- Документация: См. `docs/ARCHITECTURE.md` и `docs/QUICKSTART.md`

---

<div align="center">

**Сделано с ❤️ используя LangGraph и MCP**

⭐ Поставьте звезду, если проект был полезен!

</div>
