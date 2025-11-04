"""
Agent Orchestrator - coordinates multi-agent workflow for letter generation.

Implements 3-phase autonomous workflow inspired by Claude Code:
- Phase 1: Research (parallel researchers gather insights)
- Phase 2: Writing (parallel writers generate variants)
- Phase 3: Review (single reviewer selects best variant)
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path

from .agent_loader import AgentLoader, AgentConfig
from .agent_wrapper import SimplePlanMCPAgent, MCPClientManager
from .logger import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """
    Orchestrates multi-agent workflow for cold email generation.

    Architecture:
    - Phase 1: 1-2 researcher agents (parallel) → research summary
    - Phase 2: 2 writer agents (parallel) → email variants
    - Phase 3: 1 reviewer agent (sequential) → best variant selection

    Unlike Claude Code, this runs AUTONOMOUSLY (no human gates).
    """

    def __init__(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
        shared_mcp_manager: Optional[MCPClientManager] = None,
        agents_dir: str = "agents"
    ):
        """
        Initialize orchestrator.

        Args:
            config: Full application config (for LLM settings, etc.)
            context: Project context (GTM, guides, instructions)
            shared_mcp_manager: Shared MCP manager for all agents
            agents_dir: Directory containing agent markdown files
        """
        self.config = config
        self.context = context
        self.shared_mcp_manager = shared_mcp_manager
        self.agents_dir = Path(agents_dir)

        # Load agent configurations
        self.agent_loader = AgentLoader(str(self.agents_dir))

        # Get orchestration settings
        orch_config = config.get('agent_orchestration', {})
        self.num_researchers = orch_config.get('research_agents', 2)
        self.num_writers = orch_config.get('writer_agents', 2)
        self.parallel_execution = orch_config.get('parallel_execution', True)

        logger.info(f"🎭 AgentOrchestrator initialized: {self.num_researchers} researchers, {self.num_writers} writers")

    async def process_lead(
        self,
        lead_data: Dict[str, Any],
        worker_id: str = "main"
    ) -> Dict[str, Any]:
        """
        Process a single lead through 3-phase workflow.

        Args:
            lead_data: Lead information (name, company, title, linkedin, etc.)
            worker_id: Worker identifier for logging

        Returns:
            Result dict with final letter or rejection
        """
        logger.info(f"[{worker_id}] 🎬 Starting multi-agent workflow for {lead_data.get('email', 'unknown')}")

        try:
            # Phase 1: Research
            logger.info(f"[{worker_id}] 📊 Phase 1: Research")
            research_results = await self._phase_research(lead_data, worker_id)

            # Check if research rejected the lead
            if research_results.get('rejected', False):
                logger.info(f"[{worker_id}] ✗ Lead rejected in research phase: {research_results.get('rejection_reason')}")
                return {
                    'status': 'rejected_research',
                    'rejected': True,
                    'rejection_reason': research_results.get('rejection_reason'),
                    'research_results': research_results,
                    'stage2_result': None
                }

            # Phase 2: Writing
            logger.info(f"[{worker_id}] ✍️  Phase 2: Writing ({self.num_writers} variants)")
            variants = await self._phase_writing(lead_data, research_results, worker_id)

            # Check if all writers rejected
            valid_variants = [v for v in variants if not v.get('rejected', False)]
            if not valid_variants:
                logger.info(f"[{worker_id}] ✗ All writers rejected the lead")
                return {
                    'status': 'rejected_writing',
                    'rejected': True,
                    'rejection_reason': 'All writer variants were rejected',
                    'research_results': research_results,
                    'variants': variants,
                    'stage2_result': None
                }

            # Phase 3: Review
            logger.info(f"[{worker_id}] 🔍 Phase 3: Review ({len(valid_variants)} variants)")
            final_result = await self._phase_review(valid_variants, research_results, worker_id)

            logger.info(f"[{worker_id}] ✅ Multi-agent workflow complete")

            return {
                'status': 'success',
                'rejected': False,
                'research_results': research_results,
                'variants': variants,
                'review_results': final_result,
                'stage2_result': final_result.get('selected_letter')  # For backward compat
            }

        except Exception as e:
            logger.error(f"[{worker_id}] ❌ Orchestrator error: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'rejected': True,
                'rejection_reason': f'Orchestrator error: {str(e)}'
            }

    async def _phase_research(
        self,
        lead_data: Dict[str, Any],
        worker_id: str
    ) -> Dict[str, Any]:
        """
        Phase 1: Research - gather insights about the lead.

        Launches 1-2 researcher agents in parallel to gather information.
        Aggregates their findings into a comprehensive research summary.

        Args:
            lead_data: Lead information
            worker_id: Worker identifier

        Returns:
            Research summary dict
        """
        # Load researcher agent config
        researcher_config = self.agent_loader.load_agent('researcher')

        # Create researcher tasks
        if self.num_researchers == 1:
            # Single researcher
            research_result = await self._run_agent(
                researcher_config,
                lead_data,
                worker_id,
                agent_id="researcher"
            )
            return self._parse_json_result(research_result)

        else:
            # Multiple researchers
            if self.parallel_execution:
                # Parallel execution
                research_tasks = []
                for i in range(self.num_researchers):
                    focus = self._get_research_focus(i)
                    task = self._run_agent(
                        researcher_config,
                        lead_data,
                        worker_id,
                        agent_id=f"researcher-{i+1}",
                        additional_context=f"\nPRIORITY FOCUS: {focus}"
                    )
                    research_tasks.append(task)

                results = await asyncio.gather(*research_tasks, return_exceptions=True)
                return self._aggregate_research(results)
            else:
                # Sequential execution
                results = []
                for i in range(self.num_researchers):
                    focus = self._get_research_focus(i)
                    try:
                        res = await self._run_agent(
                            researcher_config,
                            lead_data,
                            worker_id,
                            agent_id=f"researcher-{i+1}",
                            additional_context=f"\nPRIORITY FOCUS: {focus}"
                        )
                        results.append(res)
                    except Exception as e:
                        results.append(e)
                return self._aggregate_research(results)

    async def _phase_writing(
        self,
        lead_data: Dict[str, Any],
        research_results: Dict[str, Any],
        worker_id: str
    ) -> List[Dict[str, Any]]:
        """
        Phase 2: Writing - generate email variants.

        Launches 2 writer agents in parallel to generate different email approaches.

        Args:
            lead_data: Lead information
            research_results: Research findings from Phase 1
            worker_id: Worker identifier

        Returns:
            List of email variant dicts
        """
        # Load writer agent config
        writer_config = self.agent_loader.load_agent('writer')

        if self.parallel_execution:
            # Create writer tasks (parallel)
            writer_tasks = []
            for i in range(self.num_writers):
                angle = self._get_writing_angle(i, research_results)
                task = self._run_agent(
                    writer_config,
                    lead_data,
                    worker_id,
                    agent_id=f"writer-{i+1}",
                    additional_context=f"\nRESEARCH FINDINGS:\n{json.dumps(research_results, indent=2)}\n\nSUGGESTED ANGLE: {angle}"
                )
                writer_tasks.append(task)

            results = await asyncio.gather(*writer_tasks, return_exceptions=True)
        else:
            # Sequential writing
            results = []
            for i in range(self.num_writers):
                angle = self._get_writing_angle(i, research_results)
                try:
                    res = await self._run_agent(
                        writer_config,
                        lead_data,
                        worker_id,
                        agent_id=f"writer-{i+1}",
                        additional_context=f"\nRESEARCH FINDINGS:\n{json.dumps(research_results, indent=2)}\n\nSUGGESTED ANGLE: {angle}"
                    )
                    results.append(res)
                except Exception as e:
                    results.append(e)

        # Parse and return variants
        variants = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[{worker_id}] Writer {i+1} failed: {result}")
                variants.append({
                    'rejected': True,
                    'rejection_reason': f'Writer agent error: {str(result)}',
                    'variant_id': i + 1
                })
            else:
                parsed = self._parse_json_result(result)
                parsed['variant_id'] = i + 1
                # Heuristic validation: flag generic/placeholder observations
                validated = self._validate_personalization(parsed, lead_data)
                if not validated['ok']:
                    logger.info(
                        f"[{worker_id}] ✗ Variant {i+1} rejected: {validated['reason']}"
                    )
                    variants.append({
                        'rejected': True,
                        'rejection_reason': validated['reason'],
                        'variant_id': i + 1
                    })
                else:
                    variants.append(parsed)

        return variants

    def _validate_personalization(self, variant: Dict[str, Any], lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Heuristically validate that personalization is specific and non-generic.

        Rules (fail if any):
        - Missing personalization_signals
        - Signals contain placeholders or ultra-generic facts (e.g., "works as X at Y")
        - Signals too short (< 6 words) and without specificity cues (digits/dates/verbs like posted/hiring/raised)
        - Contains obvious placeholders like "company", "companyName", "jobTitle"

        Returns:
            { ok: bool, reason: str }
        """
        try:
            signals = []
            # Writer might put signals either at top-level or inside letter
            if isinstance(variant, dict):
                signals = variant.get('personalization_signals') or []
                if not signals and isinstance(variant.get('letter'), dict):
                    signals = variant['letter'].get('personalization_signals') or []

            if not signals:
                return { 'ok': False, 'reason': 'Missing personalization_signals (must reference a specific, verifiable observation)' }

            # Prepare basic context words to detect tautologies
            role = (lead_data.get('job_title') or lead_data.get('jobTitle') or '').lower()
            company = (lead_data.get('company') or lead_data.get('companyName') or '').lower()
            person = (lead_data.get('name') or '').lower()

            # Disallowed generic patterns
            disallowed_substrings = [
                'you work as', 'you are working as', 'работаешь', 'ты работаешь',
                'works as', 'working as', 'it support manager',
                'at company', 'в компании company', 'company company',
                'job title', 'companyname', 'linkedin profile', 'generic observation'
            ]

            specificity_markers = [
                'posted', 'post', 'commented', 'article', 'hiring', 'opening', 'open roles', 'raised', 'series',
                'joined', 'months', 'years', 'week', 'weeks', 'days', 'yesterday', 'today', 'announcement', 'launch',
                'funding', 'seed', 'series a', 'series b', 'series c'
            ]

            def looks_generic(text: str) -> bool:
                t = (text or '').strip().lower()
                if not t:
                    return True
                # Placeholder tokens or boilerplate
                if any(s in t for s in disallowed_substrings):
                    return True
                if 'company' == t or 'job title' == t:
                    return True
                # Pure tautology of role/company
                if company and company in t and ('work' in t or 'работа' in t) and (role and role in t):
                    return True
                # Very short and no specificity cues
                word_count = len(t.split())
                has_digit = any(ch.isdigit() for ch in t)
                has_marker = any(m in t for m in specificity_markers)
                if word_count < 6 and not has_digit and not has_marker:
                    return True
                return False

            bad = [s for s in signals if looks_generic(s)]
            if bad:
                example = bad[0]
                return {
                    'ok': False,
                    'reason': f"Generic/placeholder observation found: '{example[:80]}'"
                }

            return { 'ok': True, 'reason': '' }
        except Exception as e:
            # Fail closed to be safe
            return { 'ok': False, 'reason': f'Personalization validation error: {str(e)}' }

    async def _phase_review(
        self,
        variants: List[Dict[str, Any]],
        research_results: Dict[str, Any],
        worker_id: str
    ) -> Dict[str, Any]:
        """
        Phase 3: Review - select best email variant.

        Single reviewer agent evaluates all variants and selects the best one.

        Args:
            variants: List of email variants from Phase 2
            research_results: Research findings (for context)
            worker_id: Worker identifier

        Returns:
            Review results with selected variant
        """
        # Load reviewer agent config
        reviewer_config = self.agent_loader.load_agent('reviewer')

        # Prepare variants for review
        variants_for_review = []
        for v in variants:
            variants_for_review.append({
                'variant_id': v.get('variant_id'),
                'letter': v.get('letter'),
                'personalization_signals': v.get('personalization_signals', []),
                'notes': v.get('notes', '')
            })

        # Create review prompt
        review_context = f"""
RESEARCH SUMMARY:
{json.dumps(research_results, indent=2)}

EMAIL VARIANTS TO REVIEW:
{json.dumps(variants_for_review, indent=2)}

Evaluate each variant and select the best one based on:
1. Personalization depth (uses specific research insights)
2. Insight quality (demonstrates understanding)
3. Authenticity (consultative, not sales-y)
4. Framework adherence (POV structure, word count, etc.)

Return your selection and reasoning.
"""

        # Run reviewer
        result = await self._run_agent(
            reviewer_config,
            {},  # No lead_data needed, all context in additional_context
            worker_id,
            agent_id="reviewer",
            additional_context=review_context
        )

        # Parse review result
        review_result = self._parse_json_result(result)

        # Extract selected variant
        selected_id = review_result.get('selected_variant', 1)
        selected_variant = next((v for v in variants if v.get('variant_id') == selected_id), variants[0])

        # Combine review + selected letter
        return {
            'selected_variant_id': selected_id,
            'selected_letter': selected_variant.get('letter'),
            'selection_reasoning': review_result.get('selection_reasoning'),
            'scores': review_result.get('scores', {}),
            'confidence': review_result.get('confidence', 'MEDIUM'),
            'rejected': selected_variant.get('rejected', False),
            'rejection_reason': selected_variant.get('rejection_reason')
        }

    async def _run_agent(
        self,
        agent_config: AgentConfig,
        lead_data: Dict[str, Any],
        worker_id: str,
        agent_id: str = "agent",
        additional_context: str = ""
    ) -> Dict[str, Any]:
        """
        Run a single agent with configuration from markdown file.

        Args:
            agent_config: Agent configuration from markdown
            lead_data: Lead information
            worker_id: Worker identifier
            agent_id: Agent instance identifier
            additional_context: Extra context to append to prompt

        Returns:
            Agent result dict
        """
        logger.debug(f"[{worker_id}] 🤖 Running {agent_id} ({agent_config.provider}/{agent_config.model})")

        # Build model config from agent config
        model_config = {
            'provider': agent_config.provider,
            'model': agent_config.model,
            'temperature': agent_config.temperature,
            'use_json_mode': False  # Agents use tools, can't use JSON mode
        }

        # Create agent instance
        agent = SimplePlanMCPAgent(
            model=f"{agent_config.provider}:{agent_config.model}",
            mcp_config=None,  # Use shared MCP manager
            max_iterations=agent_config.max_iterations,
            shared_mcp_manager=self.shared_mcp_manager,
            temperature=agent_config.temperature,
            config=self.config,
            model_config=model_config
        )

        # Build task prompt from markdown instructions
        task_prompt = self._build_task_prompt(
            agent_config,
            lead_data,
            additional_context
        )

        # Run agent
        result = await agent.run(task_prompt)

        return result

    def _build_task_prompt(
        self,
        agent_config: AgentConfig,
        lead_data: Dict[str, Any],
        additional_context: str = ""
    ) -> str:
        """
        Build task prompt for agent from markdown instructions + context.

        Args:
            agent_config: Agent configuration
            lead_data: Lead information
            additional_context: Extra context to include

        Returns:
            Complete task prompt string
        """
        # Start with agent instructions from markdown
        prompt_parts = [agent_config.instructions]

        # Add lead data if provided
        if lead_data:
            lead_section = f"""
## LEAD INFORMATION

- **Name**: {lead_data.get('name', 'N/A')}
- **Email**: {lead_data.get('email', 'N/A')}
- **Company**: {lead_data.get('company', 'N/A')}
- **Title**: {lead_data.get('job_title', 'N/A')}
- **LinkedIn**: {lead_data.get('linkedin_url', 'N/A')}
"""
            prompt_parts.append(lead_section)

        # Add project context (GTM, guides) for writer/reviewer
        if agent_config.role in ['writing', 'review']:
            context_section = f"""
## PROJECT CONTEXT

### ICP & Value Proposition
{self.context.get('gtm', '')}

### Writing Guides
{self.context.get('guides', '')}
"""
            prompt_parts.append(context_section)

        # Add additional context (research results, etc.)
        if additional_context:
            prompt_parts.append(additional_context)

        return "\n\n".join(prompt_parts)

    def _parse_json_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse JSON from agent result.

        Args:
            result: Agent run result

        Returns:
            Parsed JSON dict
        """
        if result.get('status') == 'error':
            return {
                'rejected': True,
                'rejection_reason': result.get('error', 'Unknown error')
            }

        final_result = result.get('final_result', '{}')

        # Try to parse JSON
        try:
            if isinstance(final_result, str):
                # Remove markdown code blocks if present
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', final_result, re.DOTALL)
                if json_match:
                    final_result = json_match.group(1)

                return json.loads(final_result)
            else:
                return final_result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {
                'rejected': True,
                'rejection_reason': f'Invalid JSON output: {str(e)}',
                'raw_output': final_result
            }

    def _get_research_focus(self, index: int) -> str:
        """Get research focus for researcher N."""
        focuses = [
            "LinkedIn profile and recent personal activity",
            "Company news, funding, and growth signals"
        ]
        return focuses[index % len(focuses)]

    def _get_writing_angle(self, index: int, research: Dict[str, Any]) -> str:
        """Get suggested writing angle for writer N."""
        insights = research.get('insights', {})
        primary = insights.get('primary_insight', '')
        secondary = insights.get('secondary_insight', '')

        angles = [
            f"Lead with primary insight: {primary[:100]}...",
            f"Lead with secondary insight: {secondary[:100]}..."
        ]
        return angles[index % len(angles)]

    def _aggregate_research(self, results: List[Any]) -> Dict[str, Any]:
        """
        Aggregate multiple research results into single summary.

        Args:
            results: List of research result dicts (or exceptions)

        Returns:
            Aggregated research summary
        """
        valid_results = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Researcher {i+1} failed: {result}")
            else:
                parsed = self._parse_json_result(result)
                if not parsed.get('rejected'):
                    valid_results.append(parsed)

        if not valid_results:
            return {
                'rejected': True,
                'rejection_reason': 'All research agents failed or rejected lead'
            }

        # For now, just use first valid result
        # TODO: Implement smarter aggregation (merge insights, combine signals)
        return valid_results[0]


# Backward compatibility helper
async def create_orchestrator(
    config: Dict[str, Any],
    context: Dict[str, Any],
    shared_mcp_manager: Optional[MCPClientManager] = None
) -> AgentOrchestrator:
    """
    Factory function to create and initialize orchestrator.

    Args:
        config: Application config
        context: Project context
        shared_mcp_manager: Shared MCP manager

    Returns:
        Initialized AgentOrchestrator
    """
    orchestrator = AgentOrchestrator(
        config=config,
        context=context,
        shared_mcp_manager=shared_mcp_manager
    )

    return orchestrator
