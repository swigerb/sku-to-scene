"""sku2scene CLI - presenter fallback that runs the same pipeline the Copilot agents call via MCP."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import catalog, ledger, qa
from .config import get_settings
from .lto import LTO_BRIEF, lto_drafts, lto_hero, run_lto
from .reroll import reroll
from .models import REGISTRY, get_model, model_summary
from .pipeline import generate_video, list_jobs
from .pricing import estimate_cost
from .readiness import readiness
from .router import Brief, route


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    elif isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, indent=2, default=str))


def _table(rows: list[list[Any]], header: list[str]) -> str:
    cols = [header] + [[str(c) for c in r] for r in rows]
    w = [max(len(r[i]) for r in cols) for i in range(len(header))]
    line = lambda r: "  ".join(c.ljust(w[i]) for i, c in enumerate(r))  # noqa: E731
    return "\n".join([line(header), line(["-" * x for x in w])] + [line(r) for r in cols[1:]])


def cmd_models(a: argparse.Namespace) -> None:
    if a.json:
        return _print([model_summary(m) for m in REGISTRY.values()], True)
    rows = []
    for m in REGISTRY.values():
        prices = ", ".join(f"{k} ${v}" for k, v in m.price_per_second.items())
        rows.append([m.display_name, "/".join(x.split("-")[0] for x in m.modes), m.offering,
                     "yes" if m.native_audio else "no", prices])
    print(_table(rows, ["Model", "Modes", "Offering", "Audio", "USD per generated second (preview)"]))
    print("\nEstimates only - not billing guarantees. MiniMax output can run ~0.7 s longer than requested.")


def cmd_catalog(a: argparse.Namespace) -> None:
    items = catalog.search(a.query or "")
    if a.json:
        return _print(items, True)
    print(_table([[p["sku"], p["name"], p["vertical"], p["image_status"]] for p in items],
                 ["SKU", "Name", "Vertical", "PIM image"]))


def cmd_scene(a: argparse.Namespace) -> None:
    _print(catalog.compose_scene(a.sku, a.channel, a.demographic, a.concept, a.audio), True)


def _brief_from_args(a: argparse.Namespace) -> Brief:
    if a.brief:
        with open(a.brief, encoding="utf-8") as f:
            return Brief.from_dict(json.load(f))
    if a.sku:
        sc = catalog.compose_scene(a.sku, a.channel, needs_audio=a.audio or None)
        return Brief(prompt=sc["prompt"], channel=a.channel, source=sc["source"], image_path=sc["image_path"],
                     stage=a.stage, needs_audio=sc["needs_audio"], strict_layout=sc["strict_layout"] or a.strict_layout,
                     physical_interaction=sc["physical_interaction"], volume=a.volume, budget_usd_per_clip=a.budget,
                     duration=a.duration, allow_post_crop=a.allow_post_crop, sku_id=a.sku)
    return Brief(prompt=a.prompt or "product video", channel=a.channel, source="pim_image" if a.image else "text",
                 image_path=a.image, stage=a.stage, needs_audio=a.audio, strict_layout=a.strict_layout,
                 physical_interaction=a.physical, volume=a.volume, budget_usd_per_clip=a.budget,
                 duration=a.duration, allow_post_crop=a.allow_post_crop)


def cmd_route(a: argparse.Namespace) -> None:
    d = route(_brief_from_args(a))
    if a.json:
        return _print(d.to_dict(), True)
    print(f"-> {d.model_name}  [{d.mode}, {d.aspect_ratio}, {d.resolution}, {d.duration}s, audio={d.audio}]")
    print(f"   est ${d.estimate_usd:.4f} (high ${d.estimate_high_usd:.4f})"
          + (f", batch ${d.batch_estimate_usd:.2f}" if d.batch_estimate_usd else ""))
    print(f"   aspect policy: {d.aspect_policy}")
    for r in d.rationale:
        print(f"   - {r}")
    for sk in d.skipped:
        print(f"   x skipped {sk['model']}: {sk['reason']}")
    if d.companions:
        print(f"   + companion shot(s): {', '.join(d.companions)}")


def cmd_estimate(a: argparse.Namespace) -> None:
    e = estimate_cost(get_model(a.model), a.duration if a.duration != "auto" else "auto", a.resolution, a.audio,
                      a.voice_control)
    if a.json:
        return _print(e.to_dict(), True)
    print(f"{a.model}: {e.seconds:g}s @ {e.price_key} ${e.usd_per_second}/s = ${e.estimate_usd:.4f} "
          f"(high ${e.estimate_high_usd:.4f}) x{a.count} = ${e.estimate_usd * a.count:.2f}")
    for c in e.caveats:
        print(f"  * {c}")


def cmd_generate(a: argparse.Namespace) -> None:
    dur: Any = a.duration
    if dur not in (None, "auto"):
        dur = float(dur)
    job = generate_video(a.model, a.prompt, a.image, dur, aspect_ratio=a.aspect, resolution=a.resolution,
                         audio=a.audio, mode=a.mode, sku=a.sku, cache_key=a.cache_key,
                         on_event=None if a.json else print)
    _print(job if a.json else {k: job.get(k) for k in ("job_id", "status", "provenance", "output", "estimate", "notes")},
           True)


def cmd_qa(a: argparse.Namespace) -> None:
    _print(qa.evaluate(job_id=a.job, video_path=a.video, sku=a.sku, brand=a.brand, prompt=a.prompt or ""), True)


def cmd_ledger(a: argparse.Namespace) -> None:
    if a.reset:
        ledger.reset()
        print("ledger cleared")
        return
    r = ledger.report()
    if a.json:
        return _print(r, True)
    rows = [[k, int(v["clips"]), f"{v['seconds']:g}", f"${v['estimate_usd']:.4f}"] for k, v in r["by_model"].items()]
    print(_table(rows, ["Model", "Clips", "Seconds", "Estimate"]))
    print(f"\nTotal estimate ${r['estimated_total_usd']:.4f} across {r['clips']} clips; backends {r['by_backend']}")
    print(r["note"])


def cmd_jobs(a: argparse.Namespace) -> None:
    jobs = list_jobs(limit=a.limit)
    if a.json:
        return _print(jobs, True)
    print(_table([[j["job_id"], j["status"], j.get("provenance", ""), j.get("output", "")] for j in jobs],
                 ["Job", "Status", "Provenance", "Output"]))


def cmd_readiness(a: argparse.Namespace) -> None:
    r = readiness(a.check_auth)
    if a.json:
        return _print(r, True)
    print(f"mode={r['mode']}  live_ready={r['live_ready']}")
    for c in r["checks"]:
        print(f"  [{'ok' if c['ok'] else '--'}] {c['check']}: {c['detail']}")
    print("\nManual prerequisites (not verifiable from here):")
    for p in r["manual_prerequisites"]:
        print(f"  - {p}")


def _say(a: argparse.Namespace):
    return None if a.json else (lambda m: print("  " + m))


def _header() -> None:
    s = get_settings()
    print(f"\nSKU to Scene - Step 2 two-tier LTO ({'LIVE Foundry' if s.live else 'MOCK: simulated clips, no Azure calls'})")
    print(f'Brief: "{LTO_BRIEF}"\n')


def _print_drafts(r: dict[str, Any]) -> None:
    print("\nDrafts:")
    rows = []
    for d in r["drafts"]:
        q = d.get("qa", {})
        sc = (q.get("scores") or {}).get("prompt_adherence", "n/a")
        rows.append([f"#{d['variant']}", d["model_name"], f"${d['estimate']['estimate_usd']:.3f}",
                     f"{d['elapsed_s']}s", sc, q.get("verdict", "-"), d["provenance"], d["output"]])
    print(_table(rows, ["Var", "Model", "Est", "Time", "Adherence", "QA", "Provenance", "Output"]))
    c = r["costs"]
    print(f"\nTurbo drafts ${c['turbo_drafts_estimate_usd']:.2f} vs ${c['same_turbo_drafts_on_h3_max_usd']:.2f} "
          f"on H3 Max (50%). {c['note']}")


def _print_clip(title: str, f: dict[str, Any]) -> None:
    q = f.get("qa", {})
    print(f"{title}: {f['model_name']} {f['mode']} audio={f.get('audio')} est ${f['estimate']['estimate_usd']:.4f} "
          f"-> {f['output']} [{f['provenance']}] QA={q.get('verdict', '-')} "
          f"publish_approved={q.get('publish_approved', False)}")
    if q.get("disclaimer"):
        print(f"  QA note: {q['disclaimer']}")


def _print_hero(r: dict[str, Any]) -> None:
    print()
    _print_clip(f"Hero (variant #{r['selected_variant']})", r["final"])
    for x in r.get("rerolls", []):
        _print_clip(f"Re-roll {x['reroll_attempt']}", x)
    c = r["costs"]
    print(f"\nDrafts ${c['drafts_estimate_usd']:.2f} + hero ${c['final_estimate_usd']:.2f} + re-rolls "
          f"${c['reroll_estimate_usd']:.2f} = ${c['total_estimate_usd']:.2f}. {c['note']}")
    if "simulated" in r["provenance"]:
        print("All clips above are SIMULATED placeholders, not Foundry renders.")


def cmd_demo_lto(a: argparse.Namespace) -> None:
    if not a.json:
        _header()
    if a.step == "drafts":
        r = lto_drafts(on_event=_say(a), evaluate=not a.no_qa)
        if a.json:
            return _print(r, True)
        _print_drafts(r)
        print(f"\nSession {r['session_id']}: pick a variant, then run  sku2scene demo lto --step hero --select N")
        return
    if a.step == "hero":
        r = lto_hero(a.select, a.session, on_event=_say(a), evaluate=not a.no_qa, max_rerolls=a.max_rerolls)
        return _print(r, True) if a.json else _print_hero(r)
    r = run_lto(select=a.select, on_event=_say(a), evaluate=not a.no_qa, max_rerolls=a.max_rerolls)
    if a.json:
        return _print(r, True)
    _print_drafts(r)
    _print_hero(r)


def cmd_reroll(a: argparse.Namespace) -> None:
    _print(reroll(a.job, max_rerolls=a.max_rerolls, on_event=_say(a)), True)

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sku2scene", description="SKU to Scene - AI-directed retail video on Foundry")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("models", help="list the five fal models, prices and capabilities").set_defaults(fn=cmd_models)
    c = sub.add_parser("catalog", help="search the mock PIM catalog")
    c.add_argument("query", nargs="?")
    c.set_defaults(fn=cmd_catalog)
    sc = sub.add_parser("scene", help="@retail-merchandiser: compose a structured scene brief for a SKU")
    sc.add_argument("sku")
    sc.add_argument("--channel", default="signage", choices=["tiktok", "signage", "pdp"])
    sc.add_argument("--demographic", default="adults 25-44")
    sc.add_argument("--concept")
    sc.add_argument("--audio", action="store_true", default=None)
    sc.set_defaults(fn=cmd_scene)

    r = sub.add_parser("route", help="@foundry-router: pick a model for a brief and explain why")
    r.add_argument("--brief", help="JSON brief file (see briefs/)")
    r.add_argument("--sku")
    r.add_argument("--prompt")
    r.add_argument("--image")
    r.add_argument("--channel", default="signage")
    r.add_argument("--stage", default="final", choices=["draft", "final"])
    r.add_argument("--audio", action="store_true")
    r.add_argument("--strict-layout", action="store_true")
    r.add_argument("--physical", action="store_true")
    r.add_argument("--volume", type=int, default=1)
    r.add_argument("--budget", type=float)
    r.add_argument("--duration", type=float)
    r.add_argument("--allow-post-crop", action="store_true")
    r.set_defaults(fn=cmd_route)

    e = sub.add_parser("estimate", help="estimate per-second cost")
    e.add_argument("model")
    e.add_argument("--duration", default=None)
    e.add_argument("--resolution")
    e.add_argument("--audio", action="store_true")
    e.add_argument("--voice-control", action="store_true")
    e.add_argument("--count", type=int, default=1)
    e.set_defaults(fn=cmd_estimate)

    g = sub.add_parser("generate", help="generate one clip (mock or live)")
    g.add_argument("model")
    g.add_argument("prompt")
    g.add_argument("--image")
    g.add_argument("--duration")
    g.add_argument("--aspect", default="16:9")
    g.add_argument("--resolution")
    g.add_argument("--audio", action="store_true")
    g.add_argument("--mode", choices=["text-to-video", "image-to-video", "reference-to-video"])
    g.add_argument("--sku")
    g.add_argument("--cache-key")
    g.set_defaults(fn=cmd_generate)

    q = sub.add_parser("qa", help="@brand-qa: evaluate a clip against brand guidelines")
    q.add_argument("--job")
    q.add_argument("--video")
    q.add_argument("--sku")
    q.add_argument("--brand")
    q.add_argument("--prompt")
    q.set_defaults(fn=cmd_qa)

    lg = sub.add_parser("ledger", help="cost report across all runs (single meter view)")
    lg.add_argument("--reset", action="store_true")
    lg.set_defaults(fn=cmd_ledger)
    j = sub.add_parser("jobs", help="recent jobs")
    j.add_argument("--limit", type=int, default=20)
    j.set_defaults(fn=cmd_jobs)
    rd = sub.add_parser("readiness", help="live-mode readiness (read-only)")
    rd.add_argument("--check-auth", action="store_true")
    rd.set_defaults(fn=cmd_readiness)

    rr = sub.add_parser("reroll", help="@brand-qa: bounded re-roll of a clip whose QA verdict is fail")
    rr.add_argument("job")
    rr.add_argument("--max-rerolls", type=int, default=2)
    rr.set_defaults(fn=cmd_reroll)

    d = sub.add_parser("demo", help="scripted demo flows")
    dsub = d.add_subparsers(dest="demo", required=True)
    lto = dsub.add_parser("lto", help="Step 2: two-tier cost & fidelity LTO flow")
    lto.add_argument("--select", type=int, default=2)
    lto.add_argument("--step", choices=["all", "drafts", "hero"], default="all",
                     help="drafts = stop for presenter selection; hero = render the selected variant")
    lto.add_argument("--session", help="draft session id (default: latest)")
    lto.add_argument("--max-rerolls", type=int, default=1)
    lto.add_argument("--no-qa", action="store_true")
    lto.set_defaults(fn=cmd_demo_lto)
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = build_parser().parse_args(argv)
    try:
        a.fn(a)
    except (KeyError, ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
