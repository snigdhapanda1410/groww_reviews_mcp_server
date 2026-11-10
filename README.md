# Groww Reviews MCP — Weekly Pulse Pipeline

> **Automated Weekly Voice-of-Customer Pulse for the Groww Investment App**  
> Aggregates public Google Play Store reviews → Cleans and filters text → Clusters ranked product themes via LLM → Publishes weekly pulse to Google Docs and dispatches stakeholder email notifications via a remote Model Context Protocol (MCP) server.

---

## 🚀 Quick Start

```powershell
# 1. Clone / open the repository
cd "c:\Projects\Grow reviwes_MCP"

# 2. Activate virtual environment
.venv\Scripts\Activate.ps1

# 3. Configure secrets (optional for dry-run; required for live LLM clustering)
# Add your GEMINI_API_KEY to .env
# GEMINI_API_KEY="your-gemini-api-key"

# 4. Run dry-run smoke test (uses snapshot, runs heuristic fallback if no API key, skips remote MCP)
python src/orchestrate.py --dry-run --date 2026-11-01

# 5. Run live end-to-end pipeline (appends to Google Doc + sends email via MCP)
python src/orchestrate.py
```

---

## 📋 Prerequisites

| Requirement | Specification | Purpose |
|---|---|---|
| **Python** | `3.11+` | Runtime environment (`.venv`) |
| **LLM Provider** | Google Gemini 1.5 Pro | Theme clustering, quote selection, action idea generation |
| **Remote MCP Server** | [`mcpservergroww.vercel.app`](https://mcpservergroww.vercel.app) | Streamable HTTP MCP server exposing Google Docs and Gmail tools |
| **Google Doc** | ID: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms` | Continuous weekly pulse living document |

---

## 📦 Installation

```powershell
# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## ⚙️ Configuration (`config/config.yaml` + `.env`)

### `config/config.yaml`
```yaml
review:
  app_id: "com.nextbillion.groww"   # Groww Play Store package ID
  country: "in"                      # India Play Store
  language: "en"                     # Review language filter
  weeks_back: 10                     # Sliding window (8–12 weeks)
  max_reviews: 500                   # Payload limit cap
  min_words: 8                       # Keep reviews strictly > 8 words
  strip_emojis: true                 # Strip SMP, Dingbats, and emoticons
  english_only: true                 # Reject Devanagari (Hindi/Marathi) and Hinglish

llm:
  provider: "gemini"                 # Gemini LLM provider
  model: "gemini-1.5-pro"           # Target model
  temperature: 0.2                   # Deterministic clustering

pulse:
  max_themes: 5                      # Maximum theme clusters (EC-11)
  top_themes: 3                      # Top themes featured in the pulse
  quotes_count: 3                    # Verbatim quote count
  action_ideas_count: 3              # Verb-led action ideas
  max_words: 250                     # Strict word limit for pulse prose (EC-18)

mcp:
  server_url: "https://mcpservergroww.vercel.app/mcp"
  health_url: "https://mcpservergroww.vercel.app/health"
  google_doc_id: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

delivery:
  email_to: "you@example.com"           # Target stakeholder recipient
  doc_title_prefix: "Groww Weekly Pulse"
  email_subject_prefix: "[Groww Pulse] Weekly Review Summary"

output:
  data_dir: "data"                   # JSON snapshots directory
  log_level: "INFO"                  # Console logging verbosity
  retention_snapshots: 12            # Retention limit (auto-prunes older snapshots)
```

### `.env` (Secrets)
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
> [!NOTE]
> `.env` is gitignored to protect credentials. If `GEMINI_API_KEY` is omitted, the pipeline automatically falls back to heuristic clustering for offline testing and dry runs.

---

## 🏃 Running the Pipeline

### Command Line Interface
```powershell
# Default: runs today's weekly pulse
python src/orchestrate.py

# Dry-run: ingests, clusters, formats pulse, skips remote MCP delivery
python src/orchestrate.py --dry-run

# Backfill or run historical week
python src/orchestrate.py --date 2026-11-01

# Force re-scrape bypassing cached snapshot (EC-30)
python src/orchestrate.py --force

# Run selectively
python src/orchestrate.py --skip-email     # Appends to Doc only
python src/orchestrate.py --skip-docs      # Sends Email only
```

### One-Click Helper Script
```powershell
# Run with forwarded CLI arguments
.\scripts\run_pulse.ps1 --dry-run --date 2026-11-01

# Launch the interactive web dashboard
.\scripts\run_pulse.ps1 -Serve
```

---

## 🖥️ Executive Pulse Frontend Dashboard

The project includes an executive dark-mode telemetry dashboard built from the latest Google Stitch design system ([`stitch/DESIGN.md`](stitch/DESIGN.md)).

```powershell
# Start local dashboard server (serves at http://localhost:8000)
python src/serve.py
```
*(You can also simply open [`index.html`](index.html) directly in any web browser without a web server).*

### Dashboard Features:
- **Executive KPI Ribbon:** Reviews Ingested (80), 100% Sanitized filters (>8 Words, Emojis Strip, English, 0 PII), 5 Discovered Clusters, and Executive Length Budget Gauge (214 / 250 words max).
- **Top 3 Voice of Customer (VoC) Themes:** Ranked product themes with verbatim quotes, star ratings, metadata tags, and volume/severity sorting.
- **PM Recommended Action Plan:** Concrete next steps starting with capitalized verbs (`FIX`, `IMPROVE`, `STREAMLINE`) with sprint checkboxes and engineering squad owners.
- **MCP Delivery Hub:** Direct link to living Google Doc (`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`), stakeholder Gmail notification status, and one-click "Copy Pulse Prose" button with animated feedback toast.
- **Interactive Ingestion Stream Table:** Explore and filter all 80 cleaned reviews by star rating (`All (80)`, `1-Star (37)`, `2-Star (2)`, `3-Star (9)`, `4-5 Star (32)`) with instant keyword search and theme badges.
- **Pipeline Execution Console Modal:** Click "Dry Run" or "Run Weekly Pipeline" to open an in-browser telemetry console streaming live stage progression.

---

## 🧪 Running Tests

The test suite consists of **93 unit and integration tests** testing all pipeline stages and edge cases without making external network calls:

```powershell
# Run all tests
.venv\Scripts\pytest -v

# Run specific test modules
.venv\Scripts\pytest tests/test_ingest.py -v       # 56 tests (PII, regex, language heuristics, >8 words)
.venv\Scripts\pytest tests/test_cluster.py -v      # 8 tests (Theme schema, EC-11 max 5 merge, EC-13 fences)
.venv\Scripts\pytest tests/test_pulse.py -v        # 8 tests (<=250 words, verbatim quote grounding, action verbs)
.venv\Scripts\pytest tests/test_mcp.py -v          # 13 tests (Streamable HTTP, /health, Docs, Gmail, CR/LF scrub)
.venv\Scripts\pytest tests/test_orchestrate.py -v  # 8 tests (CLI, caching, EC-35 partial failure, retention)
```

---

## ⏰ Scheduling (Weekly Execution)

### Option A — Windows Task Scheduler (Recommended)
Use the included helper script to register the pipeline to run autonomously every Monday at 08:00 AM using the virtual environment's Python executable:

```powershell
# Register the weekly scheduled task
.\scripts\schedule_weekly.ps1 -Action Register

# Check task status and next run time
.\scripts\schedule_weekly.ps1 -Action Status

# Manually trigger immediate run for testing
.\scripts\schedule_weekly.ps1 -Action RunNow

# Unregister when no longer needed
.\scripts\schedule_weekly.ps1 -Action Unregister
```

### Option B — Antigravity `/schedule` Command
In the AGY chat interface, use the `/schedule` slash command:
```
/schedule
```
Prompt: *"Run `python src/orchestrate.py` in `c:\Projects\Grow reviwes_MCP` every Monday at 8:00 AM"*

### Option C — Manual Trigger
Run manually every Monday using:
```powershell
.\scripts\run_pulse.ps1
```

---

## 🏛️ Architecture & Project Structure

```
Grow reviwes_MCP\
├── src\
│   ├── ingest.py        ← Play Store scraping, PII redaction, emoji & language cleaning
│   ├── cluster.py       ← LLM theme clustering, schema bounds, excess theme merge (≤5)
│   ├── pulse.py         ← Verbatim quote selection, action ideas, ≤250 words prose formatting
│   ├── mcp_client.py    ← Streamable HTTP MCP client session (JSON-RPC 2.0 over SSE)
│   ├── mcp_docs.py      ← append_to_google_doc tool integration
│   ├── mcp_gmail.py     ← send_email tool integration with header sanitization
│   └── orchestrate.py   ← End-to-end pipeline runner, caching (EC-30), snapshot retention
├── config\
│   └── config.yaml      ← Tuneable parameters
├── data\                ← Weekly reviews and pulse JSON snapshots (auto-pruned to last 12)
├── scripts\
│   ├── run_pulse.ps1       ← One-click PowerShell pipeline runner
│   └── schedule_weekly.ps1 ← Windows Task Scheduler automation manager
├── tests\
│   ├── fixtures\        ← Mock review and cluster JSON files
│   ├── test_ingest.py
│   ├── test_cluster.py
│   ├── test_pulse.py
│   ├── test_mcp.py
│   └── test_orchestrate.py
├── docs\
│   ├── architecture.md       ← Full architectural design and data flow
│   ├── implementation-plan.md← Phase-wise delivery plan and exit criteria
│   ├── edge-cases.md         ← Edge case registry (EC-01 to EC-35)
│   └── problemstatement.txt  ← Product requirements and constraints
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

Detailed design documentation:
- [Architecture & Design Decisions](docs/architecture.md)
- [Phase-wise Implementation Plan](docs/implementation-plan.md)
- [Edge Case Catalog & Defensive Guards](docs/edge-cases.md)

---

## 🔒 Constraints & Privacy Guarantees

1. **MCP-First Architecture:** No raw Google OAuth or REST client code in the project. All write mutations occur through the authenticated remote MCP server (`https://mcpservergroww.vercel.app`).
2. **Strict PII Redaction:** Reviewer names, reviewer photos, and review IDs are dropped during ingestion. Emails, 10-digit Indian phone numbers, and Aadhaar numbers in review content are replaced with `[REDACTED]`. Quotes undergo secondary PII scrubbing prior to pulse assembly.
3. **Strict Data Cleaning:**
   - Emojis stripped from review bodies.
   - Reviews with $\le 8$ words discarded; only rich feedback with $> 8$ words retained.
   - Non-English reviews (Devanagari Hindi/Marathi, Romanized Hinglish) filtered out.
4. **Volume & Length Boundaries:**
   - Maximum 5 theme clusters discovered; top 3 themes highlighted.
   - Written pulse note strictly $\le 250$ words (enforced programmatically with automatic condensation fallback).
5. **Retention:** Historical JSON snapshots in `data/` are automatically pruned to the last 12 weekly snapshots to conserve local storage.
