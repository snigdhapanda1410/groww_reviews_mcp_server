# 🚀 Groww Reviews MCP — Cloud Deployment Plan

> **Authoritative Deployment Plan:**  
> Please see the complete, detailed deployment specification in [`docs/deployment-plan.md`](docs/deployment-plan.md).

### Quick Summary

| Component | Platform | Configuration File | Command / Strategy |
|---|---|---|---|
| **Backend API & Orchestrator** | **Railway** | [`railway.json`](railway.json), [`Procfile`](Procfile), [`runtime.txt`](runtime.txt) | Python 3.11 Nixpacks Web Service (`python src/serve.py`) |
| **Weekly Cron Automation** | **Railway** | Cron Schedule: `0 2 * * 1` (Mondays 07:30 IST) | Background Worker (`python src/orchestrate.py`) |
| **Frontend Telemetry UI** | **Vercel** | [`vercel.json`](vercel.json), [`index.html`](index.html) | Edge CDN with reverse proxy rewrite (`/api/*` → Railway) |
| **Remote MCP Server** | **Vercel** | Live at `https://mcpservergroww.vercel.app` | Streamable HTTP (`append_to_google_doc`, `send_email`) |

### Key Deployment Files Created in Repository:
1. [`railway.json`](railway.json) — Railway build & healthcheck specification (`/api/status`).
2. [`Procfile`](Procfile) — Process start command (`web: python src/serve.py`).
3. [`runtime.txt`](runtime.txt) — Python runtime pin (`python-3.11.9`).
4. [`vercel.json`](vercel.json) — Vercel reverse proxy rewrites and security headers.
5. [`docs/deployment-plan.md`](docs/deployment-plan.md) — Comprehensive step-by-step runbook with Mermaid topology diagrams.

