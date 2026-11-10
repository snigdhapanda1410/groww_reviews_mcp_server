"""
src/mcp_gmail.py
─────────────────────────────────────────────────────────────────────────────
Phase 4 — Gmail MCP Integration Layer

Responsibilities:
  1. Dispatch the weekly pulse notification email via Gmail using
     the remote MCP tool 'send_email'.
  2. Format the standardized stakeholder email body (Doc link + inline pulse).
  3. Validate recipient and sanitize subject line (prohibit CR/LF injection).
  4. Return messageId and threadId from the MCP server.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from src.mcp_client import DeliveryError, MCPError, _load_config, call_mcp_tool

logger = logging.getLogger(__name__)


def build_email_body(
    week_ending: str,
    doc_url: str,
    pulse_prose: str,
) -> str:
    """Format the standardized email body containing Doc link and inline pulse summary."""
    return f"""Hi,

Your Groww app weekly review pulse is ready for w/e {week_ending}.

📄 Full pulse (Google Doc): {doc_url}

---
INLINE SUMMARY

{pulse_prose}

---
This email was generated automatically by the Groww Reviews MCP pipeline.
Reviews sourced from public Google Play Store data.
"""


def sanitize_email_field(text: str) -> str:
    """Strip CR/LF characters to comply with server-side header injection prevention."""
    return re.sub(r"[\r\n]+", " ", text).strip()


async def send_pulse_email(
    doc_url: str,
    pulse_prose: str,
    week_ending: str,
    to: str | None = None,
    subject: str | None = None,
    server_url: str | None = None,
    config_path: str = "config/config.yaml",
    client_session: Any = None,
) -> dict[str, Any]:
    """
    Send the weekly pulse email via the remote MCP server.

    Args:
        doc_url: URL of the updated Google Doc.
        pulse_prose: Formatted plain-text pulse note.
        week_ending: ISO date string for the week ending.
        to: Recipient email address. If None, read from config.delivery.email_to.
        subject: Optional email subject line.
        server_url: Remote MCP server URL.
        config_path: Path to config.yaml.
        client_session: Optional mock/custom session for unit testing.

    Returns:
        Dict containing messageId, threadId, and success status.

    Raises:
        DeliveryError: If sending email fails via the MCP tool.
        MCPError: If MCP communication fails.
        ValueError: If recipient or body is invalid.
    """
    cfg = _load_config(config_path)
    delivery_cfg = cfg.get("delivery", {})

    recipient = to or os.getenv("EMAIL_TO") or delivery_cfg.get("email_to")
    if not recipient or recipient.startswith("you@"):
        raise ValueError(
            "Invalid recipient email address. Provide 'to' parameter or configure "
            "'delivery.email_to' in config/config.yaml."
        )

    recipient = sanitize_email_field(recipient)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", recipient):
        raise ValueError(f"Malformed recipient email address: '{recipient}'")

    subject_prefix = delivery_cfg.get("email_subject_prefix", "[Groww Pulse] Weekly Review Summary")
    final_subject = subject or f"{subject_prefix} — {week_ending}"
    final_subject = sanitize_email_field(final_subject)

    body = build_email_body(
        week_ending=week_ending,
        doc_url=doc_url,
        pulse_prose=pulse_prose,
    )

    logger.info("Sending pulse email to '%s' via MCP...", recipient)

    result = await call_mcp_tool(
        tool_name="send_email",
        arguments={
            "to": recipient,
            "subject": final_subject,
            "body": body,
        },
        server_url=server_url,
        config_path=config_path,
        client_session=client_session,
    )

    logger.info("Email dispatched successfully. Message ID: %s", result.get("messageId"))
    return {
        "success": True,
        "messageId": result.get("messageId"),
        "threadId": result.get("threadId"),
        "to": recipient,
        "subject": final_subject,
    }


def send_pulse_email_sync(
    doc_url: str,
    pulse_prose: str,
    week_ending: str,
    to: str | None = None,
    subject: str | None = None,
    server_url: str | None = None,
    config_path: str = "config/config.yaml",
    client_session: Any = None,
) -> dict[str, Any]:
    """Synchronous wrapper for send_pulse_email."""
    return asyncio.run(
        send_pulse_email(
            doc_url=doc_url,
            pulse_prose=pulse_prose,
            week_ending=week_ending,
            to=to,
            subject=subject,
            server_url=server_url,
            config_path=config_path,
            client_session=client_session,
        )
    )
