import json

from typer.testing import CliRunner

from ax_cli.commands import qa
from ax_cli.main import app

runner = CliRunner()


class FakeClient:
    def __init__(self):
        self.calls = []

    def whoami(self):
        self.calls.append(("whoami",))
        return {
            "username": "madtank",
            "principal_type": "user",
            "bound_agent": None,
        }

    def list_spaces(self):
        self.calls.append(("list_spaces",))
        return {"spaces": [{"id": "space-1", "name": "Team Hub"}]}

    def get_space(self, space_id):
        self.calls.append(("get_space", space_id))
        return {"id": space_id, "name": "Team Hub"}

    def list_space_members(self, space_id):
        self.calls.append(("list_space_members", space_id))
        return {"members": [{"username": "madtank"}]}

    def list_agents(self, *, space_id=None, limit=None):
        self.calls.append(("list_agents", space_id, limit))
        return {"agents": [{"id": "agent-1", "name": "aX"}], "total": 1}

    def list_tasks(self, limit=20, *, space_id=None, agent_id=None):
        self.calls.append(("list_tasks", limit, space_id, agent_id))
        return {"tasks": [{"id": "task-1", "title": "Fix it"}], "total": 1}

    def list_context(self, prefix=None, *, space_id=None):
        self.calls.append(("list_context", prefix, space_id))
        return {"items": [{"key": "ctx"}], "count": 1}

    def list_messages(self, limit=20, channel="main", *, space_id=None, agent_id=None):
        self.calls.append(("list_messages", limit, channel, space_id, agent_id))
        return {"messages": [{"id": "msg-1", "content": "hello"}], "count": 1}

    def set_context(self, space_id, key, value, *, ttl=None):
        self.calls.append(("set_context", space_id, key, value, ttl))
        return {"ok": True, "key": key}

    def get_context(self, key, *, space_id=None):
        self.calls.append(("get_context", key, space_id))
        return {"key": key, "value": "stored"}

    def delete_context(self, key, *, space_id=None):
        self.calls.append(("delete_context", key, space_id))
        return 204

    def upload_file(self, path, *, space_id=None):
        self.calls.append(("upload_file", path, space_id))
        return {
            "attachment_id": "att-1",
            "url": "/api/v1/uploads/files/probe.md",
            "content_type": "text/markdown",
            "size": 12,
            "original_filename": "probe.md",
        }

    def send_message(self, space_id, content, *, attachments=None, **kwargs):
        self.calls.append(("send_message", space_id, content, attachments, kwargs))
        return {"id": "msg-upload"}


def _json_output(result):
    return json.loads(result.output)


def test_contract_smoke_read_only_passes_explicit_space_to_api_reads(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(qa, "get_client", lambda: fake)
    monkeypatch.setattr(qa, "resolve_space_id", lambda client, explicit=None: explicit or "space-1")

    result = runner.invoke(app, ["qa", "contracts", "--json"])

    assert result.exit_code == 0, result.output
    payload = _json_output(result)
    assert payload["ok"] is True
    assert payload["mode"] == "read_only"
    assert payload["space_id"] == "space-1"
    assert ("list_agents", "space-1", 10) in fake.calls
    assert ("list_tasks", 10, "space-1", None) in fake.calls
    assert ("list_context", None, "space-1") in fake.calls
    assert ("list_messages", 10, "main", "space-1", None) in fake.calls


def test_contract_smoke_env_uses_named_user_login_space(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(
        qa,
        "_client_for_env",
        lambda env_name: (
            fake,
            {
                "environment": env_name,
                "space_id": "dev-space",
            },
        ),
    )
    monkeypatch.setattr(
        qa,
        "resolve_space_id",
        lambda client, explicit=None: (_ for _ in ()).throw(AssertionError("space should come from env config")),
    )

    result = runner.invoke(app, ["qa", "contracts", "--env", "dev", "--json"])

    assert result.exit_code == 0, result.output
    payload = _json_output(result)
    assert payload["ok"] is True
    assert payload["environment"] == "dev"
    assert payload["space_id"] == "dev-space"
    assert ("list_agents", "dev-space", 10) in fake.calls
    assert ("list_tasks", 10, "dev-space", None) in fake.calls


def test_contract_smoke_env_requires_space_when_named_login_is_ambiguous(monkeypatch):
    fake = FakeClient()
    fake.list_spaces = lambda: {
        "spaces": [
            {"id": "space-1", "name": "One"},
            {"id": "space-2", "name": "Two"},
        ]
    }
    monkeypatch.setattr(qa, "_client_for_env", lambda env_name: (fake, {"environment": env_name}))
    monkeypatch.setattr(
        qa,
        "resolve_space_id",
        lambda client, explicit=None: (_ for _ in ()).throw(AssertionError("must not use runtime config fallback")),
    )

    result = runner.invoke(app, ["qa", "contracts", "--env", "dev", "--json"])

    assert result.exit_code == 1
    assert "No default space is configured for env 'dev'" in result.output


def test_contract_smoke_write_roundtrip_sets_gets_and_deletes_context(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(qa, "get_client", lambda: fake)
    monkeypatch.setattr(qa, "resolve_space_id", lambda client, explicit=None: "space-1")

    result = runner.invoke(app, ["qa", "contracts", "--write", "--json"])

    assert result.exit_code == 0, result.output
    payload = _json_output(result)
    assert payload["ok"] is True
    assert payload["artifacts"]["context_key"].startswith("qa:")
    assert [call[0] for call in fake.calls].count("set_context") == 1
    assert [call[0] for call in fake.calls].count("get_context") == 1
    assert [call[0] for call in fake.calls].count("delete_context") == 1


def test_contract_smoke_upload_can_emit_context_backed_message(monkeypatch, tmp_path):
    sample = tmp_path / "probe.md"
    sample.write_text("# Probe\n")
    fake = FakeClient()
    monkeypatch.setattr(qa, "get_client", lambda: fake)
    monkeypatch.setattr(qa, "resolve_space_id", lambda client, explicit=None: "space-1")

    result = runner.invoke(
        app,
        [
            "qa",
            "contracts",
            "--write",
            "--upload-file",
            str(sample),
            "--send-message",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = _json_output(result)
    assert payload["ok"] is True
    assert payload["artifacts"]["attachment_id"] == "att-1"
    assert payload["artifacts"]["message_id"] == "msg-upload"
    send_call = next(call for call in fake.calls if call[0] == "send_message")
    attachment = send_call[3][0]
    assert attachment["context_key"] == payload["artifacts"]["upload_context_key"]
    assert attachment["filename"] == "probe.md"


def test_preflight_writes_ci_artifact(monkeypatch, tmp_path):
    fake = FakeClient()
    artifact = tmp_path / "preflight.json"
    monkeypatch.setattr(
        qa,
        "_client_for_env",
        lambda env_name: (
            fake,
            {
                "environment": env_name,
                "space_id": "dev-space",
            },
        ),
    )

    result = runner.invoke(
        app,
        [
            "qa",
            "preflight",
            "--env",
            "dev",
            "--for",
            "playwright",
            "--artifact",
            str(artifact),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = _json_output(result)
    saved = json.loads(artifact.read_text())
    assert payload["ok"] is True
    assert payload["preflight"]["target"] == "playwright"
    assert payload["preflight"]["artifact"] == str(artifact.resolve())
    assert saved == payload


def test_matrix_runs_doctor_and_preflight_for_each_env_and_writes_artifacts(monkeypatch, tmp_path):
    doctor_calls = []
    preflight_calls = []

    def fake_doctor(*, env_name, explicit_space_id):
        doctor_calls.append((env_name, explicit_space_id))
        return {
            "ok": True,
            "selected_env": env_name,
            "effective": {
                "principal_intent": "user",
                "auth_source": f"user_login:{env_name}",
                "base_url": f"https://{env_name}.paxai.app",
                "host": f"{env_name}.paxai.app",
                "space_id": explicit_space_id,
            },
            "warnings": [],
            "problems": [],
        }

    def fake_preflight(**kwargs):
        preflight_calls.append(kwargs)
        env_name = kwargs["env_name"]
        return {
            "ok": True,
            "environment": env_name,
            "space_id": kwargs["space_id"],
            "preflight": {
                "target": kwargs["target"],
                "passed": True,
            },
            "checks": [
                {"name": "auth.whoami", "ok": True},
                {"name": "tasks.list", "ok": True, "count": 3},
            ],
        }

    monkeypatch.setattr(qa, "diagnose_auth_config", fake_doctor)
    monkeypatch.setattr(qa, "_preflight_result", fake_preflight)

    result = runner.invoke(
        app,
        [
            "qa",
            "matrix",
            "--env",
            "dev",
            "--env",
            "next",
            "--space",
            "dev=space-dev",
            "--space",
            "next=space-next",
            "--for",
            "playwright",
            "--artifact-dir",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = _json_output(result)
    assert payload["ok"] is True
    assert payload["target"] == "playwright"
    assert [row["env"] for row in payload["envs"]] == ["dev", "next"]
    assert doctor_calls == [("dev", "space-dev"), ("next", "space-next")]
    assert [call["space_id"] for call in preflight_calls] == ["space-dev", "space-next"]
    assert (tmp_path / "dev-preflight.json").exists()
    assert (tmp_path / "next-preflight.json").exists()
    assert (tmp_path / "matrix.json").exists()
