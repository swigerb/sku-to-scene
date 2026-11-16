"""ComfyUI custom nodes for fal video models on Microsoft Foundry (SKU to Scene).

These nodes call the same `sku_to_scene` package that the GitHub Copilot agents and the CLI use, so a
workflow a creative director builds in ComfyUI hits exactly the same routes, payload validation, auth and
cost estimates as the automated pipeline ("ComfyUI + code parity").

Install: copy or symlink this folder into ComfyUI/custom_nodes/ and `pip install -e <repo>[live]` into the
ComfyUI Python environment. Live renders need SKU2SCENE_MODE=live and FOUNDRY_ENDPOINT (Entra ID via
DefaultAzureCredential, scope https://cognitiveservices.azure.com/.default). Mock mode replays cache hits
with their recorded provenance, including authentic Foundry renders; only cache-miss placeholders are
labelled simulated. Cached replay is not live generation.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

MODEL_KEYS = ["kling-v3-pro", "ltx-2.5-fast", "ltx-2.5-pro", "minimax-h3-max", "minimax-h3-max-turbo"]


def _image_to_png(image) -> str:
    """ComfyUI IMAGE tensor [B,H,W,C] float 0..1 -> temp PNG path (first frame of the batch)."""
    import numpy as np
    from PIL import Image

    arr = (image[0].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    fd, path = tempfile.mkstemp(suffix=".png", prefix="sku2scene-")
    os.close(fd)
    Image.fromarray(arr).save(path)
    return path


class FoundryFalVideo:
    """Generate a clip with one of the five fal video models on Microsoft Foundry."""

    CATEGORY = "SKU to Scene/Foundry"
    RETURN_TYPES = ("STRING", "STRING", "FLOAT")
    RETURN_NAMES = ("video_path", "provenance", "estimate_usd")
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (MODEL_KEYS, {"default": "ltx-2.5-fast"}),
                "prompt": ("STRING", {"multiline": True}),
                "duration": ("STRING", {"default": "6"}),
                "aspect_ratio": (["16:9", "9:16", "1:1"], {"default": "16:9"}),
                "resolution": ("STRING", {"default": ""}),
                "audio": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "start_image": ("IMAGE",),
                "sku": ("STRING", {"default": ""}),
            },
        }

    def generate(self, model, prompt, duration, aspect_ratio, resolution, audio, start_image=None, sku=""):
        from sku_to_scene.config import REPO_ROOT
        from sku_to_scene.pipeline import generate_video

        image_path = _image_to_png(start_image) if start_image is not None else None
        dur = duration if duration == "auto" else float(duration)
        job = generate_video(model, prompt, image_path, dur, aspect_ratio=aspect_ratio,
                             resolution=resolution or None, audio=audio, sku=sku or None,
                             label=f"ComfyUI | {model}")
        out = Path(job["output"])
        return (str(out if out.is_absolute() else REPO_ROOT / out), job["provenance"],
                float(job["estimate"]["estimate_usd"]))


class FoundryFalRoute:
    """Ask the SKU to Scene router which model fits a brief (same policy as @foundry-router)."""

    CATEGORY = "SKU to Scene/Foundry"
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("model", "mode", "rationale")
    FUNCTION = "route"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True}),
                "channel": (["tiktok", "signage", "pdp"], {"default": "signage"}),
                "stage": (["draft", "final"], {"default": "final"}),
                "has_approved_image": ("BOOLEAN", {"default": False}),
                "needs_audio": ("BOOLEAN", {"default": False}),
                "strict_layout": ("BOOLEAN", {"default": False}),
                "volume": ("INT", {"default": 1, "min": 1, "max": 100000}),
            }
        }

    def route(self, prompt, channel, stage, has_approved_image, needs_audio, strict_layout, volume):
        from sku_to_scene.router import Brief, route

        d = route(Brief(prompt=prompt, channel=channel, stage=stage,
                        source="pim_image" if has_approved_image else "text",
                        image_path="comfyui-start-image.png" if has_approved_image else None,
                        needs_audio=needs_audio, strict_layout=strict_layout, volume=volume))
        return (d.model, d.mode, "\n".join(d.rationale))


NODE_CLASS_MAPPINGS = {"SkuToSceneFoundryFalVideo": FoundryFalVideo, "SkuToSceneFoundryFalRoute": FoundryFalRoute}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SkuToSceneFoundryFalVideo": "Foundry fal Video (Kling / LTX / MiniMax)",
    "SkuToSceneFoundryFalRoute": "Foundry fal Router (SKU to Scene)",
}
