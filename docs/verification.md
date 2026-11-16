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
  approved-PIM heroes are selectable. Text-only patio and all new account drafts are preview-only.
  Switching area, step or view and restarting must pause replaced or hidden media.
- Check the sun/moon radios by pointer, Tab, arrows, Home and End. Exactly one is selected. A valid
  `scoutTheme` query overrides the saved `s2s-theme`, then the system preference is the fallback.
- New clips display **Awaiting human review — not approved** if the valid review record has no finding for
  that clip. A failed/malformed review-file load instead displays **Human-review evidence unavailable**.
  The original coffee-audio publication blocker, concept #2 silence and 2/8 screening baseline remain unchanged.
- New text-only drafts use no approved PIM reference. Their unchanged per-brand thresholds screen sampled
  frames for the fictional rules; no-logo/plain-packaging requirements differ from original branded product
  references. See each appended manifest record's measured scores, findings and Content Safety severities.
  No new Foundry Evaluations run was performed: **Not yet evaluated** is distinct from direct vision screening.
- For any **Silent presentation edit**, verify the displayed file has no audio stream and the original-audio
  rendition remains available. Unexpected model audio is not a native-audio capability claim. Its removal
  is a disclosed local edit, not a new generation or a fix for semantic audio quality.

### Account recording attempts

Nine initial six-second requests total **$3.24** at repository list prices. One permitted re-roll each for
Coho, Proseware, Wide World, Munson and Best For You adds **$1.44**, totaling **$4.68 estimated generation**,
not invoice-confirmed Azure spend.
No further generation is authorized by this record. Direct screening used fourteen vision requests and
twenty-eight Content Safety image analyses (two sampled frames per attempt); token-level charges and actual
Azure billing were not returned by the runner, so an exact QA charge cannot be substantiated here.
No new Foundry Evaluations run was submitted.

| Clip | Request ID | Generation estimate |
| --- | --- | ---: |
| `account-tailspin-draft` | `5f58d22c-daca-44b5-9693-d6470c1d39a2` | $0.54 |
| `account-coho-draft` | `f924196a-237f-430b-8104-02fcc01d3133` | $0.24 |
| `account-vanarsdel-draft` | `275b8c72-c692-42f6-9fce-5cf0df3fd1d7` | $0.24 |
| `account-tailwind-draft` | `14fe8d78-dbf5-4cb9-a5f3-12a7b08376c4` | $0.54 |
| `account-wide-world-draft` | `cacd055a-3289-40a8-9332-fd58ecc860be` | $0.24 |
| `account-southridge-draft` | `60f7be4e-6a0e-4e78-b381-f81608b089c0` | $0.48 |
| `account-proseware-draft` | `44fd2967-501e-4d83-80e9-8e0fb28e3d46` | $0.48 |
| `account-best-for-you-draft` | `23a926ac-ec14-4e9b-a84b-d70f7cf31f1d` | $0.24 |
| `account-munson-draft` | `ef6ee9fd-a65c-4f18-b19a-4796bda6f866` | $0.24 |
| `account-coho-draft-r1` | `4ec1703e-6006-4bb8-87d0-aed9e354c3f4` | $0.24 |
| `account-proseware-draft-r1` | `d9c4c1e9-01f4-420b-8757-31805a02ac28` | $0.48 |
| `account-wide-world-draft-r1` | `a5481167-5d0c-4b70-b4d9-7a80eac64644` | $0.24 |
| `account-munson-draft-r1` | `0a64488f-2c9a-41d9-a685-77fe05eff9ad` | $0.24 |
| `account-best-for-you-draft-r1` | `222530a6-13d7-4710-8a2e-9f63bdec954d` | $0.24 |

Screening: **5 pass / 9 fail** across fourteen new attempts, with no human publication approvals.
`@brand-qa` additionally inspected the retained 28 frames locally, without more service calls. Its observations
are separate from measured scores: passing scores were not rewritten to hide disagreements.

Only the VanArsdel draft remains in primary playback, still awaiting human review. Eight other new examples
are withheld, with their briefs, request evidence and original scores retained:

| Example | Why withheld / bounded re-roll outcome |
| --- | --- |
| Tailspin | Wrong product bundle; adherence alone does not qualify for a re-roll. |
| Coho | Initial printed text; its one re-roll has a sampled Violence severity 2 flag. |
| Tailwind | Apparent writing-like background marks need human assessment despite a recorded pass; no speculative re-roll. |
| Wide World | Initial labels/markings despite a recorded pass; re-roll still has rack labels and wrong bottle count. |
| Southridge | Additional agent review found a different object order despite a recorded pass; no adherence-only re-roll. |
| Proseware | Initial brand-like text; re-roll has third-party computer logos. |
| Best For You | Initial sampled Violence severity 2 flag; re-roll passed measured screening but includes expressly excluded utensils. |
| Munson | Initial shelf/signage text; re-roll fails product fidelity. A visible bottle contradicts an initial recorded finding, which is preserved. |

Both severity 2 results are service flags needing human assessment, not definitive unsafe-content findings.
The three later re-rolls have zero severities in their sampled image categories; that does not establish
full-video safety or negate the initial flags. All five re-roll chains are exhausted. No further paid work
was performed to chase a pass.

The two LTX presentations are natively six seconds and silent. MiniMax returned roughly 6.58 seconds with an
unexpected audio stream; displayed copies were locally made silent and re-encoded to **6.000 seconds**.
The full-length original-audio renditions are retained. `qa_sampled_from` identifies those untrimmed renditions:
the recorded QA was sampled before the presentation-only trim, not rerun or relabelled afterward.

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
