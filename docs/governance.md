# Governance, data handling and enterprise integration

## fal data handling (read first)

Per Microsoft Learn ([Enable fal models](https://learn.microsoft.com/azure/foundry/how-to/fal-ai-models/enable-fal-models)):

- The fal models are a **preview**, and fal **operates them outside Microsoft facilities**.
- Enabling them means the customer **elects to send data to fal**.
- **Microsoft customer agreements, the Microsoft Product Terms/DPA and Microsoft compliance certifications do
  not apply** to fal's processing; fal's terms do.
- An administrator must review these terms before registering `Fal.EnableDeploy`. This repo never registers
  the feature or accepts terms.

So the demo does **not** claim unified enterprise compliance for fal processing. What Foundry does provide is
the operational wrapper described below.

## What the Foundry wrapper gives you (talk-track claims)

- **One endpoint pattern, one auth model, one meter:** all five models sit behind
  `https://<resource>.services.ai.azure.com/providers/falai/...`. They use Entra ID RBAC and Azure billing for the
  deployments, so creative agencies don't each run separate vendor accounts. `sku2scene ledger` shows the single
  meter view (estimates).
- **Deployment choices:** Kling v3 Pro on a US Data Zone offering; LTX and MiniMax on Global Standard.
- **Pipeline integration:** chain generation with the following:
  - **Azure AI Content Safety:** `qa.py` calls `contentsafety/image:analyze` on extracted frames when
    `CONTENT_SAFETY_ENDPOINT` is set, as a pre-publish gate for digital signage.
  - **Vision evaluation:** `qa.py` scores logo integrity, label legibility, product fidelity (against the
    **approved catalog reference image**) and prompt adherence with an Azure OpenAI vision deployment.
  - **Foundry Evaluations:** the per-clip QA above calls vision and Content Safety directly; it is not Foundry
    Evaluations. A separate, opt-in **Foundry Evals v1** run scores the cached clips, a negative control and the
    routing decisions. It uses a disclosed two-stage design and never changes QA verdicts or approvals. See
    [Foundry Evaluations](foundry-evaluations-plan.md).
- **No-spend rehearsal:** `SKU2SCENE_MODE=mock` plus `SKU2SCENE_QA_EVALUATORS=off` makes no generation or QA
  calls; the browser demo makes no cloud calls at all. See [verification.md](verification.md).

## QA fails closed

- A pass requires **all four** scores, each finite and within [0, 1], at or above threshold.
- Missing, malformed or errored evaluator output → `manual_review`/`error`, **never approval**.
- A measured pass sets `automated_checks_passed`; it does not grant human approval.
  `human_signoff_required` is true and `publish_approved` remains false.
- Scripted **rehearsal values** (`measured: false`) apply only to matching simulated clips, never authentic
  Foundry cache entries. Without a real evaluator, authentic clips return `manual_review`; offline cache
  playback does not turn them into measured approvals.
- A failed clip may be re-rolled on LTX-2.5 Pro or Kling v3 Pro, **bounded per root job** (`MAX_REROLLS=2`). The
  budget is reserved before dispatch, so concurrent or failed paid submits still count. A parent can be re-rolled
  only once; after that, follow its child.

## Provenance

`demo-cache/manifest.json` and the run ledger record `provenance` as `simulated` or `foundry`. Simulated clips are
also visibly labelled in-frame. Never present a simulated clip as a Foundry render.

Live smoke generation and authenticated downloads were exercised on all five variants on 2026-11-16.
This validates transport, not enterprise compliance. Azure OpenAI vision scoring and Azure AI Content Safety
were also exercised on sampled authentic frames. VLM scores are AI screening judgments, not ground-truth
measurements of SKU fidelity; the full clip and its audio still require human review. Content Safety's sampled
image categories are not a full-video safety guarantee. Foundry Evals v1 results are AI screening evidence too;
human review found the Northwind hero's native audio unsuitable (a publication blocker).
No generated clip is approved for publication.

The manifest also labels a **negative control**: an authentic coffee clip was intentionally screened against
the drill reference and failed all four checks. This is a mismatched-reference experiment, not a failed render.
Ordinary clip entries keep their actual SKU and measured verdict, including genuine failures; thresholds are
never relaxed to make the showcase pass.

Cached Foundry clips are small H.264 display renditions (longest edge at most 1280 pixels), not unmodified
full-resolution masters. The manifest records source dimensions/hash, display media properties, request ID
and measured wall-clock latency. `accepted_to_completed_s` excludes download/encoding; `elapsed_s` covers the
generation pipeline through download. Neither is fal's inference-only timing. Source URLs and account
identifiers are deliberately excluded. Review both visuals and audio manually before using the clips externally.
