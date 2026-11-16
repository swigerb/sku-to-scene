# SKU to Scene

### AI-Directed Retail Video at Enterprise Scale

Turn static product catalog assets (approved PIM imagery and text briefs) into channel-ready video with an
**agent-orchestrated creative supply chain**. Three GitHub Copilot agents, run as a [Squad](https://github.com/bradygaster/squad)
team, route each merchandising brief to the right **fal video model in Microsoft Foundry**: `Kling v3 Pro`,
`LTX-2.5 Fast`, `LTX-2.5 Pro`, `MiniMax H3 Max` or `MiniMax H3 Max Turbo`. Routing weighs latency, budget, audio
needs and source asset type.

> [!WARNING]
> **The fal models on Foundry are a preview. They run outside Microsoft facilities.** Microsoft Learn says that
> enabling them means you *elect to send your data to fal*. **Microsoft customer agreements, the Microsoft Product
> Terms/DPA and Microsoft certifications do not apply** to that processing; fal's own terms do. Before anyone
> registers the `Microsoft.CognitiveServices/Fal.EnableDeploy` preview feature, an administrator must review and
> accept those terms. This repo never registers features, accepts terms or provisions resources for you. See
> [docs/governance.md](docs/governance.md).

> [!IMPORTANT]
> **All eight cached clips are authentic Foundry renders**, and live generation has been exercised on all five
> model variants. Check `demo-cache/manifest.json` for each clip's provenance: `foundry` means an authentic render;
> `simulated` denotes a visibly labelled local fallback. **Mock mode** replays cached generation without new jobs
> (configured QA evaluators can still call Azure).
> **Live mode** (`SKU2SCENE_MODE=live`) makes billable Foundry calls. Generation is not brand approval:
> vision scoring and Content Safety are screening aids, and human sign-off is still required.
> See [Current status](#current-status--blockers).

## Why five model variants matter: RCG routing

| RCG vertical | Representative accounts* | Demo use case | Foundry model(s) | Why this model wins |
| --- | --- | --- | --- | --- |
| Apparel & Home Decor | Gap, TJX, Target, Costco | **PDP image-to-video lookbooks**: animate a flat-lay or ghost-mannequin shot into fabric movement and showroom scenes | **Kling v3 Pro** (I2V) | Keeps SKU visual fidelity from the approved PIM image while adding fabric physics and camera motion |
| QSR, Coffee & C-Store | McDonald's, Starbucks, 7-Eleven | **Rapid LTO social ads**: steam, ice clinks, pour shots | **LTX-2.5 Fast → LTX-2.5 Pro** / **Kling v3 Pro** | Iterate concepts cheaply on the fast tier, then render the winner with native audio |
| Home Improvement & Electronics | The Home Depot, Lowe's, Best Buy, Staples | **In-context and assembly previews**: products on a job site or in a home office | **Kling v3 Pro + MiniMax H3 Max** | Kling handles physical interaction; H3 Max follows strict multi-object layout constraints |
| Grocery & Pharmacy | Kroger, Albertsons, Walgreens | **High-volume weekly circulars and digital endcaps** | **MiniMax H3 Max Turbo** | **Half the per-second rate of H3 Max**, so high-SKU weekly personalization is affordable |

\*Illustrative account types only. All demo brands are fictional: **Northwind Coffee**, **Contoso Pro**,
**Fabrikam** and **Woodgrove Wellness**. No real logos or trademarks are used.

Routing rules in `src/sku_to_scene/router.py`, each decision with an explanation:

- Drafting or A/B testing → `LTX-2.5 Fast` or `MiniMax H3 Max Turbo` (Turbo for volume)
- Approved hero image + native audio → `Kling v3 Pro` image-to-video
- Strict multi-object layout → `MiniMax H3 Max`
- Text brief + synchronized audio, final quality → `LTX-2.5 Pro`
- Budget caps reserve the worst-case duration (`auto` is priced at the model maximum). Unsupported settings are
  rejected or rerouted, never sent. One example: LTX has no 1:1, so square PDP output uses a documented
  crop policy.

Details, prices and sources: [docs/model-routing.md](docs/model-routing.md).

## Architecture

```mermaid
flowchart LR
  subgraph Copilot["GitHub Copilot app (Squad team, Fusion routing)"]
    M["@retail-merchandiser<br/>SKU + channel → scene brief"]
    R["@foundry-router<br/>route + cost guardrails"]
    Q["@brand-qa<br/>frames + reference → verdict"]
  end
  PIM[("catalog/ PIM mock<br/>assets/products/")] --> M
  M --> R
  R -->|MCP: sku-to-scene| S["Local MCP server<br/>(Python, stdio)"]
  CLI["sku2scene CLI<br/>(presenter fallback)"] --> S
  Comfy["ComfyUI nodes<br/>(visual track)"] --> S
  S -->|mock: replay| Cache[("demo-cache/<br/>Authentic Foundry renders")]
  S -->|cache miss only| Placeholder["Local SIMULATED placeholder"]
  S -->|live: Entra ID| F["Microsoft Foundry<br/>/providers/falai/v1/..."]
  F --> K[Kling v3 Pro] & L[LTX-2.5 Fast/Pro] & X[MiniMax H3 Max/Turbo]
  S --> Ledger[("run + cost ledger")]
  S --> Q
  Q -->|fail: bounded re-roll| R
  Q -.optional.-> AOAI["Azure OpenAI vision<br/>+ AI Content Safety"]
```

## Quickstart (mock mode, no Azure)

Requirements: Python 3.11+ and ffmpeg on `PATH` (for frame extraction and crops).

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q                                          # offline tests

sku2scene models                                   # the five models, routes, preview prices
sku2scene route --brief briefs\qsr-lto-pumpkin-cold-brew.json
sku2scene demo lto --step drafts                   # Step 2a: three fast-tier drafts + adherence QA
sku2scene demo lto --step hero --select 2          # Step 2b: presenter picks #2 → Kling v3 Pro hero + audio
sku2scene ledger                                   # one meter across all models (estimates, not bills)
sku2scene readiness                                # read-only live-mode checklist
```

Set `SKU2SCENE_MOCK_LATENCY_SCALE=1` on stage to simulate realistic per-model render times.

### Runtime interface

**CLI** (`sku2scene --help`): `models`, `catalog`, `scene`, `route`, `estimate`, `generate`, `qa`, `reroll`,
`ledger`, `jobs`, `readiness` and `demo lto --step drafts|hero`.

**MCP server** `sku-to-scene` (stdio). It is registered in `.mcp.json`, `.copilot/mcp-config.json` and
`.vscode/mcp.json` as `python scripts/run_mcp_server.py`. That is a stdlib-only launcher which always runs the
server with the repository's `.venv` interpreter. MCP hosts don't inherit shell activation, so complete the
quickstart install into `.venv` first. Override the interpreter with `SKU2SCENE_PYTHON`, and use `python3` as
the command on macOS/Linux if `python` isn't on `PATH`. If `.venv` is missing, it prints setup steps and exits.
`python scripts/verify_mcp_stdio.py` runs initialize → tools/list → tools/call through that exact launcher from a
de-activated environment. The server exposes these tools:

- Catalog and briefs: `list_models`, `search_catalog`, `get_sku`, `compose_scene`
- Routing and cost: `route_brief`, `estimate_cost`
- Generation: `generate_video(model, prompt, image_path, duration, ...)`, `generate_drafts`
- LTO flow: `lto_draft_concepts`, `lto_render_hero(select)`, `run_lto_demo`
- Jobs and QA: `job_status`, `extract_frames`, `evaluate_brand_compliance`, `reroll_clip`
- Reporting: `cost_report`, `foundry_readiness`

## The agents (Squad 1.1.0 + Copilot custom agents)

| Agent | Role |
| --- | --- |
| `@retail-merchandiser` | Reads SKU metadata, demographic and channel spec (TikTok 9:16, Signage 16:9, PDP 1:1). Writes scene prompts, camera directives and audio cues. |
| `@foundry-router` | Applies the enterprise guardrails, picks the fal endpoint, estimates per-second cost and dispatches through MCP. |
| `@brand-qa` | Reviews extracted frames **against the approved catalog reference image** (logo, label legibility, product hallucination, adherence). Fails closed; requests a bounded re-roll on LTX-2.5 Pro or Kling v3 Pro. |

The agents are defined in two places:

- **Squad members**: `.squad/agents/<name>/charter.md`, with routing in `.squad/routing.md`
- **Copilot custom agents**: `.github/agents/<name>.agent.md`, so you can address them as `@retail-merchandiser`,
  `@foundry-router` and `@brand-qa` in the app

Scaffolded with `@bradygaster/squad-cli` **1.1.0**, the npm `latest` dist-tag when this was built.
`.mcp.json` pins `@bradygaster/squad-cli@1.1.0`.

### Copilot Fusion model routing

`.squad/config.json` follows Squad 1.1.0's model-selection layers:

```json
{ "defaultModel": "hydrafusion", "agentModelOverrides": { "brand-qa": "hydrafusion-max" } }
```

`hydrafusion` (Fusion High) drives the team, and `brand-qa` gets `hydrafusion-max` (Fusion Max) for vision-heavy QA.
Squad's own template calls these an **opt-in research preview that may be unavailable** (for example, when
preview models are disabled by policy). If `hydrafusion` is unavailable, Squad falls forward to the head of its
quality-first premium chain and records the spawn with source `fallback` and a rationale naming the unavailable
model, so the demo never claims Fusion is guaranteed. Picking a session model in the app is inherited by every
sub-agent spawn. In the Copilot app you can
also choose **Auto → Fusion tier (High / Max)** in the model picker for the whole session. The `.agent.md` files
deliberately omit a `model:` field; model choice stays with Squad config and the app.

## Live mode (Microsoft Foundry)

1. An administrator reviews the fal preview terms (see the warning above), then registers `Fal.EnableDeploy`
   on a **designated non-production demo subscription**.
2. Deploy the five models. Kling v3 Pro uses the US Data Zone offering; LTX and MiniMax use Global Standard
   (PayGo). See [docs/foundry-setup.md](docs/foundry-setup.md).
3. Copy `.env.example` to `.env`, then set `SKU2SCENE_MODE=live`, `FOUNDRY_ENDPOINT=https://<resource>.services.ai.azure.com`
   and the deployment names. Set `FOUNDRY_TENANT_ID` (or `AZURE_TENANT_ID`) for tenant-pinned CLI auth, and
   `FOUNDRY_SUBSCRIPTION_ID` if the CLI default account is in another tenant. Subscription selection takes
   precedence and never changes the CLI default. Without either selector, auth uses `DefaultAzureCredential`.
   Assign **Foundry User** on the account. **A fal.ai `FAL_KEY` is not used.**
4. `pip install -e ".[live]"`, then run `sku2scene readiness --check-auth`.
   With `SKU2SCENE_MODE=live`, `python scripts/precache.py --yes` regenerates the already-authentic cached
   clips and records provenance. This submits **new billable generation jobs**; live mode and `--yes` are required.

**Route prefix:** the Learn route list shows `/providers/falai/<model>/...`, but the Learn code samples and the
ComfyUI article use `/providers/falai/v1/...`. The default is `providers/falai/v1`; override it with
`FOUNDRY_FAL_ROUTE_PREFIX`.

## Docs

- [15-minute executive demo script](docs/demo-script.md), with talk track and fallback cues
- [Foundry setup and provisioning](docs/foundry-setup.md)
- [Model routing and pricing reference](docs/model-routing.md)
- [Governance, data handling, Content Safety and Evaluations](docs/governance.md)
- [ComfyUI optional visual track](docs/comfyui.md)
- [Demo prep checklist](docs/prep-checklist.md)

## Current status / blockers

- ✅ Mock mode works end to end locally: CLI, MCP server over stdio through the configured launcher, Squad and
  Copilot agents, and the pytest suite. CI (`.github/workflows/ci.yml`) runs the same checks.
- **Live smoke runs verified on 2026-11-16:** Entra-only authentication, submit/status/result polling and MP4
  downloads succeeded for all five variants. Endpoint and account identifiers stay in ignored local configuration.

| Model | Requested settings | End-to-end wall time | Requested-duration estimate |
| --- | --- | --- | --- |
| MiniMax H3 Max Turbo | T2V, 5 s, 480P | 44.02 s, including transient-401 recovery | $0.1250 |
| LTX-2.5 Fast | T2V, 6 s, 720p | 50.06 s | $0.5400 |
| Kling v3 Pro | I2V, 3 s, native audio requested and audio stream present | 191.03 s | $0.5544 |
| LTX-2.5 Pro | T2V, 6 s, 720p | 54.67 s | $0.7200 |
| MiniMax H3 Max | T2V, 5 s, 480P | 18.76 s | $0.2500 |

These are individual observations, not comparative benchmarks or latency guarantees. Wall time includes
submission, polling and download; it is not fal's `timings.inference`. MiniMax returned an audio stream even
without an audio request; that observation is not a claim about a supported audio-control parameter.

- **Cache:** eight authentic display renditions, about 6.2 MB total; no simulated cached clips remain.
  [Play the Northwind hero](demo-cache/lto-hero-kling.mp4). All request IDs, timings and QA evidence are in the manifest.
- **Live QA verified:** Azure OpenAI vision scoring compares sampled generated frames with approved PIM imagery
  and brand rules; Azure AI Content Safety analyzes those frames. **Two cached clips passed automated screening
  and six failed**; all sampled Content Safety severities were zero. In the separate recorded LTO run, the hero
  passed while two drafts failed. A deliberate cold-brew-versus-drill negative control also failed.
  These are model-generated screening judgments, not ground-truth quality scores or human approval.
- **Bounded re-roll verified:** the failed live LTX draft triggered one Kling I2V re-roll. It still failed prompt
  adherence, and the chain stopped; reusing the root was refused before dispatch. No thresholds were relaxed.
- **Generation cost:** 18 accepted jobs, $10.4806 requested-duration estimate / $10.7851 conservative reservation
  against the $15 cap. These are list-price estimates, not an Azure bill; QA token/image charges are separate.
- ⚠️ **Human sign-off remains mandatory.** `automated_checks_passed` records a measured pass;
  `publish_approved` stays false and `human_signoff_required` stays true. Without configured evaluators, clips
  receive `manual_review`. Foundry Evaluations is not integrated.
- ⚠️ Prices are **preview list prices × requested seconds**. These are estimates, not bills. MiniMax outputs can
  run about 0.7 s longer than requested.

## Sources

- [Building the next generation of multimodal AI experiences with fal in Microsoft Foundry](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/building-the-next-generation-of-multimodal-ai-experiences-with-fal-in-microsoft-/4570032)
- [Direct your next shot with fal on Microsoft Foundry and ComfyUI](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/direct-your-next-shot-with-fal-on-microsoft-foundry-and-comfyui/4570230)
- [Microsoft Learn: Enable fal models in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/fal-ai-models/enable-fal-models)
- [Squad model selection](https://github.com/bradygaster/squad/blob/dev/docs/src/content/docs/features/model-selection.md)

## License

MIT. Product images are AI-generated for fictional brands.
