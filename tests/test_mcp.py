"""
tests/test_mcp.py
─────────────────────────────────────────────────────────────────────────────
Phase 4 / Phase 6 — Unit tests for MCP Integration layer (Docs & Gmail)

Coverage:
  - mcp_client.check_mcp_health
  - mcp_client.call_mcp_tool & _parse_tool_result
  - mcp_docs.append_pulse_to_doc
  - mcp_gmail.send_pulse_email & header sanitization
  - Error propagation (DeliveryError, MCPError, ValueError)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.mcp_client import (
    DeliveryError,
    MCPError,
    check_mcp_health,
    call_mcp_tool,
    call_mcp_tool_sync,
)
from src.mcp_docs import append_pulse_to_doc, append_pulse_to_doc_sync
from src.mcp_gmail import (
    build_email_body,
    sanitize_email_field,
    send_pulse_email,
    send_pulse_email_sync,
)


class MockTextContent:
    def __init__(self, text: str):
        self.text = text


class MockCallToolResult:
    def __init__(self, text: str, is_error: bool = False):
        self.content = [MockTextContent(text)]
        self.is_error = is_error


class TestMcpClient:
    def test_check_mcp_health_success(self):
        mock_resp_data = json.dumps({
            "status": "ok",
            "service": "google-workspace-mcp",
            "authenticated": True,
            "tools": ["send_email", "append_to_google_doc"],
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_resp_data
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            health = check_mcp_health("https://fake.url/health")
            assert health["status"] == "ok"
            assert "send_email" in health["tools"]

    def test_check_mcp_health_failure_raises_mcperror(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            with pytest.raises(MCPError, match="health check failed"):
                check_mcp_health("https://fake.url/health")

    def test_call_mcp_tool_with_mock_session_success(self):
        async def _run():
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = MockCallToolResult(
                json.dumps({"success": True, "documentId": "doc123"})
            )
            res = await call_mcp_tool("append_to_google_doc", {"documentId": "doc123"}, client_session=mock_session)
            assert res["success"] is True
            assert res["documentId"] == "doc123"

        asyncio.run(_run())

    def test_call_mcp_tool_with_mock_session_error(self):
        async def _run():
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = MockCallToolResult(
                json.dumps({"success": False, "message": "Auth token expired"}),
                is_error=True,
            )
            with pytest.raises(DeliveryError, match="Auth token expired"):
                await call_mcp_tool("append_to_google_doc", {"documentId": "doc123"}, client_session=mock_session)

        asyncio.run(_run())


class TestMcpDocs:
    def test_append_pulse_to_doc_success(self):
        async def _run():
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = MockCallToolResult(
                json.dumps({
                    "success": True,
                    "message": "Content appended successfully",
                    "documentId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                    "documentUrl": "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
                })
            )
            result = await append_pulse_to_doc(
                content="Groww Weekly Pulse Content",
                document_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                client_session=mock_session,
            )
            assert result["success"] is True
            assert "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" in result["documentUrl"]

        asyncio.run(_run())

    def test_append_pulse_to_doc_empty_content_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            asyncio.run(append_pulse_to_doc(content="", document_id="doc123"))

    def test_append_pulse_to_doc_missing_id_raises(self, tmp_path):
        empty_cfg = tmp_path / "config.yaml"
        empty_cfg.write_text("mcp: {}\n")
        with pytest.raises(ValueError, match="No target Google Doc ID configured"):
            asyncio.run(append_pulse_to_doc(content="Some content", document_id=None, config_path=str(empty_cfg)))

    def test_append_pulse_to_doc_sync(self):
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = MockCallToolResult(
            json.dumps({
                "success": True,
                "documentId": "doc_sync",
                "documentUrl": "https://docs.google.com/document/d/doc_sync/edit",
            })
        )
        result = append_pulse_to_doc_sync(
            content="Sync content",
            document_id="doc_sync",
            client_session=mock_session,
        )
        assert result["success"] is True
        assert result["documentId"] == "doc_sync"


class TestMcpGmail:
    def test_send_pulse_email_success(self):
        async def _run():
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = MockCallToolResult(
                json.dumps({
                    "success": True,
                    "messageId": "msg_998877",
                    "threadId": "thread_112233",
                })
            )
            result = await send_pulse_email(
                doc_url="https://docs.google.com/document/d/123/edit",
                pulse_prose="Top Themes: Crashes, KYC",
                week_ending="2026-11-01",
                to="stakeholder@example.com",
                client_session=mock_session,
            )
            assert result["success"] is True
            assert result["messageId"] == "msg_998877"
            assert result["to"] == "stakeholder@example.com"

        asyncio.run(_run())

    def test_send_pulse_email_invalid_recipient_raises(self):
        with pytest.raises(ValueError, match="Malformed recipient"):
            asyncio.run(send_pulse_email(
                doc_url="https://doc.url",
                pulse_prose="Summary",
                week_ending="2026-11-01",
                to="not-an-email",
            ))

    def test_sanitize_email_field_strips_crlf(self):
        dirty_subject = "Weekly Summary\r\nBcc: evil@hacker.com"
        clean = sanitize_email_field(dirty_subject)
        assert "\r" not in clean
        assert "\n" not in clean
        assert clean == "Weekly Summary Bcc: evil@hacker.com"

    def test_build_email_body_contains_doc_link_and_summary(self):
        body = build_email_body(
            week_ending="2026-11-01",
            doc_url="https://docs.google.com/document/d/123/edit",
            pulse_prose="TOP THEMES\n1. Bug",
        )
        assert "https://docs.google.com/document/d/123/edit" in body
        assert "TOP THEMES" in body
        assert "2026-11-01" in body

    def test_send_pulse_email_sync(self):
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = MockCallToolResult(
            json.dumps({"success": True, "messageId": "msg_sync"})
        )
        result = send_pulse_email_sync(
            doc_url="https://doc.url",
            pulse_prose="Prose",
            week_ending="2026-11-01",
            to="user@example.com",
            client_session=mock_session,
        )
        assert result["success"] is True
        assert result["messageId"] == "msg_sync"
