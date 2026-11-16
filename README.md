<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/web/logo-horizontal-dark.png">
    <img src="assets/brand/web/logo-horizontal-light.png" alt="SKU to Scene" width="480">
  </picture>
</p>

<p align="center"><strong>AI-Directed Retail Video at Enterprise Scale</strong></p>

<p align="center">
  <a href="https://swigerb.github.io/sku-to-scene/"><strong>▶ Open the browser demo</strong></a> ·
  <a href="docs/demo-script.md">Demo script</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/verification.md">Verification</a>
</p>

SKU to Scene turns static product catalog assets (approved PIM imagery and text briefs) into channel-ready
video through an **agent-orchestrated creative supply chain**. Three GitHub Copilot agents, run as a
[Squad](https://github.com/bradygaster/squad) team with Copilot Fusion model routing, send each merchandising
brief to the right **fal video model in Microsoft Foundry** — `Kling v3 Pro`, `LTX-2.5 Fast`, `LTX-2.5 Pro`,
`MiniMax H3 Max` or `MiniMax H3 Max Turbo` — based on latency, budget, audio needs and source asset.

> [!WARNING]
> **fal models on Foundry are a preview and run outside Microsoft facilities.** Enabling them means you elect to
> send data to fal; **Microsoft customer agreements, the Product Terms/DPA and Microsoft certifications do not
> apply** to that processing. An administrator must review fal's terms before registering `Fal.EnableDeploy`.
> See [governance](docs/governance.md).

## What you're looking at

- **The browser demo** replays eight **cached, authentic Foundry renders** with their recorded QA evidence. It
  makes no cloud calls and generates nothing new. Only the recorded Variant #2 has a Kling hero render.
- **Automated QA is a screening aid, not approval.** Recorded verdicts: **2 pass / 6 fail**; every clip still
  needs human sign-off (`publish_approved` is false).
- **Costs are estimates** (preview list price × requested seconds), not Azure bills.
- Foundry Evaluations is **not** integrated yet — see the [plan](docs/foundry-evaluations-plan.md).

## The agents

| Agent | Role |
| --- | --- |
| `@retail-merchandiser` | SKU metadata + demographic + channel (TikTok 9:16, Signage 16:9, PDP 1:1) → scene prompt, camera directives, audio cues |
| `@foundry-router` | Applies guardrails, picks the fal endpoint, estimates per-second cost and dispatches via MCP |
| `@brand-qa` | Scores extracted frames against the approved catalog image; fails closed; bounded re-roll on LTX-2.5 Pro or Kling v3 Pro |

## Why five model variants matter

| RCG vertical | Representative accounts* | Use case | Foundry model(s) |
| --- | --- | --- | --- |
| Apparel & Home Decor | Gap, TJX, Target, Costco | PDP image-to-video lookbooks | **Kling v3 Pro** (I2V) |
| QSR, Coffee & C-Store | McDonald's, Starbucks, 7-Eleven | Rapid LTO social ads with sound | **LTX-2.5 Fast → Pro** / **Kling v3 Pro** |
| Home Improvement & Electronics | The Home Depot, Lowe's, Best Buy, Staples | In-context and assembly previews | **Kling v3 Pro + MiniMax H3 Max** |
| Grocery & Pharmacy | Kroger, Albertsons, Walgreens | High-volume weekly circulars and endcaps | **MiniMax H3 Max Turbo** (half H3 Max's per-second rate) |

\*Illustrative account types only. All demo brands are fictional (Northwind Coffee, Contoso Pro, Fabrikam,
Woodgrove Wellness). Routing rules and prices: [model-routing](docs/model-routing.md).

## Quickstart (no Azure, no spend)

Requires Python 3.11+ and ffmpeg on `PATH`.

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:SKU2SCENE_MODE = "mock"; $env:SKU2SCENE_QA_EVALUATORS = "off"   # rehearsal: no cloud calls
pytest -q
sku2scene route --brief briefs\qsr-lto-pumpkin-cold-brew.json
sku2scene demo lto --step drafts
sku2scene demo lto --step hero --select 2
sku2scene ledger
```

In the Copilot app, the `sku-to-scene` MCP server (`.mcp.json`) is preconfigured for the same no-spend rehearsal.
Preview the static site locally with `python scripts\build_site.py` and
`python -m http.server 8765 --directory _site`.

## Live mode (billable)

Live generation was validated once on all five variants ([record](docs/live-validation.md)). To use your own
Foundry account: deploy the models, assign **Foundry User**, put your endpoint and tenant in an ignored `.env`,
set `SKU2SCENE_MODE=live`, run `pip install -e ".[live]"` and `sku2scene readiness --check-auth`.
Step-by-step: [foundry-setup](docs/foundry-setup.md). No `FAL_KEY` is used; auth is Entra ID.

## Documentation

| Doc | Covers |
| --- | --- |
| [Demo script](docs/demo-script.md) · [Prep checklist](docs/prep-checklist.md) | 15-minute executive pitch and rehearsal |
| [Architecture](docs/architecture.md) | Flow, CLI/MCP tools, agents, Fusion routing, static site |
| [Model routing](docs/model-routing.md) | Routes, payload constraints, pricing, routing policy |
| [Foundry setup](docs/foundry-setup.md) | Provisioning, RBAC, auth troubleshooting, optional QA vision |
| [Governance](docs/governance.md) | fal data handling, fail-closed QA, provenance |
| [Live validation](docs/live-validation.md) | Measured smoke runs, cache, QA results, spend |
| [Verification & troubleshooting](docs/verification.md) | Remaining limitations, recovery, bug-report template |
| [Foundry Evaluations plan](docs/foundry-evaluations-plan.md) | Phased plan (not yet implemented) |
| [ComfyUI](docs/comfyui.md) | Optional visual track |

## Sources

- [Building the next generation of multimodal AI experiences with fal in Microsoft Foundry](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/building-the-next-generation-of-multimodal-ai-experiences-with-fal-in-microsoft-/4570032)
- [Direct your next shot with fal on Microsoft Foundry and ComfyUI](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/direct-your-next-shot-with-fal-on-microsoft-foundry-and-comfyui/4570230)
- [Microsoft Learn: Enable fal models in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/fal-ai-models/enable-fal-models)

## License

MIT. Product images are AI-generated for fictional brands. SKU to Scene logo and icon assets are in
[`assets/brand/`](assets/brand/).