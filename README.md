<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/web/logo-horizontal-dark.png">
    <img src="assets/brand/web/logo-horizontal-light.png" alt="SKU to Scene" width="480">
  </picture>
</p>

<p align="center"><strong>AI-Directed Retail Video for product catalogs</strong><br />
<sub>Curated technical reference preview: not production-qualified and not approved for customer campaigns</sub></p>

<p align="center">
  <a href="https://swigerb.github.io/sku-to-scene/"><strong>▶ Open the browser demo</strong></a> ·
  <a href="docs/demo-script.md">Demo script</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/verification.md">Verification</a>
</p>

## Quick tour

The video below is the **original recorded overview v1** (the browser's **Watch original overview v1 · 2:54**).
Its footage, Ava narration, embedded captions and original-eight results are unchanged. Its statements about
the original eight clips are historical, not claims about the curated preview. The browser's
[versioned demo dispositions](demo-cache/evaluations/demo-dispositions-v1.json) identify selected presentation
derivatives separately from native originals and historical screening, and the
[curated reference-preview scope v1](demo-cache/evaluations/curated-release-v1.json) records which examples are
featured and which are learning cases.

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

SKU to Scene shows how static product catalog assets (approved PIM imagery and text briefs) can become short
retail video concepts through an **agent-orchestrated creative supply chain**; every output still needs review. Three GitHub Copilot agents, run as a
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
  makes no cloud calls and generates nothing new. Start with **Watch original overview v1 · 2:54** (the narrated
  video with captions), **Start guided demo** or **Explore scenarios**. One selected fictional account tells one story at a
  time, with a compact brief and one active recording. Northwind has Brief → Concepts → Recorded result → Review;
  the other examples skip Concepts because they have only one recording. Previewing never selects:
  only explicit selection of Northwind concept #2 unlocks its recorded coffee hero. Text-only examples reach
  review without pretending to have a PIM hero. The gallery features eight presentations by default; six learning
  cases sit in a collapsed **Learning cases and known limitations** section within their categories. The
  **Change example** control groups all 14 as Featured presentations and Learning cases; every default entry,
  including `#guide/<area>`, opens a featured example, and direct links to learning cases state their unresolved defect.
  The gallery uses compact recorded-poster cards and a single focused preview dialog; full briefs, public
  sources and historical recordings are in details. Returning from a walkthrough restores the browsing context.
  Technical evidence defaults to the current recording, with an explicit all-attempts scope.
  Restart and Fullscreen are under Options; light/dark theme choices are explicit and remembered.
- **This is a curated reference preview, not full remediation.** [Curated scope v1](demo-cache/evaluations/curated-release-v1.json)
  features **8 fictional-demo presentations** (Northwind silent derivative, Tailspin, Coho, Fabrikam, VanArsdel,
  Zava silent generic-layout derivative, Proseware with its explicit background variance, Munson). **6 learning
  cases** (Alpine, Woodgrove, Southridge, Tailwind, Wide World, Best For You) keep their original recordings,
  evidence and unresolved defects; each still needs a replacement. **6 replacement attempts were rejected and none
  was selected**; they stay unpublished. These are different populations, not a total. No example has
  customer-campaign approval, and `release_ready` in the dispositions keeps its full-remediation meaning (false).
- **Automated QA is a screening aid, not approval.** Original eight verdicts: **2 pass / 6 fail**; every clip still
  needs human sign-off (`publish_approved` is false).
- **Costs are estimates** (preview list price × requested seconds), not Azure bills. The release pass's
  **$3.7032** is conservative consumed reservations, not an Azure invoice.
- **AI evaluations (Foundry Evals v1) were run** over the cached clips, a negative control and the router's
  decisions. They use a disclosed two-stage design (vision observations, then cloud text graders), sit next to the
  original verdicts and never change them. See [Foundry Evaluations](docs/foundry-evaluations-plan.md).
  The later [targeted checks](demo-cache/evaluations/targeted-evals-v2.json) (Zava **partial**; a grocery
  rationale and a deliberately unsupported control) are bounded direct Azure OpenAI evaluations, not Foundry
  Evals service runs.
- **Human review blocks the native Northwind hero:** its café/frothing audio is loud and does not match the
  picture. The browser features a separately identified **silent presentation derivative** of that render;
  removing the audio does not make the native audio acceptable and is not campaign approval. The retained native
  original and its finding stay in source history. Draft concept #2 has no audio track (not requested).
- **All 14 fictional accounts keep a playable recorded example; playable is not repaired.** The nine new ones are silent text-to-video
  exploratory drafts: preview-only (no approved PIM hero), **Awaiting human review — not approved** and
  **Not yet evaluated** by Foundry Evaluations. All nine selected new-account clips passed automated screening,
  including Proseware's realistic-office replacement. This does not erase review concerns: Southridge retains
  its original studio clip and order disclosure because neither realistic-room replacement qualified.
  Safe failed earlier attempts appear as **QA learning examples** (a different idea from the six curated
  learning cases, which are retained selected recordings); text, trade-dress, Content Safety and agent-observed
  product defects can withhold an attempt even when AI screening passed. Evidence stays visible.
  See [verification](docs/verification.md#account-drafts).
  The original eight clips and v1 evidence are unchanged.

**Fictional brands and products. Real company names identify representative retail segments and cite public
sources only; no affiliation, endorsement, trademarks, or customer data.**

### Aim for photographic realism

Use real-world environments, believable material detail, natural lighting and photographic camera language,
not only the word "photorealistic." Approved real product photography with **Kling v3 Pro image-to-video**
is the strongest lever for recognizable products and realistic context. Busier scenes increase accidental
text, logo and trade-dress risk; keep QA and human inspection focused on those details, object identity,
physics and framing. Realistic-looking footage remains AI-generated and must be described honestly.

## The agents

| Agent | Role |
| --- | --- |
| `@retail-merchandiser` | SKU metadata + demographic + channel (TikTok 9:16, Signage 16:9, PDP 1:1) → scene prompt, camera directives, audio cues |
| `@foundry-router` | Applies guardrails, picks the fal endpoint, estimates per-second cost and dispatches via MCP |
| `@brand-qa` | Scores extracted frames against the approved catalog image; fails closed; bounded re-roll on LTX-2.5 Pro or Kling v3 Pro |

## Why five model variants matter

| Area | Representative account | Fictional example | Video need / model | Curated role |
| --- | --- | --- | --- | --- |
| QSR / coffee / convenience | Starbucks | Northwind Coffee | Seasonal launch: three drafts → recorded Kling hero | Featured |
| QSR / coffee / convenience | McDonald's | Tailspin Burger Co. | Value-bundle creative / LTX-2.5 Fast | Featured |
| QSR / coffee / convenience | 7-Eleven | Coho Corner Market | Fresh-food handoff / MiniMax Turbo | Featured |
| Apparel / home decor | Gap | Fabrikam | Approved jacket lookbook / Kling | Featured |
| Apparel / home decor | TJX | VanArsdel Finds | Changing assortment discovery / Turbo | Featured |
| Apparel / home decor | Target | Tailwind Traders | Home-decor newness / LTX Fast | Learning case |
| Apparel / home decor | Costco | Wide World Wholesale | Warehouse essentials / Turbo | Learning case |
| Home / electronics | The Home Depot | Alpine Pro Supply | Contoso Pro drill in context / Kling | Learning case |
| Home / electronics | Lowe's | Zava DIY | Fabrikam Home patio layout / H3 Max (text-only preview) | Featured |
| Home / electronics | Best Buy | Southridge Electronics | Litware laptop content / H3 Max | Learning case |
| Home / electronics | Staples | Proseware Workplace Supply | Workplace-kit arrangement / H3 Max | Featured |
| Grocery / pharmacy | Walgreens | Woodgrove Wellness | Calm seasonal wellness screen / Turbo | Learning case |
| Grocery / pharmacy | Kroger | Best For You Market | Weekly meal inspiration / Turbo | Learning case |
| Grocery / pharmacy | Albertsons | Munson's Markets | Localized grocery basket / Turbo | Featured |

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

## Live mode (optional, deliberate and billable)

The browser demo and the recommended presenter path need no live calls. Live generation was validated once on
all five variants ([record](docs/live-validation.md)). To use your own
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