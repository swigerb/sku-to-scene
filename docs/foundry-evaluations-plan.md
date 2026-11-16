# Foundry Evaluations

**Status: v1 executed (recorded, read-only replay).** The results are in
[demo-cache/evaluations/foundry-evals-v1.json](../demo-cache/evaluations/foundry-evals-v1.json). Human findings
are in [human-review.json](../demo-cache/evaluations/human-review.json). The browser demo replays both under
**AI evaluations** and runs no evaluations itself.

The original QA in `qa.py` calls an Azure OpenAI vision deployment and Azure AI Content Safety **directly**.
It is not Foundry Evaluations, and its verdicts in `demo-cache/manifest.json` (2 pass / 6 fail) are an
immutable baseline. The evaluations sit **next to** those verdicts and never change them, the thresholds or
`publish_approved`.

References (Microsoft Learn):
[Cloud evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation) ·
[Cloud evaluation datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-datasets) ·
[Custom evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators) ·
[Regions, limits and virtual network](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network)

## Design: two stages, disclosed

Native image input to a grader was tried and **rejected by the service** three times, with two vision
deployments (`Image inputs are not supported for grader model: … Try again with a vision model.`). The temporary
spike deployments were deleted. No public grader-model allowlist exists, so the service errors are the evidence.

1. **Stage A — vision observation.** The `brand-qa-vision` deployment views 4 sampled frames per clip next to
   the approved PIM reference image. It writes neutral observations, not scores. Output tokens are capped per
   call.
2. **Stage B — Foundry Evals.** `azure-ai-projects>=2.2.0`, `get_openai_client()` and the Evals API. Text
   `label_model` graders score the Stage A observations against stage-aware rubrics. Each check runs **three
   times**.
3. **Routing** is evaluated separately against grounded expected behaviour from `router.py`. It uses no media.
4. **Audio signal** uses a Foundry Python grader over local ffmpeg measurements: stream present, integrated
   loudness and true peak. It **cannot judge whether sounds match the picture.**

Limits: visual checks depend on Stage A text and can miss details a direct visual judge would catch. They judge
frames, not motion. Datasets are **inline `file_content`, not registered Foundry datasets**, and are pinned by
content hash.

## v1 runs (all completed)

| Check | Eval ID | Rows | Runs (×3 unless noted) |
| --- | --- | --- | --- |
| Concept adherence | `eval_2aad1e2eb0c5436fa995e4ce21abd011` | 8 | `evalrun_dcb47b3e…`, `evalrun_bc905a10…`, `evalrun_bd563616…` |
| Product identity | `eval_fa293ecfed2c4c0e88fcf1ddf80ac010` | 5 | `evalrun_d3c16fb7…`, `evalrun_4739d508…`, `evalrun_7604bdc9…` |
| Brand marks | `eval_5132015f322643188f4986f9a27b243d` | 4 | `evalrun_2df142a3…`, `evalrun_313889d9…`, `evalrun_c4eba4cd…` |
| Routing | `eval_3c572a85a5514a84a363c6b5fa4f83d8` | 9 | `evalrun_ee4db480…`, `evalrun_9459493d…`, `evalrun_7ef09e77…` |
| Audio signal | `eval_cefd1271b834422bad35b7dd904975b7` | 5 | `evalrun_c8c3e72edbcc4c79931c377ef4a2d124` (×1) |

The full IDs, per-row reasons and versions are in the JSON. Versions: `media-rubric-v1`, `routing-cases-v1`,
`audio-signal-v1` and `observation-v1`, plus SHA-256 hashes of the graders and observations.

Two earlier audio runs **failed**: `evalrun_65fac372…` and `evalrun_8b280b72…`. The cloud Python sandbox passes
item values as strings, so numeric comparisons raised errors and every row was rejected as invalid input. The
grader now coerces values explicitly. The failed runs are kept as superseded evidence.

## Results

- **Concept adherence:** `partial` 3/3 for all 8 clips. The service normalizes non-passing labels to
  `fail`/score 0. The demo shows the grader's own verdict and the service label as **separate fields**.
- **Product identity:** `match` 3/3 on the four image-to-video renders. The **negative control** (cold-brew
  clip vs drill reference) is `mismatch` 3/3, as expected.
- **Brand marks:** `consistent` 3/3, except the drill, which is `split` 2/3 and **needs human review**. The
  approved PIM image is black/teal, but the catalog rule says "yellow housing". This conflict goes to a
  human; there is no majority vote.
- **Text-to-video drafts and patio:** identity and brand marks are **N/A** with a recorded reason. No
  approved image was an input, so they are judged at the final image-to-video stage.
- **Routing:** model and mode 9/9 on every run. The grocery rationale was judged ungrounded 2/3, which is a
  **grader calibration finding, not a routing defect**.
- **Audio signal:** hero `fail` (true peak +2.0 dBTP, clipping risk) and draft 3 `fail` (−42.8 LUFS, very
  quiet). Draft 2 has **no audio stream**: audio was not requested, `has_audio=false`. That check is N/A.

### Why the original QA shows so many fails

- The three drafts are concept clips scored by final-brand checks, so they fail by design.
- The drill misses prompt adherence: 0.72 against a 0.75 threshold.
- The patio is text-to-video with no label, so the logo and label checks score 0.
- The grocery clip is a genuine product-fidelity failure (0.18: missing items).
- The AI evaluation separates concept adherence from final-brand fidelity rather than turning those fails green.

## Human review (not AI validation)

These findings come from [human-review.json](../demo-cache/evaluations/human-review.json):

- **The Northwind hero audio is a publication blocker.** Café ambience is loud and the frothing sound does not
  match the picture. The demo plays it at 50% volume, but that is mitigation, not a semantic fix.
- Drafts 1 and 3 (MiniMax Turbo) contain audio that was not requested and has not been reviewed for meaning.
- The grocery clip shows a conflict: original QA failed product fidelity, while the AI evaluation's identity
  check says `match` 3/3. A human must decide.

## Cost

| Item | Value |
| --- | --- |
| Estimated spend | **$0.2201** of a $5.00 coordinator cap |
| Tokens | 78,716 input + 18,273 output |
| Assumed rates | $1/M input and $5/M output, plus a $0.05 spike reservation |
| Pre-run estimate | $0.6522 |
| Logged during the run | $0.347 (double-counted duplicate usage rows; recomputed) |

When `per_model_usage` is empty, **the service returned no usage or cost attribution**. That is not proof of
zero cost; the reservation stays in the estimate. These are estimates, not Azure bills.

## Re-running (billable, opt-in)

```powershell
pip install -e ".[eval]"
.\.venv\Scripts\python.exe scripts\run_foundry_evals.py              # dry run: estimate only
.\.venv\Scripts\python.exe scripts\run_foundry_evals.py --yes --max-usd 5   # billable
```

The runner:

- Needs a live Foundry project in an ignored `.env` and `--yes`.
- Reserves each call's estimate **before** dispatch and stops at the cap.
- Persists eval and run IDs immediately.
- Stops on a timeout instead of starting more runs.
- Exits non-zero on service errors, failed runs or incomplete runs. Low scores and the expected negative-control
  rejection are not operational errors.

Normal MCP and Pages modes never call it.

## Next phases

- **Calibration:** at least two human reviewers label each check after watching the full clip with audio.
  Measure agreement, then adjust rubric wording under a new version. Eight clips are a smoke set, not a
  calibration set.
- **Registered datasets:** move inline rows to versioned Foundry datasets.
- **Direct visual judging:** revisit when a supported grader model accepts image input, or use a secured
  endpoint evaluator.
- **Audio semantics:** an audio-capable model (for example gpt-audio) could review the track against
  timestamped visual observations. That would still not be synchronized audiovisual validation and would need
  calibration.
- **CI:** a `workflow_dispatch`-only job with a cost cap and OIDC to a non-production project.
