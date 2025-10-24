# 🚀 Outreach Orchestrator

**Parallel cold outreach system with AI-powered classification and personalized letter generation.**

Two-stage processing pipeline:
- **Stage 1**: Fast ICP classification using DeepSeek
- **Stage 2**: Deep research & personalized letter writing with MCP tools

## Features

✨ **Two-Stage Processing**
- Stage 1: Quick relevance classification
- Stage 2: Deep research + personalized letter generation (for relevant leads only)

⚡ **Parallel Processing**
- 3-5 parallel workers
- SQLite-based task queue
- Resume capability after interruption

🧠 **Agent Personality**
- GTM.md: Project manifest and ICP definition
- Guides: POV Framework, writing style
- Instructions: Detailed task specifications

📊 **Progress Tracking**
- Real-time statistics
- SQLite persistence
- Graceful shutdown (Ctrl+C)
- Resume from where you left off

💾 **Results Export**
- Comprehensive CSV output
- Stage 1 & Stage 2 results
- Generated letters with personalization signals
- Error tracking

## Project Structure

```
outreach_orchestrator/
├── context/                    # Agent personality & knowledge
│   ├── GTM.md                 # Your project manifest (copy from .example)
│   ├── agent_instruction.md   # Agent task instructions
│   └── guides/
│       ├── pov_framework.md   # POV Framework guide
│       └── writing_style.md   # Writing style guide
├── src/
│   ├── orchestrator.py        # Main controller
│   ├── worker_pool.py         # Parallel worker management
│   ├── task_queue.py          # SQLite task queue
│   ├── context_loader.py      # Loads context files
│   ├── result_writer.py       # CSV export
│   └── run.py                 # CLI entry point
├── data/
│   ├── input/                 # Place your lead CSV files here
│   ├── output/                # Results will be saved here
│   └── progress.db            # SQLite database (auto-created)
└── scripts/
    └── run.sh                 # Convenience wrapper script
```

## Prerequisites

- Python 3.11+
- DeepSeek API key (for classification and letter generation)
- MCP servers configured in `mcp_config.json` (Bright Data, Firecrawl, etc.)

## Installation

### 1. Install Dependencies

```bash
cd outreach_orchestrator

# Install with pip
pip install -e .

# Or with uv (recommended for faster installation)
uv pip install -e .
```

**Dependencies installed:**
- `aiosqlite` - SQLite async support for task queue
- `tqdm` - Progress bars
- `langchain-core`, `langchain-openai`, `langchain-anthropic` - LLM integrations
- `langgraph` - Agent orchestration
- `langchain-mcp-adapters` - MCP tools integration
- `python-dotenv` - Environment variables

### 2. Set Up Environment Variables

Create a `.env` file in the project root (or use the provided `.env.example`):

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required in `.env`:**
- `DEEPSEEK_API_KEY`: DeepSeek API key (get from https://platform.deepseek.com/)
- Bright Data credentials (configured in `mcp_config.json`)

**Optional settings:**
- `WORKERS`: Number of parallel workers (default: 5)
- `CLASSIFICATION_BATCH_SIZE`: Batch size for classification (default: 5)
- `EXECUTOR_MAX_ITERATIONS`: Max tool calls per step (default: 50)
- `CLASSIFICATION_MODEL`: Model for classification (default: deepseek:deepseek-chat)
- `LETTER_GEN_MODEL`: Model for letter generation (default: deepseek:deepseek-chat)

### 3. Set Up Context Files

```bash
# Copy example files
cp context/GTM.md.example context/GTM.md
cp context/agent_instruction.md.example context/agent_instruction.md
cp context/guides/pov_framework.md.example context/guides/pov_framework.md
cp context/guides/writing_style.md.example context/guides/writing_style.md

# Edit GTM.md with your project details
nano context/GTM.md
```

**IMPORTANT:** Fill out `GTM.md` completely - this is the foundation of your outreach strategy.

## Usage

### Basic Usage

```bash
# Run with input CSV
./scripts/run.sh --input data/input/leads.csv --output data/output/results.csv

# Or using Python directly
python -m src.run --input data/input/leads.csv --output data/output/results.csv
```

### Advanced Usage

```bash
# Specify number of workers
./scripts/run.sh --input leads.csv --workers 3

# Resume from previous run (if interrupted)
./scripts/run.sh --resume

# Custom context directory
./scripts/run.sh --input leads.csv --context /path/to/custom/context

# Custom database location
./scripts/run.sh --input leads.csv --db /path/to/progress.db
```

### Command Line Options

```
Options:
  --input, -i      Path to input CSV file with leads
  --output, -o     Path to output CSV file (default: data/output/results.csv)
  --context, -c    Path to context directory (default: context/)
  --workers, -w    Number of parallel workers (default: 5, recommended: 3-5)
  --db             Path to SQLite database (default: data/progress.db)
  --resume, -r     Resume from previous run
```

## Input CSV Format

Your input CSV should have these columns:

```csv
Email,First Name,Last Name,companyName,jobTitle,linkedIn
john@example.com,John,Smith,Acme Corp,VP Engineering,linkedin.com/in/johnsmith
```

**Required columns:**
- `Email` or `email`
- `linkedIn` or `linkedin_url` or `LinkedIn`

**Optional but recommended:**
- `First Name`, `Last Name` (or `name`)
- `companyName` (or `company`)
- `jobTitle` (or `job_title`)
- Any other enrichment data from your source

## Output CSV Format

Results CSV includes:

**Lead Info:**
- email, name, company, job_title, linkedin_url

**Stage 1 - Classification:**
- `stage1_relevant`: true/false
- `stage1_reason`: Why relevant/not relevant

**Stage 2 - Letter Generation:**
- `stage2_status`: completed/skipped
- `stage2_rejected`: true/false (if agent rejected after deep research)
- `stage2_rejection_reason`: Why rejected
- `letter_subject`: Email subject line
- `letter_body`: Email body (100-150 words)
- `letter_send_time_msk`: Recommended send time in Moscow timezone
- `relevance_score`: HIGH/MEDIUM/LOW
- `personalization_signals`: Specific details used

**Meta:**
- `final_status`: not_relevant_stage1, not_relevant_stage2, success, error
- `error`: Error message if failed
- `processed_at`: Timestamp

## Workflow

### For Each Lead:

1. **Stage 1 - Classification** (cold-outreach-agent)
   - Quick relevance check using DeepSeek
   - Based on ICP from GTM.md
   - Decision: relevant ✓ or not relevant ✗

2. **Stage 2 - Letter Generation** (plan_mcp_agent) *[only if Stage 1 = relevant]*
   - Deep LinkedIn profile research (via MCP tools)
   - Company research
   - Re-validation (can reject even if Stage 1 passed)
   - Generate personalized email using POV Framework
   - Recommend send time

3. **Result Storage**
   - Save to SQLite database
   - Continue to next lead

4. **Export**
   - Final CSV with all results
   - Summary statistics

## Rate Limiting

- **Workers:** 3-5 parallel (configurable)
- **Stage 1:** Fast classification (DeepSeek)
- **Stage 2:** Slower (MCP tools, web scraping, thinking)
- **Automatic:** Semaphore controls concurrency

## Resume Capability

If the process is interrupted (Ctrl+C, crash, etc.):

```bash
# Resume from where you left off
./scripts/run.sh --resume
```

The system will:
- ✓ Load progress from SQLite database
- ✓ Reset any tasks stuck in "processing" state
- ✓ Continue with pending tasks
- ✓ Preserve all completed results

## Graceful Shutdown

Press `Ctrl+C` to initiate graceful shutdown:
1. Stops accepting new tasks
2. Finishes currently processing tasks
3. Saves all progress to database
4. Exports results to CSV

Press `Ctrl+C` twice for immediate force shutdown.

## Troubleshooting

### "Context directory not found"
```bash
# Make sure you set up context files
cp context/GTM.md.example context/GTM.md
# Edit GTM.md with your details
```

### "DeepSeek API error"
```bash
# Check your .env file
cat .env | grep DEEPSEEK_API_KEY
```

### "MCP connection failed"
```bash
# Check plan_mcp_agent/mcp_config.json
# Verify Bright Data credentials in .env
```

### "Tasks stuck in processing"
```bash
# Reset stuck tasks and resume
./scripts/run.sh --resume
```

## Performance Tips

1. **Start small:** Test with 10-20 leads first
2. **Workers:** 3-5 is optimal (more = rate limiting issues)
3. **MCP tools:** Each worker needs MCP subprocesses (memory intensive)
4. **DeepSeek:** Fast for classification, slower for letter generation
5. **Monitor:** Watch for errors and adjust

## Architecture

```
Orchestrator
    ↓
Task Queue (SQLite)
    ↓
Worker Pool (3-5 workers)
    ↓
    ├─→ Worker 1 → [Stage 1] → [Stage 2] → Save
    ├─→ Worker 2 → [Stage 1] → [Stage 2] → Save
    ├─→ Worker 3 → [Stage 1] → [Stage 2] → Save
    ├─→ Worker 4 → [Stage 1] → [Stage 2] → Save
    └─→ Worker 5 → [Stage 1] → [Stage 2] → Save
```

**Stage 1: cold-outreach-agent**
- Classification using DeepSeek
- Fast (~1-2s per lead)
- Returns: {relevant: bool, reason: str}

**Stage 2: plan_mcp_agent** (only if Stage 1 = relevant)
- Deep research via MCP tools
- Letter generation using POV Framework
- Slower (~30-60s per lead)
- Returns: {rejected: bool, letter: {...}, notes: str}

## Example Run

```bash
$ ./scripts/run.sh --input data/input/leads.csv --workers 3

================================================================================
🚀 OUTREACH ORCHESTRATOR - Starting
================================================================================

🔧 Initializing components...
✓ Loaded agent context
✓ Initialized task queue
✓ Initialized worker pool (3 workers)

📂 Loading leads from: data/input/leads.csv
✓ Added 50 new tasks

📊 Task Queue Status:
  Total: 50
  Pending: 50
  Processing: 0
  Completed: 0
  Failed: 0

⚙️  Processing 50 leads...
👥 Workers: 3

[Worker-W1] Processing: john@example.com
[Worker-W2] Processing: sarah@company.com
[Worker-W3] Processing: mike@startup.io

[Worker-W1] ✓ Relevant (Stage 1): VP Engineering at B2B SaaS, 200 employees
[Worker-W1] 🔧 Generating letter (Stage 2)...
[Worker-W2] ✗ Not relevant (Stage 1): Individual contributor, not decision maker

📊 Progress: 2 processed | 48 pending | S1:1/1 | S2:0/0 | Errors:0

[Worker-W1] ✓ Letter generated!

📊 Progress: 3 processed | 47 pending | S1:1/2 | S2:1/0 | Errors:0

...

💾 Exporting results to: data/output/results.csv

================================================================================
📊 PROCESSING SUMMARY
================================================================================

Total Leads Processed: 50

🔍 Stage 1 - Classification:
  ✓ Relevant: 12 (24.0%)
  ✗ Not Relevant: 38 (76.0%)

✉️  Stage 2 - Letter Generation:
  ✓ Letters Generated: 9 (18.0%)
  ✗ Rejected (Stage 2): 3
  ⚙️  Processed: 12

💾 Results saved to: data/output/results.csv
================================================================================

✅ ORCHESTRATOR FINISHED
================================================================================
```

## License

MIT

## Support

For issues and questions, check:
- `context/` files for agent configuration
- `.env` for API keys
- SQLite database (`data/progress.db`) for task status

## Credits

Built on top of:
- **cold-outreach-agent**: ICP classification pipeline
- **plan_mcp_agent**: AI agent with MCP tools integration
- **DeepSeek**: LLM for classification and generation
- **Bright Data**: LinkedIn enrichment via MCP
