"""
src/serve.py
─────────────────────────────────────────────────────────────────────────────
Local Development & Telemetry Server for Groww Reviews MCP Dashboard.

Serves the frontend (index.html) and provides lightweight REST APIs to:
  - Query MCP server health
  - Fetch review & pulse snapshots
  - Trigger dry-run or live pipeline executions directly from the UI

Usage:
  python src/serve.py [--port 8000]
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.mcp_client import check_mcp_health
from src.orchestrate import load_config, run_pipeline

logger = logging.getLogger("groww_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler supporting static frontend delivery and JSON APIs."""

    def _set_cors_headers(self, content_type: str = "application/json") -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", content_type)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/status":
            self._handle_api_status()
        elif path == "/api/data":
            self._handle_api_data(query)
        else:
            self._handle_static_file(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/run":
            self._handle_api_run()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def _handle_api_status(self) -> None:
        try:
            cfg = load_config()
            health_url = cfg.get("mcp", {}).get("health_url", "https://mcpservergroww.vercel.app/health")
            health_info = check_mcp_health(health_url)
        except Exception as exc:
            health_info = {"status": "error", "error": str(exc)}

        data_dir = PROJECT_ROOT / "data"
        snapshots = []
        if data_dir.exists():
            for f in sorted(data_dir.glob("pulse_*.json"), reverse=True):
                date_str = f.stem.replace("pulse_", "")
                snapshots.append(date_str)

        payload = {
            "status": "ok",
            "mcp": health_info,
            "snapshots": snapshots,
            "default_snapshot": snapshots[0] if snapshots else None,
        }
        self.send_response(HTTPStatus.OK)
        self._set_cors_headers("application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))

    def _handle_api_data(self, query: dict[str, list[str]]) -> None:
        data_dir = PROJECT_ROOT / "data"
        date_param = query.get("date", [None])[0]

        if not date_param:
            snapshots = sorted([f.stem.replace("pulse_", "") for f in data_dir.glob("pulse_*.json")], reverse=True)
            date_param = snapshots[0] if snapshots else "2026-11-01"

        pulse_file = data_dir / f"pulse_{date_param}.json"
        reviews_file = data_dir / f"reviews_{date_param}.json"

        pulse_data = {}
        if pulse_file.exists():
            pulse_data = json.loads(pulse_file.read_text(encoding="utf-8"))

        reviews_data = []
        if reviews_file.exists():
            raw_rev = json.loads(reviews_file.read_text(encoding="utf-8"))
            reviews_data = raw_rev.get("reviews", []) if isinstance(raw_rev, dict) else raw_rev

        payload = {
            "date": date_param,
            "pulse": pulse_data,
            "reviews": reviews_data,
            "review_count": len(reviews_data),
        }
        self.send_response(HTTPStatus.OK)
        self._set_cors_headers("application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _handle_api_run(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except json.JSONDecodeError:
            body = {}

        dry_run = bool(body.get("dry_run", True))
        date_param = body.get("date")

        try:
            logger.info("Executing pipeline via API (dry_run=%s, date=%s)...", dry_run, date_param)
            result = run_pipeline(dry_run=dry_run, week_ending=date_param)
            # Remove raw objects if not JSON serializable
            result_clean = {
                "status": result.get("status"),
                "week_ending": result.get("week_ending"),
                "review_count": result.get("review_count"),
                "theme_count": result.get("theme_count"),
                "word_count": result.get("word_count"),
                "doc_url": result.get("doc_url"),
                "message_id": result.get("message_id"),
                "pulse_prose": result.get("pulse_prose"),
                "top_themes": result.get("pulse_payload", {}).get("top_themes", []),
                "action_ideas": result.get("pulse_payload", {}).get("action_ideas", []),
            }
            self.send_response(HTTPStatus.OK)
            self._set_cors_headers("application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "result": result_clean}).encode("utf-8"))
        except Exception as exc:
            logger.error("Pipeline run via API failed: %s", exc)
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self._set_cors_headers("application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(exc)}).encode("utf-8"))

    def _handle_static_file(self, path: str) -> None:
        if path in ("", "/"):
            file_path = PROJECT_ROOT / "index.html"
        else:
            file_path = (PROJECT_ROOT / path.lstrip("/")).resolve()

        # Security check: must reside inside project root
        if not str(file_path).startswith(str(PROJECT_ROOT)):
            self.send_error(HTTPStatus.FORBIDDEN, "Access denied")
            return

        if not file_path.exists() or not file_path.is_file():
            # Fallback to index.html for SPA-like navigation
            file_path = PROJECT_ROOT / "index.html"

        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        self.send_response(HTTPStatus.OK)
        self._set_cors_headers(mime_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    server_address = (host, port)
    httpd = HTTPServer(server_address, DashboardHandler)
    logger.info("Groww Reviews Pulse API & Dashboard live at http://%s:%d", host, port)
    logger.info("Press Ctrl+C to terminate server.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve Groww Reviews Dashboard")
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host address to bind (default 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8000)),
        help="Port to listen on (default 8000 or $PORT)",
    )
    args = parser.parse_args()
    run_server(args.host, args.port)

