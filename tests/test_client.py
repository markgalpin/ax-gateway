"""Tests for AxClient auth and token class selection."""

from unittest.mock import MagicMock

import httpx
import pytest

from ax_cli.client import (
    AxClient,
    RateLimitPreemptedError,
    _mime_from_ext,
    _mime_from_filename,
    _RateLimitState,
    _RetryOnAuthClient,
)


class TestTokenClassSelection:
    """Verify correct token class is requested based on PAT prefix + agent_id."""

    def test_user_pat_with_agent_id_is_blocked(self, tmp_path, monkeypatch, mock_exchange):
        """User PATs exchange to user JWTs, so an agent-bound profile must not use one."""
        mock_post = mock_exchange()
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ax").mkdir()
        (tmp_path / ".ax" / "config.toml").write_text("")

        client = AxClient(
            "https://example.com",
            "axp_u_UserKey.UserSecret",
            agent_id="some-agent-uuid",
        )
        with pytest.raises(SystemExit):
            client._get_jwt()

        mock_post.assert_not_called()

    def test_user_pat_with_agent_name_is_blocked(self, tmp_path, monkeypatch, mock_exchange):
        """Agent-name config plus user PAT is also an attribution boundary violation."""
        mock_post = mock_exchange()
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ax").mkdir()
        (tmp_path / ".ax" / "config.toml").write_text("")

        client = AxClient(
            "https://example.com",
            "axp_u_UserKey.UserSecret",
            agent_name="some-agent",
        )
        with pytest.raises(SystemExit):
            client._get_jwt()

        mock_post.assert_not_called()

    def test_agent_pat_with_agent_id_uses_agent_access(self, tmp_path, monkeypatch, mock_exchange):
        """Agent-bound PATs (axp_a_) with agent_id should use agent_access."""
        mock_post = mock_exchange()
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ax").mkdir()
        (tmp_path / ".ax" / "config.toml").write_text("")

        client = AxClient(
            "https://example.com",
            "axp_a_AgentKey.AgentSecret",
            agent_id="some-agent-uuid",
        )
        client._get_jwt()

        call_body = mock_post.call_args[1]["json"]
        assert call_body["requested_token_class"] == "agent_access"
        assert call_body["agent_id"] == "some-agent-uuid"

    def test_agent_pat_without_agent_id_falls_back_to_user_access(self, tmp_path, monkeypatch, mock_exchange):
        """Agent-bound PATs need configured agent_id before requesting agent_access."""
        mock_post = mock_exchange()
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ax").mkdir()
        (tmp_path / ".ax" / "config.toml").write_text("")

        client = AxClient(
            "https://example.com",
            "axp_a_AgentKey.AgentSecret",
        )
        client._get_jwt()

        call_body = mock_post.call_args[1]["json"]
        assert call_body["requested_token_class"] == "user_access"
        assert "agent_id" not in call_body

    def test_user_pat_without_agent_id_uses_user_access(self, tmp_path, monkeypatch, mock_exchange):
        """User PAT without agent_id → user_access."""
        mock_post = mock_exchange()
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ax").mkdir()
        (tmp_path / ".ax" / "config.toml").write_text("")

        client = AxClient(
            "https://example.com",
            "axp_u_UserKey.UserSecret",
        )
        client._get_jwt()

        call_body = mock_post.call_args[1]["json"]
        assert call_body["requested_token_class"] == "user_access"


def test_cli_mime_overrides_normalize_common_source_artifacts_to_safe_text():
    assert _mime_from_ext(".java") == "text/plain"
    assert _mime_from_ext(".go") == "text/plain"
    assert _mime_from_ext(".rs") == "text/plain"
    assert _mime_from_ext(".yaml") == "text/plain"
    assert _mime_from_ext(".sh") == "text/plain"
    assert _mime_from_filename("Dockerfile") == "text/plain"
    assert _mime_from_filename("Makefile") == "text/plain"


def test_connect_sse_uses_v1_route_and_explicit_space_id():
    client = AxClient("https://example.com", "legacy-token")
    client._http.stream = MagicMock(return_value="stream-response")

    result = client.connect_sse(space_id="space-123")

    assert result == "stream-response"
    call = client._http.stream.call_args
    assert call.args[:2] == ("GET", "/api/v1/sse/messages")
    assert call.kwargs["params"] == {"token": "legacy-token", "space_id": "space-123"}


def test_list_messages_passes_explicit_space_id():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"messages": []},
        request=httpx.Request("GET", "https://example.com/api/v1/messages"),
    )
    client._http.get = MagicMock(return_value=response)

    client.list_messages(limit=5, channel="main", space_id="space-123")

    assert client._http.get.call_args.args[0] == "/api/v1/messages"
    assert client._http.get.call_args.kwargs["params"] == {
        "limit": 5,
        "channel": "main",
        "space_id": "space-123",
    }


def test_list_messages_can_request_unread_and_mark_read():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"messages": [], "unread_count": 0},
        request=httpx.Request("GET", "https://example.com/api/v1/messages"),
    )
    client._http.get = MagicMock(return_value=response)

    client.list_messages(
        limit=5,
        channel="main",
        space_id="space-123",
        unread_only=True,
        mark_read=True,
    )

    assert client._http.get.call_args.kwargs["params"] == {
        "limit": 5,
        "channel": "main",
        "space_id": "space-123",
        "unread_only": "true",
        "mark_read": "true",
    }


def test_send_message_allows_metadata_and_message_type():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"id": "msg-1"},
        request=httpx.Request("POST", "https://example.com/api/v1/messages"),
    )
    client._http.post = MagicMock(return_value=response)

    client.send_message(
        "space-123",
        "context signal",
        channel="automation-alerts",
        metadata={"ui": {"widget": {"resource_uri": "ui://context/explorer"}}},
        message_type="system",
    )

    assert client._http.post.call_args.args[0] == "/api/v1/messages"
    assert client._http.post.call_args.kwargs["json"] == {
        "content": "context signal",
        "space_id": "space-123",
        "channel": "automation-alerts",
        "message_type": "system",
        "metadata": {"ui": {"widget": {"resource_uri": "ui://context/explorer"}}},
    }


def test_mark_message_read_calls_backend_read_endpoint():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"status": "success", "message_id": "msg-1"},
        request=httpx.Request("POST", "https://example.com/api/v1/messages/msg-1/read"),
    )
    client._http.post = MagicMock(return_value=response)

    assert client.mark_message_read("msg-1")["status"] == "success"
    assert client._http.post.call_args.args[0] == "/api/v1/messages/msg-1/read"


def test_mark_all_messages_read_calls_backend_endpoint():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"status": "success", "marked_read": 2},
        request=httpx.Request("POST", "https://example.com/api/v1/messages/mark-all-read"),
    )
    client._http.post = MagicMock(return_value=response)

    assert client.mark_all_messages_read()["marked_read"] == 2
    assert client._http.post.call_args.args[0] == "/api/v1/messages/mark-all-read"


def test_parse_json_names_agent_create_html_shell_as_api_contract_failure():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        text="<!DOCTYPE html><html></html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("POST", "https://example.com/api/v1/agents"),
    )

    with pytest.raises(httpx.HTTPStatusError) as exc:
        client._parse_json(response)

    message = str(exc.value)
    assert "Agent create returned HTML instead of JSON" in message
    assert "quota" in message
    assert "name conflict" in message


def test_parse_json_names_send_message_html_shell_as_routing_failure():
    """Parallel of the agents-create case: when the hosted SPA captures
    POST /api/v1/messages, the CLI cannot post reply metadata, so the
    error message names that consequence rather than the generic
    'frontend may be catching this route' hint."""
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        text="<!DOCTYPE html><html></html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("POST", "https://example.com/api/v1/messages"),
    )

    with pytest.raises(httpx.HTTPStatusError) as exc:
        client._parse_json(response)

    message = str(exc.value)
    assert "Send-message returned HTML instead of JSON" in message
    assert "parent_id" in message
    assert "agent-to-agent reply routing" in message


def test_record_tool_call_posts_audit_payload():
    client = AxClient("https://example.com", "legacy-token", agent_id="agent-123", agent_name="codex")
    response = httpx.Response(
        202,
        json={"ok": True, "tool_call_id": "tool-1"},
        request=httpx.Request("POST", "https://example.com/api/v1/tool-calls"),
    )
    client._http.post = MagicMock(return_value=response)

    result = client.record_tool_call(
        tool_name="shell",
        tool_call_id="tool-1",
        space_id="space-123",
        tool_action="wc -c README.md",
        arguments={"command": "wc -c README.md"},
        initial_data={"output": "28358 README.md"},
        status="success",
        message_id="msg-1",
        correlation_id="msg-1",
    )

    assert result["tool_call_id"] == "tool-1"
    assert client._http.post.call_args.args[0] == "/api/v1/tool-calls"
    assert client._http.post.call_args.kwargs["json"] == {
        "tool_name": "shell",
        "tool_call_id": "tool-1",
        "status": "success",
        "space_id": "space-123",
        "tool_action": "wc -c README.md",
        "arguments": {"command": "wc -c README.md"},
        "initial_data": {"output": "28358 README.md"},
        "message_id": "msg-1",
        "correlation_id": "msg-1",
    }


def test_set_agent_processing_status_includes_optional_fields():
    client = AxClient("https://example.com", "legacy-token", agent_id="agent-123", agent_name="codex")
    response = httpx.Response(
        200,
        json={"ok": True, "event": "agent_processing", "status": "processing"},
        request=httpx.Request("POST", "https://example.com/api/v1/agents/processing-status"),
    )
    client._http.post = MagicMock(return_value=response)

    result = client.set_agent_processing_status(
        "msg-1",
        "processing",
        agent_name="codex",
        space_id="space-123",
        activity="Running command",
        tool_name="shell",
        progress={"current": 1, "total": 3, "unit": "steps"},
        detail={"command": "pwd"},
        reason="gateway_runtime",
        error_message=None,
        retry_after_seconds=5,
        parent_message_id="parent-1",
    )

    assert result["status"] == "processing"
    assert client._http.post.call_args.args[0] == "/api/v1/agents/processing-status"
    assert client._http.post.call_args.kwargs["json"] == {
        "message_id": "msg-1",
        "status": "processing",
        "agent_name": "codex",
        "activity": "Running command",
        "tool_name": "shell",
        "progress": {"current": 1, "total": 3, "unit": "steps"},
        "detail": {"command": "pwd"},
        "reason": "gateway_runtime",
        "retry_after_seconds": 5,
        "parent_message_id": "parent-1",
    }


def test_set_agent_processing_status_posts_rich_payload():
    client = AxClient("https://example.com", "legacy-token", agent_id="agent-123", agent_name="codex")
    response = httpx.Response(
        202,
        json={"ok": True},
        request=httpx.Request("POST", "https://example.com/api/v1/agents/processing-status"),
    )
    client._http.post = MagicMock(return_value=response)

    result = client.set_agent_processing_status(
        "msg-1",
        "tool_call",
        agent_name="codex",
        space_id="space-123",
        activity="Running tests",
        tool_name="shell",
        progress={"current": 1, "total": 3, "unit": "steps"},
        detail={"command": "pytest tests/test_gateway_commands.py"},
        reason="tool started",
        error_message="",
        retry_after_seconds=5,
        parent_message_id="parent-1",
    )

    assert result["ok"] is True
    assert client._http.post.call_args.args[0] == "/api/v1/agents/processing-status"
    assert client._http.post.call_args.kwargs["json"] == {
        "message_id": "msg-1",
        "status": "tool_call",
        "agent_name": "codex",
        "activity": "Running tests",
        "tool_name": "shell",
        "progress": {"current": 1, "total": 3, "unit": "steps"},
        "detail": {"command": "pytest tests/test_gateway_commands.py"},
        "reason": "tool started",
        "error_message": "",
        "retry_after_seconds": 5,
        "parent_message_id": "parent-1",
    }


def test_list_tasks_passes_explicit_space_id():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"tasks": []},
        request=httpx.Request("GET", "https://example.com/api/v1/tasks"),
    )
    client._http.get = MagicMock(return_value=response)

    client.list_tasks(limit=7, space_id="space-123")

    assert client._http.get.call_args.args[0] == "/api/v1/tasks"
    assert client._http.get.call_args.kwargs["params"] == {
        "limit": 7,
        "space_id": "space-123",
    }


def test_list_agents_passes_explicit_space_id_and_limit():
    client = AxClient("https://example.com", "legacy-token")
    response = httpx.Response(
        200,
        json={"agents": []},
        request=httpx.Request("GET", "https://example.com/api/v1/agents"),
    )
    client._http.get = MagicMock(return_value=response)

    client.list_agents(space_id="space-123", limit=500)

    assert client._http.get.call_args.args[0] == "/api/v1/agents"
    assert client._http.get.call_args.kwargs["params"] == {
        "space_id": "space-123",
        "limit": 500,
    }


class TestCredentialManagement:
    """Verify credential management request payloads."""

    def _response(self, method: str, url: str, status_code: int, *, json=None, text: str | None = None):
        request = httpx.Request(method, url)
        if text is not None:
            return httpx.Response(
                status_code,
                text=text,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        return httpx.Response(status_code, json=json or {}, request=request)

    def test_create_key_with_allowed_agents_sets_agent_scope(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        response = httpx.Response(
            201,
            json={"ok": True},
            request=httpx.Request("POST", "https://example.com/api/v1/keys"),
        )
        client._http.post = MagicMock(return_value=response)

        client.create_key("agent-key", allowed_agent_ids=["agent-123"])

        body = client._http.post.call_args.kwargs["json"]
        assert body["agent_scope"] == "agents"
        assert body["allowed_agent_ids"] == ["agent-123"]

    def test_create_key_with_bound_agent_id(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        response = httpx.Response(
            201,
            json={"credential_id": "cred-1", "token": "axp_a_…"},
            request=httpx.Request("POST", "https://example.com/api/v1/keys"),
        )
        client._http.post = MagicMock(return_value=response)

        client.create_key("bound-key", bound_agent_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

        body = client._http.post.call_args.kwargs["json"]
        assert body["name"] == "bound-key"
        assert body["bound_agent_id"] == "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
        assert "agent_scope" not in body

    def test_create_key_with_bound_agent_id_and_scope(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        response = httpx.Response(
            201,
            json={},
            request=httpx.Request("POST", "https://example.com/api/v1/keys"),
        )
        client._http.post = MagicMock(return_value=response)

        agent_uuid = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"
        client.create_key(
            "combo",
            allowed_agent_ids=[agent_uuid],
            bound_agent_id=agent_uuid,
        )

        body = client._http.post.call_args.kwargs["json"]
        assert body["agent_scope"] == "agents"
        assert body["allowed_agent_ids"] == [agent_uuid]
        assert body["bound_agent_id"] == agent_uuid

    def test_create_task_sends_assignee_id_in_body(self):
        client = AxClient("https://example.com", "legacy-token", agent_id="creator-agent")
        response = httpx.Response(
            201,
            json={"id": "task-123", "space_id": "space-123", "assignee_id": "target-agent"},
            request=httpx.Request("POST", "https://example.com/api/v1/tasks"),
        )
        client._http.post = MagicMock(return_value=response)

        client.create_task(
            "space-123",
            "Review the spec",
            priority="medium",
            assignee_id="target-agent",
        )

        body = client._http.post.call_args.kwargs["json"]
        assert body["space_id"] == "space-123"
        assert body["assignee_id"] == "target-agent"

    def test_create_task_falls_back_from_hosted_html_and_verifies_space(self):
        client = AxClient("https://example.com", "legacy-token", agent_id="creator-agent")
        html_response = httpx.Response(
            200,
            text="<!doctype html><html></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("POST", "https://example.com/api/v1/tasks"),
        )
        create_response = httpx.Response(
            201,
            json={"id": "task-123", "title": "Review the spec"},
            request=httpx.Request("POST", "https://example.com/api/tasks"),
        )
        whoami_response = httpx.Response(
            200,
            json={"resolved_space_id": "space-123"},
            request=httpx.Request("GET", "https://example.com/auth/me"),
        )
        list_response = httpx.Response(
            200,
            json={"tasks": [{"id": "task-123", "space_id": "space-123"}]},
            request=httpx.Request("GET", "https://example.com/api/v1/tasks?limit=100&space_id=space-123"),
        )
        client._http.post = MagicMock(side_effect=[html_response, create_response])
        client._http.get = MagicMock(side_effect=[whoami_response, list_response])

        data = client.create_task("space-123", "Review the spec", priority="high")

        assert data["id"] == "task-123"
        assert client._http.post.call_args_list[0].args[0] == "/api/v1/tasks"
        assert client._http.post.call_args_list[1].args[0] == "/api/tasks"
        assert client._http.get.call_args_list[0].args[0] == "/auth/me"
        assert client._http.get.call_args_list[1].kwargs["params"] == {"limit": 100, "space_id": "space-123"}

    def test_create_task_fallback_refuses_when_session_space_differs(self):
        client = AxClient("https://example.com", "legacy-token", agent_id="creator-agent")
        html_response = httpx.Response(
            200,
            text="<!doctype html><html></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("POST", "https://example.com/api/v1/tasks"),
        )
        whoami_response = httpx.Response(
            200,
            json={"resolved_space_id": "madtank-space"},
            request=httpx.Request("GET", "https://example.com/auth/me"),
        )
        client._http.post = MagicMock(return_value=html_response)
        client._http.get = MagicMock(return_value=whoami_response)

        with pytest.raises(RuntimeError, match="Refusing to create the task"):
            client.create_task("ax-cli-dev-space", "Review the spec", priority="high")

        assert client._http.post.call_count == 1

    def test_create_task_fallback_rejects_unverified_space(self):
        client = AxClient("https://example.com", "legacy-token", agent_id="creator-agent")
        html_response = httpx.Response(
            200,
            text="<!doctype html><html></html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("POST", "https://example.com/api/v1/tasks"),
        )
        create_response = httpx.Response(
            201,
            json={"id": "task-123", "title": "Review the spec"},
            request=httpx.Request("POST", "https://example.com/api/tasks"),
        )
        whoami_response = httpx.Response(
            200,
            json={"bound_agent": {"default_space_id": "space-123"}},
            request=httpx.Request("GET", "https://example.com/auth/me"),
        )
        list_response = httpx.Response(
            200,
            json={"tasks": [{"id": "other-task", "space_id": "space-123"}]},
            request=httpx.Request("GET", "https://example.com/api/v1/tasks?limit=100&space_id=space-123"),
        )
        client._http.post = MagicMock(side_effect=[html_response, create_response])
        client._http.get = MagicMock(side_effect=[whoami_response, list_response])

        with pytest.raises(RuntimeError, match="not visible in requested space"):
            client.create_task("space-123", "Review the spec", priority="high")

    def test_gateway_auth_contract_task_create_exchanges_then_posts_api_tasks(self, monkeypatch):
        import httpx

        exchange_calls = []

        def fake_exchange(url, *, json=None, headers=None, timeout=None):
            exchange_calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
            return httpx.Response(
                200,
                json={
                    "access_token": "exchanged.jwt",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "tasks:read tasks:write",
                    "token_class": "agent_access",
                    "agent_id": "agent-123",
                    "agent_name": "cli-sentinel-local",
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_exchange)
        client = AxClient("https://example.com", "axp_a_AgentKey.AgentSecret", agent_name="cli-sentinel-local")
        task_response = httpx.Response(
            201,
            json={
                "id": "task-123",
                "task_display_id": "a1b2c3",
                "title": "Land gateway stub",
                "status": "not_started",
                "priority": "high",
                "posted_by": {"id": "agent-123", "type": "agent"},
                # Backend echoes space_id so the client can verify the task
                # actually landed in the requested space (acceptance criterion
                # for ax-cli-dev tasks 97e2f06c / cbb8f887 / 7fbd5d0f).
                "space_id": "space-hint",
            },
            request=httpx.Request("POST", "https://example.com/api/tasks"),
        )
        client._http.post = MagicMock(return_value=task_response)

        data = client.create_task("space-hint", "Land gateway stub", description="Contract draft", priority="high")

        assert data["id"] == "task-123"
        assert exchange_calls == [
            {
                "url": "https://example.com/auth/exchange",
                "json": {
                    "requested_token_class": "agent_access",
                    "audience": "ax-api",
                    "scope": "tasks:read tasks:write messages:read messages:write agents:read",
                    "agent_name": "cli-sentinel-local",
                },
                "headers": {
                    "Authorization": "Bearer axp_a_AgentKey.AgentSecret",
                    "Content-Type": "application/json",
                },
                "timeout": 10.0,
            }
        ]
        assert client._http.post.call_args.args[0] == "/api/tasks"
        assert client._http.post.call_args.kwargs["headers"]["Authorization"] == "Bearer exchanged.jwt"
        body = client._http.post.call_args.kwargs["json"]
        assert body == {
            "title": "Land gateway stub",
            "description": "Contract draft",
            "requirements": {
                "source": "gateway-first-cli",
                "space_id_hint": "space-hint",
                "fingerprint": client._base_headers["X-AX-FP"],
            },
            "priority": "high",
            "deadline": None,
        }
        assert "space_id" not in body
        assert "assigned_agent_id" not in body
        assert "assignee_id" not in body

    def test_gateway_auth_contract_task_create_refuses_when_response_space_mismatches(self, monkeypatch):
        """Regression for ax-cli-dev 97e2f06c / 7fbd5d0f: the auth-contract path
        used to silently land tasks in the credential's default space when it
        differed from --space-id. Verify that a mismatched response space_id
        now raises RuntimeError instead of returning a false success.
        """
        import httpx

        def fake_exchange(url, *, json=None, headers=None, timeout=None):
            return httpx.Response(
                200,
                json={
                    "access_token": "exchanged.jwt",
                    "expires_in": 3600,
                    "token_class": "agent_access",
                    "agent_id": "agent-123",
                    "agent_name": "cli-sentinel-local",
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_exchange)
        client = AxClient("https://example.com", "axp_a_AgentKey.AgentSecret", agent_name="cli-sentinel-local")
        task_response = httpx.Response(
            201,
            json={
                "id": "task-123",
                "title": "Land gateway stub",
                # Backend filed it in madtank's default workspace despite
                # space_id_hint=ax-cli-dev-space — this is the silent-misfile
                # scenario the bug reports describe.
                "space_id": "madtank-space",
            },
            request=httpx.Request("POST", "https://example.com/api/tasks"),
        )
        client._http.post = MagicMock(return_value=task_response)

        with pytest.raises(RuntimeError, match="created in the wrong space"):
            client.create_task("ax-cli-dev-space", "Land gateway stub", priority="high")

    def test_gateway_auth_contract_task_create_verifies_via_list_when_response_omits_space_id(self, monkeypatch):
        """Backend doesn't always echo space_id today; client falls back to a
        list_tasks probe in the requested space to confirm the new task is
        actually there before returning success.
        """
        import httpx

        def fake_exchange(url, *, json=None, headers=None, timeout=None):
            return httpx.Response(
                200,
                json={
                    "access_token": "exchanged.jwt",
                    "expires_in": 3600,
                    "token_class": "agent_access",
                    "agent_id": "agent-123",
                    "agent_name": "cli-sentinel-local",
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_exchange)
        client = AxClient("https://example.com", "axp_a_AgentKey.AgentSecret", agent_name="cli-sentinel-local")
        task_response = httpx.Response(
            201,
            json={"id": "task-123", "title": "Land gateway stub"},
            request=httpx.Request("POST", "https://example.com/api/tasks"),
        )
        list_response = httpx.Response(
            200,
            json={"tasks": [{"id": "task-123", "space_id": "ax-cli-dev-space"}]},
            request=httpx.Request("GET", "https://example.com/api/v1/tasks"),
        )
        client._http.post = MagicMock(return_value=task_response)
        client._http.get = MagicMock(return_value=list_response)

        data = client.create_task("ax-cli-dev-space", "Land gateway stub", priority="high")

        assert data["id"] == "task-123"
        # Verification round-trip used the requested space, not the default.
        assert client._http.get.call_args.kwargs["params"]["space_id"] == "ax-cli-dev-space"

    def test_gateway_auth_contract_task_create_refuses_when_list_misses(self, monkeypatch):
        """If the response omits space_id and the new task isn't visible in
        the requested space, surface a clear failure instead of pretending."""
        import httpx

        def fake_exchange(url, *, json=None, headers=None, timeout=None):
            return httpx.Response(
                200,
                json={
                    "access_token": "exchanged.jwt",
                    "expires_in": 3600,
                    "token_class": "agent_access",
                    "agent_id": "agent-123",
                    "agent_name": "cli-sentinel-local",
                },
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx, "post", fake_exchange)
        client = AxClient("https://example.com", "axp_a_AgentKey.AgentSecret", agent_name="cli-sentinel-local")
        task_response = httpx.Response(
            201,
            json={"id": "task-123", "title": "Land gateway stub"},
            request=httpx.Request("POST", "https://example.com/api/tasks"),
        )
        list_response = httpx.Response(
            200,
            json={"tasks": [{"id": "some-other-task", "space_id": "ax-cli-dev-space"}]},
            request=httpx.Request("GET", "https://example.com/api/v1/tasks"),
        )
        client._http.post = MagicMock(return_value=task_response)
        client._http.get = MagicMock(return_value=list_response)

        with pytest.raises(RuntimeError, match="not visible in requested space"):
            client.create_task("ax-cli-dev-space", "Land gateway stub", priority="high")

    def test_issue_agent_pat_sends_requested_audience(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        response = httpx.Response(
            201,
            json={"ok": True},
            request=httpx.Request("POST", "https://example.com/credentials/agent-pat"),
        )
        client._http.post = MagicMock(return_value=response)

        client.mgmt_issue_agent_pat("agent-123", audience="mcp")

        body = client._http.post.call_args.kwargs["json"]
        assert body["audience"] == "mcp"

    def test_issue_enrollment_sends_requested_audience(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        response = httpx.Response(
            201,
            json={"ok": True},
            request=httpx.Request("POST", "https://example.com/credentials/enrollment"),
        )
        client._http.post = MagicMock(return_value=response)

        client.mgmt_issue_enrollment(audience="both")

        body = client._http.post.call_args.kwargs["json"]
        assert body["audience"] == "both"

    def test_mgmt_create_agent_prefers_api_v1_route(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        client._http.post = MagicMock(
            return_value=self._response(
                "POST",
                "https://example.com/api/v1/agents/manage/create",
                201,
                json={"agent": {"id": "agent-123", "name": "new-agent"}},
            )
        )

        result = client.mgmt_create_agent("new-agent")

        assert result["agent"]["id"] == "agent-123"
        assert client._http.post.call_args.args[0] == "/api/v1/agents/manage/create"

    def test_mgmt_create_agent_falls_back_to_legacy_route_on_route_miss(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        client._http.post = MagicMock(
            side_effect=[
                self._response(
                    "POST",
                    "https://example.com/api/v1/agents/manage/create",
                    404,
                    json={"detail": "Not Found"},
                ),
                self._response(
                    "POST",
                    "https://example.com/agents/manage/create",
                    201,
                    json={"agent": {"id": "agent-123", "name": "new-agent"}},
                ),
            ]
        )

        result = client.mgmt_create_agent("new-agent")

        assert result["agent"]["id"] == "agent-123"
        assert [call.args[0] for call in client._http.post.call_args_list] == [
            "/api/v1/agents/manage/create",
            "/agents/manage/create",
        ]

    def test_mgmt_create_agent_falls_back_when_frontend_catches_route(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        client._http.post = MagicMock(
            side_effect=[
                self._response(
                    "POST",
                    "https://example.com/api/v1/agents/manage/create",
                    200,
                    text="<!DOCTYPE html><html></html>",
                ),
                self._response(
                    "POST",
                    "https://example.com/agents/manage/create",
                    201,
                    json={"agent": {"id": "agent-123", "name": "new-agent"}},
                ),
            ]
        )

        result = client.mgmt_create_agent("new-agent")

        assert result["agent"]["id"] == "agent-123"
        assert [call.args[0] for call in client._http.post.call_args_list] == [
            "/api/v1/agents/manage/create",
            "/agents/manage/create",
        ]

    def test_mgmt_create_agent_does_not_fallback_on_auth_failure(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        client._http.post = MagicMock(
            return_value=self._response(
                "POST",
                "https://example.com/api/v1/agents/manage/create",
                401,
                json={"detail": "Not authenticated"},
            )
        )

        with pytest.raises(httpx.HTTPStatusError):
            client.mgmt_create_agent("new-agent")

        assert client._http.post.call_count == 1

    def test_mgmt_list_agents_falls_back_to_legacy_route_on_route_miss(self):
        client = AxClient("https://example.com", "axp_u_UserKey.UserSecret")
        client._admin_headers = MagicMock(return_value={"Authorization": "Bearer admin"})
        client._http.get = MagicMock(
            side_effect=[
                self._response(
                    "GET",
                    "https://example.com/api/v1/agents/manage/list",
                    405,
                    json={"detail": "Method Not Allowed"},
                ),
                self._response(
                    "GET",
                    "https://example.com/agents/manage/list",
                    200,
                    json=[{"id": "agent-123", "name": "new-agent"}],
                ),
            ]
        )

        result = client.mgmt_list_agents()

        assert result == [{"id": "agent-123", "name": "new-agent"}]
        assert [call.args[0] for call in client._http.get.call_args_list] == [
            "/api/v1/agents/manage/list",
            "/agents/manage/list",
        ]


# ---------------------------------------------------------------------------
# _RateLimitState tests
# ---------------------------------------------------------------------------

class TestRateLimitState:
    def test_record_sets_exhausted_when_remaining_zero(self):
        state = _RateLimitState()
        state.record(remaining=0, reset_at=9999999999.0)
        assert state.exhausted is True

    def test_record_clears_exhausted_when_remaining_positive(self):
        state = _RateLimitState()
        state.record(remaining=0, reset_at=9999999999.0)
        state.record(remaining=50, reset_at=9999999999.0)
        assert state.exhausted is False

    def test_record_updates_reset_at(self):
        state = _RateLimitState()
        state.record(remaining=0, reset_at=1234567890.0)
        assert state.reset_at == 1234567890.0

    def test_wait_if_needed_no_op_when_not_exhausted(self, monkeypatch):
        import time as _time
        sleeps = []
        monkeypatch.setattr(_time, "sleep", lambda s: sleeps.append(s))
        state = _RateLimitState()
        state.record(remaining=50, reset_at=_time.time() + 30)
        state.wait_if_needed(120.0)
        assert sleeps == []

    def test_low_water_threshold_triggers_before_zero(self, monkeypatch):
        """Exhaustion fires at <= RATE_LIMIT_LOW_WATER, not just at 0."""
        import time as _time
        monkeypatch.setattr(_time, "sleep", lambda s: None)
        from ax_cli.client import RATE_LIMIT_LOW_WATER
        state = _RateLimitState()
        state.record(remaining=RATE_LIMIT_LOW_WATER, reset_at=_time.time() + 30)
        assert state.exhausted is True
        state.record(remaining=RATE_LIMIT_LOW_WATER + 1, reset_at=_time.time() + 30)
        assert state.exhausted is False

    def test_wait_if_needed_sleeps_when_exhausted(self, monkeypatch):
        import time as _time
        sleeps = []
        monkeypatch.setattr(_time, "sleep", lambda s: sleeps.append(s))
        state = _RateLimitState()
        state.record(remaining=0, reset_at=_time.time() + 30)
        state.wait_if_needed(120.0)
        assert len(sleeps) == 1
        assert sleeps[0] > 0

    def test_wait_if_needed_calls_callback(self, monkeypatch):
        import time as _time
        monkeypatch.setattr(_time, "sleep", lambda s: None)
        calls = []
        state = _RateLimitState()
        state.record(remaining=0, reset_at=_time.time() + 30)
        state.wait_if_needed(120.0, on_wait=lambda w, r: calls.append((w, r)))
        assert len(calls) == 1
        assert calls[0][0] > 0

    def test_wait_if_needed_clears_exhausted_after_wait(self, monkeypatch):
        import time as _time
        now = [_time.time()]
        monkeypatch.setattr(_time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
        monkeypatch.setattr(_time, "time", lambda: now[0])
        state = _RateLimitState()
        state.record(remaining=0, reset_at=now[0] + 30)
        state.wait_if_needed(120.0)
        assert state.exhausted is False

    def test_wait_if_needed_raises_preempted_when_wait_exceeds_max(self, monkeypatch):
        import time as _time
        sleeps = []
        monkeypatch.setattr(_time, "sleep", lambda s: sleeps.append(s))
        state = _RateLimitState()
        state.record(remaining=0, reset_at=_time.time() + 999)
        with pytest.raises(RateLimitPreemptedError) as exc_info:
            state.wait_if_needed(30.0)
        assert sleeps == []
        assert exc_info.value.retry_after_seconds > 0
        assert "try again after" in str(exc_info.value)

    def test_shared_state_coordinates_across_clients(self, monkeypatch):
        """Two _RetryOnAuthClient instances sharing state both see exhaustion."""
        import time as _time
        sleeps = []
        monkeypatch.setattr(_time, "sleep", lambda s: sleeps.append(s))

        shared = _RateLimitState()
        request = httpx.Request("GET", "https://example.com/api/v1/agents")
        ok = httpx.Response(200, headers={
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(_time.time() + 30),
        }, request=request)

        inner_a = MagicMock()
        inner_a.get.return_value = ok
        client_a = _RetryOnAuthClient(inner_a, get_fresh_jwt=None, rate_limit_state=shared)

        inner_b = MagicMock()
        inner_b.get.return_value = ok
        client_b = _RetryOnAuthClient(inner_b, get_fresh_jwt=None, rate_limit_state=shared)

        client_a.get("/api/v1/agents")   # records exhaustion on shared state
        client_b.get("/api/v1/agents")   # should sleep before making its request
        assert len(sleeps) == 1          # exactly one sleep from client_b's proactive wait

    def test_wait_if_needed_does_not_clear_exhausted_if_record_fires_during_sleep(self, monkeypatch):
        """If record() sets a new low-water window during the sleep, the post-sleep
        clear must not overwrite it back to False."""
        import time as _time
        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)
            # Simulate a concurrent record() arriving while we were sleeping
            state.record(remaining=0, reset_at=_time.time() + 60)

        monkeypatch.setattr(_time, "sleep", fake_sleep)
        state = _RateLimitState()
        state.record(remaining=0, reset_at=_time.time() + 0.1)  # just expired
        state.wait_if_needed(120.0)
        assert state.exhausted is True  # new window set during sleep must survive

    def test_missing_rate_limit_headers_do_not_update_state(self):
        """Responses without x-ratelimit-remaining must not touch _RateLimitState."""
        import time as _time
        state = _RateLimitState()
        state.record(remaining=50, reset_at=_time.time() + 30)

        request = httpx.Request("GET", "https://example.com/api/v1/agents")
        # Response with no rate-limit headers at all (e.g. CDN, health-check endpoint)
        no_headers = httpx.Response(200, request=request)

        inner = MagicMock()
        inner.get.return_value = no_headers
        client = _RetryOnAuthClient(inner, get_fresh_jwt=None, rate_limit_state=state)
        client.get("/api/v1/agents")

        assert state.remaining == 50  # unchanged
        assert state.exhausted is False

    def test_exhausted_without_reset_header_uses_current_time(self):
        """When remaining hits low-water but reset header is absent, reset_at is set to
        now so wait_if_needed sleeps at most 0.5s instead of waiting on a stale window."""
        import time as _time
        state = _RateLimitState()
        stale_reset = _time.time() + 9999  # far future — a leftover from a previous window
        state.record(remaining=50, reset_at=stale_reset)

        # Now record exhaustion with no reset header
        before = _time.time()
        state.record(remaining=0, reset_at=0.0)
        after = _time.time()

        assert state.exhausted is True
        assert before <= state.reset_at <= after + 1  # reset_at ≈ now, not the stale future

    def test_missing_rate_limit_headers_pass_none_to_callback(self):
        """on_request_complete receives remaining=None when headers are absent."""
        calls = []
        request = httpx.Request("GET", "https://example.com/api/v1/agents")
        no_headers = httpx.Response(200, request=request)

        inner = MagicMock()
        inner.get.return_value = no_headers
        client = _RetryOnAuthClient(
            inner,
            get_fresh_jwt=None,
            on_request_complete=lambda method, path, status, remaining, reset_at, ct="": calls.append(remaining),
        )
        client.get("/api/v1/agents")
        assert calls == [None]
