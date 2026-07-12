"""Token-based authentication for control panel endpoints."""
from __future__ import annotations

import os
from functools import wraps
from typing import Callable

from flask import request, jsonify


def _get_expected_token() -> str | None:
    return os.environ.get("CONTROL_PANEL_TOKEN")


def require_auth(f: Callable) -> Callable:
    """Decorator: reject requests that don't carry the correct ******"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        expected = _get_expected_token()
        if not expected:
            # No token configured → auth disabled (dev/local use only)
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        provided = auth_header[len("Bearer "):]
        if provided != expected:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)

    return wrapper
