# Foundry Evaluations plan (not yet implemented)

**Status: plan only.** Nothing here has been run. The QA in this repository today (`qa.py`) calls an Azure
OpenAI vision deployment and Azure AI Content Safety **directly**; it is **not** Foundry Evaluations. This plan
describes how to move regression scoring onto Foundry cloud evaluation without overstating what the service
accepts.

References (Microsoft Learn):
[Cloud evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation) ·
[Cloud evaluation datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-datasets) ·
[Custom evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators) ·
[Regions, limits and virtual network](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network)

## Goals and non-goals

- **Goal:** repeatable, versioned regression scoring for (a) the agent routing decisions and (b) generated media,
  calibrated against human labels, runnable on demand with a cost cap.
- **Non-goals:** replacing human publication sign-off; relaxing thresholds; rewriting the historic
  `demo-cache/manifest.json` evidence; generating new video inside an evaluation run.

## Platform facts that shape the design

- The current cloud guide uses `azure-ai-projects>=2.2.0`, `project_client.get_openai_client()` and the Evals
  API with **versioned JSONL datasets** and explicit `{{item.field}}` mappings.
- **Code evaluators run without network access**, so they cannot call our VLM or Content Safety.
- **Prompt evaluators** return `result` and `reason`.
- **Endpoint evaluators** can wrap networked QA but need a separately secured deployment and project connection.
  They return `score`, `reason`, `status` and `schema_version`, with a **30-second timeout**.
- Maximum dataset **row size is 2 MB**; East US 2 is a supported region.
- Raw MP4 input is **not assumed** to be supported. Video must be represented as pre-extracted frames or
  references to them.

## Phase 0 — capability spike (gate)

Small, separately authorized, capped spend. Answer before building anything:

1. Can a prompt evaluator in our project/region accept **image input** (frame + PIM reference) in a dataset row?
2. If not, is an **endpoint evaluator** over pre-extracted frames approved by security (private deployment,
   managed identity, project connection, no secrets in rows)?
3. Do rows with two to four downscaled frames stay well under 2 MB? (Prefer frame URIs in governed storage over
   inline base64.)

Exit: a written decision (prompt evaluator vs endpoint adapter) with run IDs and errors recorded.

## Phase 1 — datasets

Two separate, versioned datasets; never mix routing and media scoring.

**`sku2scene-routing` (no media).** One row per brief: brief fields (stage, channel, has approved image, audio,
strict layout, volume, budget) and the **grounded expected behaviour** derived from `router.py` rules and
`docs/model-routing.md` (expected model, mode, aspect ratio and estimated cost band). Include the sample briefs
in `briefs/` plus edge cases (no PIM image with audio requested, conflicting signals, budget below draft cost).
Score with a deterministic code evaluator (exact model/mode match, cost within band) — no network needed.

**`sku2scene-media` (frames).** One row per clip from existing evidence only: clip ID, request ID, model, mode,
SKU, PIM reference frame, two to four extracted frames (extracted offline; **no ffmpeg or rendering inside a
scoring request**), scene prompt, brand ID, catalog revision and brand rules. Seed with the 8 cached clips and
include the **negative control** (cold-brew clip vs drill reference) labelled `expected: fail`. Keep historical
scores and each clip's recorded `qa.thresholds` as read-only baseline evidence, not as labels.

## Phase 2 — custom multimodal brand rubric

A versioned rubric (`rubric_version`) mirroring today's four checks — logo integrity, label legibility, product
fidelity, prompt adherence — with each brand's thresholds from the pinned revision of
[catalog/brands.json](../catalog/brands.json) as that brand's **floor**, not a universal threshold.
Use each historical clip's recorded `qa.thresholds` in [demo-cache/manifest.json](../demo-cache/manifest.json)
when comparing its original verdict; later catalog revisions must not reinterpret it.
Add an explicit `applicable` flag per check so cases such as the unbranded patio set are scored "not applicable"
by rule rather than failing. That is a rubric change recorded under a new version, re-calibrated against humans,
and **never** applied retroactively to the historic manifest.

Implementation follows the Phase 0 decision: a prompt evaluator with image input, or an endpoint adapter that
wraps the existing vision scoring over pre-extracted frames, returns within 30 s, and persists its own request
IDs and errors. Content Safety stays a separate check with severities reported alongside, not blended into a score.

## Phase 3 — human calibration

- At least two reviewers label each media row per check (pass/fail/not applicable) after watching the full clip
  with audio. Labels live in a separate `human_labels` dataset version; model scores never overwrite them.
- Measure agreement (per-check precision/recall vs human, Cohen's κ between reviewers). Adjust the rubric
  wording, not the thresholds, until agreement is acceptable; if thresholds must change, raise them only with
  documented evidence and a new rubric version.
- Expand beyond 8 clips before trusting the numbers; 8 rows is a smoke set, not a calibration set.

## Repeatability and invariants

- Pin dataset version, rubric version, brand ID, catalog revision and per-brand thresholds, evaluator
  model/deployment version, prompt template hash and frame extraction settings in every run record.
- Run each media row at least three times (temperature 0) to measure score variance; flag checks whose variance
  crosses a threshold boundary.
- Invariants enforced in tests: a brand's thresholds never decrease without a reviewed change; the negative
  control must fail; missing or errored scores are `manual_review`, never pass; `publish_approved` is never
  set by an evaluator.

## CI integration

- `workflow_dispatch` only (manual opt-in), never on push or pull request.
- Inputs: dataset version, rubric version and a **cost cap**; the job refuses to start if the row count × unit
  estimate exceeds it.
- Federated (OIDC) credentials to a non-production project; no keys in the repository or logs.
- Outputs: evaluation run ID, per-row results and errors as an artifact. A regression report compares with
  the previous run; failures block publication, not merges.

## Acceptance gates

| Gate | Pass condition |
| --- | --- |
| G0 Spike | Image-input path or approved endpoint adapter decided; run IDs and errors recorded |
| G1 Routing | 100% expected model/mode on the routing set; cost within band |
| G2 Media smoke | 8 clips + negative control scored; negative control fails; no evaluator errors swallowed |
| G3 Calibration | Agreed per-check precision/recall against human labels on an expanded set |
| G4 Repeatability | Score variance within tolerance across three runs; no threshold-straddling flips unflagged |
| G5 Operations | Manual CI job with cost cap, OIDC auth and archived results |

## Risks

- Model graders drift between versions — pin and re-calibrate on upgrade.
- Frame sampling misses transient defects — full-clip human review remains required.
- Audio is out of scope until a supported audio evaluator path exists; listen manually.
- fal preview data handling applies to generation, not evaluation; evaluation inputs are frames already in
  your tenant, but confirm data-handling approval for any new evaluator deployment.
