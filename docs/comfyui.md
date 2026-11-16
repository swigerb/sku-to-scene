# ComfyUI optional visual track

This track is based on [Direct your next shot with fal on Microsoft Foundry and ComfyUI](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/direct-your-next-shot-with-fal-on-microsoft-foundry-and-comfyui/4570230).
The blog shows custom nodes that call Foundry with `DefaultAzureCredential` and `FOUNDRY_ENDPOINT`. This repo
ships its **own** nodes (`comfyui/custom_nodes/sku_to_scene_foundry/`) that extend the idea to all five models.
They call the same `sku_to_scene` package as the agents and CLI: same routes, payload validation, crop policy,
cost estimate, ledger and provenance.

| Node | Purpose |
| --- | --- |
| **Foundry fal Video (Kling / LTX / MiniMax)** | Model, prompt, duration, aspect ratio, resolution, audio and an optional start `IMAGE` → video path, provenance, estimate |
| **Foundry fal Router (SKU to Scene)** | Brief signals → the model and mode `@foundry-router` would choose, with the rationale |

## Install

1. Copy or symlink `comfyui/custom_nodes/sku_to_scene_foundry` into `ComfyUI/custom_nodes/`.
2. In ComfyUI's Python environment, run `pip install -e <path-to-repo>[live]`.
3. For live renders, set `SKU2SCENE_MODE=live`, `FOUNDRY_ENDPOINT` and `FOUNDRY_DEPLOYMENT_*`, and sign in with
   `az login`. Without these, the nodes return **simulated** placeholders labelled `provenance=simulated`.
4. Load `comfyui/workflows/lto-two-tier.api.json` (API format). It runs an LTX-2.5 Fast draft, then a Kling v3
   Pro hero from `nwc-pumpkin-cold-brew-hero.png`; copy that image into ComfyUI's `input/` folder first.

Keyframe → motion: to start from a generated keyframe (for example a gpt-image or FLUX image node), wire its
`IMAGE` output into `start_image`.

Status: the nodes were smoke-tested in mock mode outside ComfyUI (direct Python calls). They haven't been run
inside a ComfyUI install or against live Foundry.
