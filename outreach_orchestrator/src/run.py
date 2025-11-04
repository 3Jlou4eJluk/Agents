"""
CLI entry point for Outreach Orchestrator.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

from .orchestrator import OutreachOrchestrator


def main():
    """Main CLI function."""
    # Load environment variables
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Outreach Orchestrator - Parallel cold outreach with classification and letter generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (clears database by default)
  python -m src.run --input data/input/leads.csv --output data/output/results.csv

  # With specific number of workers
  python -m src.run --input leads.csv --output results.csv --workers 3

  # Resume from previous run (keeps database)
  python -m src.run --resume

  # Custom context directory
  python -m src.run --input leads.csv --context /path/to/context

Note:
  By default, the database is cleared on each new run.
  Use --resume to continue from a previous run without clearing.
        """
    )

    parser.add_argument(
        '--input', '-i',
        type=str,
        help='Path to input CSV file with leads'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/output/results.csv',
        help='Path to output CSV file (default: data/output/results.csv)'
    )

    parser.add_argument(
        '--context', '-c',
        type=str,
        default='context',
        help='Path to context directory (default: context/)'
    )

    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=5,
        help='Number of parallel workers (default: 5, recommended: 3-5)'
    )

    parser.add_argument(
        '--db',
        type=str,
        default='data/progress.db',
        help='Path to SQLite database (default: data/progress.db)'
    )

    parser.add_argument(
        '--resume', '-r',
        action='store_true',
        help='Resume from previous run (keeps database intact; default is to clear database on new runs)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config.json file (default: config.json in project root)'
    )

    parser.add_argument(
        '--multi-agent',
        action='store_true',
        help='Enable multi-agent orchestration (3-phase: Research → Writing → Review). Overrides config.json setting.'
    )

    parser.add_argument(
        '--single-agent',
        action='store_true',
        help='Use legacy single-agent mode. Overrides config.json setting.'
    )

    # Start position to skip first N rows from input CSV
    parser.add_argument(
        '--start-position',
        '--start_position',
        dest='start_position',
        type=int,
        default=0,
        help='Zero-based index in input CSV to start from (skip first N rows)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.resume and not args.input:
        parser.error("--input is required unless using --resume")

    # Check input file exists
    if args.input and not Path(args.input).exists():
        print(f"❌ Error: Input file not found: {args.input}")
        sys.exit(1)

    # Check context directory exists
    if not Path(args.context).exists():
        print(f"❌ Error: Context directory not found: {args.context}")
        print(f"\nPlease create it with:")
        print(f"  1. Copy context/*.example files to remove .example extension")
        print(f"  2. Fill out GTM.md with your project details")
        print(f"  3. Customize guides/ if needed")
        sys.exit(1)

    # Determine agent mode override
    agent_mode_override = None
    if args.multi_agent:
        agent_mode_override = True
        print("🎭 Multi-agent mode enabled (CLI override)")
    elif args.single_agent:
        agent_mode_override = False
        print("🤖 Single-agent mode enabled (CLI override)")

    # Create orchestrator
    orchestrator = OutreachOrchestrator(
        input_csv=args.input or '',
        output_csv=args.output,
        context_dir=args.context,
        workers=args.workers,
        resume=args.resume,
        db_path=args.db,
        config_path=args.config,
        multi_agent_override=agent_mode_override,
        start_position=max(0, args.start_position or 0)
    )

    # Run
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
