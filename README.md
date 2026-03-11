# LinkedIn Recruiter Multi-Model Sourcing Pipeline

A Python pipeline that replaces the single-model OpenClaw sourcing agent with a cost-efficient multi-model architecture. Cheap models (GPT-4o-mini / Gemini Flash) handle DOM extraction; Opus handles candidate judgment.

## Architecture

```
LinkedIn DOM → [Cheap Model: Extract Snippets] → [Hard Filters] → [Opus: Facial Judgment]
    → [Cheap Model: Extract Full Profile] → [Opus: Final Judgment] → [Save to Pipeline]
```

**Cost savings:** Opus never touches raw DOM (~15-20K tokens per page). It only sees small structured JSON payloads (~200-1500 tokens per candidate).

## Setup

```bash
cd linkedin-sourcing-pipeline

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (first time only)
playwright install chromium

# Copy and edit config
cp config.example.env .env
# Edit .env with your API keys
```

## Configuration (.env)

```
ANTHROPIC_API_KEY=sk-ant-...        # For Opus judgment calls
OPENAI_API_KEY=sk-...               # For GPT-4o-mini extraction (option A)
GOOGLE_API_KEY=...                   # For Gemini Flash extraction (option B)
CHEAP_MODEL_PROVIDER=openai          # "openai" or "google"
CDP_URL=http://127.0.0.1:18800      # OpenClaw managed browser CDP
```

## Usage

### Test on a single page first
```bash
# Attach to your logged-in LinkedIn Recruiter browser
# Navigate to a search results page manually
# Then run:
python run.py --brief briefs/brazil-v2.json --test-single-page
```

### Full run
```bash
python run.py --brief briefs/brazil-v2.json --search-config search_config.json
```

### Re-run judgment on existing extractions
```bash
python run.py --brief briefs/brazil-v2.json --rejudge-from output/snippets.jsonl
```

## Output Files

All in `output/` directory:
- `snippets.jsonl` — Raw candidate extractions from list view
- `facial_judgments.jsonl` — Opus facial-fit decisions
- `profile_summaries.jsonl` — Full profile extractions for FACIAL_YES candidates
- `final_judgments.jsonl` — Opus final save/reject decisions
- `progress.json` — Checkpoint state for resuming interrupted runs
- `run_log.jsonl` — Timestamped event log for debugging
