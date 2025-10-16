# Cold Outreach Agent - План реализации

## Концепция

Агент для анализа обогащенных LinkedIn профилей и подготовки cold outreach стратегии.

**Ключевая идея:** Для больших объемов данных (>100 профилей) использовать **гибридный подход**:
- ⚡ **Быстрые алгоритмы** (hardcoded) для массовой обработки
- 🧠 **LLM агент** для reasoning и сложных решений

## Архитектура

```
Enriched JSON (1000+ profiles)
    ↓
[Агент с промптом и tools]
    ├→ [batch_score_leads] ← быстрый алгоритм
    ├→ [filter_by_criteria] ← быстрый алгоритм
    ├→ [rank_by_priority] ← быстрый алгоритм
    ├→ [analyze_top_leads] ← LLM для топ 50
    └→ [generate_outreach] ← LLM персонализация
```

**Агент решает стратегию:**
- "Сначала отфильтрую по signals (recent job change)"
- "Проскорю всех по ICP matching"
- "Топ 50 отправлю на детальный LLM анализ"
- "Для топ 20 сгенерирую персональные outreach сообщения"

## Преимущества подхода

### ✅ Эффективность
- Быстрые алгоритмы для фильтрации/скоринга (миллисекунды)
- LLM только для сложных задач (копейки)
- **Пример:** 1000 профилей → 50 через LLM вместо 1000

### ✅ Гибкость
- Алгоритмы легко менять (Python код)
- Агент адаптирует стратегию под данные
- Можно добавлять новые tools

### ✅ Стоимость
- $0.03 для обработки 1000 профилей вместо $3

## Платформы для реализации

### 1. n8n (рекомендуется для продакшена)

**Плюсы:**
- Визуальный редактор агентских флоу
- AI Agent node с tool calling
- 400+ интеграций (CRM, Notion, Slack)
- Self-hosted = бесплатно
- Scheduling, webhooks, error handling
- Debugging UI

**Минусы:**
- Нужен Docker/VPS (~$5/мес)
- Setup ~10 минут

**Когда использовать:**
- Нужны интеграции с другими сервисами
- Регулярные запуски по расписанию
- Хочешь визуально видеть флоу

**Setup:**
```bash
docker run -d -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

---

### 2. Langflow (рекомендуется для прототипа)

**Плюсы:**
- Специально для LLM агентов
- Проще чем n8n
- Drag-and-drop для AI workflows
- Python под капотом
- Легко экспортировать в код

**Минусы:**
- Меньше интеграций
- Молодой проект

**Когда использовать:**
- Быстрое прототипирование агента
- Фокус только на LLM обработке
- Хочешь потом перенести в код

**Setup:**
```bash
pip install langflow
langflow run
```

---

### 3. Python + Claude API (максимальный контроль)

**Плюсы:**
- Полный контроль
- Минимум зависимостей
- Версионирование как код
- Легко интегрировать с существующим проектом

**Минусы:**
- Нужно писать агентский луп
- Нет визуального UI

**Когда использовать:**
- Хочешь максимальный контроль
- Простой кейс
- Нужна интеграция с существующим кодом

---

### 4. LlamaIndex Agents

**Плюсы:**
- Готовый агентский луп
- Проще чем LangChain
- Хорошая документация
- Много готовых tools

**Минусы:**
- Дополнительная зависимость
- Нет UI

**Когда использовать:**
- Нужны готовые компоненты
- Не хочешь писать луп с нуля
- Планируешь RAG + agents

---

### 5. LangGraph ⭐ (РЕКОМЕНДУЕТСЯ для production)

**Современный фреймворк от LangChain** для production-grade агентов.

**Ключевая идея:** Агенты как **state machines** (граф состояний) вместо простого луппа.

**Плюсы:**
- ✅ **Полный контроль** над флоу агента
- ✅ **State management** - агент помнит всё
- ✅ **Human-in-the-loop** - можешь остановить и скорректировать
- ✅ **Персистентность** - продолжить после сбоя
- ✅ **Готовые шаблоны** агентов (ReAct, Plan-Execute, Multi-agent)
- ✅ **LangGraph Studio** - визуальный UI (beta)
- ✅ **Debugging** через LangSmith
- ✅ **Production-ready** - streaming, webhooks, API

**Минусы:**
- Нужно писать код (Python)
- Studio пока в beta

**Когда использовать:**
- **Production агенты** с высокими требованиями
- Нужен контроль над состояниями
- Сложная логика с условиями
- Human-in-the-loop
- Версионирование как код

**Setup:**
```bash
pip install langgraph langchain-anthropic
```

**Пример (готовая заготовка):**
```python
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

# 1. Определить tools
tools = [
    filter_by_signals_tool,
    score_leads_tool,
    rank_by_priority_tool,
    analyze_lead_deeply_tool,
]

# 2. LLM
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")

# 3. Создать агента (ReAct loop из коробки!)
agent = create_react_agent(
    llm,
    tools,
    state_modifier="Ты sales analyst..."  # промпт
)

# 4. Запустить
result = agent.invoke({
    "messages": [("user", "Обработай enriched.json")]
})
```

**Готовые шаблоны агентов:**
- **ReAct Agent** - классический think→act→observe
- **Plan-and-Execute** - сначала план, потом выполнение
- **Multi-agent** - несколько агентов координируют
- **Research Assistant** - поиск + анализ
- **Code Assistant** - генерация + выполнение кода

**LangGraph Studio (NEW!):**
- Визуальный редактор как n8n, но для LangGraph
- Видишь граф состояний в реальном времени
- Debugging + tracing каждого шага
- Экспорт в Python код
- Пока в beta, но очень круто

**LangGraph Cloud:**
- Managed deployment
- Деплоишь агента → получаешь API
- Human-in-the-loop из коробки
- Streaming responses

**Ссылки:**
- Repo: https://github.com/langchain-ai/langgraph
- Примеры: https://github.com/langchain-ai/langgraph/tree/main/examples
- Docs: https://langchain-ai.github.io/langgraph/
- Studio: https://blog.langchain.dev/langgraph-studio/

---

### 6. Open WebUI (для интерактива)

**Плюсы:**
- UI как Claude Desktop
- Легко тестировать промпты
- Function calling support
- Быстрый setup

**Минусы:**
- Меньше гибкости
- Не для автоматизации

**Когда использовать:**
- Нужен UI для ручного тестирования
- Интерактивная работа с данными
- Прототипирование промптов

**Setup:**
```bash
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

---

## Сравнение платформ

| Критерий | **LangGraph** | n8n | Langflow | Python API | LlamaIndex | Open WebUI |
|----------|---------------|-----|----------|------------|------------|------------|
| **Setup время** | 2 мин | 10 мин | 5 мин | 0 мин | 2 мин | 2 мин |
| **UI** | ✅ Studio (beta) | ✅ Отличный | ✅ Отличный | ❌ CLI | ❌ CLI | ✅ Хороший |
| **Гибкость** | ✅✅✅ Полная | Хорошая | Средняя | Полная | Хорошая | Низкая |
| **Для агентов** | ✅✅✅ Специально | ✅ AI Agent | ✅ Специально | ⚠️ Нужен луп | ✅ Готово | ⚠️ Базово |
| **Готовые шаблоны** | ✅✅ Много | ✅ Ноды | ✅ Компоненты | ❌ | ✅ Базовые | ❌ |
| **State management** | ✅✅✅ Да | ⚠️ Через переменные | ⚠️ Ограниченно | ❌ | ⚠️ Базово | ❌ |
| **Human-in-loop** | ✅✅✅ Нативно | ⚠️ Через паузы | ❌ | ❌ | ❌ | ✅ Chat |
| **Персистентность** | ✅✅✅ Да | ⚠️ Базово | ❌ | ❌ | ❌ | ❌ |
| **Интеграции** | Библиотеки | 400+ | Мало | Библиотеки | Библиотеки | Мало |
| **Стоимость** | Free | Free | Free | Free | Free | Free |
| **Автоматизация** | ✅✅✅ | ✅✅✅ | ✅✅ | ✅✅✅ | ✅✅✅ | ❌ |
| **Debugging** | ✅✅✅ LangSmith | ✅ Visual | ✅ Visual | Логи | Логи | ✅ Chat |
| **Production-ready** | ✅✅✅ | ✅✅ | ⚠️ Молодой | ✅✅✅ | ✅✅ | ❌ |

---

## Рекомендация по выбору

### ⭐ Для production агента (ТОП):
**LangGraph** - полный контроль, state management, персистентность, готовые шаблоны

### Для UI + интеграции с кучей сервисов:
**n8n** - визуальный, надежный, 400+ интеграций (CRM, Slack, Notion)

### Для быстрого прототипа с UI:
**Langflow** - быстро собрать визуально, потом экспортировать в код

### Для разовой простой обработки:
**Python + Claude API** - минимум кода, интеграция с существующим проектом

### Для интерактивного тестирования:
**Open WebUI** - удобно пробовать промпты и смотреть результаты

---

## Архитектура tools (алгоритмы)

### Быстрые алгоритмы (Python)

```python
# 1. Массовая фильтрация
def filter_by_signals(leads: list, criteria: dict) -> list:
    """
    Фильтрует профили по сигналам.

    Criteria:
    - recent_job_change: bool
    - min_tenure_months: int
    - max_tenure_months: int
    - required_companies: list
    - required_roles: list
    """
    # Быстрая фильтрация без LLM
    pass

# 2. Скоринг по ICP
def score_leads(leads: list, icp_config: dict) -> list:
    """
    Оценка 0-100 по Ideal Customer Profile.

    ICP config:
    - target_roles: ["VP Engineering", "CTO"]
    - target_company_size: "50-500"
    - must_have_signals: ["recent_job_change"]
    - bonus_signals: ["team_growth"]
    """
    # Алгоритмический скоринг
    pass

# 3. Ранжирование
def rank_by_priority(leads: list) -> list:
    """
    Сортировка по приоритету для outreach.

    Критерии:
    - ICP score (50%)
    - Signals score (30%)
    - Seniority (20%)
    """
    pass

# 4. Дедупликация
def deduplicate_leads(leads: list) -> list:
    """
    Удаление дубликатов по email/linkedin.
    """
    pass

# 5. Группировка
def group_by_company(leads: list) -> dict:
    """
    Группировка по компаниям для account-based outreach.
    """
    pass
```

### LLM tools (через агента)

```python
# 1. Детальный анализ
@tool
def analyze_lead_deeply(lead: dict, context: str) -> dict:
    """
    Глубокий анализ профиля через Claude.
    Используется только для топ кандидатов.
    """
    prompt = f"""
    Проанализируй профиль:
    {lead}

    Контекст: {context}

    Оцени:
    1. Fit с нашим ICP
    2. Вероятность ответа
    3. Pain points
    4. Персонализация для outreach
    """
    # Claude API call
    pass

# 2. Генерация outreach
@tool
def generate_outreach_message(lead: dict, template: str) -> str:
    """
    Персонализированное сообщение на основе профиля.
    """
    pass

# 3. Проверка новостей
@tool
def check_company_news(company: str) -> dict:
    """
    Поиск последних новостей о компании.
    """
    pass
```

---

## Пример промпта для агента

```
Ты sales analyst специализирующийся на B2B SaaS cold outreach.

Твоя задача:
1. Загрузить enriched JSON с LinkedIn профилями
2. Найти лучших кандидатов для cold outreach
3. Приоритизировать по вероятности конверсии
4. Подготовить персонализированные стратегии

Доступные инструменты:
- filter_by_signals: Быстрая фильтрация по job change сигналам
- score_leads: ICP scoring (0-100)
- rank_by_priority: Ранжирование для outreach
- analyze_lead_deeply: Детальный LLM анализ (используй экономно!)
- generate_outreach_message: Персонализированные сообщения
- check_company_news: Поиск новостей о компании

Стратегия:
1. Используй БЫСТРЫЕ алгоритмы для массовой обработки
2. LLM только для топ кандидатов (экономь токены!)
3. Приоритизируй recent job changes (< 6 месяцев)
4. Учитывай seniority и company fit

ICP (Ideal Customer Profile):
- Роли: VP Engineering, Engineering Manager, CTO
- Компании: B2B SaaS, 50-500 сотрудников
- Сигналы: Недавняя смена работы, team growth
- Локация: US, Europe

Результат:
- Топ 50 профилей с обоснованием
- Для топ 20: персонализированные outreach стратегии
- Группировка по компаниям если несколько лидов
```

---

## Стоимость обработки

### Пример: 1000 профилей

**Подход 1: Все через LLM (неэффективно)**
- 1000 профилей × 2000 токенов = 2M токенов
- Claude 3.5 Sonnet: ~$6

**Подход 2: Гибридный (эффективно)**
- Фильтрация: 1000 → 200 профилей (алгоритм, бесплатно)
- Скоринг: 200 профилей (алгоритм, бесплатно)
- LLM анализ: 50 профилей × 2000 токенов = 100K токенов
- Outreach: 20 профилей × 1000 токенов = 20K токенов
- **Итого:** 120K токенов ≈ **$0.36**

**Экономия: 94%**

---

## План реализации

### Этап 1: Алгоритмы (без LLM)
1. Создать `src/scoring.py` с быстрыми алгоритмами
2. Скрипт `scripts/score_leads.py` для тестирования
3. Валидация на существующих данных

### Этап 2: Выбор платформы
- **Для production агента** → **LangGraph** (готовые шаблоны + полный контроль)
- Если нужен UI + интеграции → n8n
- Если быстрый прототип → Langflow
- Если простая обработка → Python + Claude API

### Этап 3: Агент
1. Определить промпт
2. Подключить tools (алгоритмы + LLM)
3. Тестирование на реальных данных

### Этап 4: Оптимизация
1. Мониторинг стоимости
2. A/B тест разных стратегий
3. Улучшение промпта

---

## Интеграции (опционально)

После базовой реализации можно добавить:

- **Notion/Airtable:** Сохранение результатов
- **Slack:** Уведомления о hot leads
- **Apollo/Clay:** Обогащение дополнительными данными
- **Lemlist/Instantly:** Автоматический outreach
- **CRM (HubSpot/Salesforce):** Синхронизация лидов

n8n упрощает эти интеграции (готовые ноды).

---

## Следующие шаги

1. **Определить ICP** (Ideal Customer Profile)
2. **Написать алгоритмы скоринга** (быстрые, без LLM)
3. **Выбрать платформу** (n8n vs Langflow vs Python)
4. **Создать агента** с промптом и tools
5. **Тестировать** на enriched.json данных
6. **Оптимизировать** стоимость и качество

---

## Полезные ссылки

### LangGraph (рекомендуется)
- **Repo:** https://github.com/langchain-ai/langgraph
- **Docs:** https://langchain-ai.github.io/langgraph/
- **Примеры агентов:** https://github.com/langchain-ai/langgraph/tree/main/examples
- **LangGraph Studio:** https://blog.langchain.dev/langgraph-studio/
- **Tutorials:** https://langchain-ai.github.io/langgraph/tutorials/

### Другие платформы
- **n8n AI Agent:** https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/
- **Langflow:** https://github.com/logspace-ai/langflow
- **Claude Tool Use:** https://docs.anthropic.com/claude/docs/tool-use
- **LlamaIndex Agents:** https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/
- **Open WebUI:** https://github.com/open-webui/open-webui

---

## Пример LangGraph агента для обработки лидов

### Архитектура графа состояний

```
START
  ↓
[Load JSON] → state.leads
  ↓
[Filter by signals] → state.filtered_leads (algorithm, fast)
  ↓
[Score leads] → state.scored_leads (algorithm, fast)
  ↓
[Rank top 50] → state.top_leads (algorithm, fast)
  ↓
[DECISION: Analyze with LLM?] → Yes/No
  ↓ Yes
[Analyze deeply] → state.analyzed_leads (LLM, expensive)
  ↓
[Generate outreach] → state.outreach_messages (LLM, expensive)
  ↓
[Save results]
  ↓
END
```

### Код (готовая заготовка)

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
import json

# 1. Определить State
class AgentState(TypedDict):
    """State агента - данные передаются между нодами"""
    messages: list  # История сообщений
    leads: list  # Все лиды из JSON
    filtered_leads: list  # После фильтрации
    scored_leads: list  # С оценками
    top_leads: list  # Топ 50
    analyzed_leads: list  # После LLM анализа
    outreach_messages: list  # Сгенерированные сообщения
    next_action: str  # Что делать дальше

# 2. Быстрые алгоритмы (tools)
def load_json(state: AgentState) -> AgentState:
    """Загрузить JSON с профилями"""
    with open('enriched.json', 'r') as f:
        state['leads'] = json.load(f)
    print(f"Loaded {len(state['leads'])} leads")
    return state

def filter_by_signals(state: AgentState) -> AgentState:
    """Быстрая фильтрация по сигналам"""
    filtered = []
    for lead in state['leads']:
        signals = lead.get('enriched_data', {}).get('signals', {})
        # Фильтр: recent job change < 6 месяцев
        if signals.get('recent_job_change') or \
           (signals.get('tenure_months') and signals['tenure_months'] < 6):
            filtered.append(lead)

    state['filtered_leads'] = filtered
    print(f"Filtered to {len(filtered)} leads with signals")
    return state

def score_leads(state: AgentState) -> AgentState:
    """Алгоритмический скоринг по ICP"""
    target_roles = ['VP Engineering', 'CTO', 'Engineering Manager']

    for lead in state['filtered_leads']:
        score = 0
        enriched = lead.get('enriched_data', {})

        # Role match (50 points)
        role = enriched.get('current_role', '')
        if any(target in role for target in target_roles):
            score += 50

        # Recent job change (30 points)
        if enriched.get('signals', {}).get('recent_job_change'):
            score += 30

        # Followers (20 points)
        followers = enriched.get('followers', 0)
        if followers > 1000:
            score += 20
        elif followers > 500:
            score += 10

        lead['icp_score'] = score

    # Сортировка по score
    state['scored_leads'] = sorted(
        state['filtered_leads'],
        key=lambda x: x.get('icp_score', 0),
        reverse=True
    )

    avg_score = sum(l.get('icp_score', 0) for l in state['scored_leads']) / len(state['scored_leads'])
    print(f"Scored {len(state['scored_leads'])} leads, avg score: {avg_score:.1f}")

    return state

def rank_top_leads(state: AgentState) -> AgentState:
    """Выбрать топ 50"""
    state['top_leads'] = state['scored_leads'][:50]
    print(f"Selected top {len(state['top_leads'])} leads for LLM analysis")
    return state

# 3. LLM ноды
def analyze_with_llm(state: AgentState) -> AgentState:
    """LLM анализ топ лидов"""
    llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")

    analyzed = []
    for lead in state['top_leads'][:20]:  # Только топ 20 для экономии
        enriched = lead.get('enriched_data', {})

        prompt = f"""
        Проанализируй LinkedIn профиль для cold outreach:

        Роль: {enriched.get('current_role')}
        Компания: {enriched.get('current_company')}
        Tenure: {enriched.get('signals', {}).get('tenure_months')} месяцев
        Recent job change: {enriched.get('signals', {}).get('recent_job_change')}

        Оцени:
        1. Fit с ICP (0-100)
        2. Вероятность ответа на cold email (0-100)
        3. Ключевые pain points
        4. Персонализация для outreach (1-2 предложения)

        Ответь в JSON формате.
        """

        response = llm.invoke([HumanMessage(content=prompt)])

        try:
            analysis = json.loads(response.content)
            lead['llm_analysis'] = analysis
            analyzed.append(lead)
        except:
            print(f"Failed to parse LLM response for {lead.get('email')}")

    state['analyzed_leads'] = analyzed
    print(f"LLM analyzed {len(analyzed)} leads")

    return state

def generate_outreach(state: AgentState) -> AgentState:
    """Генерация персонализированных сообщений"""
    llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")

    messages = []
    for lead in state['analyzed_leads'][:10]:  # Топ 10
        analysis = lead.get('llm_analysis', {})
        enriched = lead.get('enriched_data', {})

        prompt = f"""
        Напиши персонализированное cold outreach сообщение:

        Профиль:
        - Имя: {lead.get('name')}
        - Роль: {enriched.get('current_role')}
        - Компания: {enriched.get('current_company')}

        Insights:
        - Pain points: {analysis.get('pain_points')}
        - Персонализация: {analysis.get('personalization')}

        Продукт: AI-powered development tools для engineering teams

        Требования:
        - Короткое (3-4 предложения)
        - Персонализированное
        - С конкретным value proposition
        - Call to action
        """

        response = llm.invoke([HumanMessage(content=prompt)])

        messages.append({
            'email': lead.get('email'),
            'name': lead.get('name'),
            'message': response.content,
            'icp_score': lead.get('icp_score'),
            'llm_score': analysis.get('icp_fit')
        })

    state['outreach_messages'] = messages
    print(f"Generated {len(messages)} outreach messages")

    return state

def save_results(state: AgentState) -> AgentState:
    """Сохранить результаты"""
    # Сохранить analyzed leads
    with open('analyzed_leads.json', 'w') as f:
        json.dump(state['analyzed_leads'], f, indent=2)

    # Сохранить outreach messages
    with open('outreach_messages.json', 'w') as f:
        json.dump(state['outreach_messages'], f, indent=2)

    print("✓ Results saved!")
    return state

# 4. Собрать граф
def create_agent():
    """Создать LangGraph агента"""
    workflow = StateGraph(AgentState)

    # Добавить ноды
    workflow.add_node("load_json", load_json)
    workflow.add_node("filter", filter_by_signals)
    workflow.add_node("score", score_leads)
    workflow.add_node("rank", rank_top_leads)
    workflow.add_node("analyze_llm", analyze_with_llm)
    workflow.add_node("generate_outreach", generate_outreach)
    workflow.add_node("save", save_results)

    # Определить флоу
    workflow.set_entry_point("load_json")
    workflow.add_edge("load_json", "filter")
    workflow.add_edge("filter", "score")
    workflow.add_edge("score", "rank")
    workflow.add_edge("rank", "analyze_llm")
    workflow.add_edge("analyze_llm", "generate_outreach")
    workflow.add_edge("generate_outreach", "save")
    workflow.add_edge("save", END)

    return workflow.compile()

# 5. Запустить
if __name__ == "__main__":
    agent = create_agent()

    # Начальный state
    initial_state = {
        "messages": [],
        "leads": [],
        "filtered_leads": [],
        "scored_leads": [],
        "top_leads": [],
        "analyzed_leads": [],
        "outreach_messages": [],
        "next_action": ""
    }

    # Запустить агента
    result = agent.invoke(initial_state)

    print("\n=== Agent completed! ===")
    print(f"Total leads: {len(result['leads'])}")
    print(f"Filtered: {len(result['filtered_leads'])}")
    print(f"Top scored: {len(result['top_leads'])}")
    print(f"LLM analyzed: {len(result['analyzed_leads'])}")
    print(f"Outreach messages: {len(result['outreach_messages'])}")
```

### Преимущества этого подхода

✅ **State management** - каждая нода видит весь контекст
✅ **Визуализация** - можно посмотреть граф в LangGraph Studio
✅ **Персистентность** - можно остановить и продолжить
✅ **Human-in-the-loop** - легко добавить подтверждение перед LLM
✅ **Debugging** - видно что происходит на каждом шаге
✅ **Гибкость** - легко менять флоу

### Стоимость обработки

**Пример: 1000 профилей**
- Load + Filter + Score + Rank: 0 токенов (алгоритмы)
- LLM анализ: 20 профилей × 2000 токенов = 40K токенов
- Outreach: 10 сообщений × 1000 токенов = 10K токенов
- **Итого:** 50K токенов ≈ **$0.15**

Вместо $6 если все через LLM!

---

## Заметки

- Приоритет: **Эффективность > Фичи**
- Большие JSON → сначала алгоритмы, потом LLM
- Агент для reasoning, не для массовой обработки
- Мониторить стоимость на каждом этапе
- **LangGraph - лучший выбор** для production агентов с контролем
