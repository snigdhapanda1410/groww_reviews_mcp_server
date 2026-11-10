"""
src/mcp_client.py
─────────────────────────────────────────────────────────────────────────────
Phase 4 — Model Context Protocol (MCP) Client Transport Layer

Connects to the Google Workspace MCP server deployed at:
  https://mcpservergroww.vercel.app/mcp

Supports tools exposed by the server:
  - append_to_google_doc: Appends plain text to the target Google Doc.
  - send_email: Dispatches plain text email via Gmail.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)

DEFAULT_SERVER_URL = "https://mcpservergroww.vercel.app/mcp"
DEFAULT_HEALTH_URL = "https://mcpservergroww.vercel.app/health"


class MCPError(RuntimeError):
    """Raised when communication with the MCP server fails."""


class DeliveryError(RuntimeError):
    """Raised when an MCP delivery tool (Docs/Gmail) execution fails."""


def _unwrap_exception(exc: BaseException) -> BaseException:
    """Recursively search for an underlying DeliveryError or MCPError inside ExceptionGroups."""
    if isinstance(exc, (DeliveryError, MCPError)):
        return exc
    if hasattr(exc, "exceptions"):
        for sub_exc in getattr(exc, "exceptions", []):
            unwrapped = _unwrap_exception(sub_exc)
            if isinstance(unwrapped, (DeliveryError, MCPError)):
                return unwrapped
    return exc


def _load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration YAML file."""
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_mcp_health(
    health_url: str | None = None,
    config_path: str = "config/config.yaml",
    timeout: int = 10,
) -> dict:
    """
    Check the health and authentication status of the remote MCP server.

    Returns:
        Dict containing server status, version, authenticated flag, and available tools.
    """
    if not health_url:
        cfg = _load_config(config_path)
        health_url = cfg.get("mcp", {}).get("health_url", DEFAULT_HEALTH_URL)

    try:
        req = urllib.request.Request(
            health_url,
            headers={"User-Agent": "GrowwReviewsMCPClient/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            logger.info("MCP server health: %s (authenticated: %s)", data.get("status"), data.get("authenticated"))
            return data
    except Exception as exc:
        logger.error("Failed to connect to MCP health endpoint '%s': %s", health_url, exc)
        raise MCPError(f"MCP server health check failed at {health_url}: {exc}") from exc


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    server_url: str | None = None,
    config_path: str = "config/config.yaml",
    client_session: Any = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Invoke an MCP tool on the remote server over Streamable HTTP transport.

    Args:
        tool_name: Name of tool to execute (e.g. 'append_to_google_doc', 'send_email').
        arguments: Dictionary of arguments conforming to tool schema.
        server_url: URL of the MCP server endpoint. Defaults to config or Vercel URL.
        config_path: Path to config.yaml if server_url is not passed.
        client_session: Optional pre-existing or mock ClientSession for testing.
        timeout: Timeout in seconds for the tool call.

    Returns:
        Parsed dictionary result returned by the MCP tool.

    Raises:
        DeliveryError: If the remote tool reports an error (e.g. invalid docId or auth error).
        MCPError: If connection or transport to the MCP server fails.
    """
    if client_session is not None:
        # Use provided or mock session directly
        try:
            res = await client_session.call_tool(tool_name, arguments)
            return _parse_tool_result(tool_name, res)
        except Exception as exc:
            raise DeliveryError(f"MCP tool '{tool_name}' execution failed: {exc}") from exc

    if not server_url:
        cfg = _load_config(config_path)
        server_url = cfg.get("mcp", {}).get("server_url", DEFAULT_SERVER_URL)

    logger.info("Connecting to MCP server at %s to invoke '%s'...", server_url, tool_name)

    try:
        async with streamable_http_client(server_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logger.debug("MCP session initialized successfully.")
                res = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=timeout,
                )
                return _parse_tool_result(tool_name, res)
    except DeliveryError:
        raise
    except asyncio.TimeoutError as exc:
        raise MCPError(f"Timeout calling MCP tool '{tool_name}' at {server_url}") from exc
    except BaseException as exc:
        unwrapped = _unwrap_exception(exc)
        if isinstance(unwrapped, (DeliveryError, MCPError)):
            raise unwrapped from exc
        raise MCPError(f"Failed to communicate with MCP server at {server_url}: {exc}") from exc


def _parse_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    """Parse TextContent JSON output from CallToolResult."""
    # Check if result is error
    is_error = getattr(result, "is_error", False)
    content_list = getattr(result, "content", [])

    if not content_list:
        if is_error:
            raise DeliveryError(f"MCP tool '{tool_name}' failed with empty response.")
        return {"success": True}

    text_output = getattr(content_list[0], "text", "")
    try:
        parsed = json.loads(text_output)
    except (json.JSONDecodeError, TypeError):
        parsed = {"text": text_output}

    if is_error or parsed.get("success") is False:
        err_msg = parsed.get("message") or parsed.get("error") or text_output
        raise DeliveryError(f"MCP tool '{tool_name}' failed: {err_msg}")

    return parsed


def call_mcp_tool_sync(
    tool_name: str,
    arguments: dict[str, Any],
    server_url: str | None = None,
    config_path: str = "config/config.yaml",
    client_session: Any = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Synchronous wrapper for call_mcp_tool."""
    return asyncio.run(
        call_mcp_tool(
            tool_name=tool_name,
            arguments=arguments,
            server_url=server_url,
            config_path=config_path,
            client_session=client_session,
            timeout=timeout,
        )
    )

