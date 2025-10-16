#!/usr/bin/env python3
"""
CLI script to run the lead pipeline.

Usage:
    python src/run.py --input leads.csv --output results.json --prompt "Your custom prompt here"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import run_pipeline


DEFAULT_CUSTOM_PROMPT = """
Analyze this lead for a personalized outreach campaign. Provide:

1. Key talking points based on their background
2. Potential pain points they might be experiencing
3. Suggested approach for initial outreach
4. Personalization opportunities

Return your analysis in JSON format with these keys: talking_points, pain_points, outreach_approach, personalization
"""


def main():
    parser = argparse.ArgumentParser(
        description="Run the lead pipeline to process and analyze leads"
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to input CSV file with leads"
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Path to output JSON file for results"
    )
    parser.add_argument(
        "--prompt",
        "-p",
        default=DEFAULT_CUSTOM_PROMPT,
        help="Custom prompt for analyzing top 20 leads"
    )
    parser.add_argument(
        "--prompt-file",
        "-f",
        help="Path to file containing custom prompt (overrides --prompt)"
    )

    args = parser.parse_args()

    # Load custom prompt from file if provided
    custom_prompt = args.prompt
    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            print(f"Error: Prompt file not found: {args.prompt_file}")
            sys.exit(1)
        custom_prompt = prompt_path.read_text(encoding="utf-8")

    # Validate input file exists
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input CSV file not found: {args.input}")
        sys.exit(1)

    # Run pipeline
    try:
        asyncio.run(run_pipeline(
            csv_path=args.input,
            output_path=args.output,
            custom_prompt=custom_prompt
        ))
        print(f"\nSuccess! Results saved to: {args.output}")
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError running pipeline: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
