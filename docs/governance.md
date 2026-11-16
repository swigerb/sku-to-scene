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
  - **Foundry Evaluations:** the QA rubric is designed to be lifted into a Foundry evaluation run for regression
    testing of prompts and models. That is a next step; it isn't wired up in this repo.

## QA fails closed

- A pass requires **all four** scores, each finite and within [0, 1], at or above threshold.
- Missing, malformed or errored evaluator output → `manual_review`/`error`, **never approval**.
- In mock mode, scores are scripted **rehearsal values** (`measured: false`), and `publish_approved` is always false.
- A failed clip may be re-rolled on LTX-2.5 Pro or Kling v3 Pro, **bounded per root job** (`MAX_REROLLS=2`). The
  budget is reserved before dispatch, so concurrent or failed paid submits still count. A parent can be re-rolled
  only once; after that, follow its child.

## Provenance

`demo-cache/manifest.json` and the run ledger record `provenance` as `simulated` or `foundry`. Simulated clips are
also visibly labelled in-frame. Never present a simulated clip as a Foundry render.
