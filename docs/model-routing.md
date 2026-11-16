# Model routing and pricing reference

All facts come from [Microsoft Learn: Enable fal models in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/fal-ai-models/enable-fal-models)
and the linked per-model schemas, plus the two Foundry blog posts listed in the README. The code registry is
`src/sku_to_scene/models.py` (`sku2scene models`).

## Routes

Base: `https://<resource>.services.ai.azure.com/<prefix>/<model base>/<route>`, where `<prefix>` defaults to
`providers/falai/v1` (`FOUNDRY_FAL_ROUTE_PREFIX`). The Learn route list omits `/v1`, but the Learn code samples
and the ComfyUI article include it. A project endpoint (`.../api/projects/<project>`) is normalized to the
resource root.

| Model | Base path | Routes | Offering |
| --- | --- | --- | --- |
| Kling v3 Pro | `kling/v3/pro` | `/text-to-video`, `/image-to-video` | US Data Zone |
| LTX-2.5 Fast | `lightricks/ltx-2.5` | `/text-to-video/fast`, `/image-to-video/fast` | Global Standard PayGo |
| LTX-2.5 Pro | `lightricks/ltx-2.5` | `/text-to-video/pro`, `/image-to-video/pro` | Global Standard PayGo |
| MiniMax H3 Max | `minimax/h3-max` | `/text-to-video`, `/image-to-video`, `/reference-to-video` | Global Standard PayGo |
| MiniMax H3 Max Turbo | `minimax/h3-max-turbo` | `/text-to-video`, `/image-to-video` | Global Standard PayGo |

Async pattern:

1. POST the route with a JSON body that includes `"model": "<deployment name>"`. The response returns a `request_id`.
2. Poll `GET <base>/requests/<id>/status` until `COMPLETED`. FAILED, CANCELED and ERROR stop the job.
3. `GET <base>/requests/<id>` returns `video.url`.
4. Download that URL with the same credentials. The client only sends credentials to the Foundry origin and
   never forwards them across a redirect to another host.

## Payload constraints enforced before submit (`payloads.py`)

| Model | Duration | Resolution / aspect | Image field | Audio |
| --- | --- | --- | --- | --- |
| Kling v3 Pro | string `"3"`–`"15"` | T2V `aspect_ratio` 16:9 / 9:16 / 1:1. I2V has **no** aspect_ratio; output follows the start image, so the router pre-crops the source | `start_image_url` (required for I2V) | `generate_audio` |
| LTX-2.5 Fast | even 6–20 or `auto` | `720p` / `1080p` / `1440p` / `2160p`; aspect `auto` / 16:9 / 9:16 **only** | `image_url` | `generate_audio` |
| LTX-2.5 Pro | **6, 8, 10** or `auto` | `720p` / `1080p`; aspect `auto` / 16:9 / 9:16 **only** | `image_url` | `generate_audio` |
| MiniMax H3 Max / Turbo | 0.92–15 s (default 5) | `480P` / `768P` / `1080P` (1080P refines from 768P) | `image_url` (data URI OK) | n/a |

Square (1:1 PDP) requests never send an unsupported aspect ratio to LTX. The router either picks a model or mode
that supports 1:1, or applies an explicit **center-crop policy**: it pre-crops the source image or post-crops the
output with ffmpeg. If ffmpeg is unavailable, it refuses **before** any billable submit.

## Preview pricing (USD per generated second)

| Model | Rates |
| --- | --- |
| MiniMax H3 Max | 480P $0.05 · 768P $0.08 · 1080P $0.16 |
| MiniMax H3 Max Turbo | 480P $0.025 · 768P $0.04 · 1080P $0.08 (exactly **50%** of H3 Max) |
| LTX-2.5 Fast | 720p $0.09 · 1080p $0.13 · 1440p $0.19 · 2160p $0.30 |
| LTX-2.5 Pro | 720p $0.12 · 1080p $0.17 |
| Kling v3 Pro | audio off $0.1232 · audio on $0.1848 · audio + voice control $0.2156 |

Estimates are list price × requested seconds and are **not billing guarantees**. MiniMax H3 output can run
about 0.7 s longer than requested, so the estimator also reports a high estimate. Under a budget cap, `auto`
durations reserve the model maximum, and non-finite or negative durations are rejected.

## Routing policy (`router.py`)

| Signal | Route |
| --- | --- |
| `stage=draft` / A-B testing | LTX-2.5 Fast or MiniMax H3 Max Turbo (Turbo when volume is high) |
| Approved PIM hero image + native audio | Kling v3 Pro image-to-video |
| Strict multi-object layout | MiniMax H3 Max |
| Text brief + synchronized audio, final | LTX-2.5 Pro |
| High volume (weekly circulars) | MiniMax H3 Max Turbo |
| Budget cap exceeded | next-cheapest compatible model, or reject with reasons |

Every decision returns a rationale, the skipped candidates with reasons, the payload preview and the cost estimate.

### Sample briefs (`briefs/`, mock mode)

| Brief | Routed model | Estimate |
| --- | --- | --- |
| Apparel PDP lookbook (Fabrikam jacket, 1:1) | Kling v3 Pro I2V (pre-crop) | $0.616 |
| Drill in context (Contoso Pro, 16:9) | Kling v3 Pro I2V | $0.739 |
| Patio set strict layout (text) | MiniMax H3 Max T2V 1080P | $0.96 |
| Flu-season endcap ×120 (Woodgrove) | MiniMax H3 Max Turbo I2V 768P | $0.24 each, $28.80 batch |
| Laptop text brief + audio | LTX-2.5 Pro | $1.02 |
| Pumpkin cold brew LTO hero | Kling v3 Pro I2V 9:16, 8 s, audio | $1.4784 |

Simulated latencies in mock mode (`simulated_latency_s`) are stage-pacing values, **not measured Foundry latencies**.
