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
from .logger import get_logger

logger = get_logger(__name__)


# Pricing per 1M tokens (USD)
PRICING = {
    'gpt-5': {
        'input': 2.50,
        'output': 10.00,
        'cached_input': 1.25  # 50% discount
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

        # Get available tools with descriptions
        tools = await self.mcp_manager.get_tools()

        # Format task with tool descriptions
        task_text = self._format_agent_task(lead_data, linkedin_url, context, tools)

        # Create agent with shared MCP manager
<<<<<<< HEAD
        max_iterations = self.config.get("worker_pool", {}).get("max_agent_iterations", 30)

        agent = SimplePlanMCPAgent(
            max_iterations=max_iterations,
            shared_mcp_manager=self.mcp_manager,  # Reuse shared MCP manager!
            config=self.config,
            model_config=self.letter_generation_config
        )

        try:
            # Initialize agent (won't re-initialize MCP)
            await agent.initialize()

            # Run agent with the task
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
# Mission: Demonstrate Deep Understanding Through a Consultative Email

{tools_description}

## Lead
- **Name:** {name}
- **Company:** {company}
- **Job Title:** {job_title}
- **LinkedIn:** {linkedin_url}

---

## The Philosophy

Mike Wonder's 45.8% reply rate came from one shift: stop educating about your solution, start educating about their problem.

You're writing as a consultant who understands their world. Your email should make them think "how did this person understand my situation so well?"

POV Framework = Context + Observation/Insight = Demonstrating Expertise

This is not a template. This is a way of thinking.

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

**About them:**
- What does their recent activity reveal about current priorities?
- What challenges exist at their role + company stage intersection?
- What keeps them up at night that's not obvious from their title?

**About their company:**
- Recent news/hiring/growth → what internal pressures does this create?
- At their stage, what typically breaks first?
- How does industry context shape what matters to them?

**Connect to our problem space** (knowledge loss in ticket resolution):
- How does this pain point manifest in THEIR specific world?
- What consequence might they not have connected yet?
- Why is this more critical for them than a generic company?

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
- Open with what you noticed (specific, recent, shows research)
- Share the non-obvious pattern or consequence you see
- Identify the challenge this creates for them
- End with a soft question that opens conversation without being pushy

**Quality standard:**
- Remove their name/company → would this fit 10 others? If yes, too generic
- Does this sound like you're a consultant in their industry?
- Would they think "how did they spot that?"
- Could a bot write this? If yes, start over

**Language:**
- English
- Sign as Michael
- No corporate fluff
- No feature lists
- No hard meeting asks

---

### 4. Self-Critique (via `sequentialthinking` again)

Read your draft critically:

- Is the observation genuinely specific to them?
- Would someone smart in their role find the insight valuable?
- Am I demonstrating understanding or just guessing?
- If I received this, would I reply?

**If any answer is "no" or "maybe":**
- Make observation more specific
- Deepen insight (ask "so what?" one more time)
- Tighten connection to their unique context

**Final check:**
- Read it out loud mentally
- Does it sound natural or formulaic?
- Is each sentence in my own words, not borrowed phrases?

**Critical**: Each email must be unique. No repeated structures. No templated language. This is about demonstrating genuine understanding, not filling in blanks.

---

## Technical Details

- `scrape_as_markdown` for LinkedIn only
- `tavily-search` for company research
- If data fails after retries, reject with clear reason
- Send time: think about timezone/role/receptiveness, specify in MSK, explain reasoning in notes
- Assessment can be in Russian
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

Mike Wonder achieved a 45.8% reply rate with one insight: **most cold emails educate about solutions, great emails educate about problems.**

Your job is to demonstrate you understand their business better than they expect from a stranger. Not by pitching, but by showing insight.

**Context + Observation/Insight = Your Why**

This isn't a formula to fill in. It's a philosophy: connect dots they haven't connected yet.

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
- What does their recent activity tell you about their current priorities?
- What challenges does someone in their role + company stage typically face?
- What do they probably worry about that isn't obvious from their title?

**About the company:**
- What does their recent news/hiring/growth suggest about internal pressures?
- At their stage (startup/scaleup/enterprise), what typically breaks first?
- How does their industry context affect what matters to them?

**Connect to ResolveOnce's pain points:**
- Where does "knowledge loss in ticket resolution" show up in THEIR world?
- What's a non-obvious consequence they might not have connected yet?
- Why does this matter MORE for them specifically than for a generic company?

**The insight test:**
- Could someone write this observation without researching them? (If yes, go deeper)
- Does this insight require understanding their specific context? (If no, keep thinking)
- Would this make them think "huh, I hadn't thought about it that way"? (That's the goal)

**About send timing:**
- Where are they located? (affects timezone conversion from MSK)
- What's their role? (executives check email early morning, engineers might prefer afternoon)
- What industry? (B2B tech companies have different email patterns than others)
- When would they be most receptive? (start of week for planning, mid-week for execution, avoid Mondays/Fridays?)
- Think: When do THEY have mental space to think about this problem?

---

### Phase 3: Write the Email

**Structure** (POV Framework):
- **Subject**: 2-3 words max (e.g., "Scaling support", "Knowledge gaps")
- **Observation**: What you noticed (specific, recent, shows research)
- **Insight**: What this typically means + the challenge it creates (non-obvious, demonstrates expertise)
- **Soft question**: Have they considered [solution category]? (not pushy, opens conversation)

**Quality bar:**
- If you removed the name/company, would this email apply to 10 other people? → Too generic, rewrite
- Does the insight feel like a consultant who knows their industry? → Good
- Is the observation something they'd think "how did they notice that?" → Great

**Language:**
- Write in English
- Sign as Michael (not Almas)
- No fluff ("hope this finds you well", "happy Tuesday")
- No feature pitching
- No hard meeting request

---

### Phase 4: Critical Review (Use `sequentialthinking` again)

Before finalizing, critique your own draft:

**Ask yourself:**
- Is this observation truly specific to THEM, or could it be anyone in their industry?
- Is the insight something a smart person in their role would find valuable?
- Does this sound like I understand their world, or am I guessing?
- If I received this email, would I reply?

**If the answer to any is "no" or "maybe":**
- Revise the observation to be more specific
- Deepen the insight by going one level further (ask "so what?" again)
- Connect more tightly to their unique context

**The ultimate test:**
"Could an automated system have written this?" → If yes, it's not good enough.

---

## Technical Notes

- Use `scrape_as_markdown` for LinkedIn URL only
- Use `tavily-search` for company research
- If data gathering fails after retries, reject the lead with a clear reason
- Assessment and send time in Russian is fine
- **Send time**: Think about their timezone, role, and when they're most receptive. Provide specific day + time in MSK (e.g., "Wednesday, 10:00 MSK" for US East Coast morning). Explain your reasoning in notes.

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
"""

<<<<<<< HEAD
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

Mike Wonder achieved a 45.8% reply rate with one insight: **most cold emails educate about solutions, great emails educate about problems.**

Your job is to demonstrate you understand their business better than they expect from a stranger. Not by pitching, but by showing insight.

**Context + Observation/Insight = Your Why**

This isn't a formula to fill in. It's a philosophy: connect dots they haven't connected yet.

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
- What does their recent activity tell you about their current priorities?
- What challenges does someone in their role + company stage typically face?
- What do they probably worry about that isn't obvious from their title?

**About the company:**
- What does their recent news/hiring/growth suggest about internal pressures?
- At their stage (startup/scaleup/enterprise), what typically breaks first?
- How does their industry context affect what matters to them?

**Connect to ResolveOnce's pain points:**
- Where does "knowledge loss in ticket resolution" show up in THEIR world?
- What's a non-obvious consequence they might not have connected yet?
- Why does this matter MORE for them specifically than for a generic company?

**The insight test:**
- Could someone write this observation without researching them? (If yes, go deeper)
- Does this insight require understanding their specific context? (If no, keep thinking)
- Would this make them think "huh, I hadn't thought about it that way"? (That's the goal)

**About send timing:**
- Where are they located? (affects timezone conversion from MSK)
- What's their role? (executives check email early morning, engineers might prefer afternoon)
- What industry? (B2B tech companies have different email patterns than others)
- When would they be most receptive? (start of week for planning, mid-week for execution, avoid Mondays/Fridays?)
- Think: When do THEY have mental space to think about this problem?

---

### Phase 3: Write the Email

**Structure** (POV Framework):
- **Subject**: 2-3 words max (e.g., "Scaling support", "Knowledge gaps")
- **Observation**: What you noticed (specific, recent, shows research)
- **Insight**: What this typically means + the challenge it creates (non-obvious, demonstrates expertise)
- **Soft question**: Have they considered [solution category]? (not pushy, opens conversation)

**Quality bar:**
- If you removed the name/company, would this email apply to 10 other people? → Too generic, rewrite
- Does the insight feel like a consultant who knows their industry? → Good
- Is the observation something they'd think "how did they notice that?" → Great

**Language:**
- Write in English
- Sign as Michael (not Almas)
- No fluff ("hope this finds you well", "happy Tuesday")
- No feature pitching
- No hard meeting request

---

### Phase 4: Critical Review (Use `sequentialthinking` again)

Before finalizing, critique your own draft:

**Ask yourself:**
- Is this observation truly specific to THEM, or could it be anyone in their industry?
- Is the insight something a smart person in their role would find valuable?
- Does this sound like I understand their world, or am I guessing?
- If I received this email, would I reply?

**If the answer to any is "no" or "maybe":**
- Revise the observation to be more specific
- Deepen the insight by going one level further (ask "so what?" again)
- Connect more tightly to their unique context

**The ultimate test:**
"Could an automated system have written this?" → If yes, it's not good enough.

---

## Technical Notes

- Use `scrape_as_markdown` for LinkedIn URL only
- Use `tavily-search` for company research
- If data gathering fails after retries, reject the lead with a clear reason
- Assessment and send time in Russian is fine
- **Send time**: Think about their timezone, role, and when they're most receptive. Provide specific day + time in MSK (e.g., "Wednesday, 10:00 MSK" for US East Coast morning). Explain your reasoning in notes.

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
