# Demo prep checklist

## Before the day (T-2 weeks)

- [ ] **Administrator:** review the fal preview terms (data processed outside Microsoft; Microsoft DPA doesn't
      apply), then decide whether to register `Fal.EnableDeploy` on a **non-production demo subscription**.
- [ ] Provision the endpoints: `Kling v3 Pro` (US Data Zone), `LTX-2.5 Fast`, `LTX-2.5 Pro`, `MiniMax H3 Max`
      and `MiniMax H3 Max Turbo` (Global Standard). Verify region and quota; tiers 1–4 = 2 RPM. See
      [foundry-setup.md](foundry-setup.md).
- [ ] Assign **Foundry User** on the account to the presenter identity; run `sku2scene readiness --check-auth`.
- [ ] Optional: deploy an Azure OpenAI vision model and a Content Safety resource for measured QA.

## Review the cached renders (T-1 week)

- [ ] The cache already contains eight authentic Foundry renders. To regenerate them, review
      `python scripts\precache.py` (plan and cost), then use `SKU2SCENE_MODE=live` and
      `python scripts\precache.py --yes`. This submits **new billable generation jobs**.
- [ ] On stage, identify replayed clips as **cached Foundry renders, not live generation**. Quote the recorded
      measured QA verdicts: **2 pass / 6 fail**. All clips require human sign-off before publication.
- [ ] Preserve the authentic cache and its evidence. `scripts\build_placeholders.py` refuses to overwrite
      Foundry entries unless explicitly passed `--force`, which replaces the clips and manifest with simulated content.
- [ ] Watch every cached clip once. Check the hero cup label, logo and condensation.

## Day of (T-1 hour)

- [ ] Open the browser demo, <https://swigerb.github.io/sku-to-scene/>, and press **▶ Replay walkthrough**. It is the zero-risk
      fallback: static cached media, no cloud calls.
- [ ] Run `pip install -e ".[dev]"` into `.venv`, then `pytest -q`.
- [ ] Confirm rehearsal is no-spend: the `sku-to-scene` MCP server runs with `SKU2SCENE_MODE=mock` and
      `SKU2SCENE_QA_EVALUATORS=off` (set in `.mcp.json`; process env overrides `.env`).
- [ ] `python scripts\verify_mcp_stdio.py` must print PASS. Restart the `sku-to-scene` MCP server (or the
      Copilot app) so it picks up `.mcp.json`.
- [ ] Copilot app: open the repo, confirm the `sku-to-scene` MCP tools are listed, and set the model to
      **Auto → Fusion (High)** (or the Squad fallback).
- [ ] Rehearse `sku2scene demo lto --step drafts` / `--step hero --select 2`; clear `.sku2scene/` afterwards for
      a clean ledger.
- [ ] Set `SKU2SCENE_MOCK_LATENCY_SCALE` (1 = realistic pacing).
- [ ] Have [demo-script.md](demo-script.md) open on the second screen.
