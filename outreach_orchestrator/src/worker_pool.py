"""
Worker Pool - parallel processing with classification and letter generation.
"""

import asyncio
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI

# Import from local modules (duplicated functionality)
from .classification import classify_single_lead
from .agent_wrapper import SimplePlanMCPAgent, load_mcp_config_from_file, MCPClientManager


class WorkerPool:
    """
    Manages parallel workers for lead processing.
    Each worker runs two stages:
    1. Cold-outreach classification
    2. Plan-MCP letter generation (if stage 1 = relevant)
    """

    def __init__(
        self,
        num_workers: int,
        context: Dict[str, str],
        mcp_config_path: Optional[str] = None
    ):
        """
        Initialize worker pool.

        Args:
            num_workers: Number of parallel workers
            context: Loaded context (GTM, guides, instruction)
            mcp_config_path: Path to MCP config
        """
        self.num_workers = num_workers
        self.context = context
        # Use local MCP config by default
        project_root = Path(__file__).parent.parent
        self.mcp_config_path = mcp_config_path or str(project_root / "mcp_config.json")

        # Initialize semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(num_workers)

        # Shared MCP client manager (one for all workers, initialized once)
        self.mcp_manager = None

        # Statistics
        self.stats = {
            'processed': 0,
            'stage1_relevant': 0,
            'stage1_not_relevant': 0,
            'stage2_letters': 0,
            'stage2_rejected': 0,
            'errors': 0
        }

    async def initialize_mcp(self):
        """Initialize shared MCP manager (call once before processing)."""
        if self.mcp_manager is not None:
            return  # Already initialized

        # Load MCP config
        try:
            mcp_config = load_mcp_config_from_file(self.mcp_config_path)
        except Exception as e:
            print(f"⚠ Could not load MCP config: {e}")
            mcp_config = {}

        # Create and initialize shared MCP manager
        self.mcp_manager = MCPClientManager(mcp_config)
        await self.mcp_manager.initialize()
        print(f"✓ Initialized shared MCP manager with {len(await self.mcp_manager.get_tools())} tools")

    async def close_mcp(self):
        """Close shared MCP manager (call once after all processing)."""
        if self.mcp_manager is not None:
            print("🔄 Closing MCP servers...")
            await self.mcp_manager.close()
            self.mcp_manager = None

    async def process_lead(self, task: Dict[str, Any], worker_id: str) -> Dict[str, Any]:
        """
        Process a single lead through both stages.

        Args:
            task: Task dictionary from queue
            worker_id: Worker identifier

        Returns:
            Result dictionary
        """
        async with self.semaphore:
            lead_data = task['lead_data']

            try:
                print(f"\n[Worker-{worker_id}] Processing: {task['email']}")

                # STAGE 1: Classification
                stage1_result = await self._stage1_classify(lead_data)

                if not stage1_result.get('relevant'):
                    print(f"[Worker-{worker_id}] ✗ Not relevant (Stage 1): {stage1_result.get('reason', 'N/A')[:80]}")
                    self.stats['stage1_not_relevant'] += 1
                    self.stats['processed'] += 1

                    return {
                        'stage1_result': stage1_result,
                        'stage2_result': None,
                        'status': 'completed'
                    }

                print(f"[Worker-{worker_id}] ✓ Relevant (Stage 1): {stage1_result.get('reason', 'N/A')[:80]}")
                self.stats['stage1_relevant'] += 1

                # STAGE 2: Letter Generation
                print(f"[Worker-{worker_id}] 🔧 Generating letter (Stage 2)...")
                stage2_result = await self._stage2_generate_letter(task, self.context)

                if stage2_result.get('rejected'):
                    print(f"[Worker-{worker_id}] ✗ Rejected (Stage 2): {stage2_result.get('reason', 'N/A')[:80]}")
                    self.stats['stage2_rejected'] += 1
                else:
                    print(f"[Worker-{worker_id}] ✓ Letter generated!")
                    self.stats['stage2_letters'] += 1

                self.stats['processed'] += 1

                return {
                    'stage1_result': stage1_result,
                    'stage2_result': stage2_result,
                    'status': 'completed'
                }

            except Exception as e:
                print(f"[Worker-{worker_id}] ⚠ Error: {str(e)}")
                self.stats['errors'] += 1
                self.stats['processed'] += 1

                return {
                    'stage1_result': None,
                    'stage2_result': None,
                    'status': 'failed',
                    'error': str(e)
                }

    async def _stage1_classify(self, lead_data: Dict) -> Dict:
        """
        Stage 1: Classify lead using cold-outreach-agent.

        Args:
            lead_data: Lead data dictionary

        Returns:
            Classification result: {relevant: bool, reason: str}
        """
        # Initialize DeepSeek for classification
        classification_model = os.getenv("DEEPSEEK_CLASSIFICATION_MODEL", "deepseek-chat")
        llm = ChatOpenAI(
            model=classification_model,
            temperature=0,
            base_url="https://api.deepseek.com",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model_kwargs={"response_format": {"type": "json_object"}}
        )

        # Prepare lead for classification
        lead = {
            'email': lead_data.get('Email') or lead_data.get('email'),
            'name': (lead_data.get('First Name', '') + ' ' + lead_data.get('Last Name', '')).strip() or lead_data.get('name'),
            'company': lead_data.get('companyName') or lead_data.get('company'),
            'job_title': lead_data.get('jobTitle') or lead_data.get('job_title'),
            'linkedin_url': lead_data.get('linkedIn') or lead_data.get('linkedin_url'),
            'raw_data': lead_data,
            'enriched_data': {}  # Will be enriched by Stage 2 if needed
        }

        # Run classification with GTM context
        gtm_context = self.context.get('gtm', '')
        result = await classify_single_lead(lead, llm, gtm_context)

        if result['error']:
            raise Exception(result['error'])

        return result['classification']

    async def _stage2_generate_letter(self, task: Dict, context: Dict) -> Dict:
        """
        Stage 2: Generate letter using plan_mcp_agent.

        Args:
            task: Task with lead data
            context: Agent context (GTM, guides, instruction)

        Returns:
            Letter generation result
        """
        if self.mcp_manager is None:
            return {
                'rejected': True,
                'reason': 'MCP manager not initialized',
                'letter': None
            }

        lead_data = task['lead_data']
        linkedin_url = task['linkedin_url']

        # Format task
        task_text = self._format_agent_task(lead_data, linkedin_url, context)

        # Create agent with shared MCP manager
        agent = SimplePlanMCPAgent(
            model="deepseek:deepseek-chat",
            max_iterations=30,
            shared_mcp_manager=self.mcp_manager  # Reuse shared MCP manager!
        )

        try:
            # Initialize agent (won't re-initialize MCP)
            await agent.initialize()

            # Run agent with the task
            result = await agent.run(task_text)

            # Extract result from agent output
            final_result = result.get('final_result', '')

            # Extract JSON from text (LLMs often add extra text around JSON)
            letter_result = self._extract_json_from_text(final_result)

            if not letter_result:
                # Fallback if no JSON found
                return {
                    'rejected': True,
                    'reason': 'Failed to parse agent response',
                    'letter': None,
                    'relevance_assessment': 'ERROR',
                    'notes': f'Raw response: {final_result[:200]}...'
                }

            return letter_result

        finally:
            # Always close agent
            await agent.close()

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """
        Extract JSON from text that may contain markdown or extra content.

        Args:
            text: Text that may contain JSON

        Returns:
            Parsed JSON dict or None
        """
        import re

        # Try 1: Find JSON in markdown code block ```json ... ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try 2: Find JSON object anywhere in text
        json_match = re.search(r'\{[^{}]*"rejected"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                # Find the full JSON object (handle nested braces)
                start = json_match.start()
                brace_count = 0
                end = start
                for i, char in enumerate(text[start:], start=start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break

                json_str = text[start:end]
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Try 3: Parse entire text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        return None

    def _format_agent_task(self, lead_data: Dict, linkedin_url: str, context: Dict) -> str:
        """
        Format task for plan_mcp_agent.

        Args:
            lead_data: Lead data
            linkedin_url: LinkedIn URL
            context: Context dictionary

        Returns:
            Formatted task string
        """
        name = (lead_data.get('First Name', '') + ' ' + lead_data.get('Last Name', '')).strip() or lead_data.get('name', 'N/A')
        company = lead_data.get('companyName') or lead_data.get('company', 'N/A')
        job_title = lead_data.get('jobTitle') or lead_data.get('job_title', 'N/A')

        return f"""
# Task: Cold Outreach Letter Generation

## Lead Information
- **Name:** {name}
- **Company:** {company}
- **Job Title:** {job_title}
- **LinkedIn:** {linkedin_url}

## Instructions - Порядок действий

**ШАГ 1: Используй sequential_thinking для планирования**
- Сначала вызови инструмент `sequentialthinking` чтобы распланировать работу

**ШАГ 2: ГЛУБОКОЕ исследование LinkedIn**
- Изучи LinkedIn профиль **ОБЯЗАТЕЛЬНО используя bright_data**
- LINKEDIN URL: {linkedin_url}
- ⚠️ **ВАЖНО: bright_data используй ТОЛЬКО для LinkedIn, ни для чего больше!**

**RETRY ЛОГИКА для bright_data:**
1. Попробуй bright_data для LinkedIn
2. Если получил ошибку или пустой результат → **ОБЯЗАТЕЛЬНО попробуй bright_data ЕЩЁ РАЗ**
3. Только после 2-х неудачных попыток можешь использовать tavily для поиска информации о человеке
4. Если совсем нет данных → отклони лида с причиной "Не удалось получить данные LinkedIn"

**ИЩИ КОНКРЕТИКУ в LinkedIn:**
- Свежие посты, активность, сертификации (последние 3-6 месяцев)
- Конференции, выступления, публикации
- Специфичные проекты, достижения, упоминания технологий
- Карьерные изменения, продвижения

**ШАГ 3: ГЛУБОКОЕ исследование компании**
- Используй **tavily-search** для изучения компании (НЕ bright_data!)
- Поищи свежие новости (последние 3-6 месяцев)
- Продукты, клиенты, кейсы
- Отрасль, конкуренты, вызовы
- Размер, стадия роста, funding

**ШАГ 4: Написание письма - КРИТЕРИИ КАЧЕСТВА**

**OBSERVATION должна быть:**
- ✅ Специфичная и свежая (последние 3-6 месяцев)
- ✅ Показывает реальное исследование (не "I saw you work at X")
- ❌ НЕ общие факты ("you're a manager")

**INSIGHT должен быть:**
- ✅ Неочевидным и демонстрирующим глубокое понимание их вызовов
- ✅ Связанным с болью ResolveOnce решает
- ❌ НЕ поверхностным ("you want to optimize processes")

**COMPANY CONTEXT:**
- ✅ Покажи понимание их бизнеса, отрасли, вызовов
- ✅ Увяжи с болью (knowledge loss, ticket resolution)

**POV Framework - СТРОГО:**
- Observation (1 sentence) - специфичная, свежая
- Insight (2-3 sentences) - глубокий, неочевидный, связь с их болью
- Soft question (1 sentence) - открытый вопрос, не pushy

- Оцени релевантность лида проекту (КОРОТКО)
- Порекомендуй время для отправки письма (по МСК)

**ШАГ 5: Финальная проверка**
- Убедись что всё готово для отправки

**КРИТИЧЕСКИ ВАЖНО:**
- 🚫 **НЕ используй bright_data для сайтов компаний, поиска, или чего-либо кроме LinkedIn!**
- 🚫 **НЕ используй firecrawl для LinkedIn - он не работает!**
- ✅ **Для LinkedIn → bright_data**
- ✅ **Для компаний/поиска → tavily-search**
- Письмо должно быть на английском языке
- Меня зовут Michael (Almas - это ошибка в документах)
- Пиши результат тут, не в документ

## Output Format

**ОБЯЗАТЕЛЬНО верни ТОЛЬКО валидный JSON (без markdown, без лишнего текста):**

Если лид релевантен:
```json
{{
  "rejected": false,
  "reason": null,
  "letter": {{
    "subject": "Email subject in English",
    "body": "Email body in English (POV Framework)",
    "send_time_msk": "Tuesday, 19:00 MSK",
    "personalization_signals": ["signal 1", "signal 2", "signal 3"]
  }},
  "relevance_assessment": "BRIEF relevance assessment in Russian",
  "notes": "Any additional notes"
}}
```

Если лид НЕ релевантен после глубокого исследования:
```json
{{
  "rejected": true,
  "reason": "Specific reason in Russian",
  "letter": null,
  "relevance_assessment": "NOT RELEVANT - brief explanation"
}}
```

---

## Project Context

{context.get('gtm', '')}

---

## Writing Guides

{context.get('guides', '')}

---

## Task Instructions

{context.get('instruction', '')}
"""

    def get_stats(self) -> Dict[str, int]:
        """Get current processing statistics."""
        return self.stats.copy()
