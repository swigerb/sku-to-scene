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

## Quick tour

<div align="center">

https://github.com/user-attachments/assets/54a3f1b5-cd44-4fe4-9893-df6bf100e777

</div>

<div align="center">
  <sub><strong>2 min 54 s</strong> &nbsp;·&nbsp; Microsoft Ava AI narration &nbsp;·&nbsp; <a href="https://github.com/swigerb/sku-to-scene/releases/download/media-v1/sku-to-scene-sizzle.mp4">1080p60 original</a> &nbsp;·&nbsp; <a href="https://github.com/swigerb/sku-to-scene/releases/download/media-v1/sku-to-scene-sizzle.srt">Captions</a><br />
  From approved product imagery to retail video concepts: QSR and coffee, apparel and lifestyle,
  home improvement, grocery, pharmacy and consumer goods. See specialist Copilot agents,
  explainable model routing, authentic recorded renders and visible quality evidence.<br />
  Fictional brands; cached demo footage, not live generation. Original clip audio is muted.
  Automated screening is not publication approval; human sign-off is required.
  fal processing is preview, outside Microsoft facilities, and subject to the <a href="docs/governance.md">governance caveats</a>.
  </sub>
</div>

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

- **The browser demo** replays **cached, authentic Foundry renders** with their recorded QA evidence. It
  makes no cloud calls and generates nothing new. Start with **Watch overview** (the narrated video with
  captions), **Start guided demo** (step-by-step, with Previous/Next/Play/Restart/Fullscreen) or **Explore
  scenarios**. Each of the four RCG areas has its own deliberate guide and fictional account briefs. Previewing
  never selects; only Northwind concept #2 has the recorded coffee hero. Other areas offer their existing PIM
  heroes; new text-only drafts are preview-only. Light/dark theme choices are explicit and remembered.
- **Automated QA is a screening aid, not approval.** Original eight verdicts: **2 pass / 6 fail**; every clip still
  needs human sign-off (`publish_approved` is false).
- **Costs are estimates** (preview list price × requested seconds), not Azure bills.
- **AI evaluations (Foundry Evals v1) were run** over the cached clips, a negative control and the router's
  decisions. They use a disclosed two-stage design (vision observations, then cloud text graders), sit next to the
  original verdicts and never change them. See [Foundry Evaluations](docs/foundry-evaluations-plan.md).
- **Human review blocks the Northwind hero:** its native café/frothing audio is loud and does not match the
  picture. Draft concept #2 has no audio track (not requested).
- **All 14 fictional accounts have a playable recorded example.** The nine new ones are silent text-to-video
  exploratory drafts: preview-only (no approved PIM hero), **Awaiting human review — not approved** and
  **Not yet evaluated** by Foundry Evaluations. Eight passed automated screening; Proseware's best attempt
  still fails (product fidelity 0.72) and is labelled as a failed draft. Safe failed attempts appear as
  **QA learning examples**; attempts with on-screen text, real-brand logos or trade dress, or Content Safety
  flags are withheld (evidence only, media not published). See [verification](docs/verification.md#account-drafts).
  The original eight clips and v1 evidence are unchanged.

**Fictional brands and products. Real company names identify representative retail segments and cite public
sources only; no affiliation, endorsement, trademarks, or customer data.**

## The agents

| Agent | Role |
| --- | --- |
| `@retail-merchandiser` | SKU metadata + demographic + channel (TikTok 9:16, Signage 16:9, PDP 1:1) → scene prompt, camera directives, audio cues |
| `@foundry-router` | Applies guardrails, picks the fal endpoint, estimates per-second cost and dispatches via MCP |
| `@brand-qa` | Scores extracted frames against the approved catalog image; fails closed; bounded re-roll on LTX-2.5 Pro or Kling v3 Pro |

## Why five model variants matter

| Area | Representative account | Fictional example | Video need / model |
| --- | --- | --- | --- |
| QSR / coffee / convenience | Starbucks | Northwind Coffee | Seasonal launch: three drafts → recorded Kling hero |
| QSR / coffee / convenience | McDonald's | Tailspin Burger Co. | Value-bundle creative / LTX-2.5 Fast |
| QSR / coffee / convenience | 7-Eleven | Coho Corner Market | Fresh-food handoff / MiniMax Turbo |
| Apparel / home decor | Gap | Fabrikam | Approved jacket lookbook / Kling |
| Apparel / home decor | TJX | VanArsdel Finds | Changing assortment discovery / Turbo |
| Apparel / home decor | Target | Tailwind Traders | Home-decor newness / LTX Fast |
| Apparel / home decor | Costco | Wide World Wholesale | Warehouse essentials / Turbo |
| Home / electronics | The Home Depot | Alpine Pro Supply | Contoso Pro drill in context / Kling |
| Home / electronics | Lowe's | Zava DIY | Fabrikam Home patio layout / H3 Max (text-only preview) |
| Home / electronics | Best Buy | Southridge Electronics | Litware laptop content / H3 Max |
| Home / electronics | Staples | Proseware Workplace Supply | Workplace-kit arrangement / H3 Max |
| Grocery / pharmacy | Walgreens | Woodgrove Wellness | Calm seasonal wellness screen / Turbo |
| Grocery / pharmacy | Kroger | Best For You Market | Weekly meal inspiration / Turbo |
| Grocery / pharmacy | Albertsons | Munson's Markets | Localized grocery basket / Turbo |

Each example is inspired by the qualitative public priorities cited in
[`catalog/accounts.json`](catalog/accounts.json), not an assertion about a relationship or private plans.
Routing rules and prices: [model-routing](docs/model-routing.md).

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
| [Foundry Evaluations](docs/foundry-evaluations-plan.md) | Executed v1 runs, results, cost, opt-in runner, next phases |
| [ComfyUI](docs/comfyui.md) | Optional visual track |

## Sources

- [Building the next generation of multimodal AI experiences with fal in Microsoft Foundry](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/building-the-next-generation-of-multimodal-ai-experiences-with-fal-in-microsoft-/4570032)
- [Direct your next shot with fal on Microsoft Foundry and ComfyUI](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/direct-your-next-shot-with-fal-on-microsoft-foundry-and-comfyui/4570230)
- [Microsoft Learn: Enable fal models in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/fal-ai-models/enable-fal-models)

## License

MIT. Product images are AI-generated for fictional brands. SKU to Scene logo and icon assets are in
[`assets/brand/`](assets/brand/).