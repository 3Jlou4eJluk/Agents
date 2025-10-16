"""
Tools for LinkedIn enrichment via Bright Data MCP and utility functions.
"""

import asyncio
import csv
import json
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class BrightDataClient:
    """Client for interacting with Bright Data MCP server."""

    def __init__(self, api_key: str | None = None):
        self.session: ClientSession | None = None
        self._read_stream = None
        self._write_stream = None
        self._exit_stack = None
        self.api_key = api_key or os.getenv("BRIGHT_DATA_API_KEY") or os.getenv("API_TOKEN")

        if not self.api_key:
            raise ValueError(
                "Bright Data API key is required. "
                "Set BRIGHT_DATA_API_KEY or API_TOKEN environment variable or pass api_key parameter."
            )

    async def __aenter__(self):
        """Async context manager entry - connect to the Bright Data MCP server."""
        # Bright Data MCP server with API key in environment
        env = os.environ.copy()
        env["API_TOKEN"] = self.api_key

        server_params = StdioServerParameters(
            command="npx",
            args=["@brightdata/mcp"],
            env=env
        )

        print("[BrightData] Connecting to MCP server...")

        # stdio_client returns an async context manager, use it properly
        self._exit_stack = stdio_client(server_params)
        self._read_stream, self._write_stream = await self._exit_stack.__aenter__()

        print("[BrightData] Creating client session...")
        self.session = ClientSession(self._read_stream, self._write_stream)

        # Enter the session context
        await self.session.__aenter__()

        print("[BrightData] Initializing session...")
        try:
            init_result = await asyncio.wait_for(
                self.session.initialize(),
                timeout=30.0
            )
            print(f"[BrightData] ✓ Session initialized: {init_result}")

            # List available tools
            tools = await self.session.list_tools()
            print(f"[BrightData] Available tools: {[tool.name for tool in tools.tools]}")

        except asyncio.TimeoutError:
            print("[BrightData] ✗ Session initialization timed out after 30s")
            raise RuntimeError("MCP session initialization timed out")
        except Exception as e:
            print(f"[BrightData] ✗ Session initialization error: {e}")
            raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - disconnect from the MCP server."""
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)

        if self._exit_stack:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)

    async def enrich_linkedin_profile(self, linkedin_url: str) -> dict[str, Any]:
        """
        Enrich a LinkedIn profile using Bright Data.

        Args:
            linkedin_url: The LinkedIn profile URL to enrich

        Returns:
            Enriched profile data as a dictionary
        """
        if not self.session:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Add https:// if not present
            if not linkedin_url.startswith(('http://', 'https://')):
                linkedin_url = f"https://{linkedin_url}"

            # Call the Bright Data MCP tool for LinkedIn enrichment with timeout
            result = await asyncio.wait_for(
                self.session.call_tool(
                    "scrape_as_markdown",
                    arguments={"url": linkedin_url}
                ),
                timeout=60.0  # 60 second timeout per profile
            )

            # Parse the result - CallToolResult has .content attribute with list of content items
            if result and hasattr(result, 'content') and result.content:
                # Get first content item
                content_items = result.content
                if len(content_items) > 0:
                    content = content_items[0]
                    if hasattr(content, 'text'):
                        # Return markdown content as enriched data
                        return {"markdown": content.text, "url": linkedin_url}
            return {}
        except asyncio.TimeoutError:
            print(f"Timeout enriching profile {linkedin_url}")
            return {"error": "timeout"}
        except Exception as e:
            print(f"Error enriching profile {linkedin_url}: {e}")
            return {"error": str(e)}

    async def enrich_batch(
        self,
        leads: list[dict],
        batch_size: int = 10,
        delay_seconds: float = 2.0
    ) -> list[dict]:
        """
        Enrich a batch of leads with rate limiting using Bright Data's scrape_batch.

        Args:
            leads: List of lead dictionaries with 'linkedin_url' field
            batch_size: Number of profiles to enrich in parallel
            delay_seconds: Delay between batches

        Returns:
            List of enriched lead dictionaries
        """
        enriched_leads = []
        total_leads = len(leads)
        total_batches = (total_leads + batch_size - 1) // batch_size
        success_count = 0
        error_count = 0

        for i in range(0, total_leads, batch_size):
            batch = leads[i:i + batch_size]
            batch_num = i // batch_size + 1

            print(f"\n[Bright Data] Batch {batch_num}/{total_batches} | Processing {len(batch)} profiles...")

            # Prepare URLs for batch request
            urls = []
            for lead in batch:
                linkedin_url = lead.get("linkedin_url", "")
                if not linkedin_url.startswith(('http://', 'https://')):
                    linkedin_url = f"https://{linkedin_url}"
                urls.append(linkedin_url)

            # Call scrape_batch with timeout
            try:
                result = await asyncio.wait_for(
                    self.session.call_tool(
                        "scrape_batch",
                        arguments={"urls": urls}
                    ),
                    timeout=600.0  # 10 minutes for batch
                )

                # Parse batch results
                enriched_data_list = []
                if result and hasattr(result, 'content') and result.content:
                    content_items = result.content
                    if len(content_items) > 0:
                        content = content_items[0]
                        if hasattr(content, 'text'):
                            # Try to parse as JSON array
                            try:
                                enriched_data_list = json.loads(content.text)
                            except json.JSONDecodeError:
                                # If not JSON, treat as single markdown
                                enriched_data_list = [{"markdown": content.text}]

                # Ensure we have results for all leads
                while len(enriched_data_list) < len(batch):
                    enriched_data_list.append({"error": "no_result"})

            except asyncio.TimeoutError:
                print(f"  ⚠ Batch timeout after 120s")
                enriched_data_list = [{"error": "timeout"} for _ in batch]
            except Exception as e:
                print(f"  ⚠ Batch error: {e}")
                enriched_data_list = [{"error": str(e)} for _ in batch]

            # Combine original lead data with enriched data
            for j, (lead, enrichment) in enumerate(zip(batch, enriched_data_list)):
                enriched_lead = lead.copy()
                if isinstance(enrichment, dict) and "error" not in enrichment:
                    enriched_lead["enriched_data"] = enrichment
                    success_count += 1
                    status = "✓"
                else:
                    enriched_lead["enriched_data"] = enrichment
                    error_count += 1
                    status = "✗"

                # Show individual progress
                current = i + j + 1
                print(f"  [{current}/{total_leads}] {status} {lead.get('name', 'N/A')}")

                enriched_leads.append(enriched_lead)

            # Show batch summary
            print(f"  Batch {batch_num} complete: {success_count} success, {error_count} errors")

            # Rate limiting delay between batches
            if i + batch_size < total_leads:
                print(f"  Waiting {delay_seconds}s before next batch...")
                await asyncio.sleep(delay_seconds)

        print(f"\n[Bright Data] Enrichment complete: {success_count}/{total_leads} successful")
        return enriched_leads


def load_leads_from_csv(csv_path: str) -> list[dict]:
    """
    Load leads from a CSV file and normalize column names.

    Supports multiple CSV formats:
    - Standard: email, name, company, linkedin_url, job_title
    - Alternative: Email, First Name, Last Name, companyName, linkedIn, jobTitle

    Args:
        csv_path: Path to the CSV file

    Returns:
        List of lead dictionaries with normalized keys
    """
    leads = []
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize to standard format
            normalized = {
                "email": row.get("Email") or row.get("email", ""),
                "name": f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip() or row.get("name", ""),
                "company": row.get("companyName") or row.get("company", ""),
                "linkedin_url": row.get("linkedIn") or row.get("linkedin_url", ""),
                "job_title": row.get("jobTitle") or row.get("job_title", ""),
            }

            # Add all original data for enrichment
            normalized["raw_data"] = dict(row)

            leads.append(normalized)

    return leads


def save_results_to_json(results: list[dict], output_path: str):
    """
    Save results to a JSON file.

    Args:
        results: List of result dictionaries
        output_path: Path to save the JSON file
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Results saved to {output_path}")
