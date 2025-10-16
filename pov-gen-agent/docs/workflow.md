# POV Email Generator Workflow

## Process Flow

```
Input: Profile Data
       ↓
   [BaseAgent]
   Generate Draft
       ↓
   [GTMAgent]
   Validate ICP Fit
       ↓
   [POVAgent]
   Validate Framework
       ↓
   Decision Point
       ↓
   Both Scores ≥ 8? ────→ YES → Output Final Email
       ↓
       NO
       ↓
   Iteration < 5? ────→ NO → Output Best Attempt
       ↓
       YES
       ↓
   Aggregate Feedback
       ↓
   [BaseAgent] (with feedback)
   Regenerate Draft
       ↓
   (Loop back to GTMAgent)
```

## Agent Responsibilities

### 1. BaseAgent
**Role:** Email draft generation

**Inputs:**
- Profile data (company, person, context)
- Feedback from previous iteration (if any)

**Process:**
- Analyze profile for context hooks
- Identify relevant patterns/insights
- Craft POV-based email following framework
- Apply feedback to improve draft

**Outputs:**
- Email draft (markdown format)

**System Prompt:** Uses POV framework, examples, and GTM manifest as context

### 2. GTMAgent
**Role:** ICP validation

**Inputs:**
- Email draft
- Profile data

**Process:**
- Evaluate target persona match
- Assess pain point relevance
- Check company fit criteria
- Verify industry alignment
- Score 0-10 based on ICP criteria

**Outputs:**
- Score (0-10)
- Issues list (specific mismatches)
- Fix recommendations (concrete changes)

**System Prompt:** Uses GTM manifest as evaluation criteria

### 3. POVAgent
**Role:** Framework validation

**Inputs:**
- Email draft

**Process:**
- Evaluate Context quality (personalization depth)
- Assess Observation/Insight (specificity, value)
- Check Problem articulation (relevance, clarity)
- Verify Soft CTA (non-pushy, value-offering)
- Score 0-10 based on framework adherence

**Outputs:**
- Score (0-10)
- Issues list (structural gaps)
- Fix recommendations (specific improvements)

**System Prompt:** Uses POV framework and examples as standards

## Iteration Logic

### Conditions
```python
MAX_ITERATIONS = 5
SCORE_THRESHOLD = 8.0

def should_continue(state):
    """Determine if we should regenerate or output"""

    # Max iterations reached - output best attempt
    if state["iteration"] >= MAX_ITERATIONS:
        return "end"

    # Both scores meet threshold - output success
    if state["gtm_score"] >= SCORE_THRESHOLD and state["pov_score"] >= SCORE_THRESHOLD:
        return "end"

    # Continue iterating
    return "generate"
```

### Feedback Aggregation
```python
def aggregate_feedback(gtm_feedback, pov_feedback):
    """Combine feedback from both agents"""

    return f"""
    ICP Validation Issues:
    {gtm_feedback}

    POV Framework Issues:
    {pov_feedback}

    Please revise the email to address both sets of concerns.
    Prioritize the lower-scoring dimension.
    """
```

## State Management

### State Schema
```python
{
    "profile_data": {
        "company": str,
        "company_size": int,
        "industry": str,
        "recent_news": str,
        "person_name": str,
        "person_title": str,
        "person_background": str,
    },
    "email_draft": str,  # Current draft (markdown)
    "gtm_score": float,  # 0-10
    "pov_score": float,  # 0-10
    "gtm_feedback": str,
    "pov_feedback": str,
    "iteration": int,
    "history": [...]  # Optional: track all drafts
}
```

## Output Format

### Success Case (Scores ≥ 8)
```json
{
    "status": "success",
    "email": "markdown email text",
    "gtm_score": 8.5,
    "pov_score": 9.0,
    "iterations": 3,
    "metadata": {
        "target_persona": "VP Sales Operations",
        "company_fit": "strong",
        "key_insight": "tool sprawl at scale stage"
    }
}
```

### Max Iterations Case
```json
{
    "status": "max_iterations",
    "email": "best attempt markdown text",
    "gtm_score": 7.5,
    "pov_score": 7.0,
    "iterations": 5,
    "warnings": [
        "Could not achieve target scores",
        "Consider reviewing profile data quality"
    ]
}
```

## Error Handling

### Profile Data Issues
- Missing required fields → Request completion
- Low-quality data → Warn user, attempt best effort
- Insufficient context → Generate based on available data

### Generation Failures
- API errors → Retry with exponential backoff
- Invalid output → Re-prompt with format instructions
- Timeout → Use previous best draft

### Validation Edge Cases
- Both scores low → Prioritize ICP fit (GTM) first
- Scores diverging → Balance both in feedback
- Scores stagnant → Increase temperature or prompt variation
