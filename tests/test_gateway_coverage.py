"""Supplementary coverage tests for ax_cli/gateway.py and ax_cli/commands/gateway.py.

Focuses on pure helper functions, error handling branches, and configuration
parsing functions that are uncovered in the main test_gateway_commands.py file.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ax_cli import gateway as gw
from ax_cli.commands import gateway as gw_cmd

# ---------------------------------------------------------------------------
# Helper: _normalized_controlled and friends (lines 275-336)
# ---------------------------------------------------------------------------


class TestNormalizedControlled:
    """Validate the controlled-vocabulary normalizer used across operator/asset profiles."""

    def test_exact_match_returned_as_is(self):
        assert gw._normalized_controlled("hosted", gw._CONTROLLED_PLACEMENTS, fallback="mailbox") == "hosted"

    def test_case_insensitive_match(self):
        assert gw._normalized_controlled("HOSTED", gw._CONTROLLED_PLACEMENTS, fallback="mailbox") == "hosted"

    def test_unknown_value_returns_fallback(self):
        assert gw._normalized_controlled("bogus", gw._CONTROLLED_PLACEMENTS, fallback="mailbox") == "mailbox"

    def test_none_value_returns_fallback(self):
        assert gw._normalized_controlled(None, gw._CONTROLLED_PLACEMENTS, fallback="mailbox") == "mailbox"

    def test_empty_string_returns_fallback(self):
        assert gw._normalized_controlled("", gw._CONTROLLED_PLACEMENTS, fallback="mailbox") == "mailbox"


class TestNormalizedControlledList:
    """Validate list-valued controlled-vocabulary normalizer."""

    def test_comma_separated_string_parsed(self):
        result = gw._normalized_controlled_list(
            "direct_message,mailbox_poll",
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message", "mailbox_poll"]

    def test_single_string_treated_as_one_element(self):
        result = gw._normalized_controlled_list(
            "direct_message",
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message"]

    def test_list_input_normalized(self):
        result = gw._normalized_controlled_list(
            ["direct_message", "MAILBOX_POLL"],
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message", "mailbox_poll"]

    def test_empty_string_returns_fallback(self):
        result = gw._normalized_controlled_list(
            "",
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["manual_trigger"]

    def test_none_returns_fallback(self):
        result = gw._normalized_controlled_list(
            None,
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["manual_trigger"]

    def test_deduplicates_entries(self):
        result = gw._normalized_controlled_list(
            "direct_message,direct_message,mailbox_poll",
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message", "mailbox_poll"]

    def test_invalid_items_filtered_out(self):
        result = gw._normalized_controlled_list(
            "direct_message,bogus_source",
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message"]

    def test_all_invalid_returns_fallback(self):
        result = gw._normalized_controlled_list(
            "bogus1,bogus2",
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["manual_trigger"]

    def test_tuple_input(self):
        result = gw._normalized_controlled_list(
            ("direct_message", "mailbox_poll"),
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message", "mailbox_poll"]

    def test_set_input(self):
        result = gw._normalized_controlled_list(
            {"direct_message"},
            gw._CONTROLLED_TRIGGER_SOURCES,
            fallback=["manual_trigger"],
        )
        assert result == ["direct_message"]


class TestNormalizedOptionalControlled:
    def test_exact_match(self):
        assert gw._normalized_optional_controlled("verified", gw._CONTROLLED_ATTESTATION_STATES) == "verified"

    def test_case_insensitive(self):
        assert gw._normalized_optional_controlled("VERIFIED", gw._CONTROLLED_ATTESTATION_STATES) == "verified"

    def test_empty_returns_none(self):
        assert gw._normalized_optional_controlled("", gw._CONTROLLED_ATTESTATION_STATES) is None

    def test_none_returns_none(self):
        assert gw._normalized_optional_controlled(None, gw._CONTROLLED_ATTESTATION_STATES) is None

    def test_unknown_returns_none(self):
        assert gw._normalized_optional_controlled("bogus", gw._CONTROLLED_ATTESTATION_STATES) is None


class TestNormalizedStringList:
    def test_comma_separated(self):
        assert gw._normalized_string_list("a,b,c", fallback=["x"]) == ["a", "b", "c"]

    def test_list_input(self):
        assert gw._normalized_string_list(["a", "b"], fallback=["x"]) == ["a", "b"]

    def test_empty_string_returns_fallback(self):
        assert gw._normalized_string_list("", fallback=["x"]) == ["x"]

    def test_empty_list_returns_fallback(self):
        assert gw._normalized_string_list([], fallback=["x"]) == ["x"]

    def test_none_returns_fallback(self):
        assert gw._normalized_string_list(None, fallback=["x"]) == ["x"]

    def test_tuple_input(self):
        assert gw._normalized_string_list(("a", "b"), fallback=["x"]) == ["a", "b"]

    def test_integer_returns_fallback(self):
        assert gw._normalized_string_list(42, fallback=["x"]) == ["x"]


class TestBoolWithFallback:
    def test_true_bool(self):
        assert gw._bool_with_fallback(True, fallback=False) is True

    def test_false_bool(self):
        assert gw._bool_with_fallback(False, fallback=True) is False

    def test_truthy_strings(self):
        for value in ("true", "1", "yes", "y", "on", "TRUE", "Yes"):
            assert gw._bool_with_fallback(value, fallback=False) is True

    def test_falsy_strings(self):
        for value in ("false", "0", "no", "n", "off", "FALSE", "No"):
            assert gw._bool_with_fallback(value, fallback=True) is False

    def test_unknown_string_returns_fallback(self):
        assert gw._bool_with_fallback("maybe", fallback=True) is True

    def test_none_returns_fallback(self):
        assert gw._bool_with_fallback(None, fallback=True) is True

    def test_integer_returns_fallback(self):
        assert gw._bool_with_fallback(42, fallback=False) is False


# ---------------------------------------------------------------------------
# Override fields (lines 338-355)
# ---------------------------------------------------------------------------


class TestOverrideFields:
    def test_nested_dict(self):
        snapshot = {"user_overrides": {"operator": {"placement": "mailbox", "activation": "on_demand"}}}
        result = gw._override_fields(snapshot, domain="operator")
        assert result == {"placement", "activation"}

    def test_nested_list(self):
        snapshot = {"user_overrides": {"operator": ["placement", "activation"]}}
        result = gw._override_fields(snapshot, domain="operator")
        assert result == {"placement", "activation"}

    def test_direct_key(self):
        snapshot = {"operator_overrides": {"placement": "mailbox"}}
        result = gw._override_fields(snapshot, domain="operator")
        assert result == {"placement"}

    def test_direct_list(self):
        snapshot = {"operator_overrides": ["placement"]}
        result = gw._override_fields(snapshot, domain="operator")
        assert result == {"placement"}

    def test_combined_nested_and_direct(self):
        snapshot = {
            "user_overrides": {"asset": {"intake_model": "live_listener"}},
            "asset_overrides": {"asset_class": "background_worker"},
        }
        result = gw._override_fields(snapshot, domain="asset")
        assert result == {"intake_model", "asset_class"}

    def test_missing_domain(self):
        snapshot = {"user_overrides": {"operator": {"placement": "x"}}}
        result = gw._override_fields(snapshot, domain="asset")
        assert result == set()


# ---------------------------------------------------------------------------
# _is_system_agent (lines 459-472)
# ---------------------------------------------------------------------------


class TestIsSystemAgent:
    def test_service_account_template(self):
        assert gw._is_system_agent({"template_id": "service_account"}) is True

    def test_inbox_template(self):
        assert gw._is_system_agent({"template_id": "inbox"}) is True

    def test_switchboard_prefix(self):
        assert gw._is_system_agent({"name": "switchboard-main"}) is True

    def test_regular_agent(self):
        assert gw._is_system_agent({"name": "echo-bot", "template_id": "echo_test"}) is False

    def test_empty_entry(self):
        assert gw._is_system_agent({}) is False


# ---------------------------------------------------------------------------
# _hide_after_stale_seconds (lines 475-492)
# ---------------------------------------------------------------------------


class TestHideAfterStaleSeconds:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("AX_GATEWAY_HIDE_AFTER_STALE_SECONDS", "120")
        assert gw._hide_after_stale_seconds() == 120.0

    def test_invalid_env_uses_default(self, monkeypatch):
        monkeypatch.setenv("AX_GATEWAY_HIDE_AFTER_STALE_SECONDS", "not_a_number")
        assert gw._hide_after_stale_seconds() == gw.RUNTIME_HIDDEN_AFTER_SECONDS

    def test_registry_override(self, monkeypatch):
        monkeypatch.delenv("AX_GATEWAY_HIDE_AFTER_STALE_SECONDS", raising=False)
        registry = {"gateway": {"hide_after_stale_seconds": 300}}
        assert gw._hide_after_stale_seconds(registry) == 300.0

    def test_registry_invalid_value(self, monkeypatch):
        monkeypatch.delenv("AX_GATEWAY_HIDE_AFTER_STALE_SECONDS", raising=False)
        registry = {"gateway": {"hide_after_stale_seconds": "bad"}}
        assert gw._hide_after_stale_seconds(registry) == gw.RUNTIME_HIDDEN_AFTER_SECONDS

    def test_default_when_no_override(self, monkeypatch):
        monkeypatch.delenv("AX_GATEWAY_HIDE_AFTER_STALE_SECONDS", raising=False)
        assert gw._hide_after_stale_seconds() == gw.RUNTIME_HIDDEN_AFTER_SECONDS

    def test_env_takes_priority_over_registry(self, monkeypatch):
        monkeypatch.setenv("AX_GATEWAY_HIDE_AFTER_STALE_SECONDS", "60")
        registry = {"gateway": {"hide_after_stale_seconds": 300}}
        assert gw._hide_after_stale_seconds(registry) == 60.0


# ---------------------------------------------------------------------------
# _asset_type_label and _output_label (lines 662-697)
# ---------------------------------------------------------------------------


class TestAssetTypeLabel:
    def test_interactive_live_listener(self):
        assert gw._asset_type_label(asset_class="interactive_agent", intake_model="live_listener") == "Live Listener"

    def test_interactive_launch_on_send(self):
        assert gw._asset_type_label(asset_class="interactive_agent", intake_model="launch_on_send") == "On-Demand Agent"

    def test_interactive_polling_mailbox(self):
        assert (
            gw._asset_type_label(asset_class="interactive_agent", intake_model="polling_mailbox")
            == "Pass-through Agent"
        )

    def test_background_queue_accept(self):
        assert gw._asset_type_label(asset_class="background_worker", intake_model="queue_accept") == "Inbox Worker"

    def test_background_queue_drain_worker_model(self):
        assert (
            gw._asset_type_label(asset_class="background_worker", intake_model="other", worker_model="queue_drain")
            == "Inbox Worker"
        )

    def test_background_worker_generic(self):
        assert gw._asset_type_label(asset_class="background_worker", intake_model="other") == "Background Worker"

    def test_scheduled_job(self):
        assert gw._asset_type_label(asset_class="scheduled_job", intake_model="any") == "Scheduled Job"

    def test_alert_listener(self):
        assert gw._asset_type_label(asset_class="alert_listener", intake_model="any") == "Alert Listener"

    def test_service_account(self):
        assert gw._asset_type_label(asset_class="service_account", intake_model="any") == "Service Account"

    def test_service_proxy(self):
        assert gw._asset_type_label(asset_class="service_proxy", intake_model="any") == "Service / Tool Proxy"

    def test_unknown_fallback(self):
        assert gw._asset_type_label(asset_class="unknown_class", intake_model="any") == "Connected Asset"


class TestOutputLabel:
    def test_all_known_paths(self):
        expected = {
            "inline_reply": "Reply",
            "manual_reply": "Manual Reply",
            "sender_inbox": "Inbox",
            "summary_post": "Summary",
            "task_update": "Task",
            "event_log": "Event Log",
            "outbound_message": "Message",
            "silent": "Silent",
        }
        for path, label in expected.items():
            assert gw._output_label([path]) == label

    def test_empty_list_defaults_to_reply(self):
        assert gw._output_label([]) == "Reply"

    def test_unknown_path_defaults_to_reply(self):
        assert gw._output_label(["unknown_path"]) == "Reply"


# ---------------------------------------------------------------------------
# phase_for_event (lines 264-272)
# ---------------------------------------------------------------------------


class TestPhaseForEvent:
    def test_known_events(self):
        assert gw.phase_for_event("message_received") == "received"
        assert gw.phase_for_event("delivered_to_inbox") == "delivered"
        assert gw.phase_for_event("message_claimed") == "claimed"
        assert gw.phase_for_event("runtime_activity") == "working"
        assert gw.phase_for_event("tool_started") == "tool"
        assert gw.phase_for_event("reply_sent") == "reply"
        assert gw.phase_for_event("runtime_error") == "result"

    def test_unknown_event_returns_none(self):
        assert gw.phase_for_event("totally_unknown") is None

    def test_empty_returns_none(self):
        assert gw.phase_for_event("") is None

    def test_none_returns_none(self):
        assert gw.phase_for_event(None) is None


# ---------------------------------------------------------------------------
# _template_operator_defaults (lines 357-456)
# ---------------------------------------------------------------------------


class TestTemplateOperatorDefaults:
    def test_echo_test_template(self):
        result = gw._template_operator_defaults("echo_test", None)
        assert result["placement"] == "hosted"
        assert result["activation"] == "persistent"
        assert result["reply_mode"] == "interactive"
        assert result["telemetry_level"] == "basic"

    def test_pass_through_template(self):
        result = gw._template_operator_defaults("pass_through", None)
        assert result["placement"] == "mailbox"
        assert result["reply_mode"] == "background"

    def test_claude_code_channel_template(self):
        result = gw._template_operator_defaults("claude_code_channel", None)
        assert result["placement"] == "attached"
        assert result["activation"] == "attach_only"

    def test_runtime_type_fallback(self):
        result = gw._template_operator_defaults(None, "echo")
        assert result["placement"] == "hosted"

    def test_unknown_falls_to_exec_defaults(self):
        result = gw._template_operator_defaults("unknown_template", "unknown_runtime")
        assert result["placement"] == "hosted"
        assert result["activation"] == "persistent"

    def test_hermes_template(self):
        result = gw._template_operator_defaults("hermes", None)
        assert result["telemetry_level"] == "rich"

    def test_service_account_template(self):
        result = gw._template_operator_defaults("service_account", None)
        assert result["placement"] == "mailbox"
        assert result["reply_mode"] == "silent"

    def test_case_insensitive_template(self):
        result = gw._template_operator_defaults("Echo_Test", None)
        assert result["placement"] == "hosted"


# ---------------------------------------------------------------------------
# _template_asset_defaults (lines 495-659)
# ---------------------------------------------------------------------------


class TestTemplateAssetDefaults:
    def test_echo_test_template_defaults(self):
        result = gw._template_asset_defaults("echo_test", None)
        assert result["asset_class"] == "interactive_agent"
        assert result["intake_model"] == "live_listener"
        assert result["addressable"] is True

    def test_service_account_template(self):
        result = gw._template_asset_defaults("service_account", None)
        assert result["asset_class"] == "service_account"
        assert result["schedulable"] is True
        assert result["externally_triggered"] is True

    def test_pass_through_template(self):
        result = gw._template_asset_defaults("pass_through", None)
        assert result["worker_model"] == "agent_check_in"
        assert "requires-approval" in result["constraints"]

    def test_unknown_falls_to_exec_default(self):
        result = gw._template_asset_defaults("unknown", "unknown")
        assert result["asset_class"] == "interactive_agent"
        assert result["intake_model"] == "live_listener"

    def test_runtime_type_used_when_no_template(self):
        result = gw._template_asset_defaults(None, "inbox")
        assert result["asset_class"] == "background_worker"
        assert result["worker_model"] == "queue_drain"


# ---------------------------------------------------------------------------
# _looks_like_setup_error (lines 1027-1036)
# ---------------------------------------------------------------------------


class TestLooksLikeSetupError:
    def test_error_state(self):
        assert gw._looks_like_setup_error({}, "error") is True

    def test_repo_not_found_in_error(self):
        assert gw._looks_like_setup_error({"last_error": "Repo not found at /tmp/x"}, "running") is True

    def test_repo_not_found_in_preview(self):
        assert gw._looks_like_setup_error({"last_reply_preview": "Repo not found"}, "running") is True

    def test_stderr_in_preview(self):
        assert gw._looks_like_setup_error({"last_reply_preview": "(stderr: something failed)"}, "running") is True

    def test_stderr_in_error(self):
        assert gw._looks_like_setup_error({"last_error": "stderr: crash"}, "running") is True

    def test_normal_running(self):
        assert gw._looks_like_setup_error({}, "running") is False


# ---------------------------------------------------------------------------
# _derive_liveness (lines 1039-1048)
# ---------------------------------------------------------------------------


class TestDeriveLiveness:
    def test_setup_error(self):
        assert gw._derive_liveness({"last_error": "stderr: crash"}, raw_state="error", last_seen_age=None) == (
            "setup_error",
            False,
        )

    def test_running_connected(self):
        assert gw._derive_liveness({}, raw_state="running", last_seen_age=10) == ("connected", True)

    def test_running_stale(self):
        assert gw._derive_liveness({}, raw_state="running", last_seen_age=9999) == ("stale", False)

    def test_running_no_age(self):
        assert gw._derive_liveness({}, raw_state="running", last_seen_age=None) == ("stale", False)

    def test_starting(self):
        assert gw._derive_liveness({}, raw_state="starting", last_seen_age=None) == ("stale", False)

    def test_reconnecting(self):
        assert gw._derive_liveness({}, raw_state="reconnecting", last_seen_age=None) == ("stale", False)

    def test_stopped(self):
        assert gw._derive_liveness({}, raw_state="stopped", last_seen_age=None) == ("offline", False)


# ---------------------------------------------------------------------------
# _derive_mode, _derive_presence, _derive_reply (lines 1151-1180)
# ---------------------------------------------------------------------------


class TestDeriveMode:
    def test_mailbox(self):
        assert gw._derive_mode({"placement": "mailbox", "activation": "queue_worker"}) == "INBOX"

    def test_persistent(self):
        assert gw._derive_mode({"placement": "hosted", "activation": "persistent"}) == "LIVE"

    def test_attach_only(self):
        assert gw._derive_mode({"placement": "attached", "activation": "attach_only"}) == "LIVE"

    def test_on_demand(self):
        assert gw._derive_mode({"placement": "hosted", "activation": "on_demand"}) == "ON-DEMAND"


class TestDerivePresence:
    def test_setup_error(self):
        assert gw._derive_presence(mode="LIVE", liveness="setup_error", work_state="idle") == "ERROR"

    def test_blocked(self):
        assert gw._derive_presence(mode="LIVE", liveness="connected", work_state="blocked") == "BLOCKED"

    def test_stale(self):
        assert gw._derive_presence(mode="LIVE", liveness="stale", work_state="idle") == "STALE"

    def test_offline_live(self):
        assert gw._derive_presence(mode="LIVE", liveness="offline", work_state="idle") == "OFFLINE"

    def test_working(self):
        assert gw._derive_presence(mode="LIVE", liveness="connected", work_state="working") == "WORKING"

    def test_queued(self):
        assert gw._derive_presence(mode="INBOX", liveness="connected", work_state="queued") == "QUEUED"

    def test_idle(self):
        assert gw._derive_presence(mode="LIVE", liveness="connected", work_state="idle") == "IDLE"


class TestDeriveReply:
    def test_interactive(self):
        assert gw._derive_reply("interactive") == "REPLY"

    def test_silent(self):
        assert gw._derive_reply("silent") == "SILENT"

    def test_summary(self):
        assert gw._derive_reply("summary_only") == "SUMMARY"

    def test_background(self):
        assert gw._derive_reply("background") == "SUMMARY"


# ---------------------------------------------------------------------------
# _derive_reachability (lines 1183-1211)
# ---------------------------------------------------------------------------


class TestDeriveReachability:
    def test_setup_error(self):
        result = gw._derive_reachability(snapshot={}, mode="LIVE", liveness="setup_error", activation="persistent")
        assert result == "unavailable"

    def test_blocked_attestation(self):
        result = gw._derive_reachability(
            snapshot={"attestation_state": "drifted"}, mode="LIVE", liveness="connected", activation="persistent"
        )
        assert result == "unavailable"

    def test_blocked_approval(self):
        result = gw._derive_reachability(
            snapshot={"approval_state": "pending"}, mode="LIVE", liveness="connected", activation="persistent"
        )
        assert result == "unavailable"

    def test_blocked_identity(self):
        result = gw._derive_reachability(
            snapshot={"identity_status": "unknown_identity"}, mode="LIVE", liveness="connected", activation="persistent"
        )
        assert result == "unavailable"

    def test_blocked_environment(self):
        result = gw._derive_reachability(
            snapshot={"environment_status": "environment_mismatch"},
            mode="LIVE",
            liveness="connected",
            activation="persistent",
        )
        assert result == "unavailable"

    def test_blocked_space(self):
        result = gw._derive_reachability(
            snapshot={"space_status": "active_not_allowed"}, mode="LIVE", liveness="connected", activation="persistent"
        )
        assert result == "unavailable"

    def test_inbox_queue_available(self):
        result = gw._derive_reachability(snapshot={}, mode="INBOX", liveness="connected", activation="queue_worker")
        assert result == "queue_available"

    def test_attach_only_stale(self):
        result = gw._derive_reachability(snapshot={}, mode="LIVE", liveness="stale", activation="attach_only")
        assert result == "attach_required"

    def test_live_connected(self):
        result = gw._derive_reachability(snapshot={}, mode="LIVE", liveness="connected", activation="persistent")
        assert result == "live_now"

    def test_on_demand_launch(self):
        result = gw._derive_reachability(snapshot={}, mode="ON-DEMAND", liveness="offline", activation="on_demand")
        assert result == "launch_available"


# ---------------------------------------------------------------------------
# _derive_work_state (lines 1103-1133)
# ---------------------------------------------------------------------------


class TestDeriveWorkState:
    def test_setup_error_is_blocked(self):
        assert gw._derive_work_state({}, liveness="setup_error") == "blocked"

    def test_drifted_attestation_blocked(self):
        assert gw._derive_work_state({"attestation_state": "drifted"}, liveness="connected") == "blocked"

    def test_pending_approval_blocked(self):
        assert gw._derive_work_state({"approval_state": "pending"}, liveness="connected") == "blocked"

    def test_identity_blocked(self):
        assert gw._derive_work_state({"identity_status": "unknown_identity"}, liveness="connected") == "blocked"

    def test_environment_blocked(self):
        assert gw._derive_work_state({"environment_status": "environment_mismatch"}, liveness="connected") == "blocked"

    def test_space_blocked(self):
        assert gw._derive_work_state({"space_status": "active_not_allowed"}, liveness="connected") == "blocked"

    def test_working_status(self):
        assert gw._derive_work_state({"current_status": "processing"}, liveness="connected") == "working"

    def test_queued_mailbox(self):
        result = gw._derive_work_state(
            {"current_status": "queued"},
            liveness="connected",
            profile={"placement": "mailbox"},
        )
        assert result == "queued"

    def test_queued_non_mailbox_stays_idle(self):
        result = gw._derive_work_state(
            {"current_status": "queued"},
            liveness="connected",
            profile={"placement": "hosted"},
        )
        assert result == "idle"

    def test_backlog_triggers_queued(self):
        result = gw._derive_work_state(
            {"backlog_depth": 5},
            liveness="connected",
            profile={"placement": "mailbox"},
        )
        assert result == "queued"

    def test_rate_limited_blocked(self):
        assert gw._derive_work_state({"current_status": "rate_limited"}, liveness="connected") == "blocked"

    def test_idle_default(self):
        assert gw._derive_work_state({}, liveness="connected") == "idle"


# ---------------------------------------------------------------------------
# _doctor_has_failed / _doctor_summary (lines 1136-1242)
# ---------------------------------------------------------------------------


class TestDoctorHasFailed:
    def test_no_result(self):
        assert gw._doctor_has_failed({}) is False

    def test_non_dict_result(self):
        assert gw._doctor_has_failed({"last_doctor_result": "ok"}) is False

    def test_failed_status(self):
        assert gw._doctor_has_failed({"last_doctor_result": {"status": "failed"}}) is True

    def test_error_status(self):
        assert gw._doctor_has_failed({"last_doctor_result": {"status": "error"}}) is True

    def test_passed_status(self):
        assert gw._doctor_has_failed({"last_doctor_result": {"status": "passed"}}) is False

    def test_failed_check_in_list(self):
        result = {"checks": [{"name": "connectivity", "status": "failed"}]}
        assert gw._doctor_has_failed({"last_doctor_result": result}) is True

    def test_all_checks_passed(self):
        result = {"checks": [{"name": "connectivity", "status": "passed"}]}
        assert gw._doctor_has_failed({"last_doctor_result": result}) is False


class TestDoctorSummary:
    def test_no_result(self):
        assert gw._doctor_summary({}) == ""

    def test_summary_present(self):
        assert gw._doctor_summary({"last_doctor_result": {"summary": "All good"}}) == "All good"

    def test_failed_checks(self):
        result = {"checks": [{"name": "connectivity", "status": "failed"}, {"name": "auth", "status": "passed"}]}
        assert "connectivity" in gw._doctor_summary({"last_doctor_result": result})


# ---------------------------------------------------------------------------
# _derive_confidence (lines 1245-1329) — partial coverage of the branches
# ---------------------------------------------------------------------------


class TestDeriveConfidence:
    def test_setup_error(self):
        confidence, reason, detail = gw._derive_confidence(
            {"last_error": "Crash"}, mode="LIVE", liveness="setup_error", reachability="unavailable"
        )
        assert confidence == "BLOCKED"
        assert reason == "setup_blocked"

    def test_identity_unbound(self):
        confidence, reason, _ = gw._derive_confidence(
            {"identity_status": "unknown_identity"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "identity_unbound"

    def test_credential_mismatch(self):
        confidence, reason, _ = gw._derive_confidence(
            {"identity_status": "credential_mismatch"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "identity_mismatch"

    def test_bootstrap_only(self):
        confidence, reason, _ = gw._derive_confidence(
            {"identity_status": "bootstrap_only"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "bootstrap_only"

    def test_environment_mismatch(self):
        confidence, reason, _ = gw._derive_confidence(
            {"environment_status": "environment_mismatch"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "environment_mismatch"

    def test_environment_blocked(self):
        confidence, reason, _ = gw._derive_confidence(
            {"environment_status": "environment_blocked"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "environment_mismatch"

    def test_space_not_allowed(self):
        confidence, reason, _ = gw._derive_confidence(
            {"space_status": "active_not_allowed"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "active_space_not_allowed"

    def test_no_active_space(self):
        confidence, reason, _ = gw._derive_confidence(
            {"space_status": "no_active_space"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"
        assert reason == "no_active_space"

    def test_space_unknown(self):
        confidence, reason, _ = gw._derive_confidence(
            {"space_status": "unknown"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "LOW"
        assert reason == "space_unknown"

    def test_approval_rejected(self):
        confidence, reason, _ = gw._derive_confidence(
            {"approval_state": "rejected"}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "BLOCKED"

    def test_doctor_failed(self):
        confidence, reason, _ = gw._derive_confidence(
            {"last_doctor_result": {"status": "failed"}}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "LOW"
        assert reason == "recent_test_failed"

    def test_low_completion_rate(self):
        confidence, reason, _ = gw._derive_confidence(
            {"completion_rate": 0.3}, mode="LIVE", liveness="connected", reachability="live_now"
        )
        assert confidence == "LOW"
        assert reason == "completion_degraded"

    def test_inbox_queue_available(self):
        confidence, reason, _ = gw._derive_confidence(
            {}, mode="INBOX", liveness="connected", reachability="queue_available"
        )
        assert confidence == "HIGH"
        assert reason == "queue_available"

    def test_on_demand_launch_available(self):
        confidence, reason, _ = gw._derive_confidence(
            {}, mode="ON-DEMAND", liveness="offline", reachability="launch_available"
        )
        assert confidence == "MEDIUM"
        assert reason == "launch_available"

    def test_live_connected(self):
        confidence, reason, _ = gw._derive_confidence({}, mode="LIVE", liveness="connected", reachability="live_now")
        assert confidence == "HIGH"
        assert reason == "live_now"

    def test_attach_required(self):
        confidence, reason, _ = gw._derive_confidence({}, mode="LIVE", liveness="stale", reachability="attach_required")
        assert confidence == "LOW"
        assert reason == "attach_required"


# ---------------------------------------------------------------------------
# _parse_iso8601 and _age_seconds (lines 2629-2646)
# ---------------------------------------------------------------------------


class TestParseIso8601:
    def test_valid_iso_with_tz(self):
        result = gw._parse_iso8601("2026-05-08T12:00:00+00:00")
        assert result is not None
        assert result.year == 2026

    def test_valid_iso_with_z(self):
        result = gw._parse_iso8601("2026-05-08T12:00:00Z")
        assert result is not None

    def test_invalid_string(self):
        assert gw._parse_iso8601("not-a-date") is None

    def test_empty_string(self):
        assert gw._parse_iso8601("") is None

    def test_none(self):
        assert gw._parse_iso8601(None) is None

    def test_non_string(self):
        assert gw._parse_iso8601(12345) is None


class TestAgeSeconds:
    def test_recent_timestamp(self):
        now = datetime.now(timezone.utc)
        past = (now - timedelta(seconds=30)).isoformat()
        result = gw._age_seconds(past, now=now)
        assert result is not None
        assert 29 <= result <= 31

    def test_future_timestamp_returns_zero(self):
        now = datetime.now(timezone.utc)
        future = (now + timedelta(seconds=60)).isoformat()
        result = gw._age_seconds(future, now=now)
        assert result == 0

    def test_none_returns_none(self):
        assert gw._age_seconds(None) is None

    def test_invalid_returns_none(self):
        assert gw._age_seconds("not-a-date") is None


# ---------------------------------------------------------------------------
# _b64url_encode / _b64url_decode (lines 1336-1342)
# ---------------------------------------------------------------------------


class TestB64UrlEncoding:
    def test_roundtrip(self):
        original = b"hello world! This is a test."
        encoded = gw._b64url_encode(original)
        decoded = gw._b64url_decode(encoded)
        assert decoded == original

    def test_no_padding_in_encoded(self):
        encoded = gw._b64url_encode(b"test")
        assert "=" not in encoded


# ---------------------------------------------------------------------------
# _payload_hash / _file_sha256 / _host_fingerprint (lines 1460-1475)
# ---------------------------------------------------------------------------


class TestPayloadHash:
    def test_deterministic(self):
        payload = {"a": 1, "b": 2}
        assert gw._payload_hash(payload) == gw._payload_hash(payload)

    def test_key_order_independent(self):
        assert gw._payload_hash({"a": 1, "b": 2}) == gw._payload_hash({"b": 2, "a": 1})

    def test_starts_with_sha256(self):
        assert gw._payload_hash({"x": "y"}).startswith("sha256:")


class TestFileSha256:
    def test_basic_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = gw._file_sha256(f)
        assert result.startswith("sha256:")
        assert len(result) > 10


class TestHostFingerprint:
    def test_returns_host_prefixed_string(self):
        result = gw._host_fingerprint()
        assert result.startswith("host:")


class TestSafeFileSha256:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        assert gw._safe_file_sha256(f) is not None

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.txt"
        assert gw._safe_file_sha256(f) is None

    def test_none_input(self):
        assert gw._safe_file_sha256(None) is None


# ---------------------------------------------------------------------------
# _without_none (line 1489)
# ---------------------------------------------------------------------------


class TestWithoutNone:
    def test_removes_none_and_empty(self):
        result = gw._without_none({"a": 1, "b": None, "c": "", "d": "ok"})
        assert result == {"a": 1, "d": "ok"}

    def test_preserves_false_and_zero(self):
        result = gw._without_none({"a": False, "b": 0, "c": None})
        assert result == {"a": False, "b": 0}


# ---------------------------------------------------------------------------
# _command_executable_path (lines 1493-1510)
# ---------------------------------------------------------------------------


class TestCommandExecutablePath:
    def test_empty_returns_none(self):
        assert gw._command_executable_path("") is None

    def test_none_returns_none(self):
        assert gw._command_executable_path(None) is None

    def test_simple_command(self):
        result = gw._command_executable_path("python3 script.py")
        # Should return something (may or may not resolve depending on environment)
        assert result is not None

    def test_env_prefix_skipped(self):
        result = gw._command_executable_path("env FOO=bar python3 script.py")
        assert result is not None

    def test_invalid_shell_syntax_returns_none(self):
        # Unterminated quotes cause shlex.split to raise ValueError
        assert gw._command_executable_path("python3 'unclosed") is None


# ---------------------------------------------------------------------------
# _environment_label_for_base_url (lines 1550-1562)
# ---------------------------------------------------------------------------


class TestEnvironmentLabelForBaseUrl:
    def test_prod(self):
        assert gw._environment_label_for_base_url("https://paxai.app") == "prod"

    def test_dev(self):
        assert gw._environment_label_for_base_url("https://dev.paxai.app") == "dev"

    def test_localhost(self):
        assert gw._environment_label_for_base_url("http://localhost:8000") == "local"

    def test_127001(self):
        assert gw._environment_label_for_base_url("http://127.0.0.1:8765") == "local"

    def test_custom_host(self):
        assert gw._environment_label_for_base_url("https://custom.example.com") == "custom.example.com"

    def test_empty(self):
        assert gw._environment_label_for_base_url("") == "unknown"

    def test_none(self):
        assert gw._environment_label_for_base_url(None) == "unknown"


# ---------------------------------------------------------------------------
# _redacted_path (lines 1565-1578)
# ---------------------------------------------------------------------------


class TestRedactedPath:
    def test_home_relative_path(self):
        home = str(Path.home())
        result = gw._redacted_path(f"{home}/projects/test")
        assert result is not None
        assert result.startswith("~")

    def test_absolute_non_home(self):
        result = gw._redacted_path("/tmp/some/file")
        assert result is not None
        assert result.startswith("/")

    def test_empty_returns_none(self):
        assert gw._redacted_path("") is None

    def test_none_returns_none(self):
        assert gw._redacted_path(None) is None


# ---------------------------------------------------------------------------
# _normalized_base_url (line 1546)
# ---------------------------------------------------------------------------


class TestNormalizedBaseUrl:
    def test_strips_trailing_slash(self):
        assert gw._normalized_base_url("https://paxai.app/") == "https://paxai.app"

    def test_strips_whitespace(self):
        assert gw._normalized_base_url("  https://paxai.app  ") == "https://paxai.app"

    def test_none_returns_empty(self):
        assert gw._normalized_base_url(None) == ""


# ---------------------------------------------------------------------------
# _space_cache_rows (lines 1581-1599)
# ---------------------------------------------------------------------------


class TestSpaceCacheRows:
    def test_valid_rows(self):
        rows = gw._space_cache_rows(
            [
                {"space_id": "s1", "name": "Space 1", "is_default": True},
                {"space_id": "s2", "name": "Space 2"},
            ]
        )
        assert len(rows) == 2
        assert rows[0]["space_id"] == "s1"
        assert rows[0]["is_default"] is True
        assert rows[1]["is_default"] is False

    def test_deduplicates(self):
        rows = gw._space_cache_rows(
            [
                {"space_id": "s1", "name": "Space 1"},
                {"space_id": "s1", "name": "Duplicate"},
            ]
        )
        assert len(rows) == 1

    def test_skips_empty_ids(self):
        rows = gw._space_cache_rows([{"name": "No ID"}, {"space_id": "", "name": "Empty ID"}])
        assert len(rows) == 0

    def test_non_list_returns_empty(self):
        assert gw._space_cache_rows("not a list") == []
        assert gw._space_cache_rows(None) == []

    def test_id_field_accepted(self):
        rows = gw._space_cache_rows([{"id": "s1", "name": "Space 1"}])
        assert len(rows) == 1
        assert rows[0]["space_id"] == "s1"


# ---------------------------------------------------------------------------
# _space_name_from_cache (lines 1605-1614)
# ---------------------------------------------------------------------------


class TestSpaceNameFromCache:
    def test_found(self):
        spaces = [{"space_id": "s1", "name": "My Space"}]
        assert gw._space_name_from_cache(spaces, "s1") == "My Space"

    def test_not_found(self):
        spaces = [{"space_id": "s1", "name": "My Space"}]
        assert gw._space_name_from_cache(spaces, "s2") is None

    def test_empty_space_id(self):
        assert gw._space_name_from_cache([], None) is None
        assert gw._space_name_from_cache([], "") is None


# ---------------------------------------------------------------------------
# _space_id_allowed (lines 1705-1708)
# ---------------------------------------------------------------------------


class TestSpaceIdAllowed:
    def test_allowed(self):
        spaces = [{"space_id": "s1"}, {"space_id": "s2"}]
        assert gw._space_id_allowed(spaces, "s1") is True

    def test_not_allowed(self):
        spaces = [{"space_id": "s1"}]
        assert gw._space_id_allowed(spaces, "s2") is False

    def test_empty_id(self):
        assert gw._space_id_allowed([{"space_id": "s1"}], None) is False
        assert gw._space_id_allowed([{"space_id": "s1"}], "") is False


# ---------------------------------------------------------------------------
# _ollama_model_rows and _recommended_ollama_model (lines 884-937)
# ---------------------------------------------------------------------------


class TestOllamaModelRows:
    def test_basic_model(self):
        payload = {
            "models": [
                {
                    "name": "llama3:latest",
                    "details": {"family": "llama", "families": ["llama"], "parameter_size": "8.0B"},
                    "modified_at": "2026-05-01T00:00:00Z",
                }
            ]
        }
        rows = gw._ollama_model_rows(payload)
        assert len(rows) == 1
        assert rows[0]["name"] == "llama3:latest"
        assert rows[0]["family"] == "llama"
        assert rows[0]["is_cloud"] is False
        assert rows[0]["is_embedding"] is False

    def test_embedding_model_detected(self):
        payload = {"models": [{"name": "nomic-embed-text", "details": {"family": "nomic"}}]}
        rows = gw._ollama_model_rows(payload)
        assert rows[0]["is_embedding"] is True

    def test_bert_family_is_embedding(self):
        payload = {"models": [{"name": "bert-model", "details": {"families": ["bert-like"]}}]}
        rows = gw._ollama_model_rows(payload)
        assert rows[0]["is_embedding"] is True

    def test_cloud_model_detected(self):
        payload = {"models": [{"name": "gpt4:cloud", "remote_host": "api.openai.com"}]}
        rows = gw._ollama_model_rows(payload)
        assert rows[0]["is_cloud"] is True

    def test_cloud_suffix(self):
        payload = {"models": [{"name": "gpt4:cloud"}]}
        rows = gw._ollama_model_rows(payload)
        assert rows[0]["is_cloud"] is True

    def test_empty_models_list(self):
        assert gw._ollama_model_rows({"models": []}) == []

    def test_no_models_key(self):
        assert gw._ollama_model_rows({}) == []

    def test_non_list_models(self):
        assert gw._ollama_model_rows({"models": "not a list"}) == []

    def test_skips_entries_without_name(self):
        payload = {"models": [{"details": {"family": "llama"}}]}
        assert gw._ollama_model_rows(payload) == []


class TestRecommendedOllamaModel:
    def test_empty_rows(self):
        assert gw._recommended_ollama_model([]) is None

    def test_prefers_local_chat_models(self):
        rows = [
            {"name": "llama3:latest", "is_cloud": False, "is_embedding": False, "modified_at": "2026-05-01"},
            {"name": "embed-model", "is_cloud": False, "is_embedding": True, "modified_at": "2026-05-01"},
        ]
        assert gw._recommended_ollama_model(rows) == "llama3:latest"

    def test_falls_to_cloud_if_no_local(self):
        rows = [
            {"name": "cloud-model:cloud", "is_cloud": True, "is_embedding": False, "modified_at": "2026-05-01"},
        ]
        assert gw._recommended_ollama_model(rows) == "cloud-model:cloud"


# ---------------------------------------------------------------------------
# _binding_type_for_entry (lines 1430-1436)
# ---------------------------------------------------------------------------


class TestBindingTypeForEntry:
    def test_attach_only(self):
        assert gw._binding_type_for_entry({"activation": "attach_only"}) == "attached_session"

    def test_queue_worker(self):
        assert gw._binding_type_for_entry({"activation": "queue_worker"}) == "queue_worker"

    def test_inbox_runtime_type(self):
        assert gw._binding_type_for_entry({"runtime_type": "inbox"}) == "queue_worker"

    def test_default_local_runtime(self):
        assert gw._binding_type_for_entry({"activation": "persistent"}) == "local_runtime"


# ---------------------------------------------------------------------------
# _asset_id_for_entry (line 1426)
# ---------------------------------------------------------------------------


class TestAssetIdForEntry:
    def test_agent_id(self):
        assert gw._asset_id_for_entry({"agent_id": "a1"}) == "a1"

    def test_asset_id(self):
        assert gw._asset_id_for_entry({"asset_id": "x1"}) == "x1"

    def test_name_fallback(self):
        assert gw._asset_id_for_entry({"name": "my-agent"}) == "my-agent"

    def test_empty(self):
        assert gw._asset_id_for_entry({}) == ""


# ---------------------------------------------------------------------------
# find_agent_entry_by_ref (lines 3845-3875)
# ---------------------------------------------------------------------------


class TestFindAgentEntryByRef:
    def test_by_name(self):
        registry = {"agents": [{"name": "echo-bot"}, {"name": "hermes"}]}
        assert gw.find_agent_entry_by_ref(registry, "echo-bot")["name"] == "echo-bot"

    def test_by_index(self):
        registry = {"agents": [{"name": "first"}, {"name": "second"}]}
        assert gw.find_agent_entry_by_ref(registry, "#2")["name"] == "second"

    def test_by_index_without_hash(self):
        registry = {"agents": [{"name": "first"}, {"name": "second"}]}
        assert gw.find_agent_entry_by_ref(registry, "1")["name"] == "first"

    def test_by_exact_install_id(self):
        registry = {"agents": [{"name": "a", "install_id": "abc-123-xyz"}]}
        assert gw.find_agent_entry_by_ref(registry, "abc-123-xyz")["name"] == "a"

    def test_by_prefix_match(self):
        registry = {"agents": [{"name": "a", "install_id": "abcdef-123456-unique"}]}
        assert gw.find_agent_entry_by_ref(registry, "abcdef")["name"] == "a"

    def test_ambiguous_prefix_returns_none(self):
        registry = {
            "agents": [
                {"name": "a", "install_id": "abcdef-1"},
                {"name": "b", "install_id": "abcdef-2"},
            ]
        }
        assert gw.find_agent_entry_by_ref(registry, "abcdef") is None

    def test_empty_ref(self):
        assert gw.find_agent_entry_by_ref({"agents": [{"name": "a"}]}, "") is None

    def test_none_ref(self):
        assert gw.find_agent_entry_by_ref({"agents": [{"name": "a"}]}, None) is None

    def test_out_of_range_index(self):
        registry = {"agents": [{"name": "only"}]}
        assert gw.find_agent_entry_by_ref(registry, "#5") is None


# ---------------------------------------------------------------------------
# upsert_agent_entry (lines 3878-3887)
# ---------------------------------------------------------------------------


class TestUpsertAgentEntry:
    def test_insert_new(self):
        registry = {"agents": []}
        result = gw.upsert_agent_entry(registry, {"name": "new-agent", "runtime_type": "echo"})
        assert result["name"] == "new-agent"
        assert len(registry["agents"]) == 1

    def test_update_existing(self):
        registry = {"agents": [{"name": "echo-bot", "runtime_type": "echo"}]}
        result = gw.upsert_agent_entry(registry, {"name": "echo-bot", "runtime_type": "hermes"})
        assert result["runtime_type"] == "hermes"
        assert len(registry["agents"]) == 1

    def test_case_insensitive_match(self):
        registry = {"agents": [{"name": "Echo-Bot", "runtime_type": "echo"}]}
        result = gw.upsert_agent_entry(registry, {"name": "echo-bot", "runtime_type": "hermes"})
        assert result["runtime_type"] == "hermes"
        assert len(registry["agents"]) == 1


# ---------------------------------------------------------------------------
# _pid_is_alive (lines 1074-1090)
# ---------------------------------------------------------------------------


class TestPidIsAlive:
    def test_zero_pid(self):
        assert gw._pid_is_alive(0) is False

    def test_none_pid(self):
        assert gw._pid_is_alive(None) is False

    def test_negative_pid(self):
        assert gw._pid_is_alive(-1) is False

    def test_non_numeric(self):
        assert gw._pid_is_alive("abc") is False

    def test_current_pid_is_alive(self):
        assert gw._pid_is_alive(os.getpid()) is True


# ---------------------------------------------------------------------------
# _external_runtime_connected / _external_runtime_expected (lines 1051-1071)
# ---------------------------------------------------------------------------


class TestExternalRuntimeConnected:
    def test_connected_recent(self):
        assert gw._external_runtime_connected({"external_runtime_state": "connected"}, last_seen_age=10) is True

    def test_connected_stale(self):
        assert gw._external_runtime_connected({"external_runtime_state": "connected"}, last_seen_age=9999) is False

    def test_unknown_state(self):
        assert gw._external_runtime_connected({"external_runtime_state": "unknown"}, last_seen_age=10) is False

    def test_no_age(self):
        assert gw._external_runtime_connected({"external_runtime_state": "connected"}, last_seen_age=None) is False


class TestExternalRuntimeExpected:
    def test_external_managed(self):
        assert gw._external_runtime_expected({"external_runtime_managed": True}) is True

    def test_external_kind(self):
        assert gw._external_runtime_expected({"external_runtime_kind": "hermes"}) is True

    def test_external_instance_id(self):
        assert gw._external_runtime_expected({"external_runtime_instance_id": "inst-1"}) is True

    def test_empty(self):
        assert gw._external_runtime_expected({}) is False


# ---------------------------------------------------------------------------
# _attached_session_log_is_ready (lines 1093-1100)
# ---------------------------------------------------------------------------


class TestAttachedSessionLogIsReady:
    def test_no_path(self):
        assert gw._attached_session_log_is_ready(None) is False
        assert gw._attached_session_log_is_ready("") is False

    def test_nonexistent_path(self):
        assert gw._attached_session_log_is_ready("/tmp/nonexistent_log_12345.txt") is False

    def test_with_listening_marker(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("Starting up\nListening for channel messages\nReady")
        assert gw._attached_session_log_is_ready(str(log)) is True

    def test_with_ax_channel_marker(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("Starting up\nConnected to ax-channel\nReady")
        assert gw._attached_session_log_is_ready(str(log)) is True

    def test_without_marker(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("Starting up\nLoading model\n")
        assert gw._attached_session_log_is_ready(str(log)) is False


# ---------------------------------------------------------------------------
# _sentinel_tool_summary (lines 4703-4726)
# ---------------------------------------------------------------------------


class TestSentinelToolSummary:
    def test_read_file(self):
        assert "Reading" in gw._sentinel_tool_summary("read", {"file_path": "/tmp/test.py"})

    def test_write_file(self):
        assert "Writing" in gw._sentinel_tool_summary("write", {"file_path": "/tmp/out.py"})

    def test_edit_file(self):
        assert "Editing" in gw._sentinel_tool_summary("edit", {"file_path": "/tmp/fix.py"})

    def test_bash(self):
        assert "Running" in gw._sentinel_tool_summary("bash", {"command": "ls -la"})

    def test_grep(self):
        assert "Searching" in gw._sentinel_tool_summary("grep", {"pattern": "TODO"})

    def test_glob(self):
        assert "Finding" in gw._sentinel_tool_summary("glob", {"pattern": "*.py"})

    def test_unknown_tool(self):
        assert "Using my_tool" in gw._sentinel_tool_summary("my_tool", {})

    def test_read_no_path(self):
        assert "Reading file" in gw._sentinel_tool_summary("read", {})

    def test_bash_no_command(self):
        assert "Running command" in gw._sentinel_tool_summary("bash", {})


# ---------------------------------------------------------------------------
# _summarize_sentinel_command (lines 4683-4700)
# ---------------------------------------------------------------------------


class TestSummarizeSentinelCommand:
    def test_apply_patch(self):
        assert "Applying patch" in gw._summarize_sentinel_command("apply_patch file.diff")

    def test_grep_command(self):
        assert "Searching" in gw._summarize_sentinel_command("rg pattern src/")

    def test_cat_command(self):
        assert "Reading" in gw._summarize_sentinel_command("cat /tmp/file.txt")

    def test_pytest_command(self):
        assert "Running tests" in gw._summarize_sentinel_command("pytest tests/")

    def test_uv_run(self):
        assert "Running tests" in gw._summarize_sentinel_command("uv run pytest")

    def test_generic_command(self):
        result = gw._summarize_sentinel_command("echo hello")
        assert "Running:" in result

    def test_long_command_truncated(self):
        long_cmd = "echo " + "a" * 200
        result = gw._summarize_sentinel_command(long_cmd)
        assert result.endswith("...")


# ---------------------------------------------------------------------------
# _sentinel_runtime_name / _sentinel_session_scope / _sentinel_session_key
# (lines 4586-4614)
# ---------------------------------------------------------------------------


class TestSentinelRuntimeName:
    def test_default_claude(self):
        assert gw._sentinel_runtime_name({}) == "claude"

    def test_codex_cli_runtime_type(self):
        assert gw._sentinel_runtime_name({"runtime_type": "codex_cli"}) == "codex"

    def test_configured_codex(self):
        assert gw._sentinel_runtime_name({"sentinel_runtime": "codex_cli"}) == "codex"

    def test_configured_claude(self):
        assert gw._sentinel_runtime_name({"sentinel_runtime": "claude_cli"}) == "claude"


class TestSentinelSessionScope:
    def test_default_agent(self):
        assert gw._sentinel_session_scope({}) == "agent"

    def test_thread_scope(self):
        assert gw._sentinel_session_scope({"sentinel_session_scope": "thread"}) == "thread"

    def test_message_scope(self):
        assert gw._sentinel_session_scope({"session_scope": "message"}) == "message"

    def test_invalid_scope_defaults_to_agent(self):
        assert gw._sentinel_session_scope({"sentinel_session_scope": "invalid"}) == "agent"


class TestSentinelSessionKey:
    def test_agent_scope(self):
        entry = {"space_id": "s1", "name": "bot"}
        key = gw._sentinel_session_key(entry, None, "msg-1")
        assert "s1" in key and "bot" in key

    def test_message_scope(self):
        entry = {"sentinel_session_scope": "message"}
        key = gw._sentinel_session_key(entry, None, "msg-42")
        assert key == "msg-42"

    def test_thread_scope_with_parent(self):
        entry = {"sentinel_session_scope": "thread"}
        data = {"parent_id": "thread-1"}
        key = gw._sentinel_session_key(entry, data, "msg-42")
        assert key == "thread-1"

    def test_thread_scope_no_parent(self):
        entry = {"sentinel_session_scope": "thread"}
        key = gw._sentinel_session_key(entry, {}, "msg-42")
        assert key == "msg-42"


# ---------------------------------------------------------------------------
# _sentinel_model (lines 4617-4623)
# ---------------------------------------------------------------------------


class TestSentinelModel:
    def test_model_field(self):
        assert gw._sentinel_model({"model": "gpt-4"}, "claude") == "gpt-4"

    def test_runtime_specific_field(self):
        assert gw._sentinel_model({"claude_model": "claude-3"}, "claude") == "claude-3"

    def test_none_when_unset(self):
        assert gw._sentinel_model({}, "claude") is None


# ---------------------------------------------------------------------------
# _compose_agent_system_prompt (lines 4198-4211)
# ---------------------------------------------------------------------------


class TestComposeAgentSystemPrompt:
    def test_with_operator_prompt(self):
        entry = {"system_prompt": "You are a helpful bot.", "name": "test", "base_url": "https://paxai.app"}
        result = gw._compose_agent_system_prompt(entry)
        assert "You are a helpful bot" in result
        assert "aX environment context" in result

    def test_skip_environment(self):
        entry = {
            "system_prompt": "Just the prompt.",
            "system_prompt_skip_environment": "true",
        }
        result = gw._compose_agent_system_prompt(entry)
        assert result == "Just the prompt."
        assert "aX environment context" not in result

    def test_no_prompt_still_has_environment(self):
        entry = {"name": "test"}
        result = gw._compose_agent_system_prompt(entry)
        assert result is not None
        assert "aX environment context" in result


# ---------------------------------------------------------------------------
# _hermes_sentinel_model (lines 4142-4147)
# ---------------------------------------------------------------------------


class TestHermesSentinelModel:
    def test_hermes_model_field(self):
        assert gw._hermes_sentinel_model({"hermes_model": "codex:gpt-4"}) == "codex:gpt-4"

    def test_sentinel_model_field(self):
        assert gw._hermes_sentinel_model({"sentinel_model": "my-model"}) == "my-model"

    def test_runtime_model(self):
        assert gw._hermes_sentinel_model({"runtime_model": "rt-model"}) == "rt-model"

    def test_default_from_env(self, monkeypatch):
        monkeypatch.delenv("AX_GATEWAY_HERMES_MODEL", raising=False)
        result = gw._hermes_sentinel_model({})
        assert result  # returns either env var or default


# ---------------------------------------------------------------------------
# _hermes_plugin_workdir and _hermes_plugin_home (lines 4315-4330)
# ---------------------------------------------------------------------------


class TestHermesPluginWorkdir:
    def test_explicit_workdir(self):
        result = gw._hermes_plugin_workdir({"workdir": "/custom/path"})
        assert str(result) == "/custom/path"

    def test_default_workdir(self):
        result = gw._hermes_plugin_workdir({"name": "test-agent"})
        assert "test-agent" in str(result)


class TestHermesPluginHome:
    def test_explicit_home(self):
        result = gw._hermes_plugin_home({"hermes_home": "/custom/hermes"})
        assert str(result) == "/custom/hermes"

    def test_default_under_workdir(self):
        result = gw._hermes_plugin_home({"workdir": "/agent/work"})
        assert str(result) == "/agent/work/.hermes"


# ---------------------------------------------------------------------------
# _approval_status (line 2155)
# ---------------------------------------------------------------------------


class TestApprovalStatus:
    def test_denied_maps_to_rejected(self):
        assert gw._approval_status({"status": "denied"}) == "rejected"

    def test_approved(self):
        assert gw._approval_status({"status": "approved"}) == "approved"

    def test_pending(self):
        assert gw._approval_status({"status": "pending"}) == "pending"

    def test_empty(self):
        assert gw._approval_status({}) == ""


# ---------------------------------------------------------------------------
# GatewayRuntimeTimeoutError
# ---------------------------------------------------------------------------


class TestGatewayRuntimeTimeoutError:
    def test_basic(self):
        exc = gw.GatewayRuntimeTimeoutError(30)
        assert exc.timeout_seconds == 30
        assert "30s" in str(exc)

    def test_with_runtime_type(self):
        exc = gw.GatewayRuntimeTimeoutError(60, runtime_type="hermes")
        assert exc.runtime_type == "hermes"
        assert "hermes" in str(exc)
        assert "60s" in str(exc)


# ---------------------------------------------------------------------------
# _normalize_allowed_spaces_payload (lines 1870-1878)
# ---------------------------------------------------------------------------


class TestNormalizeAllowedSpacesPayload:
    def test_dict_with_spaces_key(self):
        rows = gw._normalize_allowed_spaces_payload({"spaces": [{"space_id": "s1", "name": "S1"}]})
        assert len(rows) == 1
        assert rows[0]["space_id"] == "s1"

    def test_dict_with_items_key(self):
        rows = gw._normalize_allowed_spaces_payload({"items": [{"space_id": "s2", "name": "S2"}]})
        assert len(rows) == 1

    def test_dict_with_results_key(self):
        rows = gw._normalize_allowed_spaces_payload({"results": [{"space_id": "s3", "name": "S3"}]})
        assert len(rows) == 1

    def test_list_input(self):
        rows = gw._normalize_allowed_spaces_payload([{"space_id": "s4", "name": "S4"}])
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# _entry_requires_operator_approval (line 2434)
# ---------------------------------------------------------------------------


class TestEntryRequiresOperatorApproval:
    def test_pass_through_requires(self):
        assert gw._entry_requires_operator_approval({"template_id": "pass_through"}) is True

    def test_explicit_flag(self):
        assert gw._entry_requires_operator_approval({"requires_approval": True}) is True

    def test_echo_does_not_require(self):
        assert gw._entry_requires_operator_approval({"template_id": "echo_test"}) is False


# ---------------------------------------------------------------------------
# find_binding / upsert_binding (lines 1754-1789)
# ---------------------------------------------------------------------------


class TestFindBinding:
    def test_by_asset_id(self):
        registry = {"bindings": [{"asset_id": "a1", "install_id": "i1"}]}
        assert gw.find_binding(registry, asset_id="a1")["install_id"] == "i1"

    def test_by_install_id(self):
        registry = {"bindings": [{"asset_id": "a1", "install_id": "i1"}]}
        assert gw.find_binding(registry, install_id="i1")["asset_id"] == "a1"

    def test_not_found(self):
        registry = {"bindings": [{"asset_id": "a1", "install_id": "i1"}]}
        assert gw.find_binding(registry, asset_id="a2") is None

    def test_multi_filter(self):
        registry = {
            "bindings": [
                {"asset_id": "a1", "install_id": "i1", "gateway_id": "g1"},
                {"asset_id": "a1", "install_id": "i2", "gateway_id": "g2"},
            ]
        }
        result = gw.find_binding(registry, asset_id="a1", gateway_id="g2")
        assert result["install_id"] == "i2"


class TestUpsertBinding:
    def test_insert(self):
        registry = {"bindings": []}
        result = gw.upsert_binding(registry, {"install_id": "i1", "asset_id": "a1"})
        assert len(registry["bindings"]) == 1
        assert result["asset_id"] == "a1"

    def test_update_existing(self):
        registry = {"bindings": [{"install_id": "i1", "asset_id": "a1", "path": "/old"}]}
        result = gw.upsert_binding(registry, {"install_id": "i1", "asset_id": "a1", "path": "/new"})
        assert len(registry["bindings"]) == 1
        assert result["path"] == "/new"


# ---------------------------------------------------------------------------
# _is_passive_runtime (used in commands/gateway.py imports)
# ---------------------------------------------------------------------------


class TestIsPassiveRuntime:
    def test_inbox_runtime(self):
        assert gw._is_passive_runtime("inbox") is True

    def test_passive_runtime(self):
        assert gw._is_passive_runtime("passive") is True

    def test_monitor_runtime(self):
        assert gw._is_passive_runtime("monitor") is True

    def test_echo_not_passive(self):
        assert gw._is_passive_runtime("echo") is False

    def test_empty(self):
        assert gw._is_passive_runtime("") is False

    def test_none(self):
        assert gw._is_passive_runtime(None) is False


# ---------------------------------------------------------------------------
# commands/gateway.py helpers
# ---------------------------------------------------------------------------


class TestRegistryRefForAgent:
    def test_by_name(self):
        registry = {"agents": [{"name": "a"}, {"name": "b"}]}
        ref = gw_cmd._registry_ref_for_agent(registry, {"name": "b"})
        assert ref == "#2"

    def test_by_install_id(self):
        registry = {"agents": [{"name": "a", "install_id": "id1"}]}
        ref = gw_cmd._registry_ref_for_agent(registry, {"name": "other", "install_id": "id1"})
        assert ref == "#1"

    def test_not_found(self):
        registry = {"agents": [{"name": "a"}]}
        ref = gw_cmd._registry_ref_for_agent(registry, {"name": "z"})
        assert ref is None


class TestWithRegistryRefs:
    def test_adds_ref_and_index(self):
        install_id = "abc12345-6789-0000-1111-222233334444"
        registry = {"agents": [{"name": "echo-bot", "install_id": install_id}]}
        result = gw_cmd._with_registry_refs(registry, {"name": "echo-bot", "install_id": install_id})
        assert result["registry_ref"] == "#1"
        assert result["registry_index"] == 1
        assert result["registry_code"] == install_id[:8]


class TestLocalProcessFingerprint:
    def test_returns_expected_keys(self, monkeypatch):
        monkeypatch.setattr(gw, "_file_sha256", lambda p: "sha256:abc")
        fp = gw_cmd._local_process_fingerprint(agent_name="test-agent")
        assert fp["agent_name"] == "test-agent"
        assert "pid" in fp
        assert "cwd" in fp
        assert "exe_path" in fp
        assert "user" in fp
        assert "platform" in fp


class TestLocalTrustSignature:
    def test_deterministic(self):
        fp = {"exe_path": "/usr/bin/python3", "cwd": "/home/user", "user": "testuser"}
        sig1 = gw_cmd._local_trust_signature("agent", fp)
        sig2 = gw_cmd._local_trust_signature("agent", fp)
        assert sig1 == sig2
        assert sig1.startswith("sha256:")


class TestLocalOriginSignature:
    def test_excludes_agent_name(self):
        fp = {"exe_path": "/usr/bin/python3", "cwd": "/home/user", "user": "testuser"}
        sig1 = gw_cmd._local_origin_signature(fp)
        assert sig1.startswith("sha256:")


# ---------------------------------------------------------------------------
# commands/gateway.py: UpstreamRateLimitedError (lines 211-232)
# ---------------------------------------------------------------------------


class TestUpstreamRateLimitedError:
    def test_basic(self):
        import httpx

        request = httpx.Request("GET", "https://paxai.app/api/v1/spaces")
        response = httpx.Response(429, request=request, headers={"retry-after": "30"})
        exc = httpx.HTTPStatusError("429", request=request, response=response)
        rate_err = gw_cmd.UpstreamRateLimitedError(exc, retries_attempted=3)
        assert rate_err.retries_attempted == 3
        assert rate_err.retry_after_seconds == 30
        assert "3 retries" in str(rate_err)

    def test_no_retry_after_header(self):
        import httpx

        request = httpx.Request("GET", "https://paxai.app")
        response = httpx.Response(429, request=request)
        exc = httpx.HTTPStatusError("429", request=request, response=response)
        rate_err = gw_cmd.UpstreamRateLimitedError(exc, retries_attempted=2)
        assert rate_err.retry_after_seconds is None


# ---------------------------------------------------------------------------
# commands/gateway.py: _load_gateway_session_or_exit
# ---------------------------------------------------------------------------


class TestLoadGatewaySessionOrExit:
    def test_exits_when_no_session(self, monkeypatch, tmp_path):
        import typer

        config_dir = tmp_path / "config"
        monkeypatch.setenv("AX_CONFIG_DIR", str(config_dir))
        with pytest.raises(typer.Exit):
            gw_cmd._load_gateway_session_or_exit()

    def test_returns_session_when_exists(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "config"
        monkeypatch.setenv("AX_CONFIG_DIR", str(config_dir))
        gw.save_gateway_session({"token": "axp_u_test", "base_url": "https://paxai.app"})
        session = gw_cmd._load_gateway_session_or_exit()
        assert session["token"] == "axp_u_test"


# ---------------------------------------------------------------------------
# commands/gateway.py: _load_gateway_user_client
# ---------------------------------------------------------------------------


class TestLoadGatewayUserClient:
    def test_no_session_exits(self, monkeypatch, tmp_path):
        import typer

        monkeypatch.setenv("AX_CONFIG_DIR", str(tmp_path / "config"))
        with pytest.raises(typer.Exit):
            gw_cmd._load_gateway_user_client()

    def test_missing_token_exits(self, monkeypatch, tmp_path):
        import typer

        monkeypatch.setenv("AX_CONFIG_DIR", str(tmp_path / "config"))
        gw.save_gateway_session({"base_url": "https://paxai.app"})
        with pytest.raises(typer.Exit):
            gw_cmd._load_gateway_user_client()

    def test_non_user_token_exits(self, monkeypatch, tmp_path):
        import typer

        monkeypatch.setenv("AX_CONFIG_DIR", str(tmp_path / "config"))
        gw.save_gateway_session({"token": "axp_a_agent.token", "base_url": "https://paxai.app"})
        with pytest.raises(typer.Exit):
            gw_cmd._load_gateway_user_client()

    def test_valid_session_returns_client(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AX_CONFIG_DIR", str(tmp_path / "config"))
        gw.save_gateway_session({"token": "axp_u_test.token", "base_url": "https://paxai.app"})
        client = gw_cmd._load_gateway_user_client()
        assert client is not None
        client.close()


# ---------------------------------------------------------------------------
# commands/gateway.py: _find_local_origin_collision
# ---------------------------------------------------------------------------


class TestFindLocalOriginCollision:
    def test_no_collision(self):
        fp = {"exe_path": "/usr/bin/python3", "cwd": "/home/user/project", "user": "testuser"}
        registry = {"agents": []}
        assert gw_cmd._find_local_origin_collision(registry, fingerprint=fp, requested_name="new-agent") is None

    def test_collision_found(self):
        fp = {"exe_path": "/usr/bin/python3", "cwd": "/home/user/project", "user": "testuser"}
        gw_cmd._local_origin_signature(fp)
        registry = {
            "agents": [
                {
                    "name": "existing-agent",
                    "local_fingerprint": fp,
                }
            ]
        }
        result = gw_cmd._find_local_origin_collision(registry, fingerprint=fp, requested_name="new-agent")
        assert result is not None
        assert result["name"] == "existing-agent"

    def test_same_name_not_collision(self):
        fp = {"exe_path": "/usr/bin/python3", "cwd": "/home/user/project", "user": "testuser"}
        registry = {"agents": [{"name": "same-agent", "local_fingerprint": fp}]}
        result = gw_cmd._find_local_origin_collision(registry, fingerprint=fp, requested_name="same-agent")
        assert result is None


# ---------------------------------------------------------------------------
# commands/gateway.py: _gateway_session_challenge_enabled
# ---------------------------------------------------------------------------


class TestGatewaySessionChallengeEnabled:
    def test_enabled(self, monkeypatch):
        monkeypatch.setenv("AX_GATEWAY_SESSION_CHALLENGE", "1")
        assert gw_cmd._gateway_session_challenge_enabled() is True

    def test_enabled_true(self, monkeypatch):
        monkeypatch.setenv("AX_GATEWAY_SESSION_CHALLENGE", "true")
        assert gw_cmd._gateway_session_challenge_enabled() is True

    def test_disabled_default(self, monkeypatch):
        monkeypatch.delenv("AX_GATEWAY_SESSION_CHALLENGE", raising=False)
        assert gw_cmd._gateway_session_challenge_enabled() is False

    def test_disabled_explicit(self, monkeypatch):
        monkeypatch.setenv("AX_GATEWAY_SESSION_CHALLENGE", "0")
        assert gw_cmd._gateway_session_challenge_enabled() is False


# ---------------------------------------------------------------------------
# commands/gateway.py: _generate_session_challenge_code
# ---------------------------------------------------------------------------


class TestGenerateSessionChallengeCode:
    def test_returns_string(self):
        code = gw_cmd._generate_session_challenge_code()
        assert isinstance(code, str)
        assert len(code) > 0

    def test_uppercase(self):
        code = gw_cmd._generate_session_challenge_code()
        assert code == code.upper()

    def test_unique(self):
        codes = {gw_cmd._generate_session_challenge_code() for _ in range(10)}
        assert len(codes) > 1  # extremely unlikely all 10 are the same


# ---------------------------------------------------------------------------
# commands/gateway.py: _find_local_session_record
# ---------------------------------------------------------------------------


class TestFindLocalSessionRecord:
    def test_found(self):
        registry = {"local_sessions": [{"session_id": "s1", "agent_name": "a"}]}
        assert gw_cmd._find_local_session_record(registry, "s1")["agent_name"] == "a"

    def test_not_found(self):
        registry = {"local_sessions": [{"session_id": "s1"}]}
        assert gw_cmd._find_local_session_record(registry, "s2") is None

    def test_empty_session_id(self):
        registry = {"local_sessions": [{"session_id": "s1"}]}
        assert gw_cmd._find_local_session_record(registry, "") is None

    def test_none_session_id(self):
        registry = {"local_sessions": []}
        assert gw_cmd._find_local_session_record(registry, None) is None

    def test_no_sessions_key(self):
        assert gw_cmd._find_local_session_record({}, "s1") is None


# ---------------------------------------------------------------------------
# _hermes_repo_candidates (lines 816-843)
# ---------------------------------------------------------------------------


class TestHermesRepoCandidates:
    def test_with_entry_path(self):
        candidates = gw._hermes_repo_candidates({"hermes_repo_path": "/custom/hermes"})
        assert Path("/custom/hermes") in candidates

    def test_with_env_var(self, monkeypatch):
        monkeypatch.setenv("HERMES_REPO_PATH", "/env/hermes")
        candidates = gw._hermes_repo_candidates({})
        assert Path("/env/hermes") in candidates

    def test_deduplicates(self):
        candidates = gw._hermes_repo_candidates({"hermes_repo_path": str(Path.home() / "hermes-agent")})
        paths = [str(c) for c in candidates]
        assert len(paths) == len(set(paths))

    def test_home_fallback_always_included(self, monkeypatch):
        monkeypatch.delenv("HERMES_REPO_PATH", raising=False)
        candidates = gw._hermes_repo_candidates({})
        assert Path.home() / "hermes-agent" in candidates


# ---------------------------------------------------------------------------
# hermes_setup_status (lines 846-881)
# ---------------------------------------------------------------------------


class TestHermesSetupStatus:
    def test_hermes_plugin_runtime_always_ready(self):
        status = gw.hermes_setup_status({"runtime_type": "hermes_plugin"})
        assert status["ready"] is True

    def test_non_hermes_template_always_ready(self):
        status = gw.hermes_setup_status({"template_id": "echo_test"})
        assert status["ready"] is True

    def test_hermes_template_not_found(self, monkeypatch):
        monkeypatch.delenv("HERMES_REPO_PATH", raising=False)
        # Mock _hermes_repo_candidates to return only nonexistent paths,
        # preventing ~/hermes-agent from being found on the dev machine.
        monkeypatch.setattr(
            gw,
            "_hermes_repo_candidates",
            lambda entry=None: [Path("/nonexistent/hermes-agent-12345")],
        )
        status = gw.hermes_setup_status(
            {
                "template_id": "hermes",
                "runtime_type": "hermes_sentinel",
            }
        )
        assert status["ready"] is False
        assert "not found" in status["summary"].lower()


# ---------------------------------------------------------------------------
# _format_daemon_log_line (line 2879-2888)
# ---------------------------------------------------------------------------


class TestFormatDaemonLogLine:
    def test_contains_message(self):
        result = gw._format_daemon_log_line("Starting gateway")
        assert "Starting gateway" in result

    def test_has_timestamp_prefix(self):
        result = gw._format_daemon_log_line("test message")
        # ISO-8601 format starts with year
        assert result[:4].isdigit()


# ---------------------------------------------------------------------------
# looks_like_space_uuid (line 3183)
# ---------------------------------------------------------------------------


class TestLooksLikeSpaceUuid:
    def test_valid_uuid(self):
        assert gw.looks_like_space_uuid("0478b063-4100-497d-bbea-2327bea48bc4") is True

    def test_invalid_string(self):
        assert gw.looks_like_space_uuid("not-a-uuid") is False

    def test_non_string(self):
        assert gw.looks_like_space_uuid(12345) is False

    def test_empty(self):
        assert gw.looks_like_space_uuid("") is False


# ---------------------------------------------------------------------------
# _launch_spec_for_entry (lines 1439-1457)
# ---------------------------------------------------------------------------


class TestLaunchSpecForEntry:
    def test_basic_entry(self):
        entry = {
            "runtime_type": "echo",
            "template_id": "echo_test",
            "exec_command": "python3 -m echo",
            "workdir": "/home/agent",
        }
        spec = gw._launch_spec_for_entry(entry)
        assert spec["runtime_type"] == "echo"
        assert spec["template_id"] == "echo_test"
        assert spec["command"] == "python3 -m echo"
        assert spec["workdir"] == "/home/agent"

    def test_model_field(self):
        entry = {"hermes_model": "codex:gpt-5.5"}
        spec = gw._launch_spec_for_entry(entry)
        assert spec["model"] == "codex:gpt-5.5"

    def test_no_model(self):
        spec = gw._launch_spec_for_entry({})
        assert "model" not in spec
