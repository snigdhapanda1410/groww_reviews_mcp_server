"""
src/mcp_docs.py
─────────────────────────────────────────────────────────────────────────────
Phase 4 — Google Docs MCP Integration Layer

Responsibilities:
  1. Append weekly pulse content to the stakeholder Google Doc using
     the remote MCP tool 'append_to_google_doc'.
  2. Handle errors (invalid URL/ID, connection failures, auth expiry).
  3. Return document ID and full document URL for subsequent Gmail notification.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.mcp_client import DeliveryError, MCPError, _load_config, call_mcp_tool

logger = logging.getLogger(__name__)


async def append_pulse_to_doc(
    content: str,
    document_id: str | None = None,
    server_url: str | None = None,
    config_path: str = "config/config.yaml",
    client_session: Any = None,
) -> dict[str, Any]:
    """
    Append formatted weekly pulse prose to a Google Doc via the MCP server.

    Args:
        content: Plain-text weekly pulse content to append.
        document_id: Google Doc document ID or full URL. If omitted, read from config.
        server_url: Remote MCP server URL (defaults to config or Vercel).
        config_path: Path to pipeline config.yaml.
        client_session: Optional mock/custom session for unit testing.

    Returns:
        Dict containing documentId, documentUrl, and success status.

    Raises:
        DeliveryError: If Google Docs API returns an error or authentication is invalid.
        MCPError: If MCP communication fails.
        ValueError: If no document_id is provided or configured.
    """
    if not document_id:
        cfg = _load_config(config_path)
        document_id = cfg.get("mcp", {}).get("google_doc_id")
        if not document_id or document_id.startswith("YOUR_"):
            raise ValueError(
                "No target Google Doc ID configured. Provide document_id or set "
                "mcp.google_doc_id in config/config.yaml."
            )

    if not content or not content.strip():
        raise ValueError("Pulse content to append cannot be empty.")

    logger.info("Appending pulse to Google Doc (%s) via MCP...", document_id)

    result = await call_mcp_tool(
        tool_name="append_to_google_doc",
        arguments={
            "documentId": document_id.strip(),
            "content": content.strip() + "\n\n",
        },
        server_url=server_url,
        config_path=config_path,
        client_session=client_session,
    )

    doc_url = result.get("documentUrl") or f"https://docs.google.com/document/d/{document_id}/edit"
    logger.info("Successfully appended pulse to Google Doc: %s", doc_url)
    return {
        "success": True,
        "documentId": result.get("documentId", document_id),
        "documentUrl": doc_url,
        "message": result.get("message", "Content appended successfully"),
    }


def append_pulse_to_doc_sync(
    content: str,
    document_id: str | None = None,
    server_url: str | None = None,
    config_path: str = "config/config.yaml",
    client_session: Any = None,
) -> dict[str, Any]:
    """Synchronous wrapper for append_pulse_to_doc."""
    return asyncio.run(
        append_pulse_to_doc(
            content=content,
            document_id=document_id,
            server_url=server_url,
            config_path=config_path,
            client_session=client_session,
        )
    )
