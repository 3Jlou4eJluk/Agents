# Architecture Overview

## Общая архитектура

PlanMCP Agent реализует паттерн **Plan-and-Execute** на базе LangGraph, комбинируя явное планирование с выполнением задач через инструменты.

## Компоненты системы

### 1. Main Agent (`agent.py`)

Главный класс `PlanMCPAgent` - точка входа в систему.

**Обязанности:**
- Инициализация LLM (Anthropic Claude, OpenAI, и др.)
- Управление MCP клиентом
- Сборка всех инструментов (OS + MCP)
- Создание и запуск LangGraph workflow

**Ключевые методы:**
- `initialize()` - асинхронная инициализация всех компонентов
- `run(objective)` - запуск выполнения задачи
- `close()` - очистка ресурсов

### 2. LangGraph Workflow (`graph.py`)

Класс `PlanExecuteGraph` реализует state machine на базе LangGraph.

**Узлы графа:**
1. **plan** - Создание начального плана
2. **execute** - Выполнение текущего шага
3. **replan** - Корректировка плана после выполнения

**Поток выполнения:**
```
START → plan → execute → replan → [continue/end]
                 ↑          ↓
                 └──────────┘
```

**State:**
```python
{
    "objective": str,           # Цель пользователя
    "plan": Plan,               # Текущий план
    "current_step_id": int,     # ID текущего шага
    "step_results": dict,       # Результаты выполнения
    "iteration": int,           # Номер итерации
    "is_complete": bool         # Завершено ли выполнение
}
```

### 3. Planner Agent (`agents/planner.py`)

Отвечает за создание и корректировку планов.

**Структура плана:**
```python
Plan:
  - objective: str
  - steps: List[Step]

Step:
  - id: int
  - description: str
  - dependencies: List[int]
  - status: "pending" | "in_progress" | "completed" | "failed"
  - result: Optional[str]
```

**Возможности:**
- Разбиение сложных задач на подзадачи
- Определение зависимостей между шагами
- Использование structured output для надежного парсинга
- Адаптация плана на основе результатов выполнения

### 4. Executor Agent (`agents/executor.py`)

Выполняет отдельные шаги плана используя ReAct паттерн.

**Процесс выполнения:**
1. Получает описание шага
2. Анализирует контекст (цель, предыдущие результаты)
3. Использует инструменты для выполнения
4. Возвращает результат или ошибку

**Особенности:**
- Итеративное использование инструментов
- Защита от бесконечных циклов (max_iterations)
- Обработка ошибок при вызове инструментов
- Поддержка как синхронных, так и асинхронных инструментов

### 5. Replanner Agent (`agents/replanner.py`)

Принимает решения о продолжении, корректировке или завершении плана.

**Логика принятия решений:**
- Определяет следующий выполнимый шаг (dependencies met)
- Решает нужно ли перепланирование
- Обновляет статусы шагов
- Обрабатывает ошибки выполнения

### 6. MCP Client Manager (`mcp/client.py`)

Управляет подключениями к MCP серверам.

**Возможности:**
- Подключение к нескольким MCP серверам одновременно
- Поддержка stdio и HTTP транспортов
- Получение инструментов от серверов
- Конвертация MCP инструментов в LangChain tools

**Конфигурация сервера:**
```python
{
    "server_name": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        "transport": "stdio"
    }
}
```

### 7. OS Tools (`tools/os_tools.py`)

Набор инструментов для работы с операционной системой.

**Инструменты:**
- `execute_shell_command` - выполнение команд
- `read_file` - чтение файлов с поддержкой диапазона строк
- `write_file` - запись/добавление в файлы
- `list_directory` - листинг директорий с фильтрацией
- `search_files` - поиск текста в файлах

**Безопасность:**
- Timeout для команд (30 сек)
- Валидация путей
- Обработка ошибок кодировки
- Ограничение вывода

## Поток данных

### Инициализация

```
User
  ↓
PlanMCPAgent.__init__()
  ↓
_initialize_llm() → создание LLM клиента
  ↓
PlanMCPAgent.initialize()
  ├─→ get_all_os_tools() → загрузка OS инструментов
  ├─→ MCPClientManager.initialize() → подключение к MCP
  └─→ PlanExecuteGraph() → создание workflow
```

### Выполнение задачи

```
User.objective
  ↓
PlanMCPAgent.run()
  ↓
LangGraph.invoke(initial_state)
  ↓
[plan node]
  ├─→ PlannerAgent.create_plan()
  ├─→ LLM call with structured output
  └─→ return Plan
  ↓
[execute node]
  ├─→ ReplannerAgent.get_next_executable_step()
  ├─→ ExecutorAgent.execute_step()
  │    ├─→ LLM + tools (ReAct loop)
  │    └─→ return result
  └─→ store result in state
  ↓
[replan node]
  ├─→ ReplannerAgent.adjust_plan()
  ├─→ check if complete
  └─→ return updated state
  ↓
[should_continue]
  ├─→ if complete → END
  └─→ if not → back to execute
```

## Ключевые паттерны

### 1. Plan-and-Execute Pattern

**Преимущества:**
- Прозрачность - виден весь план заранее
- Эффективность - можно использовать разные модели для разных шагов
- Параллелизм - независимые шаги могут выполняться параллельно
- Адаптивность - план корректируется на основе результатов

### 2. ReAct (Reasoning + Acting)

**В Executor Agent:**
```
1. Thought: LLM анализирует что нужно сделать
2. Action: LLM выбирает инструмент и параметры
3. Observation: Результат выполнения инструмента
4. Repeat: Пока задача не выполнена
```

### 3. State Management

**LangGraph State:**
- Immutable - каждый узел возвращает новое состояние
- Typed - TypedDict с аннотациями типов
- Accumulated - messages используют `add_messages` reducer

### 4. Tool Abstraction

**Единый интерфейс:**
- OS tools - реализованы как LangChain @tool декораторы
- MCP tools - конвертированы через langchain-mcp-adapters
- Custom tools - можно добавить через стандартный LangChain API

## Расширяемость

### Добавление новых инструментов

```python
from langchain_core.tools import tool

@tool
def my_tool(param: str) -> str:
    """Tool description."""
    return result

agent.tools.append(my_tool)
```

### Добавление новых агентов

```python
class CustomAgent:
    def __init__(self, llm):
        self.llm = llm

    async def process(self, state):
        # Custom logic
        return updated_state

# Add to graph
workflow.add_node("custom", custom_agent.process)
```

### Кастомизация workflow

```python
# Modify graph building in PlanExecuteGraph._build_graph()
workflow.add_node("validation", validation_node)
workflow.add_edge("plan", "validation")
workflow.add_edge("validation", "execute")
```

## Сравнение с альтернативами

### vs Simple ReAct Agent

| Аспект | PlanMCP Agent | Simple ReAct |
|--------|---------------|--------------|
| Планирование | Явное, заранее | Неявное, шаг за шагом |
| Прозрачность | Высокая | Низкая |
| Для сложных задач | ✅ Отлично | ⚠️ Может зацикливаться |
| Скорость простых задач | Медленнее | Быстрее |

### vs Claude Desktop

| Аспект | PlanMCP Agent | Claude Desktop |
|--------|---------------|----------------|
| Open Source | ✅ | ❌ |
| Кастомизация | ✅ Полная | ⚠️ Ограниченная |
| Self-hosted | ✅ | ❌ |
| Выбор модели | ✅ Любая | ❌ Только Claude |
| Планирование | ✅ Явное | ❌ Неявное |

## Performance Considerations

### Оптимизации

1. **Async/await** - все I/O операции асинхронные
2. **Structured output** - быстрый парсинг планов
3. **Tool caching** - MCP инструменты загружаются один раз
4. **Early termination** - остановка при достижении цели

### Ограничения

1. **Max iterations** - защита от бесконечных циклов
2. **Command timeout** - 30 сек на shell команду
3. **Context size** - может быть ограничен размером контекста LLM

## Безопасность

### Меры безопасности

1. **Path validation** - проверка путей в file operations
2. **Command timeout** - ограничение времени выполнения
3. **Error isolation** - ошибки не останавливают весь workflow
4. **No arbitrary code execution** - только pre-defined tools

### Рекомендации

- Запускайте в изолированной среде (Docker, VM)
- Ограничьте доступ к критичным директориям
- Проверяйте input от пользователя
- Логируйте все действия

## Будущие улучшения

1. **Параллельное выполнение** - независимые шаги одновременно
2. **Human-in-the-loop** - подтверждение критичных действий
3. **Caching** - кэширование результатов LLM
4. **Streaming** - потоковый вывод результатов
5. **Multi-agent** - специализированные агенты для разных типов задач
