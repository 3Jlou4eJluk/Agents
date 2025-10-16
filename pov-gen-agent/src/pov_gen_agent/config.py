"""Configuration constants for POV Email Generator."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# DeepSeek API Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-reasoner"

# Generation Parameters
MAX_ITERATIONS = 5
SCORE_THRESHOLD = 8.0
TEMPERATURE = 0.7

# Document Paths
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
POV_FRAMEWORK_PATH = DOCS_DIR / "pov_framework.md"
EXAMPLE_PATH = DOCS_DIR / "example.md"
GTM_MANIFEST_PATH = DOCS_DIR / "gtm_manifest.md"
WORKFLOW_PATH = DOCS_DIR / "workflow.md"


def load_document(path: Path) -> str:
    """Load a document from the docs directory."""
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    return path.read_text()


# Load documents into memory
try:
    POV_FRAMEWORK = load_document(POV_FRAMEWORK_PATH)
    EXAMPLE = load_document(EXAMPLE_PATH)
    GTM_MANIFEST = load_document(GTM_MANIFEST_PATH)
    WORKFLOW = load_document(WORKFLOW_PATH)
except FileNotFoundError as e:
    print(f"Warning: {e}")
    POV_FRAMEWORK = ""
    EXAMPLE = ""
    GTM_MANIFEST = ""
    WORKFLOW = ""
