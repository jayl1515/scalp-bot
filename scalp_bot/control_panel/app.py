"""Flask application factory for the scalp-bot control panel app."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from . import audit
from .auth import require_auth
from .services import ControlPanelService
from .state import BotState, bot_state
from .storage import AppDatabase
from .validation import validate_settings


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_database_path() -> Path:
    return _repo_root() / "instance" / "scalp_bot.db"


def create_app(
    state: BotState | None = None,
    *,
    database_path: str | Path | None = None,
    config_path: str | Path | None = None,
    data_path: str | Path | None = None,
) -> Flask:
    if state is None:
        state = bot_state

    repo_root = _repo_root()
    resolved_config_path = Path(config_path or os.environ.get("SCALP_BOT_CONFIG_PATH", repo_root / "config" / "sample_config.json"))
    resolved_data_path = Path(data_path or os.environ.get("SCALP_BOT_DATA_PATH", repo_root / "data" / "btcusdt_1h.csv"))
    resolved_database_path = Path(database_path or os.environ.get("CONTROL_PANEL_DB_PATH", _default_database_path()))

    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

    database = AppDatabase(resolved_database_path)
    audit.set_backend(database)
    service = ControlPanelService(
        state=state,
        database=database,
        config_path=resolved_config_path,
        data_path=resolved_data_path,
    )
    service.persist_state()
    app.config["CONTROL_PANEL_SERVICE"] = service

    def _actor() -> str:
        return request.remote_addr or "unknown"

    def _status_payload() -> dict[str, object]:
        return state.to_dict() | {"active_paper_run_id": state.active_paper_run_id}

    def _json_body() -> dict:
        body = request.get_json(silent=True)
        if body is None:
            return {}
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        return body

    def _value_error_response(action: str, exc: ValueError, *, status_code: int, public_error: str):
        audit.record(action, _actor(), "rejected", str(exc))
        return jsonify({"error": public_error}), status_code

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/manifest.webmanifest")
    def manifest():
        payload = {
            "name": "scalp-bot",
            "short_name": "scalp-bot",
            "display": "standalone",
            "background_color": "#09111f",
            "theme_color": "#3b82f6",
            "start_url": "/",
            "scope": "/",
            "icons": [
                {
                    "src": "/static/icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
        }
        return app.response_class(
            json.dumps(payload),
            mimetype="application/manifest+json",
        )

    @app.get("/sw.js")
    def service_worker():
        response = send_from_directory(static_dir, "sw.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/app")
    @require_auth
    def get_app_metadata():
        return jsonify(service.app_metadata())

    @app.get("/api/status")
    @require_auth
    def get_status():
        return jsonify(_status_payload())

    @app.post("/api/start")
    @require_auth
    def start_bot():
        if state.kill_switch_active:
            audit.record("start", _actor(), "rejected", "kill switch active")
            return jsonify({"error": "Kill switch is active. Deactivate before starting."}), 409

        paper_session = None
        if state.running:
            audit.record("start", _actor(), "noop", "already running")
            return jsonify({"message": "Bot is already running.", "status": _status_payload()})

        state.start()
        if state.mode == "paper" and not state.active_paper_run_id:
            paper_session = service.start_paper_session({"title": "Paper session from control panel"})
        service.persist_state()
        audit.record("start", _actor(), "success", f"mode={state.mode}")
        return jsonify({"message": "Bot started.", "status": _status_payload(), "paper_session": paper_session})

    @app.post("/api/stop")
    @require_auth
    def stop_bot():
        if not state.running:
            audit.record("stop", _actor(), "noop", "already stopped")
            return jsonify({"message": "Bot is already stopped.", "status": _status_payload()})

        state.stop()
        paper_session = None
        if state.active_paper_run_id:
            paper_session = service.stop_paper_session({"notes": "Stopped from the control panel."})
        service.persist_state()
        audit.record("stop", _actor(), "success")
        return jsonify({"message": "Bot stopped.", "status": _status_payload(), "paper_session": paper_session})

    @app.post("/api/killswitch")
    @require_auth
    def kill_switch():
        state.activate_kill_switch()
        paper_session = None
        if state.active_paper_run_id:
            paper_session = service.stop_paper_session({"notes": "Kill switch activated."})
        service.persist_state()
        audit.record("killswitch", _actor(), "success")
        return jsonify({
            "message": "Kill switch activated. Bot stopped.",
            "status": _status_payload(),
            "paper_session": paper_session,
        })

    @app.post("/api/killswitch/reset")
    @require_auth
    def reset_kill_switch():
        state.kill_switch_active = False
        service.persist_state()
        audit.record("killswitch_reset", _actor(), "success")
        return jsonify({"message": "Kill switch deactivated.", "status": _status_payload()})

    @app.get("/api/mode")
    @require_auth
    def get_mode():
        return jsonify({"mode": state.mode})

    @app.post("/api/mode/paper")
    @require_auth
    def set_paper():
        prev = state.mode
        state.set_mode("paper")
        service.persist_state()
        audit.record("set_mode", _actor(), "success", "paper")
        return jsonify({"message": "Switched to paper mode.", "mode": state.mode, "previous": prev})

    @app.post("/api/mode/confirm-live")
    @require_auth
    def confirm_live():
        body = request.get_json(silent=True) or {}
        if body.get("confirm") != "LIVE":
            audit.record("set_mode", _actor(), "rejected", "missing confirmation")
            return jsonify({
                "error": "To switch to live mode send JSON body: {\"confirm\": \"LIVE\"}",
            }), 422
        if state.active_paper_run_id:
            audit.record("set_mode", _actor(), "rejected", "paper session active")
            return jsonify({"error": "Stop the active paper session before switching to live mode."}), 409

        prev = state.mode
        state.set_mode("live")
        service.persist_state()
        audit.record("set_mode", _actor(), "success", "live")
        return jsonify({
            "message": "Switched to LIVE mode. Real orders will be placed.",
            "mode": state.mode,
            "previous": prev,
        })

    @app.get("/api/settings")
    @require_auth
    def get_settings():
        return jsonify(state.settings_override)

    @app.put("/api/settings")
    @require_auth
    def update_settings():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        errors = validate_settings(body)
        if errors:
            audit.record("update_settings", _actor(), "rejected", "; ".join(errors))
            return jsonify({"errors": errors}), 422

        state.settings_override.update(body)
        service.persist_state()
        audit.record("update_settings", _actor(), "success", json.dumps(body))
        return jsonify({"message": "Settings updated.", "settings": state.settings_override})

    @app.post("/api/backtests")
    @require_auth
    def create_backtest():
        try:
            body = _json_body()
        except ValueError as exc:
            return _value_error_response("backtest", exc, status_code=400, public_error="Request body must be a JSON object.")
        errors = validate_settings(body.get("config_overrides") or {})
        if errors:
            return jsonify({"errors": errors}), 422
        try:
            run = service.run_backtest(body)
        except ValueError as exc:
            return _value_error_response("backtest", exc, status_code=400, public_error="Unable to create backtest.")
        audit.record("backtest", _actor(), "success", run["id"])
        return jsonify(run), 201

    @app.get("/api/runs")
    @require_auth
    def list_runs():
        run_type = request.args.get("type") or None
        status = request.args.get("status") or None
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 200))
        except ValueError:
            limit = 50
        return jsonify(service.list_runs(run_type=run_type, status=status, limit=limit))

    @app.get("/api/runs/compare")
    @require_auth
    def compare_runs():
        raw_ids = request.args.get("ids", "")
        run_ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        try:
            comparison = service.compare_runs(run_ids)
        except ValueError as exc:
            return _value_error_response("compare_runs", exc, status_code=400, public_error="Unable to compare the selected runs.")
        return jsonify(comparison)

    @app.get("/api/runs/<run_id>")
    @require_auth
    def get_run(run_id: str):
        payload = service.get_run(run_id)
        if payload is None:
            return jsonify({"error": f"Run '{run_id}' was not found."}), 404
        return jsonify(payload)

    @app.get("/api/paper/session")
    @require_auth
    def current_paper_session():
        session = service.get_active_paper_session()
        return jsonify({"session": session})

    @app.post("/api/paper/start")
    @require_auth
    def start_paper_session():
        if state.mode != "paper":
            return jsonify({"error": "Switch to paper mode before starting a paper session."}), 409
        try:
            body = _json_body()
            errors = validate_settings(body.get("config_overrides") or {})
            if errors:
                return jsonify({"errors": errors}), 422
            session = service.start_paper_session(body)
        except ValueError as exc:
            return _value_error_response("paper_start", exc, status_code=409, public_error="Unable to start the paper session.")
        audit.record("paper_start", _actor(), "success", session["id"])
        return jsonify(session), 201

    @app.post("/api/paper/signal")
    @require_auth
    def log_paper_signal():
        try:
            body = _json_body()
            signal = service.log_paper_signal(body)
        except ValueError as exc:
            return _value_error_response("paper_signal", exc, status_code=409, public_error="Unable to log the paper signal.")
        audit.record("paper_signal", _actor(), "success", signal.get("symbol") or "signal")
        return jsonify(signal), 201

    @app.post("/api/paper/trade")
    @require_auth
    def log_paper_trade():
        try:
            body = _json_body()
            trade = service.log_paper_trade(body)
        except ValueError as exc:
            return _value_error_response("paper_trade", exc, status_code=409, public_error="Unable to log the paper trade.")
        audit.record("paper_trade", _actor(), "success", trade.get("symbol") or "trade")
        return jsonify(trade), 201

    @app.post("/api/paper/stop")
    @require_auth
    def stop_paper_session():
        try:
            body = _json_body()
            session = service.stop_paper_session(body)
        except ValueError as exc:
            return _value_error_response("paper_stop", exc, status_code=409, public_error="Unable to stop the paper session.")
        audit.record("paper_stop", _actor(), "success", session["id"])
        return jsonify(session)

    @app.get("/api/logs")
    @require_auth
    def get_logs():
        try:
            n = int(request.args.get("n", 50))
            n = max(1, min(n, 500))
        except ValueError:
            n = 50
        return jsonify(audit.get_recent(n))

    return app


def main() -> None:
    host = os.environ.get("CONTROL_PANEL_HOST", "0.0.0.0")
    port = int(os.environ.get("CONTROL_PANEL_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app = create_app()
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
