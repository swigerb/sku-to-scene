# Demo prep checklist

## Before the day (T-2 weeks)

- [ ] **Administrator:** review the fal preview terms (data processed outside Microsoft; Microsoft DPA doesn't
      apply), then decide whether to register `Fal.EnableDeploy` on a **non-production demo subscription**.
- [ ] Provision the endpoints: `Kling v3 Pro` (US Data Zone), `LTX-2.5 Fast`, `LTX-2.5 Pro`, `MiniMax H3 Max`
      and `MiniMax H3 Max Turbo` (Global Standard). Verify region and quota; tiers 1–4 = 2 RPM. See
      [foundry-setup.md](foundry-setup.md).
- [ ] Assign Cognitive Services User to the presenter identity; run `sku2scene readiness --check-auth`.
- [ ] Optional: deploy an Azure OpenAI vision model and a Content Safety resource for measured QA.

## Build the fallbacks (T-1 week)

- [ ] `python scripts\precache.py` (plan and cost), then `python scripts\precache.py --yes` to replace the
      simulated clips with real renders. Confirm `provenance: "foundry"` in `demo-cache/manifest.json`.
- [ ] If live isn't available, keep the simulated clips and **say so on stage**.
- [ ] Watch every cached clip once. Check the hero cup label, logo and condensation.

## Day of (T-1 hour)

- [ ] Run `pip install -e ".[dev]"` into `.venv`, then `pytest -q`.
- [ ] `python scripts\verify_mcp_stdio.py` must print PASS. Restart the Copilot app so it picks up `.mcp.json`.
- [ ] Copilot app: open the repo, confirm the `sku-to-scene` MCP tools are listed, and set the model to
      **Auto → Fusion (High)** (or the Squad fallback).
- [ ] Rehearse `sku2scene demo lto --step drafts` / `--step hero --select 2`; clear `.sku2scene/` afterwards for
      a clean ledger.
- [ ] Set `SKU2SCENE_MOCK_LATENCY_SCALE` (1 = realistic pacing).
- [ ] Have [demo-script.md](demo-script.md) open on the second screen.
