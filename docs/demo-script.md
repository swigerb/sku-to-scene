# 15-minute executive demo script

## Recorded browser walkthrough

The browser demo replays existing recordings; it does not generate video or run fresh evaluations.
Optionally open **Watch overview** for the captioned introduction, then choose **Start guided demo**.
Use **Next** and **Previous** deliberately, with **Play/Pause** for playback; the guide does not advance on a timer.
Previewing a draft does not choose it. Explicitly choose **concept #2** to continue to its available recorded
hero; concepts #1 and #3 have no recorded hero.

Open **Technical evidence** to inspect model routing, original QA and recorded evaluations separately.
Keep each clip's publication status visible: AI screening is not human approval, and the recorded human
publication blockers remain unresolved. If human-review evidence is unavailable, treat every clip as not approved.
Return to the guide or explore the scenario gallery without implying that cached playback is a live cloud run.

## CLI and agent pitch

**Setup:** GitHub Copilot app open on this repo, with the Squad team loaded (`@retail-merchandiser`,
`@foundry-router`, `@brand-qa`). Before you start:

- Model picker: **Auto → Fusion (High)**, if Fusion is available in your org.
- `SKU2SCENE_MOCK_LATENCY_SCALE=1` for realistic pacing, or `0.1` to move quickly.
- A terminal canvas open with `sku2scene` as the fallback.
- `demo-cache/` clips ready to play.
- Live pacing: the measured 8-second Kling hero took about **281 seconds end to end**, not 15-60 seconds.
  Start it early and use the authentic cached render to keep the 15-minute pitch on time.

**Honesty rule:** say "simulated preview" for any clip whose provenance is `simulated`. Say "estimate" for
every price. The eight checked-in clips are authentic, but only two passed automated screening. Open the
manifest's recorded QA evidence when offline; without configured evaluators, a new run returns manual review.
The live bounded re-roll also failed prompt adherence and stopped at its cap; do not describe it as an approved fix.

| Time | Beat | On screen | Talk track | Fallback cue |
| --- | --- | --- | --- | --- |
| 0:00–1:30 | **The problem** | README hero + RCG table | "Retailers have millions of approved PIM images and almost no video. Agencies can't scale to weekly, regional, per-SKU video. SKU to Scene turns the catalog into a creative supply chain." | Static slide/README only |
| 1:30–3:00 | **Five models, one wrapper** | `sku2scene models` | "Five fal variants on Foundry, behind one endpoint pattern, one Entra ID auth model and one Azure meter. Each one wins a different job: fidelity (Kling), speed/iteration (LTX Fast), audio-synced finals (LTX Pro), layout adherence (H3 Max), volume economics (Turbo, half the H3 Max rate)." | — |
| 3:00–4:30 | **Agents, not prompts** | `.squad/team.md`, `.github/agents/` | "Three specialist agents on Copilot Fusion: the merchandiser writes the brief, the router enforces guardrails and cost, and brand QA checks frames against the approved product image. Fusion is a preview; if it's unavailable, Squad falls back visibly." | — |
| 4:30–6:00 | **Routing is explainable** | `sku2scene route --brief briefs\grocery-flu-season-endcap.json`, then `...\home-patio-layout.json` | "120 localized endcaps → Turbo, $28.80 estimated for the batch. A strict patio-set layout → H3 Max. Every decision shows why, and what it skipped." | — |
| 6:00–10:30 | **Step 2 live: two-tier LTO** | In chat, paste the pumpkin cold brew prompt (`briefs/qsr-lto-pumpkin-cold-brew.json` → `presenter_prompt`) | "Three storyboard drafts in parallel on the fast tier: Turbo and LTX Fast. Brand QA scores prompt adherence." Then type **"Go with variant #2."** "Now the router upgrades to Kling v3 Pro image-to-video, from our approved hero cup image, with native ice and pour audio." | If chat stalls: `sku2scene demo lto --step drafts`, then `--step hero --select 2`. Play `demo-cache/lto-hero-kling.mp4` |
| 10:30–12:00 | **Brand QA + re-roll** | `@brand-qa` measured findings and Content Safety results | "QA compares frames with the approved reference. Our real hero passed automated screening, but two real drafts failed. The failed LTX draft triggered one bounded Kling re-roll. These are AI judgments, not human sign-off. Missing evaluators return manual review, never invented scores." | Show `docs/governance.md` and the manifest evidence; the mismatched drill-reference negative control is clearly labelled |
| 12:00–13:00 | **One meter** | `sku2scene ledger` | "Drafts about $1.02, hero about $1.48, run total about $2.50 in estimates. One ledger across three model vendors." | — |
| 13:00–14:00 | **ComfyUI parity** | `comfyui/workflows/lto-two-tier.api.json` | "Creative directors can node-chain the same models in ComfyUI. The nodes call this same package, so engineering can put the same workflow into CI/CD." | Screenshot / doc |
| 14:00–15:00 | **Governance close** | README warning box | "Be clear-eyed: fal processes outside Microsoft facilities, and Microsoft's DPA doesn't cover it, so your admin reviews the terms before enabling. What Foundry gives you is one endpoint, RBAC, deployment choices (Kling on a US Data Zone) and pipeline hooks for Content Safety and evaluations. Next step: a scoped pilot on one vertical." | — |

## Presenter prompt (Step 2)

> We're launching a fall pumpkin cold brew LTO for a national coffee chain. Generate 3 rapid storyboard concepts
> using our lowest-cost fast models in Microsoft Foundry, evaluate prompt adherence, and then render the best
> concept in high fidelity with native audio using our approved hero cup image.

The agents use the MCP tools `lto_draft_concepts` → (presenter picks) → `lto_render_hero(select=2)`.
`run_lto_demo` is the one-shot rehearsal version only.
