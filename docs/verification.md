# Verifying the remaining limitations and troubleshooting

What is proven, what still needs a human, how to check it safely and what to do when something looks wrong.
Default to the **cheapest surface that answers the question**:

| Surface | Use it for | Cloud calls |
| --- | --- | --- |
| Browser replay (GitHub Pages or `_site/` locally) | Watching recorded clips and recorded QA evidence | None |
| CLI / MCP with `SKU2SCENE_MODE=mock` and `SKU2SCENE_QA_EVALUATORS=off` | Rehearsing routing, cost, ledger and agent flow | None |
| CLI / MCP with `SKU2SCENE_MODE=live` | A deliberate, authorized new render or QA run | **Billable** |

`SKU2SCENE_MODE=mock` alone is not no-spend: if `.env` configures vision or Content Safety, QA still calls them.
Set `SKU2SCENE_QA_EVALUATORS=off` too (the repository MCP configs already do).

## Recorded QA outcomes

The original eight cached clips are authentic Foundry renders. Scores are AI screening judgments, not ground truth.
Thresholds differ by brand. The current definitions are in [catalog/brands.json](../catalog/brands.json),
versioned with the repository. For a cached clip's recorded verdict, use that clip's `qa.thresholds` in
[demo-cache/manifest.json](../demo-cache/manifest.json), not a later catalog revision.

| Brand | Logo | Label | Product | Prompt |
| --- | ---: | ---: | ---: | ---: |
| Northwind Coffee | 0.80 | 0.70 | 0.80 | 0.70 |
| Contoso Pro | 0.80 | 0.70 | 0.85 | 0.75 |
| Fabrikam | 0.70 | 0.50 | 0.85 | 0.70 |
| Woodgrove Wellness | 0.80 | 0.80 | 0.85 | 0.70 |
| Litware | 0.80 | 0.60 | 0.80 | 0.75 |

| Clip | Model | Verdict | Failed checks | What a human should check |
| --- | --- | --- | --- | --- |
| `lto-draft-1` | MiniMax H3 Max Turbo (T2V) | fail | all four | Measured warped/blurred logo and partly legible label; not a rule that text-only drafts must fail |
| `lto-draft-2` | LTX-2.5 Fast (T2V) | fail | all four | Distorted, unreadable cup label; drink colour differs from the PIM image |
| `lto-draft-3` | MiniMax H3 Max Turbo (T2V) | fail | all four | Different (invented) brand mark on the cup |
| `lto-hero-kling` | Kling v3 Pro (I2V, audio) | **pass** | none | Logo/label across all frames; requested street scene only partly shown; audio cue alignment |
| `hero-apparel-kling` | Kling v3 Pro (I2V) | **pass** | none | Label legibility at angled views; orbit is partial, not a full 360° |
| `hero-home-kling` | Kling v3 Pro (I2V) | fail | prompt adherence (0.72) | Job site and handheld tracking not clearly shown; safety glasses unverifiable |
| `hero-patio-h3max` | MiniMax H3 Max (T2V) | fail | logo, label (0.00) | Text-only brief; no visible label or logo exists to score (see applicability note) |
| `hero-grocery-turbo` | MiniMax H3 Max Turbo (I2V) | fail | product, prompt | Omits thermometer and honey from the bundle; not a pharmacy endcap |

Applicability: the patio product has no PIM image and no visible logo, so logo/label checks score 0. The
current rubric treats that as a fail (fail-closed). Do not lower thresholds or rewrite the manifest to change
it; the Foundry Evals v1 rubric marks such checks N/A with a reason, without changing the original verdict (see
[foundry-evaluations-plan.md](foundry-evaluations-plan.md)).

## Area-guide and account-preview checks

- Open `#guide/qsr`, `#guide/apparel`, `#guide/home` and `#guide/grocery`, including in a narrow iframe.
  Home cards should open those guides; `#guide` must still open coffee. Every area lists all of its fictional
  accounts and their public citations. No real company name belongs in a fictional brand/product field.
- Step deliberately. Playing a preview must not select it. Only Northwind concept #2 and the existing
  approved-PIM heroes are selectable. Text-only patio, all new account drafts and QA learning examples are preview-only.
  Switching area, step or view and restarting must pause replaced or hidden media.
- Check the sun/moon radios by pointer, Tab, arrows, Home and End. Exactly one is selected. A valid
  `scoutTheme` query overrides the saved `s2s-theme`, then the system preference is the fallback.
- New clips display **Awaiting human review — not approved** if the valid review record has no finding for
  that clip. A failed/malformed review-file load instead displays **Human-review evidence unavailable**.
  The original coffee-audio publication blocker, concept #2 silence and 2/8 screening baseline remain unchanged.
- Every account plays one recorded example. New drafts use no approved PIM reference, stay preview-only, and
  show **Not yet evaluated** until a separate Foundry Evaluations run covers them. Learning examples carry
  **QA learning example — failed screening; not approved**; withheld attempts have no player anywhere.

## Account drafts

Twenty-three silent text-to-video attempts cover the nine new fictional accounts. Each row is an authentic
Foundry render screened by `@brand-qa` (two sampled frames, Azure OpenAI vision against the brand rules, and
Content Safety). The verdicts and scores are the recorded ones; nothing was relabelled. Estimates use preview
list price × requested seconds (6 s each): **$8.10 total**, not an Azure bill.
The first 22 attempts used $7.62 of the original $8 cap. A separately authorized completion
ceiling added at most $1.50 for Proseware only ($9.12 cumulative); one $0.48 attempt was made,
with a conservative duration-overrun estimate of $0.536. No further generation is planned.

- The first 14 attempts (initial + one re-roll) were rendered before the public-source research was final.
  The four gap accounts (Tailspin, Coho, Proseware, Munson) were then re-briefed as simplified one-shot scenes
  with fewer objects, gentle camera moves and no text-bearing environments (`-s1` to `-s3`). Each brief keeps
  its earlier prompts in `prompt_history`, and each manifest record stores its `brief_version`.
- **Playable example:** the one clip shown per account. Eight passed screening. Proseware's best attempt still
  fails product fidelity and is shown as a failed draft.
- Four passing examples (Tailwind, Wide World, Southridge, Best For You) also show a **Reviewer note** from an
  additional agent frame review. Their recorded screening pass is unchanged; a human decides.
- **QA learning example:** safe and text-free, but failed screening. Shown only to explain what the gate caught.
- **Withheld:** on-screen text, a real-brand logo or design resemblance, or a Content Safety flag. The media is
  not published; the request and screening evidence remain here and in the site's QA table.
- No new Foundry Evaluations run covers these drafts, so the site shows **Not yet evaluated**. No human review
  has approved any of them.

| Clip | Model | Estimate | Request ID | QA (fidelity / adherence) | Disposition |
| --- | --- | --- | --- | --- | --- |
| `account-tailspin-draft` | ltx-2.5-fast | $0.54 | `5f58d22c-daca-44b5-9693-d6470c1d39a2` | fail (0.35 / 0.40) | QA learning example |
| `account-coho-draft` | minimax-h3-max-turbo | $0.24 | `f924196a-237f-430b-8104-02fcc01d3133` | fail (0.40 / 0.15) | Withheld: Prohibited printed packaging text in sampled frames. |
| `account-vanarsdel-draft` | minimax-h3-max-turbo | $0.24 | `275b8c72-c692-42f6-9fce-5cf0df3fd1d7` | pass (0.93 / 0.78) | **Playable example** |
| `account-tailwind-draft` | ltx-2.5-fast | $0.54 | `14fe8d78-dbf5-4cb9-a5f3-12a7b08376c4` | pass (0.92 / 0.88) | **Playable example** |
| `account-wide-world-draft` | minimax-h3-max-turbo | $0.24 | `cacd055a-3289-40a8-9332-fd58ecc860be` | pass (0.92 / 0.98) | **Playable example** |
| `account-southridge-draft` | minimax-h3-max | $0.48 | `60f7be4e-6a0e-4e78-b381-f81608b089c0` | pass (0.98 / 0.96) | **Playable example** |
| `account-proseware-draft` | minimax-h3-max | $0.48 | `44fd2967-501e-4d83-80e9-8e0fb28e3d46` | fail (0.40 / 0.35) | Withheld: Prohibited brand-like packaging text in sampled frames. |
| `account-best-for-you-draft` | minimax-h3-max-turbo | $0.24 | `23a926ac-ec14-4e9b-a84b-d70f7cf31f1d` | fail (0.92 / 0.88) | Withheld: Content Safety flagged a sampled frame (Violence severity 2). Withheld pending human assessment. |
| `account-munson-draft` | minimax-h3-max-turbo | $0.24 | `ef6ee9fd-a65c-4f18-b19a-4796bda6f866` | fail (0.55 / 0.35) | Withheld: Additional agent frame review found visible shelf/signage text. |
| `account-coho-draft-r1` | minimax-h3-max-turbo | $0.24 | `4ec1703e-6006-4bb8-87d0-aed9e354c3f4` | fail (0.92 / 0.78) | Withheld: Content Safety flagged a sampled frame (Violence severity 2). Withheld pending human assessment. |
| `account-proseware-draft-r1` | minimax-h3-max | $0.48 | `d9c4c1e9-01f4-420b-8757-31805a02ac28` | fail (0.35 / 0.25) | Withheld: Visible third-party computer logo in the background. |
| `account-wide-world-draft-r1` | minimax-h3-max-turbo | $0.24 | `a5481167-5d0c-4b70-b4d9-7a80eac64644` | fail (0.78 / 0.74) | Withheld: Product-fidelity failure; additional agent review found background rack labels and four bottles instead of six. |
| `account-munson-draft-r1` | minimax-h3-max-turbo | $0.24 | `0a64488f-2c9a-41d9-a685-77fe05eff9ad` | fail (0.72 / 0.78) | QA learning example |
| `account-best-for-you-draft-r1` | minimax-h3-max-turbo | $0.24 | `222530a6-13d7-4710-8a2e-9f63bdec954d` | pass (0.92 / 0.78) | **Playable example** |
| `account-tailspin-draft-s1` | ltx-2.5-fast | $0.54 | `d5429d37-e4b1-40de-9c10-04995c418895` | pass (0.98 / 0.96) | **Playable example** |
| `account-coho-draft-s1` | minimax-h3-max-turbo | $0.24 | `65d6a50b-e1f2-4fab-b1b4-c5bcdb4ed53c` | fail (0.92 / 0.18) | QA learning example |
| `account-proseware-draft-s1` | minimax-h3-max | $0.48 | `d3ed5e81-dfbe-41e7-b441-b7363e63c107` | fail (0.62 / 0.58) | QA learning example |
| `account-munson-draft-s1` | minimax-h3-max-turbo | $0.24 | `999dbba9-2616-4daf-bbed-d2c691d22eab` | pass (0.98 / 0.96) | **Playable example** |
| `account-coho-draft-s2` | minimax-h3-max-turbo | $0.24 | `129bc61c-22f4-4468-b766-2117a70b7ad5` | fail (0.78 / 0.84) | QA learning example |
| `account-proseware-draft-s2` | minimax-h3-max | $0.48 | `cdd4e4d5-2e03-487c-b3d9-c5dc8263eedb` | fail (0.72 / 0.18) | Withheld: Office chair closely resembles a well-known designer chair (real trade-dress risk). |
| `account-coho-draft-s3` | minimax-h3-max-turbo | $0.24 | `0d8530c6-e943-482c-a3a0-20651689fb67` | pass (0.92 / 0.88) | **Playable example** |
| `account-proseware-draft-s3` | minimax-h3-max | $0.48 | `c7202825-5765-4c82-a292-f6106afe9fed` | fail (0.72 / 0.78) | **Playable example** |
| `account-proseware-draft-s4` | minimax-h3-max | $0.48 | `51903f88-100b-437e-a933-cab7d18aeb1d` | fail (0.55 / 0.35) | QA learning example; s3 remains selected |

The completion attempt removed colored packaging, retaining the unchanged four-component SKU and
brand rubric. Its two sampled frames contained no visible writing and Content Safety returned severity 0
in every category. The vision judge still failed fidelity and adherence, interpreting the paper as boxed.
It also called the explicitly requested mug and cloth extra objects: this is a calibration concern,
not grounds to alter the recorded verdict. The higher-scoring s3 remains the clearly failed selected draft.
There are now six learning examples and eight withheld attempts; no historical output or verdict was replaced.

Completion QA used one vision call (2,558 input + 205 output = **2,763 tokens**) and two
Content Safety image calls, all HTTP 200. Their request IDs and token counts are recorded in
the new manifest entry's `completion_usage`. The incremental QA allowance was approximately $0.50;
no billed-cost response is supplied by these APIs, and historical QA token usage was not captured,
so an actual cumulative Azure QA dollar total is unavailable. These are screening calls, not a new
Foundry Evaluations run. Human approval remains mandatory.

## Verifying what automation cannot

1. **Full-clip visual review.** QA samples frames; it does not watch every frame. Play each clip end to end at
   full screen and check logo, label legibility, product shape and colour, hands and physics, and any
   hallucinated objects. Record the reviewer, date and decision outside the manifest.
2. **Audio semantics and sync.** The manifest proves only that an audio stream exists (`media.has_audio`).
   Listen with headphones: does the sound match the brief (ice, pour, ambience), is it in sync, is there speech
   or music you did not ask for? Check the stream with `ffprobe -hide_banner demo-cache\lto-hero-kling.mp4`.
   Recorded measurements (`ffmpeg -af ebur128=peak=true`, signal only, not meaning):

   | Clip | Audio | Integrated | True peak | Finding |
   | --- | --- | --- | --- | --- |
   | `lto-hero-kling` | requested, mono AAC | −24.6 LUFS | +2.0 dBTP | **Publication blocker (human):** loud café ambience, frothing does not match the picture; clipping risk |
   | `lto-draft-1` | not requested, present | −25.6 LUFS | −11.6 dBTP | Unreviewed model audio |
   | `lto-draft-2` | not requested, **no stream** | — | — | Silence is the file, not the player |
   | `lto-draft-3` | not requested, present | −42.8 LUFS | −24.5 dBTP | Very quiet, unreviewed |

   The browser demo plays the hero at 50% volume. That is mitigation only and does not fix the mismatch.
   Fixing it requires one of: a re-render with a revised audio cue, a reviewed edited mix (keeping the native
   original, labelled), or publishing without audio. Each needs human sign-off.
3. **Content Safety coverage.** Severities cover sampled frames and image categories only, not audio or every
   frame. Treat zero severity as "nothing found in samples", not a full-video guarantee.
4. **ComfyUI.** The nodes have been exercised only by direct Python calls in mock mode. Safe offline check
   (no ComfyUI install, no cloud):

   ```powershell
   $env:SKU2SCENE_MODE='mock'; $env:SKU2SCENE_QA_EVALUATORS='off'
   .venv\Scripts\python.exe -c "import importlib.util as u,sys; s=u.spec_from_file_location('n','comfyui/custom_nodes/sku_to_scene_foundry/__init__.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print(sorted(m.NODE_CLASS_MAPPINGS))"
   ```

   Next, load `comfyui/workflows/lto-two-tier.api.json` in a real ComfyUI install still in mock mode. Only then,
   with separate authorization and a spend cap, run one live render.
5. **Fusion routing.** Confirm the session model picker shows Auto → Fusion; if Squad records a `fallback`
   spawn, say so on stage.
6. **Human sign-off.** No clip has `publish_approved: true`, and none should without a named human reviewer.

## Troubleshooting

| Symptom | Likely cause | Do this (no duplicate billable submits) |
| --- | --- | --- |
| `readiness --check-auth` reports 401/403 on the probe | Foundry User role missing or not yet propagated | Assign **Foundry User** on the account, wait, retry. The probe uses a fresh request ID each time. |
| 401 on status/result right after a successful submit | RBAC propagation race or per-URL denial cache | The client retries for ~3 min with fresh query nonces. If it still fails, keep the request ID and later GET `.../requests/<id>/status` and `.../requests/<id>`. **Do not resubmit.** |
| 429 Too Many Requests | ~2 requests/minute per deployment at default capacity | The client honours `Retry-After` up to three times. Run drafts sequentially; don't fire parallel jobs. |
| Timeout or network error during submit | Acceptance is uncertain | Check the ledger/job record for a request ID before trying again. Paid submits are never retried automatically. |
| Clip looks wrong but QA passed | Frame sampling missed it, or the VLM misjudged | Treat human review as authoritative; file a bug with evidence; do not publish. |
| QA fails on a check that cannot apply | Rubric applicability gap (for example patio logo) | Leave the verdict; note it for the versioned rubric. Never tune thresholds to pass. |
| Mock rehearsal shows `pass`/`fail` instead of `manual_review` | Cloud evaluators enabled via `.env` | Set `SKU2SCENE_QA_EVALUATORS=off` and restart the MCP server. |
| Browser demo shows no video | Stale cache or blocked autoplay | Hard-refresh; press play on the video itself. A "Playback didn't start" message names the browser's reason. |
| Browser demo says "Human-review evidence unavailable" | `human-review.json` failed to load or is malformed | Treat publication as blocked. Rebuild the site from `main`; check `demo-cache/evaluations/human-review.json` is valid. Don't present the page as showing all blockers. |
| Calculator says a duration isn't supported | That model/tier doesn't accept it (for example LTX Fast at 1440p/2160p caps at 10 s) | Pick a listed duration; lists come from the payload validator. Clip counts must be whole numbers ≥ 1. |

### Isolate, then recover

1. **Revert to trusted media first.** For the show, use the browser replay or mock mode with the committed
   cache. It is never overwritten by mock runs, and `scripts/build_placeholders.py` refuses to replace
   Foundry entries without `--force`.
2. **Isolate:** does it reproduce in mock mode (code/routing issue) or only live (service, quota, auth)?
   One model or all? One SKU/reference or all?
3. **Recover existing jobs** by request ID with GETs before considering any new submission.
4. **Bounded re-roll only on explicit live opt-in:** `sku2scene reroll` (or `reroll_clip`) is capped per root
   job (`MAX_REROLLS=2`) and reserves budget before dispatch. Use it only when live mode and spend are
   authorized.

### Bug report template

Never include tokens, keys, endpoints, tenant/subscription IDs, resource names, user paths or email addresses.

```markdown
**Surface:** browser replay | CLI mock | MCP mock | CLI live | MCP live
**Commit:** <git SHA>
**Settings:** SKU2SCENE_MODE=<mock|live>, SKU2SCENE_QA_EVALUATORS=<on|off>, model=<key>, mode=<t2v|i2v>,
  duration=<s>, resolution=<tier>, aspect=<ratio>, audio=<on|off>
**Request ID(s):** <fal request id, if any>   **Clip / job ID:** <id>
**Timing:** submitted <UTC>, accepted→completed <s>, error at <UTC>
**Expected:** ...
**Actual:** ... (HTTP status and error code, redacted)
**Evidence:** frame numbers / timestamps, QA scores and findings, screenshot (redacted)
**Reproduces in mock?** yes | no
```
