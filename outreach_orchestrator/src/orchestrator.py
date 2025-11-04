"""
Outreach Orchestrator - main controller for parallel lead processing.
"""

import asyncio
import signal
from pathlib import Path
from typing import Optional
from tqdm.asyncio import tqdm

from .task_queue import TaskQueue
from .worker_pool import WorkerPool
from .context_loader import ContextLoader
from .result_writer import ResultWriter
from .config_loader import load_config
from .logger import setup_logging, get_logger

logger = get_logger(__name__)


class OutreachOrchestrator:
    """
    Main orchestrator for cold outreach campaign.
    Manages task queue, worker pool, and result export.
    """

    def __init__(
        self,
        input_csv: str,
        output_csv: str,
        context_dir: str = "context",
        workers: int = 5,
        resume: bool = False,
        db_path: str = "data/progress.db",
        config_path: Optional[str] = None,
        multi_agent_override: Optional[bool] = None,
        start_position: int = 0
    ):
        """
        Initialize orchestrator.

        Args:
            input_csv: Path to input CSV file
            output_csv: Path to output CSV file
            context_dir: Path to context directory
            workers: Number of parallel workers
            resume: Whether to resume from previous run
            db_path: Path to SQLite database
            config_path: Path to config.json file
        """
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.context_dir = context_dir
        self.num_workers = workers
        self.resume = resume
        self.db_path = db_path
        self.start_position = max(0, int(start_position or 0))

        # Load configuration
        self.config = load_config(config_path)

        # Apply CLI override for multi-agent mode if provided
        if multi_agent_override is not None:
            if 'agent_orchestration' not in self.config:
                self.config['agent_orchestration'] = {}
            self.config['agent_orchestration']['enabled'] = multi_agent_override

        prompt_mode = self.config.get('prompt_mode', 'creative')

        # Get model configs
        classification_cfg = self.config['models']['classification']
        letter_cfg = self.config['models']['letter_generation']

        # Get rate limiting config
        rate_limiting_cfg = self.config.get('rate_limiting', {})
        rate_limiting_enabled = rate_limiting_cfg.get('enabled', False)

        print(f"✓ Loaded config:")
        print(f"  - Classification: {classification_cfg.get('provider', 'deepseek')}/{classification_cfg['model']} (temp={classification_cfg['temperature']})")
        print(f"  - Letter generation: {letter_cfg.get('provider', 'deepseek')}/{letter_cfg['model']} (temp={letter_cfg['temperature']})")
        print(f"  - Prompt mode: {prompt_mode} {'(no template phrases)' if prompt_mode == 'creative' else '(with examples)'}")

        # Show rate limiting info
        if rate_limiting_enabled:
            providers_info = []
            for provider in ['openai', 'deepseek', 'claude']:
                if provider in rate_limiting_cfg:
                    pconf = rate_limiting_cfg[provider]
                    rpm = pconf.get('requests_per_minute') or pconf.get('rpm')
                    rps = pconf.get('requests_per_second')
                    burst = pconf.get('burst', '?')
                    if rpm is not None:
                        providers_info.append(f"{provider}: {rpm} req/min (burst={burst})")
                    elif rps is not None:
                        providers_info.append(f"{provider}: {rps} req/s (burst={burst})")
            if providers_info:
                print(f"  - Rate limiting: ✓ ENABLED ({', '.join(providers_info)})")
        else:
            print(f"  - Rate limiting: ✗ DISABLED")

        # Show MCP status
        mcp_enabled = self.config.get('mcp', {}).get('enabled', True)
        print(f"  - MCP tools: {'✓ ENABLED' if mcp_enabled else '✗ DISABLED'}")

        # Components
        self.task_queue: Optional[TaskQueue] = None
        self.worker_pool: Optional[WorkerPool] = None
        self.context: Optional[dict] = None

        # Graceful shutdown flag
        self.shutdown_requested = False

    async def run(self):
        """Main orchestration flow."""
        print("\n" + "="*80)
        print("🚀 OUTREACH ORCHESTRATOR - Starting")
        print("="*80)

        # Setup logging
        log_file = setup_logging(log_dir="logs", log_level="DEBUG")
        print(f"📝 Logging to: {log_file}\n")

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        try:
            # 1. Initialize components
            await self._initialize()

            # 2. Load tasks from CSV
            if not self.resume:
                print(f"\n📂 Loading leads from: {self.input_csv}")
                added = await self.task_queue.load_from_csv(self.input_csv, start_position=self.start_position)
                print(f"✓ Added {added} new tasks")

            # 3. Show initial stats
            stats = await self.task_queue.get_stats()
            print(f"\n📊 Task Queue Status:")
            print(f"  Total: {stats['total']}")
            print(f"  Pending: {stats['pending']}")
            print(f"  Processing: {stats['processing']}")
            print(f"  Completed: {stats['completed']}")
            print(f"  Failed: {stats['failed']}")

            # 4. Reset stuck tasks if resuming
            if self.resume and stats['processing'] > 0:
                reset = await self.task_queue.reset_processing_tasks()
                print(f"  ↻ Reset {reset} stuck tasks")
                stats = await self.task_queue.get_stats()

            # 5. Start processing
            await self._process_queue()

            # 6. Export results
            await self._export_results()

        except KeyboardInterrupt:
            print("\n\n⚠ Interrupted by user. Saving progress...")
            await self._export_results()

        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            raise

        finally:
            # Clean up MCP servers
            if hasattr(self, 'worker_pool') and self.worker_pool:
                await self.worker_pool.close_mcp()

            print("\n" + "="*80)
            print("✅ ORCHESTRATOR FINISHED")
            print("="*80 + "\n")

    async def _initialize(self):
        """Initialize all components."""
        print("\n🔧 Initializing components...")

        # Load context
        context_loader = ContextLoader(self.context_dir)
        self.context = context_loader.load_context()
        print("✓ Loaded agent context")

        # Initialize task queue
        self.task_queue = TaskQueue(self.db_path)

        # Clean database if NOT resuming (default behavior)
        if not self.resume:
            await self.task_queue.initialize(clean=True)
            print("✓ Initialized task queue (clean start)")
        else:
            await self.task_queue.initialize(clean=False)
            print("✓ Initialized task queue (resume mode)")

        # Initialize worker pool
        self.worker_pool = WorkerPool(
            num_workers=self.num_workers,
            context=self.context,
            config=self.config
        )
        print(f"✓ Initialized worker pool ({self.num_workers} workers)")

        # Initialize shared MCP manager
        await self.worker_pool.initialize_mcp()

    async def _process_queue(self):
        """Process all tasks in the queue."""
        stats = await self.task_queue.get_stats()
        total_to_process = stats['pending']

        if total_to_process == 0:
            print("\n✓ No pending tasks to process")
            return

        print(f"\n⚙️  Processing {total_to_process} leads...")
        print(f"👥 Workers: {self.num_workers}")
        print("")

        # Create worker coroutines
        workers = [
            self._worker(worker_id=f"W{i+1}")
            for i in range(self.num_workers)
        ]

        # Run all workers
        await asyncio.gather(*workers)

    async def _worker(self, worker_id: str):
        """
        Worker coroutine that processes tasks from queue.

        Args:
            worker_id: Unique worker identifier
        """
        while not self.shutdown_requested:
            # Get next task
            task = await self.task_queue.get_next_task(worker_id)

            if task is None:
                # No more tasks
                break

            try:
                # Process the task
                result = await self.worker_pool.process_lead(task, worker_id)

                # Update task with results
                await self.task_queue.update_task(
                    task_id=task['id'],
                    status=result.get('status', 'completed'),
                    stage1_result=result.get('stage1_result'),
                    stage2_result=result.get('stage2_result'),
                    error=result.get('error')
                )

                # Print progress
                worker_stats = self.worker_pool.get_stats()
                token_stats = self.worker_pool.get_token_stats()
                compression_stats = self.worker_pool.get_compression_stats()
                processed = worker_stats['processed']
                stats = await self.task_queue.get_stats()
                pending = stats['pending']

                # Format token count (in K)
                total_tokens_k = (token_stats['total_input'] + token_stats['total_output']) / 1000
                cached_tokens_k = token_stats['total_cached'] / 1000
                cost_usd = token_stats['total_cost_usd']

                print(f"\n📊 Progress: {processed} processed | {pending} pending | "
                      f"S1:{worker_stats['stage1_relevant']}/{worker_stats['stage1_not_relevant']} | "
                      f"S2:{worker_stats['stage2_letters']}/{worker_stats['stage2_rejected']} | "
                      f"Errors:{worker_stats['errors']}")

                # Token info
                token_line = f"💰 Tokens: {total_tokens_k:.1f}K total ({cached_tokens_k:.1f}K cached) | Cost: ${cost_usd:.3f}"

                # Add compression info if any compressions occurred
                if compression_stats['total_compressions'] > 0:
                    saved = compression_stats['total_messages_before'] - compression_stats['total_messages_after']
                    token_line += f" | 🗜️  {compression_stats['total_compressions']} compressions ({saved} msgs saved)"

                print(token_line)

            except Exception as e:
                print(f"[{worker_id}] ❌ Worker error: {e}")
                await self.task_queue.update_task(
                    task_id=task['id'],
                    status='failed',
                    error=str(e)
                )

    async def _export_results(self):
        """Export all results to CSV."""
        print(f"\n💾 Exporting results to: {self.output_csv}")

        # Get all tasks
        tasks = await self.task_queue.get_all_tasks()

        # Write to CSV
        ResultWriter.write_results(tasks, self.output_csv)

        # Get token stats and compression stats
        token_stats = self.worker_pool.get_token_stats() if self.worker_pool else None
        compression_stats = self.worker_pool.get_compression_stats() if self.worker_pool else None

        # Print summary
        ResultWriter.print_summary(tasks, self.output_csv, token_stats, compression_stats)

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def handle_shutdown(signum, frame):
            if not self.shutdown_requested:
                print("\n\n⚠ Shutdown requested. Finishing current tasks...")
                self.shutdown_requested = True
            else:
                print("\n\n⚠ Force shutdown!")
                raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
