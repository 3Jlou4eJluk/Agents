# Configuration

## Overview

`outreach_orchestrator` is a standalone project with its own configuration files.

## Configuration Files

### 1. Environment Variables (`.env`)

**Location:** `outreach_orchestrator/.env`

**Required variables:**
- `DEEPSEEK_API_KEY` - DeepSeek API for classification & generation
- `ANTHROPIC_API_KEY` - (if using Claude models)

**Orchestrator-specific variables:**
- `WORKERS=5` - Number of parallel workers
- `CLASSIFICATION_BATCH_SIZE=5` - Batch size for Stage 1
- `EXECUTOR_MAX_ITERATIONS=50` - Max tool calls per Stage 2
- `CLASSIFICATION_MODEL=deepseek:deepseek-chat` - Model for classification
- `LETTER_GEN_MODEL=deepseek:deepseek-chat` - Model for letter generation

### 2. MCP Configuration (`mcp_config.json`)

**Location:** `outreach_orchestrator/mcp_config.json`

The orchestrator uses its own MCP configuration:
- `bright-data` - LinkedIn enrichment
- `firecrawl-mcp` - Company website scraping
- `tavily-mcp` - Web search
- `server-brave-search` - Alternative web search

**Default in code:**
```python
project_root = Path(__file__).parent.parent
self.mcp_config_path = mcp_config_path or str(project_root / "mcp_config.json")
```

## Setup Steps

### First Time Setup

1. **Configure environment variables:**
   ```bash
   cd outreach_orchestrator

   # Copy and edit .env
   cp .env.example .env
   nano .env  # Add your API keys
   ```

2. **Configure MCP servers (optional):**
   ```bash
   # MCP config is pre-configured with common servers
   # Edit if you need to add/remove servers
   nano mcp_config.json
   ```

### Verifying Configuration

```bash
# Check .env exists
ls -la .env

# Check MCP config exists
ls -la mcp_config.json

# Check environment variables are loaded
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('DEEPSEEK_API_KEY:', os.getenv('DEEPSEEK_API_KEY')[:20] + '...')"
```

## MCP Servers Configuration

Edit `mcp_config.json` to customize which MCP servers to use:

```json
{
  "mcpServers": {
    "bright-data": {
      "command": "npx",
      "args": ["@brightdata/mcp"],
      "env": {
        "API_TOKEN": "your_bright_data_token",
        "BROWSER_AUTH": "your_browser_auth"
      },
      "transport": "stdio"
    },
    "firecrawl-mcp": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "your_firecrawl_key"
      },
      "transport": "stdio"
    }
  }
}
```

## Troubleshooting

### ".env not found"
```bash
# Make sure .env exists in project root
ls -la .env

# If not, copy from example
cp .env.example .env
```

### "MCP servers not connecting"
```bash
# Check MCP config exists and is valid
cat mcp_config.json

# Check API keys are set in .env
grep API_KEY .env
```

### "DEEPSEEK_API_KEY not found"
```bash
# Make sure DEEPSEEK_API_KEY is in .env
echo "DEEPSEEK_API_KEY=sk-your-key-here" >> .env
```
