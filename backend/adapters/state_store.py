"""Persistent state helpers for queue history."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.models import TriageResult


def coerce_triage_result(value: Any) -> TriageResult | None:
    if isinstance(value, TriageResult):
        return value
    if isinstance(value, dict):
        try:
            return TriageResult.model_validate(value)
        except Exception:
            return None
    if isinstance(value, str):
        return TriageResult(
            success="success=True" in value,
            source_path="",
            dest_path="",
            hardlink_path=None,
            error_msg=None if "success=True" in value else value,
        )
    return None


def load_history(state_file: Path) -> list[dict[str, Any]]:
    if not state_file.exists():
        return []
    data = json.loads(state_file.read_text())
    history: list[dict[str, Any]] = []
    for entry in data.get("history", []):
        if not isinstance(entry, dict):
            continue
        result = coerce_triage_result(entry.get("result"))
        if result is None:
            continue
        history.append({**entry, "result": result})
    return history


def save_history(state_file: Path, history: list[dict[str, Any]]) -> None:
    payload = {
        "history": [_serialize_history_entry(entry) for entry in history[-100:]],
        "timestamp": str(datetime.now(timezone.utc).isoformat()),
    }
    state_file.write_text(json.dumps(payload, default=str, indent=2))


def _serialize_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    result = coerce_triage_result(entry.get("result"))
    return {
        "job_id": entry.get("job_id", ""),
        "result": result.model_dump() if result else None,
        "title": entry.get("title", ""),
        "mode": entry.get("mode"),
        "confidence": entry.get("confidence"),
        "timestamp": entry.get("timestamp"),
    }
