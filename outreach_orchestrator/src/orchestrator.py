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
        db_path: str = "data/progress.db"
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
        """
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.context_dir = context_dir
        self.num_workers = workers
        self.resume = resume
        self.db_path = db_path

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

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        try:
            # 1. Initialize components
            await self._initialize()

            # 2. Load tasks from CSV
            if not self.resume:
                print(f"\n📂 Loading leads from: {self.input_csv}")
                added = await self.task_queue.load_from_csv(self.input_csv)
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
        await self.task_queue.initialize()
        print("✓ Initialized task queue")

        # Initialize worker pool
        self.worker_pool = WorkerPool(
            num_workers=self.num_workers,
            context=self.context
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
                processed = worker_stats['processed']
                stats = await self.task_queue.get_stats()
                pending = stats['pending']

                print(f"\n📊 Progress: {processed} processed | {pending} pending | "
                      f"S1:{worker_stats['stage1_relevant']}/{worker_stats['stage1_not_relevant']} | "
                      f"S2:{worker_stats['stage2_letters']}/{worker_stats['stage2_rejected']} | "
                      f"Errors:{worker_stats['errors']}")

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

        # Print summary
        ResultWriter.print_summary(tasks, self.output_csv)

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
