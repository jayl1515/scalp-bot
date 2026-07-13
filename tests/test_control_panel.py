"""Tests for the scalp-bot control panel (API, auth, validation, guardrails)."""
from __future__ import annotations

import json
import os

import pytest

from scalp_bot.control_panel import audit
from scalp_bot.control_panel.app import create_app
from scalp_bot.control_panel.state import BotState
from scalp_bot.control_panel.validation import validate_settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def state():
    return BotState()


@pytest.fixture
def app(state, tmp_path):
    """Flask test app backed by an isolated BotState."""
    application = create_app(state=state, database_path=tmp_path / "control_panel.db")
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clear_audit():
    audit.clear()
    yield
    audit.clear()


@pytest.fixture
def authed_client(app, monkeypatch):
    """Client that sends the correct ******"""
    monkeypatch.setenv("CONTROL_PANEL_TOKEN", "test-secret")
    return app.test_client()


TOKEN = "test-secret"


def auth(token=TOKEN):
    return {"Authorization": "Bearer " + token}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.get_json()["status"] == "ok"

    def test_health_no_auth_required(self, client, monkeypatch):
        monkeypatch.setenv("CONTROL_PANEL_TOKEN", "secret")
        r = client.get("/api/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuth:
    def test_status_requires_token(self, client, monkeypatch):
        monkeypatch.setenv("CONTROL_PANEL_TOKEN", TOKEN)
        r = client.get("/api/status")
        assert r.status_code == 401

    def test_status_wrong_token_rejected(self, client, monkeypatch):
        monkeypatch.setenv("CONTROL_PANEL_TOKEN", TOKEN)
        r = client.get("/api/status", headers=auth("wrong"))
        assert r.status_code == 401

    def test_status_correct_token_accepted(self, client, monkeypatch):
        monkeypatch.setenv("CONTROL_PANEL_TOKEN", TOKEN)
        r = client.get("/api/status", headers=auth())
        assert r.status_code == 200

    def test_no_env_token_allows_all(self, client, monkeypatch):
        monkeypatch.delenv("CONTROL_PANEL_TOKEN", raising=False)
        r = client.get("/api/status")
        assert r.status_code == 200

    def test_missing_bearer_prefix_rejected(self, client, monkeypatch):
        monkeypatch.setenv("CONTROL_PANEL_TOKEN", TOKEN)
        r = client.get("/api/status", headers={"Authorization": TOKEN})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

class TestStatus:
    def test_default_state(self, client, state):
        r = client.get("/api/status")
        data = r.get_json()
        assert data["running"] is False
        assert data["mode"] == "paper"
        assert data["kill_switch_active"] is False

    def test_started_state(self, client, state):
        state.start()
        data = client.get("/api/status").get_json()
        assert data["running"] is True
        assert data["started_at"] is not None


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

class TestStartStop:
    def test_start_bot(self, client, state):
        r = client.post("/api/start")
        assert r.status_code == 200
        assert state.running is True

    def test_start_already_running_is_noop(self, client, state):
        state.start()
        r = client.post("/api/start")
        assert r.status_code == 200
        assert "already running" in r.get_json()["message"]

    def test_stop_bot(self, client, state):
        state.start()
        r = client.post("/api/stop")
        assert r.status_code == 200
        assert state.running is False

    def test_stop_already_stopped_is_noop(self, client, state):
        r = client.post("/api/stop")
        assert r.status_code == 200
        assert "already stopped" in r.get_json()["message"]

    def test_start_blocked_when_kill_switch_active(self, client, state):
        state.kill_switch_active = True
        r = client.post("/api/start")
        assert r.status_code == 409
        assert "Kill switch" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_kill_switch_stops_bot(self, client, state):
        state.start()
        r = client.post("/api/killswitch")
        assert r.status_code == 200
        assert state.kill_switch_active is True
        assert state.running is False

    def test_kill_switch_reset(self, client, state):
        state.activate_kill_switch()
        r = client.post("/api/killswitch/reset")
        assert r.status_code == 200
        assert state.kill_switch_active is False

    def test_start_after_reset_allowed(self, client, state):
        state.activate_kill_switch()
        client.post("/api/killswitch/reset")
        r = client.post("/api/start")
        assert r.status_code == 200
        assert state.running is True


# ---------------------------------------------------------------------------
# Mode (paper / live guardrails)
# ---------------------------------------------------------------------------

class TestMode:
    def test_default_mode_is_paper(self, client, state):
        assert state.mode == "paper"

    def test_get_mode(self, client, state):
        r = client.get("/api/mode")
        assert r.get_json()["mode"] == "paper"

    def test_set_paper_mode(self, client, state):
        state.set_mode("live")
        r = client.post("/api/mode/paper")
        assert r.status_code == 200
        assert state.mode == "paper"

    def test_confirm_live_requires_confirmation(self, client, state):
        r = client.post(
            "/api/mode/confirm-live",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert r.status_code == 422
        assert state.mode == "paper"

    def test_confirm_live_wrong_value_rejected(self, client, state):
        r = client.post(
            "/api/mode/confirm-live",
            data=json.dumps({"confirm": "yes"}),
            content_type="application/json",
        )
        assert r.status_code == 422
        assert state.mode == "paper"

    def test_confirm_live_success(self, client, state):
        r = client.post(
            "/api/mode/confirm-live",
            data=json.dumps({"confirm": "LIVE"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert state.mode == "live"

    def test_confirm_live_without_body_rejected(self, client, state):
        r = client.post("/api/mode/confirm-live")
        assert r.status_code == 422
        assert state.mode == "paper"


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_payload_valid(self):
        assert validate_settings({}) == []

    def test_valid_float_field(self):
        assert validate_settings({"base_capital": 100.0}) == []

    def test_float_out_of_range(self):
        errs = validate_settings({"base_capital": 0.0})
        assert any("base_capital" in e for e in errs)

    def test_invalid_type(self):
        errs = validate_settings({"base_capital": "notanumber"})
        assert any("base_capital" in e for e in errs)

    def test_unknown_key(self):
        errs = validate_settings({"hack_field": 999})
        assert any("hack_field" in e for e in errs)

    def test_nested_risk_valid(self):
        assert validate_settings({"risk": {"max_daily_loss_pct": 0.05}}) == []

    def test_nested_risk_invalid_int(self):
        errs = validate_settings({"risk": {"max_consecutive_losses": 0}})
        assert errs

    def test_nested_strategy_valid(self):
        settings = {
            "strategy": {
                "ema_fast_period": 8,
                "ema_slow_period": 21,
                "risk_per_trade_pct": 0.05,
            }
        }
        assert validate_settings(settings) == []

    def test_float_passed_as_int_field_rejected(self):
        errs = validate_settings({"risk": {"max_consecutive_losses": 2.5}})
        assert errs


class TestSettingsEndpoint:
    def test_get_settings_empty_by_default(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert r.get_json() == {}

    def test_put_valid_settings(self, client, state):
        payload = {"base_capital": 50.0}
        r = client.put(
            "/api/settings",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert state.settings_override["base_capital"] == 50.0

    def test_settings_persist_across_app_restarts(self, state, tmp_path):
        db_path = tmp_path / "persistent.db"
        first_app = create_app(state=state, database_path=db_path)
        first_app.config["TESTING"] = True
        first_client = first_app.test_client()
        first_client.put(
            "/api/settings",
            data=json.dumps({"base_capital": 50.0}),
            content_type="application/json",
        )

        reloaded_state = BotState()
        second_app = create_app(state=reloaded_state, database_path=db_path)
        second_app.config["TESTING"] = True
        second_client = second_app.test_client()
        response = second_client.get("/api/settings")
        assert response.status_code == 200
        assert response.get_json()["base_capital"] == 50.0

    def test_put_invalid_settings_returns_422(self, client):
        payload = {"base_capital": -100}
        r = client.put(
            "/api/settings",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert r.status_code == 422
        assert "errors" in r.get_json()

    def test_put_unknown_key_returns_422(self, client):
        r = client.put(
            "/api/settings",
            data=json.dumps({"evil_key": 1}),
            content_type="application/json",
        )
        assert r.status_code == 422

    def test_put_non_json_body_returns_400(self, client):
        r = client.put(
            "/api/settings",
            data="not json",
            content_type="text/plain",
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_start_action_logged(self, client):
        client.post("/api/start")
        logs = audit.get_recent()
        assert any(e["action"] == "start" for e in logs)

    def test_stop_action_logged(self, client, state):
        state.start()
        client.post("/api/stop")
        logs = audit.get_recent()
        assert any(e["action"] == "stop" for e in logs)

    def test_kill_switch_logged(self, client):
        client.post("/api/killswitch")
        logs = audit.get_recent()
        assert any(e["action"] == "killswitch" for e in logs)

    def test_settings_change_logged(self, client):
        client.put(
            "/api/settings",
            data=json.dumps({"base_capital": 30.0}),
            content_type="application/json",
        )
        logs = audit.get_recent()
        assert any(e["action"] == "update_settings" for e in logs)

    def test_logs_endpoint(self, client):
        client.post("/api/start")
        r = client.get("/api/logs")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_rejected_auth_not_logged(self, client, monkeypatch):
        monkeypatch.setenv("CONTROL_PANEL_TOKEN", TOKEN)
        client.get("/api/status", headers=auth("wrong"))
        logs = audit.get_recent()
        # Auth rejections don't reach handler code, so no log entry expected
        assert all(e.get("action") != "get_status" for e in logs)


# ---------------------------------------------------------------------------
# UI route
# ---------------------------------------------------------------------------

class TestUIRoute:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"scalp-bot" in r.data
        assert b"<html" in r.data

    def test_manifest_is_available(self, client):
        r = client.get("/manifest.webmanifest")
        assert r.status_code == 200
        assert r.mimetype == "application/manifest+json"


class TestAppMetadata:
    def test_app_metadata_includes_dataset_summary(self, client):
        r = client.get("/api/app")
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["dataset"]["total_candles"] > 0
        assert "dashboard" in payload["available_sections"]


class TestBacktestRuns:
    def test_backtest_run_is_persisted(self, client):
        r = client.post(
            "/api/backtests",
            data=json.dumps({"title": "Range check", "start_date": "2024-01-01", "end_date": "2024-01-02"}),
            content_type="application/json",
        )
        assert r.status_code == 201
        run = r.get_json()
        assert run["run_type"] == "backtest"
        assert run["status"] == "completed"
        assert run["trade_count"] > 0

        detail = client.get(f"/api/runs/{run['id']}")
        assert detail.status_code == 200
        assert detail.get_json()["config"]["base_capital"] == 20.0

    def test_duplicate_backtests_keep_separate_rows(self, client):
        first = client.post(
            "/api/backtests",
            data=json.dumps({"start_date": "2024-01-01", "end_date": "2024-01-02"}),
            content_type="application/json",
        )
        second = client.post(
            "/api/backtests",
            data=json.dumps({"start_date": "2024-01-01", "end_date": "2024-01-02"}),
            content_type="application/json",
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.get_json()["id"] != second.get_json()["id"]

        listing = client.get("/api/runs?type=backtest").get_json()
        ids = [entry["id"] for entry in listing]
        assert first.get_json()["id"] in ids
        assert second.get_json()["id"] in ids

    def test_compare_runs_endpoint(self, client):
        first = client.post(
            "/api/backtests",
            data=json.dumps({"title": "A", "start_date": "2024-01-01T00:00:00", "end_date": "2024-01-01T05:59:00"}),
            content_type="application/json",
        ).get_json()
        second = client.post(
            "/api/backtests",
            data=json.dumps({"title": "B", "start_date": "2024-01-01T06:00:00", "end_date": "2024-01-01T11:59:00"}),
            content_type="application/json",
        ).get_json()
        response = client.get(f"/api/runs/compare?ids={first['id']},{second['id']}")
        assert response.status_code == 200
        assert len(response.get_json()["runs"]) == 2


class TestPaperRuns:
    def test_paper_session_persists_events_and_trades(self, client):
        started = client.post(
            "/api/paper/start",
            data=json.dumps({"title": "Morning session"}),
            content_type="application/json",
        )
        assert started.status_code == 201
        run_id = started.get_json()["id"]

        signal = client.post(
            "/api/paper/signal",
            data=json.dumps({"symbol": "BTCUSDT", "bias": "long", "note": "Breakout"}),
            content_type="application/json",
        )
        assert signal.status_code == 201

        trade = client.post(
            "/api/paper/trade",
            data=json.dumps({
                "symbol": "BTCUSDT",
                "side": "long",
                "quantity": 1.0,
                "entry_price": 100.0,
                "exit_price": 101.0,
                "note": "Target hit",
            }),
            content_type="application/json",
        )
        assert trade.status_code == 201

        stopped = client.post(
            "/api/paper/stop",
            data=json.dumps({"notes": "Done for the day"}),
            content_type="application/json",
        )
        assert stopped.status_code == 200
        detail = client.get(f"/api/runs/{run_id}")
        assert detail.status_code == 200
        payload = detail.get_json()
        assert payload["status"] == "stopped"
        assert payload["trade_count"] == 1
        assert payload["event_count"] >= 3
