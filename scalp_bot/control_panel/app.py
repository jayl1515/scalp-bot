"""Flask application factory for the scalp-bot control panel."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from . import audit
from .auth import require_auth
from .state import BotState, bot_state
from .validation import validate_settings

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(state: BotState | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        state: Optional BotState to use (defaults to the module-level singleton).
               Passing a custom instance is useful in tests.
    """
    if state is None:
        state = bot_state

    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _actor() -> str:
        """Best-effort actor identifier from request context."""
        return request.remote_addr or "unknown"

    # ------------------------------------------------------------------
    # UI route
    # ------------------------------------------------------------------

    @app.get("/")
    def index():
        return render_template("index.html")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # Bot status
    # ------------------------------------------------------------------

    @app.get("/api/status")
    @require_auth
    def get_status():
        return jsonify(state.to_dict())

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    @app.post("/api/start")
    @require_auth
    def start_bot():
        if state.kill_switch_active:
            audit.record("start", _actor(), "rejected", "kill switch active")
            return jsonify({"error": "Kill switch is active. Deactivate before starting."}), 409

        if state.running:
            audit.record("start", _actor(), "noop", "already running")
            return jsonify({"message": "Bot is already running.", "status": state.to_dict()})

        state.start()
        audit.record("start", _actor(), "success", f"mode={state.mode}")
        return jsonify({"message": "Bot started.", "status": state.to_dict()})

    @app.post("/api/stop")
    @require_auth
    def stop_bot():
        if not state.running:
            audit.record("stop", _actor(), "noop", "already stopped")
            return jsonify({"message": "Bot is already stopped.", "status": state.to_dict()})

        state.stop()
        audit.record("stop", _actor(), "success")
        return jsonify({"message": "Bot stopped.", "status": state.to_dict()})

    # ------------------------------------------------------------------
    # Kill switch
    # ------------------------------------------------------------------

    @app.post("/api/killswitch")
    @require_auth
    def kill_switch():
        state.activate_kill_switch()
        audit.record("killswitch", _actor(), "success")
        return jsonify({"message": "Kill switch activated. Bot stopped.", "status": state.to_dict()})

    @app.post("/api/killswitch/reset")
    @require_auth
    def reset_kill_switch():
        state.kill_switch_active = False
        audit.record("killswitch_reset", _actor(), "success")
        return jsonify({"message": "Kill switch deactivated.", "status": state.to_dict()})

    # ------------------------------------------------------------------
    # Mode: paper / live (with explicit confirmation)
    # ------------------------------------------------------------------

    @app.get("/api/mode")
    @require_auth
    def get_mode():
        return jsonify({"mode": state.mode})

    @app.post("/api/mode/paper")
    @require_auth
    def set_paper():
        prev = state.mode
        state.set_mode("paper")
        audit.record("set_mode", _actor(), "success", "paper")
        return jsonify({"message": "Switched to paper mode.", "mode": state.mode, "previous": prev})

    @app.post("/api/mode/confirm-live")
    @require_auth
    def confirm_live():
        """Switch to live mode.  Body must include ``{"confirm": "LIVE"}``."""
        body = request.get_json(silent=True) or {}
        if body.get("confirm") != "LIVE":
            audit.record("set_mode", _actor(), "rejected", "missing confirmation")
            return jsonify({
                "error": "To switch to live mode send JSON body: {\"confirm\": \"LIVE\"}",
            }), 422

        prev = state.mode
        state.set_mode("live")
        audit.record("set_mode", _actor(), "success", "live")
        return jsonify({
            "message": "Switched to LIVE mode. Real orders will be placed.",
            "mode": state.mode,
            "previous": prev,
        })

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

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
        audit.record("update_settings", _actor(), "success", json.dumps(body))
        return jsonify({"message": "Settings updated.", "settings": state.settings_override})

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point for ``python -m scalp_bot.control_panel``
# ---------------------------------------------------------------------------

def main() -> None:
    host = os.environ.get("CONTROL_PANEL_HOST", "0.0.0.0")
    port = int(os.environ.get("CONTROL_PANEL_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app = create_app()
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
