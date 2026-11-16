"""Append-only JSONL run ledger: every clip (mock or live) is metered against one estimate table."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import Settings, get_settings


def _path(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return s.data_dir / "ledger.jsonl"


def record(entry: dict[str, Any], settings: Settings | None = None) -> None:
    p = _path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}) + "\n")


def entries(settings: Settings | None = None) -> list[dict[str, Any]]:
    p = _path(settings)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def report(settings: Settings | None = None) -> dict[str, Any]:
    rows = entries(settings)
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"clips": 0, "seconds": 0.0, "estimate_usd": 0.0})
    by_backend: dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("status") != "completed":
            continue
        b = by_model[r["model"]]
        b["clips"] += 1
        b["seconds"] += float(r.get("seconds") or 0)
        b["estimate_usd"] = round(b["estimate_usd"] + float(r.get("estimate_usd") or 0), 4)
        by_backend[r.get("backend", "?")] += 1
    total = round(sum(v["estimate_usd"] for v in by_model.values()), 4)
    return {
        "clips": sum(int(v["clips"]) for v in by_model.values()),
        "estimated_total_usd": total,
        "by_model": dict(by_model),
        "by_backend": dict(by_backend),
        "note": (
            "Estimates from preview list prices x requested seconds. Mock-backend rows cost nothing; "
            "they show what the same run would be metered at on Foundry. Not a bill."
        ),
    }


def reset(settings: Settings | None = None) -> None:
    p = _path(settings)
    if p.exists():
        p.unlink()
