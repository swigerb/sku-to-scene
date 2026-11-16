# Architecture, interfaces and agents

## Flow

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
  Cache --> Site["Static browser replay<br/>(GitHub Pages)"]
```

## Three surfaces, three levels of "live"

| Surface | What runs | Cloud calls |
| --- | --- | --- |
| **Browser replay** (`site/`, published to GitHub Pages) | Static HTML/JS over recorded renders and recorded QA evidence | **None.** Nothing is generated or evaluated in the browser. |
| **CLI / MCP, mock mode** (`SKU2SCENE_MODE=mock`, `SKU2SCENE_QA_EVALUATORS=off`) | Real routing, cost estimates, ledger and job records; generation replays `demo-cache/` | **None.** QA returns `manual_review` with the recorded verdict attached. |
| **CLI / MCP, live mode** (`SKU2SCENE_MODE=live`) | Real Foundry jobs; QA uses configured Azure OpenAI vision + Content Safety | **Billable** generation and QA calls. |

Mock mode alone does not stop QA calls: if `.env` configures vision or Content Safety endpoints, `qa.evaluate`
calls them. The repository MCP configs therefore pin `SKU2SCENE_MODE=mock` and `SKU2SCENE_QA_EVALUATORS=off`
for rehearsal (process environment overrides `.env`).

## CLI

`sku2scene --help`: `models`, `catalog`, `scene`, `route`, `estimate`, `generate`, `qa`, `reroll`, `ledger`,
`jobs`, `readiness` and `demo lto --step drafts|hero`. Set `SKU2SCENE_MOCK_LATENCY_SCALE=1` on stage to simulate
realistic per-model render times in mock mode.

## MCP server

`sku-to-scene` (stdio) is registered in `.mcp.json`, `.copilot/mcp-config.json` and `.vscode/mcp.json` as
`python scripts/run_mcp_server.py`. That stdlib-only launcher always runs the server with the repository's
`.venv` interpreter, because MCP hosts don't inherit shell activation. Override the interpreter with
`SKU2SCENE_PYTHON`; use `python3` as the command on macOS/Linux if `python` isn't on `PATH`. If `.venv` is
missing, it prints setup steps and exits. `python scripts/verify_mcp_stdio.py` runs initialize → tools/list →
tools/call through that exact launcher from a de-activated environment.

Tools:

- Catalog and briefs: `list_models`, `search_catalog`, `get_sku`, `compose_scene`
- Routing and cost: `route_brief`, `estimate_cost`
- Generation: `generate_video(model, prompt, image_path, duration, ...)`, `generate_drafts`
- LTO flow: `lto_draft_concepts`, `lto_render_hero(select)`, `run_lto_demo`
- Jobs and QA: `job_status`, `extract_frames`, `evaluate_brand_compliance`, `reroll_clip`
- Reporting: `cost_report`, `foundry_readiness`

To go live from the app, change the `env` block of the `sku-to-scene` entry (remove the two rehearsal overrides)
and restart the MCP server. Live calls are billable.

## Agents (Squad 1.1.0 + Copilot custom agents)

- **Squad members**: `.squad/agents/<name>/charter.md`, routing in `.squad/routing.md`.
- **Copilot custom agents**: `.github/agents/<name>.agent.md`, addressable as `@retail-merchandiser`,
  `@foundry-router` and `@brand-qa`.

Scaffolded with `@bradygaster/squad-cli` 1.1.0; `.mcp.json` pins that version.

### Copilot Fusion model routing

`.squad/config.json` follows Squad 1.1.0's model-selection layers:

```json
{ "defaultModel": "hydrafusion", "agentModelOverrides": { "brand-qa": "hydrafusion-max" } }
```

`hydrafusion` (Fusion High) drives the team and `brand-qa` gets `hydrafusion-max` (Fusion Max). Squad's template
calls these an **opt-in research preview that may be unavailable** (for example when preview models are disabled
by policy). If unavailable, Squad falls forward to its quality-first premium chain and records the spawn with
source `fallback`, so the demo never claims Fusion is guaranteed. In the Copilot app you can also choose
**Auto → Fusion tier (High / Max)** for the whole session. The `.agent.md` files deliberately omit `model:`.

## Static demo site

`site/` holds the browser app (`index.html`, `app.css`, `app.js`). `scripts/build_site.py --out _site` builds a
curated artifact: only the app files, brand assets, the four product images, the eight cached MP4s and a
`data.json` derived from `demo-cache/manifest.json` and the catalog. It refuses non-`foundry` clips and never
copies `.env`, `.sku2scene/` or the repository root. `.github/workflows/pages.yml` deploys it to GitHub Pages.

Preview locally:

```powershell
python scripts\build_site.py --out _site
python -m http.server 8765 --directory _site   # then open http://127.0.0.1:8765/
```
