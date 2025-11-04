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
from .config_loader import load_config, get_classification_config, get_letter_generation_config, create_llm
from .agent_orchestrator import AgentOrchestrator
from .logger import get_logger

logger = get_logger(__name__)


# Pricing per 1M tokens (USD)
PRICING = {
    'gpt-5': {
        'input': 2.50,
        'output': 10.00,
        'cached_input': 1.25  # 50% discount (estimated, update with actual pricing)
    },
    'gpt-4o': {
        'input': 2.50,
        'output': 10.00,
        'cached_input': 1.25
    },
    'gpt-4o-mini': {
        'input': 0.150,
        'output': 0.600,
        'cached_input': 0.075
    },
    'deepseek-chat': {
        'input': 0.14,
        'output': 0.28,
        'cached_input': 0.014  # 90% discount
    },
    'o1': {
        'input': 15.00,
        'output': 60.00,
        'cached_input': 7.50
    },
    'o1-mini': {
        'input': 3.00,
        'output': 12.00,
        'cached_input': 1.50
    }
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """
    Calculate cost for token usage.

    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cached_tokens: Number of cached input tokens

    Returns:
        Cost in USD
    """
    pricing = PRICING.get(model, PRICING['gpt-4o'])  # Default to GPT-4o pricing

    # Regular input tokens (excluding cached)
    regular_input = max(0, input_tokens - cached_tokens)

    cost = (
        (regular_input / 1_000_000) * pricing['input'] +
        (cached_tokens / 1_000_000) * pricing['cached_input'] +
        (output_tokens / 1_000_000) * pricing['output']
    )

    return cost


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
        mcp_config_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize worker pool.

        Args:
            num_workers: Number of parallel workers
            context: Loaded context (GTM, guides, instruction)
            mcp_config_path: Path to MCP config
            config: Application configuration dictionary
        """
        self.num_workers = num_workers
        self.context = context
        # Use local MCP config by default
        project_root = Path(__file__).parent.parent
        self.mcp_config_path = mcp_config_path or str(project_root / "mcp_config.json")

        # Load config if not provided
        self.config = config or load_config()

        # Get model configs
        self.classification_config = get_classification_config(self.config)
        self.letter_generation_config = get_letter_generation_config(self.config)

        # Initialize semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(num_workers)

        # Shared MCP client manager (one for all workers, initialized once)
        self.mcp_manager = None

        # Agent orchestrator (multi-agent mode)
        self.orchestrator = None
        self.multi_agent_enabled = self.config.get('agent_orchestration', {}).get('enabled', False)

        # Statistics
        self.stats = {
            'processed': 0,
            'stage1_relevant': 0,
            'stage1_not_relevant': 0,
            'stage2_letters': 0,
            'stage2_rejected': 0,
            'errors': 0
        }

        # Token tracking
        self.token_stats = {
            'stage1_input': 0,
            'stage1_output': 0,
            'stage1_cached': 0,
            'stage2_input': 0,
            'stage2_output': 0,
            'stage2_cached': 0,
            'total_input': 0,
            'total_output': 0,
            'total_cached': 0,
            'total_cost_usd': 0.0
        }

        # Compression tracking
        self.compression_stats = {
            'total_compressions': 0,
            'total_messages_before': 0,
            'total_messages_after': 0
        }

    async def initialize_mcp(self):
        """Initialize shared MCP manager (call once before processing)."""
        if self.mcp_manager is not None:
            return  # Already initialized

        # Load MCP config from file
        try:
            mcp_config = load_mcp_config_from_file(self.mcp_config_path)
        except Exception as e:
            logger.warning(f"⚠ Could not load MCP config: {e}")
            mcp_config = {}

        # Filter MCP servers based on config.json enabled flags
        mcp_enabled_flags = self.config.get('mcp', {})
        filtered_config = {}

        for server_name, server_config in mcp_config.items():
            # Check if this server is enabled in config.json
            # Default to True if not specified (backward compatibility)
            is_enabled = mcp_enabled_flags.get(server_name, True)

            if is_enabled:
                filtered_config[server_name] = server_config
            else:
                logger.info(f"MCP server '{server_name}' disabled in config")

        # Show summary
        total_servers = len(mcp_config)
        enabled_servers = len(filtered_config)
        if enabled_servers < total_servers:
            logger.info(f"MCP: {enabled_servers}/{total_servers} servers enabled")

        # Create and initialize shared MCP manager
        self.mcp_manager = MCPClientManager(filtered_config)
        await self.mcp_manager.initialize()
        logger.info(f"✓ Initialized shared MCP manager with {len(await self.mcp_manager.get_tools())} tools")

        # Initialize agent orchestrator if multi-agent mode enabled
        if self.multi_agent_enabled:
            logger.info("🎭 Initializing Agent Orchestrator (multi-agent mode)...")
            self.orchestrator = AgentOrchestrator(
                config=self.config,
                context=self.context,
                shared_mcp_manager=self.mcp_manager
            )
            logger.info("✓ Agent Orchestrator ready")

    async def close_mcp(self):
        """Close shared MCP manager (call once after all processing)."""
        if self.mcp_manager is not None:
            logger.info("🔄 Closing MCP servers...")
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
                logger.info(f"[Worker-{worker_id}] Processing: {task['email']}")

                # STAGE 1: Classification
                stage1_result = await self._stage1_classify(lead_data)

                if not stage1_result.get('relevant'):
                    logger.info(f"[Worker-{worker_id}] ✗ Not relevant (Stage 1): {stage1_result.get('reason', 'N/A')[:80]}")
                    self.stats['stage1_not_relevant'] += 1
                    self.stats['processed'] += 1

                    return {
                        'stage1_result': stage1_result,
                        'stage2_result': None,
                        'status': 'completed'
                    }

                logger.info(f"[Worker-{worker_id}] ✓ Relevant (Stage 1): {stage1_result.get('reason', 'N/A')[:80]}")
                self.stats['stage1_relevant'] += 1

                # STAGE 2: Letter Generation
                logger.info(f"[Worker-{worker_id}] 🔧 Generating letter (Stage 2)...")
                stage2_result = await self._stage2_generate_letter(task, self.context)

                if stage2_result.get('rejected'):
                    logger.info(f"[Worker-{worker_id}] ✗ Rejected (Stage 2): {stage2_result.get('reason', 'N/A')[:80]}")
                    self.stats['stage2_rejected'] += 1
                else:
                    logger.info(f"[Worker-{worker_id}] ✓ Letter generated!")
                    self.stats['stage2_letters'] += 1

                self.stats['processed'] += 1

                return {
                    'stage1_result': stage1_result,
                    'stage2_result': stage2_result,
                    'status': 'completed'
                }

            except Exception as e:
                logger.error(f"[Worker-{worker_id}] ⚠ Error: {str(e)}")
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
        # Create LLM using config
        llm = create_llm(
            self.config,
            self.classification_config,
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

        # Track tokens if available
        if 'usage' in result and result['usage']:
            usage = result['usage']
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            cached_tokens = usage.get('cached_tokens', 0)

            self.token_stats['stage1_input'] += input_tokens
            self.token_stats['stage1_output'] += output_tokens
            self.token_stats['stage1_cached'] += cached_tokens
            self.token_stats['total_input'] += input_tokens
            self.token_stats['total_output'] += output_tokens
            self.token_stats['total_cached'] += cached_tokens

            # Calculate cost
            model = self.classification_config.get('model', 'gpt-4o')
            cost = calculate_cost(model, input_tokens, output_tokens, cached_tokens)
            self.token_stats['total_cost_usd'] += cost

        return result['classification']

    async def _stage2_generate_letter(self, task: Dict, context: Dict) -> Dict:
        """
        Stage 2: Generate letter.

        Routes to either:
        - Multi-agent orchestrator (if agent_orchestration.enabled)
        - Single agent (legacy mode)

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

        # Route to orchestrator if multi-agent mode enabled
        if self.multi_agent_enabled and self.orchestrator:
            return await self._stage2_multi_agent(task, context)

        # Otherwise use legacy single-agent mode
        return await self._stage2_single_agent(task, context)

    async def _stage2_multi_agent(self, task: Dict, context: Dict) -> Dict:
        """
        Stage 2: Generate letter using multi-agent orchestrator.

        Args:
            task: Task with lead data
            context: Agent context

        Returns:
            Letter generation result
        """
        lead_data = task['lead_data']

        # Prepare lead data for orchestrator
        lead_info = {
            'email': task['email'],
            'name': lead_data.get('name') or f"{lead_data.get('First Name', '')} {lead_data.get('Last Name', '')}".strip(),
            'company': lead_data.get('company') or lead_data.get('companyName'),
            'job_title': lead_data.get('job_title') or lead_data.get('jobTitle'),
            'linkedin_url': task.get('linkedin_url')
        }

        # Run orchestrator
        orch_result = await self.orchestrator.process_lead(lead_info, worker_id=task.get('worker_id', 'unknown'))

        # Normalize to canonical stage2_result format expected by ResultWriter:
        # {
        #   'rejected': bool,
        #   'reason': str|None,
        #   'letter': { 'subject', 'body', 'send_time_msk', ... } | None,
        #   'relevance_assessment': str|None,
        #   'notes': str|None
        # }
        # Orchestrator returns review_results with selected_letter and may set rejected flags at top level.
        if not isinstance(orch_result, dict):
            return {
                'rejected': True,
                'reason': 'Invalid orchestrator result',
                'letter': None,
                'relevance_assessment': 'ERROR',
                'notes': ''
            }

        if orch_result.get('status') == 'error':
            return {
                'rejected': True,
                'reason': orch_result.get('rejection_reason') or orch_result.get('error', 'Orchestrator error'),
                'letter': None,
                'relevance_assessment': 'ERROR',
                'notes': ''
            }

        if orch_result.get('rejected'):
            return {
                'rejected': True,
                'reason': orch_result.get('rejection_reason', 'Rejected by orchestrator'),
                'letter': None,
                'relevance_assessment': 'NOT RELEVANT',
                'notes': ''
            }

        review = orch_result.get('review_results', {}) or {}
        letter = review.get('selected_letter') or orch_result.get('stage2_result')

        # Try to propagate optional fields from the selected variant, if available
        relevance_assessment = None
        notes = review.get('selection_reasoning')

        try:
            selected_id = review.get('selected_variant_id') or review.get('selected_variant')
            variants = orch_result.get('variants') or []
            selected_variant = next((v for v in variants if v.get('variant_id') == selected_id), None)
            if isinstance(selected_variant, dict):
                relevance_assessment = selected_variant.get('relevance_assessment')
                # If writer returned notes at top level, append to notes
                if selected_variant.get('notes'):
                    notes = (notes + f"\n\nWriter notes: {selected_variant.get('notes')}") if notes else selected_variant.get('notes')
        except Exception:
            pass

        return {
            'rejected': False,
            'reason': None,
            'letter': letter if isinstance(letter, dict) else None,
            'relevance_assessment': relevance_assessment,
            'notes': notes
        }

    async def _stage2_single_agent(self, task: Dict, context: Dict) -> Dict:
        """
        Stage 2: Generate letter using single plan_mcp_agent (legacy mode).

        Args:
            task: Task with lead data
            context: Agent context (GTM, guides, instruction)

        Returns:
            Letter generation result
        """
        lead_data = task['lead_data']
        linkedin_url = task['linkedin_url']

        # Get available tools with descriptions
        tools = await self.mcp_manager.get_tools()

        # Format task with tool descriptions
        task_text = self._format_agent_task(lead_data, linkedin_url, context, tools)

        # Create agent with shared MCP manager
        max_iterations = self.config.get("worker_pool", {}).get("max_agent_iterations", 30)

        agent = SimplePlanMCPAgent(
            max_iterations=max_iterations,
            shared_mcp_manager=self.mcp_manager,  # Reuse shared MCP manager!
            config=self.config,
            model_config=self.letter_generation_config
        )

        try:
            # Run agent with the task (agent handles its own initialization)
            result = await agent.run(task_text)

            # Extract result from agent output
            final_result = result.get('final_result', '')

            # Track tokens from agent
            if 'token_usage' in result and result['token_usage']:
                usage = result['token_usage']
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cached_tokens = usage.get('cached_tokens', 0)

                self.token_stats['stage2_input'] += input_tokens
                self.token_stats['stage2_output'] += output_tokens
                self.token_stats['stage2_cached'] += cached_tokens
                self.token_stats['total_input'] += input_tokens
                self.token_stats['total_output'] += output_tokens
                self.token_stats['total_cached'] += cached_tokens

                # Calculate cost
                model = self.letter_generation_config.get('model', 'gpt-4o')
                cost = calculate_cost(model, input_tokens, output_tokens, cached_tokens)
                self.token_stats['total_cost_usd'] += cost

            # Track compression stats
            if 'compression_stats' in result and result['compression_stats']:
                comp = result['compression_stats']
                self.compression_stats['total_compressions'] += comp.get('count', 0)
                self.compression_stats['total_messages_before'] += comp.get('messages_before', 0)
                self.compression_stats['total_messages_after'] += comp.get('messages_after', 0)

            # Extract JSON from text (LLMs often add extra text around JSON)
            letter_result = self._extract_json_from_text(final_result)

            if not letter_result:
                # Enhanced error logging
                logger.warning(f"JSON parsing failed for lead")
                logger.debug(f"Response length: {len(final_result)} chars")
                logger.debug(f"First 500 chars: {final_result[:500]}")

                # Check if response contains rejection signals
                lower_result = final_result.lower()
                rejection_signals = ['reject', 'not relevant', 'не релевант', 'not a good fit', 'inappropriate']

                if any(signal in lower_result for signal in rejection_signals):
                    # Model rejected the lead - save full output
                    logger.info("Detected rejection in response, saving full output")
                    return {
                        'rejected': True,
                        'reason': 'Lead rejected by model (JSON parsing failed, but rejection detected)',
                        'letter': None,
                        'relevance_assessment': 'NOT RELEVANT',
                        'notes': f'Full model output:\n\n{final_result}'
                    }

                # No rejection detected - this is a parsing error
                logger.debug(f"Last 200 chars: {final_result[-200:]}")
                logger.error(f"Failed to parse JSON from agent response")
                return {
                    'rejected': True,
                    'reason': 'Failed to parse agent response - JSON not found in output',
                    'letter': None,
                    'relevance_assessment': 'ERROR',
                    'notes': f'Response length: {len(final_result)} | Preview: {final_result[:300]}...'
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

        if not text or not isinstance(text, str):
            return None

        # Try 1: Parse entire text as JSON (cleanest case)
        try:
            result = json.loads(text.strip())
            if isinstance(result, dict) and 'rejected' in result:
                return result
        except json.JSONDecodeError:
            pass

        # Try 2: Find JSON in markdown code block ```json ... ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try 3: Find JSON object with "rejected" field anywhere in text
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
            except json.JSONDecodeError as e:
                logger.debug(f"JSON parse error at position {start}: {str(e)}")
                pass

        # Try 4: Look for any JSON object in the text (more permissive)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                # Find the full JSON object
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
                result = json.loads(json_str)
                # Validate it has expected structure
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        return None

    def _format_agent_task_creative(self, lead_data: Dict, linkedin_url: str, context: Dict, tools: list) -> str:
        """
        Creative mode: Philosophy-driven prompt WITHOUT example phrases.
        Prevents LLM from templating "This usually means" etc.
        """
        name = (lead_data.get('First Name', '') + ' ' + lead_data.get('Last Name', '')).strip() or lead_data.get('name', 'N/A')
        company = lead_data.get('companyName') or lead_data.get('company', 'N/A')
        job_title = lead_data.get('jobTitle') or lead_data.get('job_title', 'N/A')

        # Format available tools with descriptions
        tools_description = "## Available Tools\n\n"
        for tool in tools:
            desc = tool.description[:300] + "..." if len(tool.description) > 300 else tool.description
            tools_description += f"**{tool.name}**\n{desc}\n\n"

        return f"""
# Your Mission: Write an Email That Shows You Actually Get Their World

{tools_description}

## Lead
- **Name:** {name}
- **Company:** {company}
- **Job Title:** {job_title}
- **LinkedIn:** {linkedin_url}

---

## The Philosophy

Mike Wonder's 45.8% reply rate came from one simple shift: stop talking about your solution, start talking about their problem.

Write like a normal person who deeply understands their world. Your email should make them think "how did this person get my situation so well?"

The formula is simple: Notice something specific about them + Share a non-obvious insight = Show you actually get it.

This is not a fill-in-the-blanks template. It's a way of thinking.

---

## How to Approach This

### 1. Research Phase

**LinkedIn research** ({linkedin_url}):
- Tool: `scrape_as_markdown` (retry once if fails)
- Look for: recent posts, certifications, job changes, projects
- Focus: What's fresh? (last 1-3 months ideal)

**Company research**:
- Tool: `tavily-search` for company news, funding, hiring, challenges
- Think: What stage? What pressures?

**Tool usage note**: `scrape_as_markdown` = LinkedIn only. `tavily-search` = everything else.

---

### 2. Think Deeply (via `sequentialthinking`)

Before writing, think through:

**About the person:**
- What do their recent posts/activities show about what they care about right now?
- What problems does someone in their role at a company like theirs actually face?
- What probably keeps them up at night that you can't tell just from their job title?

**About their company:**
- Recent news/hiring/growth → what internal pressures does this create?
- At their stage, what typically breaks first?
- How does industry context shape what matters to them?

**Connect to the real problem** (what happens when support knowledge gets lost):
- Does their team solve the same issues twice because past solutions aren't documented?
- Do new support hires struggle because they can't find how previous tickets were resolved?
- Are engineers wasting hours searching through old tickets instead of helping customers?
- How does THIS pain show up in THEIR specific situation?

**Test your thinking:**
- Could someone say this without deep research? → Keep digging
- Does this insight require understanding THEIR context? → Good
- Would this make them pause and think "I hadn't seen it that way"? → That's the goal

**About timing:**
- Their location and timezone?
- Role patterns (execs: early morning, engineers: afternoon)?
- Industry norms?
- When do they have mental space for this?

---

### 3. Draft the Email

**Subject line:**
- 2-3 words maximum
- Don't trigger mental spam filter
- Make them curious

**Email body:**
- Open with what you noticed about them (specific, recent, shows you did homework)
- Share what this probably means for them (non-obvious insight they haven't considered)
- Connect it to a real problem they're likely facing
- End with a question that opens dialogue without being salesy

**Quality check:**
- Take out their name/company → could this work for 10 others? If yes, too generic
- Does this sound like a real person talking, not a sales pitch?
- Would they think "how did they notice that about me?"
- Could ChatGPT write this? If yes, start over

**Language:**
- English
- Sign as Michael
- No corporate fluff
- No feature lists
- No hard meeting asks

---

### 4. Reality Check (via `sequentialthinking` again)

Read what you wrote and be honest:

- Is this observation truly about THEM, or could it be anyone?
- Would someone doing their job actually care about this insight?
- Am I showing I get their world, or am I just guessing?
- If I got this email, would I actually reply?

**If any answer is "no" or "maybe":**
- Get more specific about them personally
- Go one level deeper (ask yourself "so what?" again)
- Make the connection to their unique situation tighter

**Final gut check:**
- Read it out loud in your head
- Does it sound like a human talking, or like you're filling in a template?
- Is each sentence in your own words?

**Important**: Every email must be different. No copy-paste structures. No template phrases. You're showing genuine understanding, not filling in blanks.

---

## Technical Details

- `scrape_as_markdown` for LinkedIn only
- `tavily-search` for company research
- If data fails after retries, reject with clear reason
- Send time: think about timezone/role/receptiveness, specify in MSK, explain reasoning in notes
- Assessment can be in Russian

---

## CRITICAL VALIDATION

**Before returning your final JSON, verify these requirements:**

1. **Word count**: Body must be 75-85 words (count them!)
2. **Signature**: Must be "Michael" (NOT "Almas" or other names)
3. **Subject line**:
   - Exactly 2-3 words
   - NO question marks (?)
4. **CTA (Call-to-Action)**:
   - Maximum 10 words
   - Format: "Have you looked into X before?" or similar
   - Only ONE question in entire email body
5. **Banned phrases** - DO NOT use:
   - "I'm curious"
   - "Curious —"
   - "I figured"
   - "I noticed"

**If ANY validation fails → STOP and FIX before returning JSON.**

---

## Output Format

**CRITICAL: Your FINAL response must be ONLY pure JSON - no markdown, no explanations, no extra text.**

Example when relevant (return exactly like this, without ```json blocks):

{{
  "rejected": false,
  "reason": null,
  "letter": {{
    "subject": "Your subject",
    "body": "Your email body",
    "send_time_msk": "Day, time MSK based on their context",
    "personalization_signals": ["signal 1", "signal 2", "signal 3"]
  }},
  "relevance_assessment": "Brief assessment in Russian",
  "notes": "Include send time reasoning"
}}

Example when not relevant (return exactly like this, without ```json blocks):

{{
  "rejected": true,
  "reason": "Specific reason in Russian",
  "letter": null,
  "relevance_assessment": "NOT RELEVANT - explanation"
}}

**REMINDER: After completing your research and analysis, your FINAL message must be ONLY the pure JSON object shown above. Nothing else. No thinking, no explanations - just the JSON.**

---

## Project Context

{context.get('gtm', '')}

---

## Writing Guides

{context.get('guides', '')}

---

## Task Instructions

{context.get('instruction', '')}

---

## CRITICAL WARNING: Do NOT Copy Context Language

**The context documents above are for YOUR understanding only!**

❌ **DO NOT:**
- Copy phrases from the context documents into your emails
- Use jargony terms ("closure quality", "resolution process", "knowledge loss", etc.)
- Make subject lines about our product or features
- Sound like you're pitching something based on the context docs

✅ **DO:**
- Write subject lines about THEIR specific situation (their company, role, recent activity)
- Create completely unique emails based on YOUR research of the lead
- Use the context to understand WHO to target and WHY, not WHAT to write
- Make every word specific to this individual lead

**Remember:** The lead has NEVER seen our context documents. Your email should sound like you researched THEM, not like you're selling our product.
"""

    def _format_agent_task_standard(self, lead_data: Dict, linkedin_url: str, context: Dict, tools: list) -> str:
        """
        Standard mode: Current prompt with example phrases.
        May lead to repetitive language but provides stronger guidance.
        """
        name = (lead_data.get('First Name', '') + ' ' + lead_data.get('Last Name', '')).strip() or lead_data.get('name', 'N/A')
        company = lead_data.get('companyName') or lead_data.get('company', 'N/A')
        job_title = lead_data.get('jobTitle') or lead_data.get('job_title', 'N/A')

        # Format available tools with descriptions
        tools_description = "## Available MCP Tools\n\n"
        tools_description += "You have access to the following tools:\n\n"
        for tool in tools:
            # Truncate long descriptions
            desc = tool.description[:300] + "..." if len(tool.description) > 300 else tool.description
            tools_description += f"**{tool.name}**\n{desc}\n\n"

        return f"""
# Your Mission: Write a Cold Email That Proves You Understand Their World

{tools_description}

## Lead
- **Name:** {name}
- **Company:** {company}
- **Job Title:** {job_title}
- **LinkedIn:** {linkedin_url}

---

## Philosophy: The POV Framework

Mike Wonder achieved a 45.8% reply rate with one simple insight: **most cold emails talk about solutions, great emails talk about problems.**

Your job is to show you understand their business better than a random stranger should. Not by pitching anything, but by sharing a real insight.

**Notice something specific + Share non-obvious insight = Show you get it**

This isn't a template to fill in. It's a way of thinking: connect dots they haven't connected yet.

---

## Your Process

### Phase 1: Research

**For LinkedIn** ({linkedin_url}):
- Use `scrape_as_markdown` to get the profile (retry once if it fails, then use `tavily-search`)
- Look for: recent activity, posts, certifications, job changes, projects mentioned
- Prioritize: What happened in the last 1-3 months? What's fresh?

**For the company**:
- Use `tavily-search` to research the company
- Look for: recent news, funding, product launches, hiring patterns, industry challenges
- Think: What stage are they at? What pressures do they face?

**Important**: Use `scrape_as_markdown` ONLY for LinkedIn. Use `tavily-search` for everything else (company research, news, etc.).

---

### Phase 2: Deep Analysis (Use `sequentialthinking`)

After gathering data, use `sequentialthinking` to think through:

**About the person:**
- What do their recent posts/activities show about what they care about right now?
- What problems does someone in their role at a company like theirs actually face?
- What probably keeps them up at night that you can't tell just from their job title?

**About the company:**
- What does their recent news/hiring/growth reveal about internal pressures?
- At their stage (startup/scaleup/enterprise), what usually breaks first?
- How does their industry change what matters to them?

**Connect to the real problem:**
- Does their team solve the same issues twice because past solutions aren't documented?
- Do new support hires struggle because they can't find how previous tickets were resolved?
- Are engineers wasting hours searching through old tickets instead of helping customers?
- How does THIS pain show up in THEIR specific world?

**Reality check on your thinking:**
- Could someone say this without researching them? (If yes, go deeper)
- Does this insight need understanding THEIR specific situation? (If no, keep digging)
- Would this make them pause and think "huh, I hadn't looked at it that way"? (That's the goal)

**About when to send:**
- Where are they? (need to convert from MSK to their timezone)
- What's their role? (execs check email early morning, engineers might prefer afternoon)
- What industry? (B2B tech has different patterns than others)
- When would they actually have headspace for this? (mid-week usually better than Monday/Friday)
- Think: When do THEY have mental space to consider this?

---

### Phase 3: Write the Email

**Structure:**
- **Subject**: 2-3 words max (e.g., "Scaling support", "Team knowledge")
- **What you noticed**: Something specific and recent about them (shows you did homework)
- **What it probably means**: The non-obvious challenge this creates (shows you get it)
- **Simple question**: Opens dialogue without being pushy

**Quality check:**
- Remove name/company → would this fit 10 other people? → Too generic, start over
- Does this sound like a real person who understands their world? → Good
- Would they think "how did they notice that about me?" → Great

**Language:**
- Write in English
- Sign as Michael (not Almas)
- No fluff ("hope this finds you well", "happy Tuesday")
- No feature pitching
- No hard meeting request

---

### Phase 4: Reality Check (Use `sequentialthinking` again)

Before you finalize, be brutally honest:

**Ask yourself:**
- Is this observation truly about THEM, or could it be anyone in their field?
- Would someone smart in their role actually care about this insight?
- Does this sound like I get their world, or am I just guessing?
- If I got this email, would I actually reply?

**If any answer is "no" or "maybe":**
- Make the observation more specific to them personally
- Go one level deeper with the insight (ask "so what?" one more time)
- Tighten the connection to their unique situation

**Final test:**
"Could ChatGPT have written this?" → If yes, it's not good enough.

---

## Technical Notes

- Use `scrape_as_markdown` for LinkedIn URL only
- Use `tavily-search` for company research
- If data gathering fails after retries, reject the lead with a clear reason
- Assessment and send time in Russian is fine
- **Send time**: Think about their timezone, role, and when they're most receptive. Provide specific day + time in MSK (e.g., "Wednesday, 10:00 MSK" for US East Coast morning). Explain your reasoning in notes.

---

## CRITICAL VALIDATION

**Before returning your final JSON, verify these requirements:**

1. **Word count**: Body must be 75-85 words (count them!)
2. **Signature**: Must be "Michael" (NOT "Almas" or other names)
3. **Subject line**:
   - Exactly 2-3 words
   - NO question marks (?)
4. **CTA (Call-to-Action)**:
   - Maximum 10 words
   - Format: "Have you looked into X before?" or similar
   - Only ONE question in entire email body
5. **Banned phrases** - DO NOT use:
   - "I'm curious"
   - "Curious —"
   - "I figured"
   - "I noticed"

**If ANY validation fails → STOP and FIX before returning JSON.**

---

## Output Format

**КРИТИЧЕСКИ ВАЖНО: Твой ФИНАЛЬНЫЙ ответ должен быть ТОЛЬКО чистый JSON - без markdown блоков, без пояснений, без лишнего текста.**

Пример если лид релевантен (верни ТОЧНО так, БЕЗ ```json блоков):

{{
  "rejected": false,
  "reason": null,
  "letter": {{
    "subject": "Email subject in English",
    "body": "Email body in English (POV Framework)",
    "send_time_msk": "Specific day and time in MSK based on their context",
    "personalization_signals": ["signal 1", "signal 2", "signal 3"]
  }},
  "relevance_assessment": "BRIEF relevance assessment in Russian",
  "notes": "Include reasoning for send time choice based on their timezone/role/industry"
}}

Пример если лид НЕ релевантен (верни ТОЧНО так, БЕЗ ```json блоков):

{{
  "rejected": true,
  "reason": "Specific reason in Russian",
  "letter": null,
  "relevance_assessment": "NOT RELEVANT - brief explanation"
}}

**НАПОМИНАНИЕ: После завершения всех исследований и анализа, твой ФИНАЛЬНЫЙ ответ должен быть ТОЛЬКО чистый JSON объект как показано выше. Ничего больше. Без размышлений, без пояснений - только JSON.**

---

## Project Context

{context.get('gtm', '')}

---

## Writing Guides

{context.get('guides', '')}

---

## Task Instructions

{context.get('instruction', '')}

---

## КРИТИЧЕСКИ ВАЖНО: НЕ Копируй Язык из Контекстных Документов

**Контекстные документы выше - только для ТВОЕГО понимания!**

❌ **НЕ ДЕЛАЙ:**
- Копируй фразы из контекстных документов в письма
- Используй жаргон ("closure quality", "resolution process", "knowledge loss" и т.д.)
- Делай subject lines про наш продукт или фичи
- Звучи как будто питчишь что-то на основе context docs

✅ **ДЕЛАЙ:**
- Пиши subject lines про ИХ конкретную ситуацию (их компания, роль, недавняя активность)
- Создавай полностью уникальные письма на основе ТВОЕГО исследования лида
- Используй контекст чтобы понять КОГО таргетить и ПОЧЕМУ, а не ЧТО писать
- Делай каждое слово специфичным для этого конкретного лида

**Помни:** Лид НИКОГДА не видел наши контекстные документы. Твое письмо должно звучать как будто ты исследовал ЕГО, а не как будто продаешь наш продукт.
"""

    def _format_agent_task(self, lead_data: Dict, linkedin_url: str, context: Dict, tools: list) -> str:
        """
        Format task for plan_mcp_agent based on prompt_mode in config.

        Args:
            lead_data: Lead data
            linkedin_url: LinkedIn URL
            context: Context dictionary
            tools: List of available MCP tools

        Returns:
            Formatted task string
        """
        # Get prompt mode from config
        prompt_mode = self.config.get('prompt_mode', 'creative')

        if prompt_mode == 'creative':
            return self._format_agent_task_creative(lead_data, linkedin_url, context, tools)
        else:
            return self._format_agent_task_standard(lead_data, linkedin_url, context, tools)

    def get_stats(self) -> Dict[str, int]:
        """Get current processing statistics."""
        return self.stats.copy()

    def get_token_stats(self) -> Dict[str, Any]:
        """Get current token usage statistics."""
        return self.token_stats.copy()

    def get_compression_stats(self) -> Dict[str, Any]:
        """Get current compression statistics."""
        return self.compression_stats.copy()
