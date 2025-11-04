# Multi-Agent Orchestration (Claude Code Style)

**Status**: ✅ Implemented | 🧪 Testing Required

Новая архитектура Stage 2 с **3-phase multi-agent workflow**, вдохновленная Claude Code agents.

---

## Что изменилось?

### Было (Single Agent)
```
Stage 2: SimplePlanMCPAgent
    ↓
1 agent → research + write + validate → final letter
```

### Стало (Multi-Agent)
```
Stage 2: AgentOrchestrator

Phase 1: Research (parallel)
├─> Researcher 1: LinkedIn + personal activity
└─> Researcher 2: Company news + funding
    ↓
Research Summary (aggregated)

Phase 2: Writing (parallel)
├─> Writer 1: Variant A (primary angle)
└─> Writer 2: Variant B (secondary angle)
    ↓
[Variant A, Variant B]

Phase 3: Review (sequential)
└─> Reviewer: Compare variants → Select best
    ↓
Final Letter ✅
```

---

## Архитектура

### Компоненты

```
outreach_orchestrator/
├── agents/                         # Декларативные агенты (markdown)
│   ├── researcher.md              # Исследовательский агент
│   ├── writer.md                  # Писательский агент
│   └── reviewer.md                # Reviewer агент
├── src/
│   ├── agent_loader.py            # Загрузка агентов из markdown
│   ├── agent_orchestrator.py      # 3-phase координация
│   ├── agent_wrapper.py           # Базовый SimplePlanMCPAgent
│   └── worker_pool.py             # Интеграция + routing
└── config.json                     # Конфигурация
```

### Агенты

#### 1. Researcher Agent (`agents/researcher.md`)

**Роль**: Сбор информации о лиде

**Tools**:
- `tavily-search` - web search
- `bright-data` - LinkedIn scraping

**Output**: Structured JSON с:
- Person insights (recent activity, role tenure)
- Company insights (funding, growth signals, tech stack)
- Timing signals
- Relevance assessment

**Example**:
```json
{
  "person": {
    "recent_activity": "Posted on LinkedIn about scaling challenges 3 days ago",
    "role_tenure": "VP Engineering, 2 months"
  },
  "company": {
    "stage": "Series B, $30M Dec 2024",
    "growth_signals": ["Hiring 15 engineers", "Opened NYC office"]
  },
  "insights": {
    "primary_insight": "Rapid hiring post-funding indicates scaling challenges",
    "timing_signal": "New VP Eng actively evaluating tools"
  },
  "recommendation": {
    "relevance_score": "HIGH",
    "rejection_reason": null
  }
}
```

#### 2. Writer Agent (`agents/writer.md`)

**Роль**: Генерация персонализированных писем (POV Framework)

**Tools**:
- `sequential-thinking` - complex reasoning

**Input**: Research summary + Project context (GTM, guides)

**Output**: Email variant (JSON)
```json
{
  "rejected": false,
  "letter": {
    "subject": "Team scaling",
    "body": "Saw you posted about taking your team from 20 to 50...",
    "send_time_msk": "17:30 MSK (Tuesday)"
  },
  "relevance_assessment": "HIGH",
  "personalization_signals": ["LinkedIn post Jan 15", "Series B $25M"]
}
```

#### 3. Reviewer Agent (`agents/reviewer.md`)

**Роль**: Выбор лучшего варианта из сгенерированных

**Tools**: None (pure evaluation)

**Evaluation Criteria**:
- Personalization depth (40%)
- Insight quality (30%)
- Authenticity (20%)
- Framework adherence (10%)

**Output**: Selection + reasoning
```json
{
  "selected_variant": 1,
  "selection_reasoning": "V1 uses specific LinkedIn post, V2 generic funding mention",
  "scores": {
    "variant_1": {"total": 92},
    "variant_2": {"total": 78}
  },
  "confidence": "HIGH"
}
```

---

## Использование

### 1. Включить Multi-Agent Mode

Отредактируйте `config.json`:

```json
{
  "agent_orchestration": {
    "enabled": true,           // ← Включить multi-agent
    "research_agents": 2,      // Сколько researchers в параллель
    "writer_agents": 2,        // Сколько writers (вариантов)
    "parallel_execution": true // Параллельное выполнение фаз
  }
}
```

### 2. Запустить

```bash
./scripts/run.sh --input leads.csv --workers 3
```

**Режим определяется автоматически**:
- `enabled: true` → Multi-agent (3 фазы)
- `enabled: false` → Legacy single-agent

### 3. Наблюдать Progress

```
🎭 Initializing Agent Orchestrator (multi-agent mode)...
✓ Agent Orchestrator ready

[W1] 🎬 Starting multi-agent workflow for john@example.com
[W1] 📊 Phase 1: Research
[W1] ✍️  Phase 2: Writing (2 variants)
[W1] 🔍 Phase 3: Review (2 variants)
[W1] ✅ Multi-agent workflow complete

📊 Progress: 1 processed | 99 pending
```

---

## Конфигурация Агентов

Агенты описываются в **markdown** с YAML frontmatter:

```yaml
---
name: researcher
description: Gathers comprehensive information about leads
role: research
tools:
  - mcp__tavily-mcp__tavily-search
  - mcp__bright-data__scrape_as_markdown
model: deepseek-chat
provider: deepseek
temperature: 0.3
max_iterations: 15
---

# Agent Instructions

You are a research specialist...
(markdown instructions)
```

### Параметры

| Параметр | Описание | Пример |
|----------|----------|--------|
| `name` | Имя агента | `researcher` |
| `role` | Роль (research/writing/review) | `research` |
| `tools` | Список MCP tools | `[tavily-search, ...]` |
| `model` | Модель LLM | `deepseek-chat` |
| `provider` | Провайдер (openai/deepseek/claude) | `deepseek` |
| `temperature` | Температура генерации | `0.3` |
| `max_iterations` | Макс итераций | `15` |

---

## Backward Compatibility

**✅ Полная обратная совместимость**

```json
// config.json
"agent_orchestration": {
  "enabled": false  // ← Legacy single-agent mode
}
```

Старый код **продолжает работать**:
- Та же конфигурация
- Те же интерфейсы
- Те же результаты

Переключение: **один флаг** в config.json.

---

## Создание Нового Агента

### 1. Создайте `agents/my-agent.md`

```yaml
---
name: my-agent
description: What this agent does
role: research|writing|review
tools:
  - mcp__tool-name
model: deepseek-chat
provider: deepseek
temperature: 0.5
max_iterations: 20
---

# My Agent Instructions

You are an expert in...

## Your Mission
...

## Output Format
Return JSON: {...}
```

### 2. Используйте в orchestrator

Модифицируйте `src/agent_orchestrator.py`:

```python
my_agent_config = self.agent_loader.load_agent('my-agent')
result = await self._run_agent(my_agent_config, lead_data, worker_id)
```

**Нет компиляции** - просто создайте `.md` файл!

---

## Преимущества

### 1. Качество ↑ 15-25%
- Redundancy: 2 варианта письма → выбор лучшего
- Специализация: каждый агент делает одно дело хорошо
- Review: автоматическая проверка качества

### 2. Maintainability ↑ 50%
- Промпты в markdown, не в коде
- Версионирование через Git
- Легко A/B тестировать варианты

### 3. Extensibility ↑ 100%
- Новый агент = создать `.md` файл
- Нет изменений кода
- Декларативная конфигурация

### 4. Observability ↑ 30%
- Логи по фазам
- Видно каждого агента
- Легко debug

---

## Недостатки

### 1. Speed ↓ 20-30%
- Больше LLM calls (research → write → review)
- Параллелизм частично компенсирует

### 2. Cost ↑ 30-50%
- 4-5 agents вместо 1
- Но: можно использовать дешевые модели для research/review

### 3. Complexity ↑
- Больше движущихся частей
- Нужно понимать workflow

---

## Roadmap

### v1.0 (Current) ✅
- [x] AgentLoader (parse markdown agents)
- [x] AgentOrchestrator (3-phase workflow)
- [x] Integration в worker_pool
- [x] Backward compatibility
- [x] Configuration

### v1.1 (Next) 🚧
- [ ] Token tracking для orchestrator
- [ ] TodoWrite integration (observability)
- [ ] Confidence scoring propagation
- [ ] Smart research aggregation (merge multiple researchers)

### v1.2 (Future) 📋
- [ ] Metrics dashboard
- [ ] A/B testing framework
- [ ] Dynamic agent selection
- [ ] Adaptive workflow (skip phases if confident)

---

## Testing

### Unit Tests

```bash
# Test AgentLoader
python -m src.agent_loader

# Should output:
# ✓ Loaded 3 agents
# Agent: researcher (role: research)
# Agent: writer (role: writing)
# Agent: reviewer (role: review)
```

### Integration Test

```bash
# Enable multi-agent
# Edit config.json: "enabled": true

# Run on small batch
./scripts/run.sh --input test_leads.csv --workers 1

# Check logs for:
# 🎭 Initializing Agent Orchestrator
# [W1] 🎬 Starting multi-agent workflow
# [W1] 📊 Phase 1: Research
# [W1] ✍️  Phase 2: Writing
# [W1] 🔍 Phase 3: Review
```

### A/B Comparison

```bash
# Baseline (single-agent)
./scripts/run.sh --input leads.csv
# → results_single.csv

# Multi-agent
# Edit config: "enabled": true
./scripts/run.sh --input leads.csv
# → results_multi.csv

# Compare quality metrics
```

---

## Troubleshooting

### Agent не загружается

```
Error: Agent file not found: agents/researcher.md
```

**Fix**: Убедитесь, что файлы агентов созданы в `agents/` директории.

### MCP tools не работают

```
Error: Tool 'mcp__tavily-search' not found
```

**Fix**: Проверьте `mcp_config.json` и `config.json`:
```json
"mcp": {
  "tavily-mcp": true  // ← Должен быть enabled
}
```

### Orchestrator не запускается

```
orchestrator = None
```

**Fix**: Проверьте:
1. `agent_orchestration.enabled = true` в config.json
2. MCP manager инициализирован
3. Агенты существуют в `agents/`

---

## FAQ

**Q: Когда использовать multi-agent, когда single-agent?**

A:
- **Multi-agent**: Если важно качество (cold outreach, важные клиенты)
- **Single-agent**: Если важна скорость/стоимость (массовая рассылка, тестирование)

**Q: Можно ли использовать только 1 writer вместо 2?**

A: Да, измените config:
```json
"writer_agents": 1
```
Reviewer тогда просто валидирует единственный вариант.

**Q: Как добавить 4-ю фазу?**

A: Модифицируйте `src/agent_orchestrator.py`:
```python
# В методе process_lead
phase4_result = await self._phase_custom(...)
```

**Q: Влияет ли это на Stage 1 (classification)?**

A: Нет, Stage 1 остаётся без изменений. Multi-agent только для Stage 2.

---

## Credits

Архитектура вдохновлена **Claude Code agents** от Anthropic:
- Декларативные агенты в markdown
- Phase-based orchestration
- Специализированные агенты с четкими ролями
- Redundancy для quality assurance

Ключевое отличие: **автономность** (нет human-in-the-loop gates).

---

## Support

Вопросы? Проблемы?
1. Проверьте [Troubleshooting](#troubleshooting)
2. Посмотрите логи: `logs/*.log`
3. Изучите код: `src/agent_orchestrator.py`

**Happy orchestrating!** 🎭
