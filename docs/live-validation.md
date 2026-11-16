# Live validation record (2026-11-16)

Historical evidence from the one-time live validation of this demo. It records what was observed; it is not a
benchmark, SLA or ongoing status. Per-clip request IDs, timings and QA evidence live in
[`demo-cache/manifest.json`](../demo-cache/manifest.json). Endpoint and account identifiers were deliberately
kept out of the repository.

## Smoke generation (all five variants)

Entra-only authentication, submit → status → result polling and MP4 download succeeded for every variant.

| Model | Requested settings | End-to-end wall time | Requested-duration estimate |
| --- | --- | --- | --- |
| MiniMax H3 Max Turbo | T2V, 5 s, 480P | 44.02 s, including transient-401 recovery | $0.1250 |
| LTX-2.5 Fast | T2V, 6 s, 720p | 50.06 s | $0.5400 |
| Kling v3 Pro | I2V, 3 s, native audio requested and audio stream present | 191.03 s | $0.5544 |
| LTX-2.5 Pro | T2V, 6 s, 720p | 54.67 s | $0.7200 |
| MiniMax H3 Max | T2V, 5 s, 480P | 18.76 s | $0.2500 |

Wall time covers submission, polling and download; it is not fal's `timings.inference`. MiniMax returned an
audio stream without an audio request; that is an observation, not a claim about an audio-control parameter.
This does not verify every mode, resolution, duration, region or deployment offering.

## Cache and QA

- **Cache:** eight authentic display renditions (about 6.2 MB); no simulated cached clips remain.
- **Screening:** Azure OpenAI vision compared sampled frames with the approved PIM image and brand rules; Azure
  AI Content Safety analysed the same frames. **2 cached clips passed automated screening and 6 failed**; all
  sampled Content Safety severities were 0. Per-clip outcomes are in [verification.md](verification.md#recorded-qa-outcomes).
- **Separate recorded LTO run** (`validation.live_lto`): three drafts, Variant #2 selected, Kling image-to-video
  hero with native audio requested. The hero passed screening.
- **Negative control** (`validation.negative_control`): the authentic cold-brew clip was deliberately scored
  against the drill reference and failed all four checks with a re-roll recommendation. It is a
  mismatched-reference experiment, not a failed render.
- **Bounded re-roll:** a failed live LTX draft triggered one Kling I2V re-roll; it still failed prompt adherence
  and the chain stopped. Reusing the root was refused before dispatch. No thresholds were relaxed.

## Spend

18 accepted generation jobs: **$10.4806** requested-duration estimate ($10.7851 conservative reservation)
against a $15 cap. Preview list price × requested seconds; not an Azure bill. QA token/image charges are separate.

## Contract findings fixed during validation

- Status/result GETs right after an accepted submit can return a transient 401 (RBAC propagation and per-URL
  denial caching). The client retries these free GETs with a unique query nonce and backoff for up to three
  minutes and never resubmits. See [foundry-setup.md](foundry-setup.md#3-configure-and-verify).
- Readiness probes authorization with a fresh random request ID every call, because a pre-propagation denial can
  stay cached for an exact URL.
- Latency recorded in the manifest is measured accepted→completed wall time, not fal's inference timing.
