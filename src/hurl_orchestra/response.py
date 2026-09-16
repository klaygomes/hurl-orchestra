"""Reading the response hurl recorded, shared by known failures and retries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def last_response(report_path: Path) -> dict[str, Any] | None:
    """The last response hurl recorded, or None when it recorded none."""
    if not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    files = data if isinstance(data, list) else [data]
    for file_result in reversed(files):
        for entry in reversed(file_result.get("entries", [])):
            for call in reversed(entry.get("calls", [])):
                response = call.get("response")
                if isinstance(response, dict):
                    return response
    return None


def header_value(response: dict[str, Any], name: str) -> str | None:
    wanted = name.lower()
    for header in response.get("headers", []):
        if str(header.get("name", "")).lower() == wanted:
            return str(header.get("value", ""))
    return None


def body_text(response: dict[str, Any], report_dir: Path) -> str | None:
    body = response.get("body")
    if not isinstance(body, str) or not body:
        return None
    body_path = report_dir / body
    try:
        return body_path.read_text(errors="replace")
    except OSError:
        return None
