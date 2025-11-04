# Сравнительный Анализ: SimplePlanMCPAgent vs Claude Code Agents

## Executive Summary

Две фундаментально разные философии агентных систем:

| SimplePlanMCPAgent (Stage 2) | Claude Code Agents |
|-------------------------------|-------------------|
| **Одиночный агент**, итеративный | **Мульти-агентная** система |
| Автономная работа (batch) | Human-in-the-loop |
| Оптимизация на масштаб | Оптимизация на качество |
| Валидация через код | Валидация через review |
| Конфигурация: JSON + Python | Конфигурация: Markdown + YAML |

---

## 1. Архитектура

### SimplePlanMCPAgent

**Файл**: `outreach_orchestrator/src/agent_wrapper.py:97-803`

```
WorkerPool (5 workers)
    ↓
    └─> SimplePlanMCPAgent (shared MCP manager)
         ↓
         └─> LLM + Tools (ReAct loop, max 30 iterations)
              ↓
              └─> Auto-validation + compression
```

**Ключевые особенности**:
- ReAct-цикл: `while iteration < max_iterations`
- Один агент = одна задача (генерация письма)
- Shared MCP manager между воркерами (оптимизация ресурсов)
- Встроенная валидация с автоматическими retry

### Claude Code Agents

**Файл**: `claude-code/plugins/feature-dev/`

```
/feature-dev command (orchestrator)
    ↓
Phase 1: Discovery → Human gate
    ↓
Phase 2: 2-3 code-explorer (parallel) → Read files → Human gate
    ↓
Phase 4: 2-3 code-architect (parallel) → Human selects → Human gate
    ↓
Phase 6: 3 code-reviewer (parallel) → Human decides
    ↓
Phase 7: Summary
```

**Ключевые особенности**:
- 7 фаз с human-in-the-loop gates
- Специализированные агенты для разных ролей
- Параллельное выполнение в рамках фазы
- Агрегация результатов оркестратором

---

## 2. Выполнение Задач

### SimplePlanMCPAgent

**Поток выполнения** (`agent_wrapper.py:525-770`):

```python
messages = [HumanMessage(content=task)]  # Системный промпт + задача
iteration = 0

while iteration < self.max_iterations:
    response = await llm_with_tools.ainvoke(messages)

    if not response.tool_calls:
        # Финальный ответ → валидация
        validation_result = self._validate_letter(letter_dict)
        if not valid and attempts < retries:
            messages.append(HumanMessage("Исправь ошибки: ..."))
            continue  # Retry
        return result

    # Выполнить tool calls
    for tool_call in response.tool_calls:
        result = await tool.ainvoke(tool_args)
        messages.append(ToolMessage(result))
```

**Терминация**:
- ✅ Агент вернул валидный JSON без tool calls
- ⚠️ Достигнут max_iterations (30)
- 🔧 Валидация провалилась → auto-fix

### Claude Code Agents

**Поток выполнения** (`feature-dev.md`):

```markdown
Phase 2: Codebase Exploration
1. Launch 2-3 code-explorer agents IN PARALLEL
   - Agent 1: "Trace authentication flow"
   - Agent 2: "Map API architecture"
   - Agent 3: "Find similar features"
2. Read all files identified by agents
3. Present comprehensive summary
   → WAIT FOR USER CONFIRMATION

Phase 4: Architecture Design
1. Launch 2-3 code-architect agents
2. Present multiple approaches
   → USER SELECTS APPROACH
```

**Терминация**:
- ✅ Фаза завершена + пользователь подтвердил
- Нет автоматического лимита итераций

---

## 3. Инструменты (Tools)

### SimplePlanMCPAgent

**MCP конфигурация** (`mcp_config.json`):

```json
{
  "mcpServers": {
    "bright-data": { "command": "npx", "args": [...], "env": {...} },
    "tavily-mcp": { "command": "npx", "args": [...], "env": {...} }
  }
}
```

**Механизм**:
- Все MCP tools доступны агенту
- Динамическая загрузка через `MultiServerMCPClient`
- Один MCP manager на все воркеры (shared connections)
- Enable/disable через `config.json`

**Пример** (`agent_wrapper.py:722-746`):
```python
for tool_call in response.tool_calls:
    tool = next((t for t in self.tools if t.name == tool_name), None)
    if tool:
        result = await tool.ainvoke(tool_args)
    else:
        result = f"Error: Tool '{tool_name}' not found"
    messages.append(ToolMessage(result))
```

### Claude Code Agents

**Декларативная спецификация** (`code-explorer.md:4`):

```yaml
---
tools: Glob, Grep, LS, Read, NotebookRead, WebFetch, TodoWrite
model: sonnet
color: yellow
---
```

**Механизм**:
- Tools указаны в YAML frontmatter
- Каждый агент видит только свои tools
- Встроенные tools (Glob, Read, etc.) + опционально MCP
- Tool execution управляется Claude Code runtime

**Профили инструментов**:
- `code-explorer`: поиск и анализ (Glob, Grep, Read)
- `code-architect`: то же + WebFetch
- `code-reviewer`: то же самое

---

## 4. Промпт-инжиниринг

### SimplePlanMCPAgent

**Композиция промпта** (`worker_pool.py:517-758`):

```python
def _format_agent_task_creative(self, lead_data, context, tools):
    return f"""
# Your Mission: Write an Email That Shows You Actually Get Their World

## Available MCP Tools
{self._format_tools_description(tools)}  # Dynamic

## Lead
- Name: {name}
- Company: {company}
- LinkedIn: {linkedin_url}

## Project Context
{context['gtm']}  # GTM.md (ICP, value prop)

## Writing Philosophy
{context['guides']}  # POV Framework, style guides

## Detailed Instructions
{context['instruction']}  # agent_instruction.md

## Output Format
Return pure JSON: {{"rejected": bool, "letter": {{...}}, ...}}
"""
```

**Источники инструкций**:
- `context/GTM.md` - ICP, ценностное предложение
- `context/guides/pov_framework.md` - методология письма
- `context/agent_instruction.md` - детальные инструкции
- `worker_pool.py` - template logic (код)

**Динамика**:
- 2 режима: "creative" vs "standard" (`config.json:prompt_mode`)
- Валидационные feedback messages при ошибках

### Claude Code Agents

**Декларативные инструкции** (`code-explorer.md`):

```yaml
---
name: code-explorer
description: Deeply analyzes existing codebase features
---

You are an expert code analyst specializing in tracing feature implementations.

## Core Mission
Provide complete understanding of how a specific feature works...

## Analysis Approach
1. Feature Discovery
   - Find entry points (APIs, UI, CLI)
   - Locate feature flags, configuration
2. Implementation Tracing
   - Follow execution path
   - Map dependencies
...

## Output Format
Provide comprehensive analysis with:
- Architecture overview
- Key files list (5-10 files)
- Data flow diagrams
```

**Иерархия**:
1. **Command** (`feature-dev.md`) - оркестрация workflow
2. **Agent** (`code-explorer.md`) - роль и подход
3. **User input** - конкретная задача

**Все в Markdown** - нет кода для изменения промптов!

---

## 5. Управление Памятью

### SimplePlanMCPAgent

**Авто-компрессия** (`agent_wrapper.py:225-367`):

```python
async def _compress_context(self, messages):
    """
    Preserves: [First message] + [Last 5 messages]
    Compresses: Everything in between
    """
    first_msg = messages[0]  # System prompt
    last_msgs = messages[-5:]  # Current context
    middle_msgs = messages[1:-5]  # To compress

    # Суммаризация через отдельный LLM
    summary = await summarizer.ainvoke("Summarize: {middle_msgs}")

    return [first_msg, SystemMessage(summary), *last_msgs]
```

**Настройки** (`config.json:80-86`):
```json
"auto_compact": {
  "enabled": true,
  "trigger_at_messages": 15,     // Порог срабатывания
  "preserve_last_messages": 5,   // Сколько последних сохранить
  "summarization_model": "gpt-4o-mini"
}
```

**Триггер** (`agent_wrapper.py:530`):
```python
if len(messages) >= self.compact_trigger:
    messages = await self._compress_context(messages)
```

### Claude Code Agents

**Изоляция контекста по фазам**:
- Каждый агент запускается с чистым контекстом
- Агенты не имеют shared memory
- Передача знаний через файлы:

```markdown
Phase 2: Agents identify key files → Orchestrator reads files
Phase 4: Agents use knowledge from read files
```

**Persistence через TodoWrite**:
- Агенты создают TODOs
- TODOs переживают фазы
- Видимы оркестратору и пользователю

**Нет автоматической компрессии** - контроль через:
- Границы фаз (свежий старт)
- Human gates (предотвращают runaway)
- File-based memory (external storage)

---

## 6. Обработка Ошибок

### SimplePlanMCPAgent

**Валидация с retry** (`agent_wrapper.py:649-690`):

```python
validation_result = self._validate_letter(letter_dict)

if not validation_result['valid']:
    if validation_attempts < self.validation_retries:
        # Retry с детальным feedback
        feedback = f"""Validation errors:
        {errors}

        Fix these issues. Requirements:
        - Body: 75-85 words
        - Subject: 2-3 words, no "?"
        - Signature: "Michael"
        - No banned phrases: {banned_phrases}
        """
        messages.append(HumanMessage(feedback))
        continue
    else:
        # Auto-fix после исчерпания retry
        letter_dict = self._auto_fix_letter(letter_dict)
```

**Auto-fix** (`lines 455-497`):
```python
def _auto_fix_letter(self, letter_dict):
    # Исправить подпись
    if last_line in ['Almas', 'Best', 'Regards']:
        last_line = 'Michael'
```

**Настройки валидации** (`config.json:62-79`):
```json
"letter_validation": {
  "enabled": true,
  "validation_retries": 2,
  "auto_fix_enabled": true,
  "word_count_min": 75,
  "word_count_max": 85,
  "banned_phrases": ["I'm curious", "I figured"]
}
```

### Claude Code Agents

**Confidence-based filtering** (`code-reviewer.md:23-33`):

```markdown
## Confidence Scoring
Rate each issue 0-100:
- 75: Highly confident
- 100: Absolutely certain

**Only report issues with confidence ≥ 80.**
```

**Валидация через human review**:
- Phase 3: Юзер отвечает на вопросы (предотвращает неоднозначность)
- Phase 4: Юзер выбирает архитектуру
- Phase 6: Юзер решает, какие issues исправлять

**Нет автоматических retry** - человек корректирует:
```
Агент ошибся → Юзер видит → Feedback → Агент исправляет
```

---

## 7. Конфигурация

### SimplePlanMCPAgent

**Многослойная конфигурация**:

1. **config.json** - основные настройки:
```json
{
  "models": {
    "classification": {"provider": "deepseek", "model": "deepseek-chat"},
    "letter_generation": {"provider": "claude", "model": "claude-sonnet-4-5"}
  },
  "worker_pool": {"num_workers": 5, "max_agent_iterations": 30},
  "letter_validation": {...},
  "auto_compact": {...},
  "prompt_mode": "creative"
}
```

2. **mcp_config.json** - MCP серверы
3. **context/*.md** - промпты и знания

**Расширяемость**:
- ✅ Добавить MCP server: edit `mcp_config.json`
- ✅ Сменить модель: edit `config.json`
- ⚠️ Изменить prompt: edit Python код
- ⚠️ Добавить валидацию: edit Python код

### Claude Code Agents

**Декларативная конфигурация**:

```
feature-dev/
├── .claude-plugin/
│   └── plugin.json          # Метаданные плагина
├── commands/
│   └── feature-dev.md       # Workflow (markdown!)
└── agents/
    ├── code-explorer.md     # Агент (markdown!)
    └── code-architect.md
```

**Новый агент** - создай `agents/my-agent.md`:
```yaml
---
name: my-agent
description: What it does
tools: Glob, Read, Grep
model: sonnet
---

You are an expert in...

## Your Mission
...
```

**Новая команда** - создай `commands/my-cmd.md`:
```yaml
---
description: Command description
---

Phase 1: Do this
Phase 2: Launch my-agent to...
```

**Расширяемость**:
- ✅ Новый агент: создай `.md` файл
- ✅ Новая команда: создай `.md` файл
- ✅ Изменить workflow: редактируй markdown
- ✅ Нет компиляции кода!

---

## 8. Ключевые Различия

| Измерение | SimplePlanMCPAgent | Claude Code Agents |
|-----------|-------------------|-------------------|
| **Философия** | Автономность | Коллаборация |
| **Масштаб** | 100+ задач параллельно | 1 задача, multiple perspectives |
| **Скорость** | Быстро (1-2 мин/задача) | Медленно (10-30 мин/задача) |
| **Контроль** | Валидация в коде | Human gates |
| **Итерации** | Max 30 автоматически | Unlimited с approval |
| **Агенты** | 1 агент/задача | 2-3 агента/фаза |
| **Память** | Auto-compression | Phase isolation |
| **Конфиг** | JSON + Python | Markdown + YAML |
| **Tools** | Все MCP tools | Per-agent subset |
| **Ошибки** | Auto-retry + fix | Human review |
| **Расширение** | Код + конфиг | Только markdown |
| **Стоимость** | Оптимизирована (compression, cheap models) | Высокая (multiple agents, human time) |

---

## Паттерны и Анти-паттерны

### SimplePlanMCPAgent

**✅ Паттерны**:
- **Shared MCP manager** - одно подключение на всех воркеров
- **Two-stage pipeline** - дешевая классификация → дорогая генерация
- **Adaptive compression** - авто-управление context window
- **Validation with recovery** - retry → auto-fix → accept with warning
- **Configuration-driven** - поведение без изменения кода

**⚠️ Компромиссы**:
- **Prompts in code** - 480 строк template в `worker_pool.py`
- **Config sprawl** - настройки разбросаны (config.json, mcp_config.json, *.md)
- **Silent tool failures** - ошибки как строки, не structured
- **No resume** - нельзя продолжить после сбоя

### Claude Code Agents

**✅ Паттерны**:
- **Separation of concerns** - command orchestrates, agents execute
- **Declarative agents** - markdown вместо кода
- **Human-in-the-loop** - gates предотвращают waste
- **Redundancy for quality** - 3 reviewers находят больше
- **Progressive context** - знания накапливаются через фазы

**⚠️ Компромиссы**:
- **No batch mode** - только 1 задача за раз
- **Context isolation** - агенты не видят друг друга
- **Manual aggregation** - человек синтезирует результаты
- **Phase rigidity** - нельзя пропустить фазы
- **Slow** - human gates добавляют латентность

---

## Выводы

### Когда использовать SimplePlanMCPAgent

✅ **Подходит для**:
- High-volume batch processing (100+ задач)
- Четкие критерии качества (можно автоматизировать валидацию)
- Tool-heavy workflows (web scraping, API calls)
- Cost-sensitive приложения
- Автономная работа без human supervision

❌ **Не подходит для**:
- Сложные креативные задачи, требующие judgment calls
- Задачи с неоднозначными требованиями
- Когда важна трассируемость решений
- Когда нужна гибкость в процессе выполнения

**Пример use case**: Cold outreach at scale
- 500 лидов → классификация → personalized emails
- Валидация качества через правила
- Параллельная обработка 5-10 воркеров
- Minimal human involvement

### Когда использовать Claude Code Agents

✅ **Подходит для**:
- Feature development в незнакомом codebase
- Архитектурные решения
- Code review с multiple perspectives
- Обучение и exploration
- Задачи, где ошибки дорого обходятся

❌ **Не подходит для**:
- Batch processing
- Repetitive tasks с четкими критериями
- Автоматизированные pipelines
- Cost-sensitive сценарии (много human time)

**Пример use case**: Implement complex feature
- Исследовать codebase (2-3 explorers)
- Спроектировать архитектуру (2-3 architects)
- Реализовать + review (3 reviewers)
- Human утверждает на каждом этапе

---

## Рекомендации

### Для outreach_orchestrator (Stage 2)

**Возможные улучшения из Claude Code**:
1. **Декларативные промпты**: переместить templates из Python в markdown
2. **TodoWrite для debugging**: track agent progress
3. **Confidence scoring**: агент оценивает уверенность в rejection
4. **Multiple perspectives**: 2 агента генерируют варианты → выбор лучшего

**Что НЕ стоит копировать**:
- Human-in-the-loop gates (убьют throughput)
- Phase-based workflow (слишком rigid)
- Context isolation (нужна continuity для personalization)

### Для Claude Code

**Возможные улучшения из SimplePlanMCPAgent**:
1. **Auto-compression**: когда контекст растет в Phase 2-4
2. **Shared MCP manager**: если агенты используют одинаковые MCP tools
3. **Validation frameworks**: structured output validation для code generation
4. **Batch mode**: опциональный режим для repetitive tasks

**Что НЕ стоит копировать**:
- Auto-retry без human review (может маскировать проблемы)
- Single-agent model (теряется benefit of multiple perspectives)
- Aggressive compression (может потерять важный context)

---

## Заключение

SimplePlanMCPAgent и Claude Code Agents представляют **ортогональные подходы** к агентным системам:

| SimplePlanMCPAgent | Claude Code |
|--------------------|-------------|
| Production system | Development tool |
| Scale → Quality | Quality → Learning |
| Automation first | Human expertise first |
| Code > Config | Config > Code |

Обе системы excellent в своих нишах. Выбор зависит от:
- **Объем задач**: 1 vs 100+
- **Стоимость ошибки**: Высокая vs Приемлемая
- **Human availability**: Limited vs Available
- **Reproducibility**: Critical vs Nice-to-have

**Гибридный подход** может быть оптимален:
- Claude Code-style exploration → SimplePlanMCPAgent-style execution
- Human defines workflow → Agent scales it
- Best of both worlds

---

*Анализ основан на кодовой базе outreach_orchestrator и claude-code репозитория (январь 2025)*
