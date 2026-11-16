"""Bounded re-roll: @brand-qa failure -> another render on the higher-fidelity tier, never an unbounded loop.

* A re-roll is only allowed when the clip's latest QA verdict is "fail" (a complete, valid score set below
  threshold). "manual_review" and "error" verdicts go to a human instead of spending more inference.
* The budget is tracked on the chain ROOT (`data_dir/rerolls/<root>.json`), reserved under a lock BEFORE
  dispatch. Failed or uncertain submits keep their reservation (they may still be metered).
* Each job can be re-rolled once; to go further, evaluate and re-roll the persisted child.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from . import catalog, qa
from .config import Settings, get_settings
from .models import get_model
from .pipeline import generate_video, get_job, save_job

MAX_REROLLS = 2
_THREAD_LOCK = threading.Lock()


class RerollRefused(RuntimeError):
    pass


def _duration_for(model: str, seconds: float) -> float | str:
    m = get_model(model)
    if m.key == "ltx-2.5-pro":
        return min((6, 8, 10), key=lambda d: abs(d - seconds))
    if m.family == "kling":
        return str(int(round(min(max(seconds, 3), 15))))
    if m.family == "ltx":
        return min(max(int(round(seconds / 2) * 2), 6), 20)
    return min(max(seconds, 0.92), 15)


def _chain_path(s: Settings, root: str) -> Path:
    d = s.data_dir / "rerolls"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{root}.json"


@contextmanager
def _locked(path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Thread lock + exclusive lock file so separate MCP/CLI processes can't double-reserve."""
    lock = path.with_suffix(".lock")
    deadline = time.monotonic() + timeout
    with _THREAD_LOCK:
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise RerollRefused(f"re-roll chain is locked ({lock.name}); try again") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)


def chain_state(root: str, settings: Settings | None = None) -> dict[str, Any]:
    p = _chain_path(settings or get_settings(), root)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"root": root, "reservations": []}


def _write(p: Path, st: dict[str, Any]) -> None:
    p.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _reserve(s: Settings, root: str, parent: str, max_rerolls: int) -> int:
    p = _chain_path(s, root)
    with _locked(p):
        st = chain_state(root, s)
        prior = next((r for r in st["reservations"] if r["parent"] == parent), None)
        if prior:
            raise RerollRefused(
                f"job {parent} was already re-rolled (attempt {prior['attempt']}, {prior['status']}, "
                f"child {prior.get('child')}); evaluate and follow the child instead"
            )
        if len(st["reservations"]) >= max_rerolls:
            raise RerollRefused(
                f"re-roll budget exhausted ({len(st['reservations'])}/{max_rerolls}) for chain {root}"
            )
        attempt = len(st["reservations"]) + 1
        st["reservations"].append(
            {"attempt": attempt, "parent": parent, "status": "reserved", "child": None, "reserved_at": time.time()}
        )
        _write(p, st)
    return attempt


def _finish(s: Settings, root: str, attempt: int, status: str, child: str | None, error: str | None = None) -> None:
    p = _chain_path(s, root)
    with _locked(p):
        st = chain_state(root, s)
        for r in st["reservations"]:
            if r["attempt"] == attempt:
                r.update(status=status, child=child, error=error)
        _write(p, st)


def reroll(
    job_id: str,
    max_rerolls: int = MAX_REROLLS,
    evaluate: bool = True,
    settings: Settings | None = None,
    on_event: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    s = settings or get_settings()
    say = on_event or (lambda _m: None)
    max_rerolls = min(max(int(max_rerolls), 0), MAX_REROLLS)
    job = get_job(job_id, s)
    verdict = (job.get("qa") or {}).get("verdict")
    if verdict != "fail":
        raise RerollRefused(
            f"job {job_id} QA verdict is {verdict!r}; re-roll requires a completed 'fail' verdict "
            "(run evaluate_brand_compliance first; manual_review/error go to a human)"
        )
    rec = job["qa"]["reroll"]
    root = job.get("reroll_root", job_id)
    attempt = _reserve(s, root, job_id, max_rerolls)

    sku = job.get("sku")
    sku_rec = catalog.get_sku(sku) if sku else None
    image = catalog.image_path(sku_rec) if sku_rec and rec["mode"] == "image-to-video" else None
    mode = rec["mode"] if image else "text-to-video"
    m = get_model(rec["model"])
    audio = bool(job.get("audio")) and m.native_audio
    say(f"@brand-qa: re-roll {attempt}/{max_rerolls} of {job_id} on {m.display_name} ({mode})")
    try:
        new = generate_video(
            m.key, job["prompt"], str(image) if image else None,
            _duration_for(m.key, float(job["estimate"]["seconds"])),
            aspect_ratio=job["aspect_ratio"], audio=audio, mode=mode, sku=sku,
            label=f"Re-roll {attempt} | {m.display_name} | {mode} | {job['aspect_ratio']}",
            settings=s, on_event=say, use_cache=False,
        )
    except BaseException as exc:
        # A failed or uncertain submit may still be metered, so the reservation stays consumed.
        _finish(s, root, attempt, "failed", None, f"{type(exc).__name__}: {exc}")
        raise
    _finish(s, root, attempt, "completed", new["job_id"])
    new.update(reroll_of=job_id, reroll_root=root, reroll_attempt=attempt)
    save_job(s, new)
    job["rerolled_by"] = new["job_id"]
    save_job(s, job)
    if evaluate:
        new["qa"] = qa.evaluate(job_id=new["job_id"], sku=sku, prompt=job["prompt"], settings=s)
    new["rerolls_remaining"] = max_rerolls - attempt
    return new
