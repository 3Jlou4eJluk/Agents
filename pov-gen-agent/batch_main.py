#!/usr/bin/env python3
"""Batch processing entry point for POV Email Generator."""

import sys
import argparse
from pathlib import Path

from src.pov_gen_agent.batch_processor import process_from_file


def main():
    """Main entry point for batch processing."""
    parser = argparse.ArgumentParser(
        description="Generate POV emails from a JSON file of leads"
    )
    parser.add_argument(
        "input_file",
        help="Path to input JSON file containing leads"
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save individual email results (default: output)"
    )
    parser.add_argument(
        "--summary-file",
        default="batch_summary.json",
        help="Path to save batch summary (default: batch_summary.json)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all leads regardless of is_relevant flag (default: only is_relevant=true)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output"
    )

    args = parser.parse_args()

    # Check if input file exists
    if not Path(args.input_file).exists():
        print(f"Error: Input file '{args.input_file}' not found")
        sys.exit(1)

    # Process leads
    try:
        summary = process_from_file(
            input_file=args.input_file,
            output_dir=args.output_dir,
            summary_file=args.summary_file,
            filter_relevant=not args.all,
            verbose=not args.quiet
        )

        # Exit with appropriate code
        if summary["errors"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
