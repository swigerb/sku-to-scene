"""ffmpeg helpers: simulated placeholder clips, frame extraction, probing, source-image cropping."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ASPECT_SIZE = {"9:16": (432, 768), "16:9": (768, 432), "1:1": (576, 576)}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _font_opt() -> str:
    for f in FONT_CANDIDATES:
        if Path(f).is_file():
            return "fontfile='" + f.replace(":", "\\:") + "':"
    return ""


def _run(args: list[str], cwd: str | None = None) -> None:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")


def render_placeholder(
    out: Path,
    label: str,
    image: Path | None = None,
    aspect: str = "16:9",
    duration: float = 5.0,
    hue: int = 0,
    audio: bool = False,
    zoom_dir: int = 1,
) -> Path:
    """Render a clearly-labelled SIMULATED clip (Ken Burns over a product image)."""
    w, h = ASPECT_SIZE.get(aspect, ASPECT_SIZE["16:9"])
    fps = 24
    frames = int(duration * fps)
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    font = _font_opt()
    with tempfile.TemporaryDirectory() as td:
        Path(td, "label.txt").write_text(label, encoding="utf-8")
        Path(td, "banner.txt").write_text("SIMULATED PREVIEW - not a Foundry render", encoding="utf-8")
        z = "min(zoom+0.0012,1.18)" if zoom_dir > 0 else "if(eq(on,0),1.18,max(zoom-0.0012,1.0))"
        vf = (
            f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps},"
            f"hue=h={hue},"
            f"drawbox=x=0:y=0:w=iw:h=34:color=black@0.6:t=fill,"
            f"drawtext={font}textfile=banner.txt:fontcolor=white:fontsize=16:x=(w-tw)/2:y=9,"
            f"drawbox=x=0:y=ih-84:w=iw:h=84:color=black@0.55:t=fill,"
            f"drawtext={font}textfile=label.txt:fontcolor=white:fontsize=15:line_spacing=6:x=14:y=h-th-16,"
            f"format=yuv420p"
        )
        args = ["ffmpeg", "-y", "-loglevel", "error"]
        if image is not None:
            args += ["-i", str(Path(image).resolve())]
        else:
            args += ["-f", "lavfi", "-i", f"color=c=0x3b2416:s={w * 2}x{h * 2}:d=1"]
        if audio:
            args += ["-f", "lavfi", "-t", str(duration), "-i", "anoisesrc=color=brown:amplitude=0.08:r=44100"]
        args += ["-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "30"]
        if audio:
            args += ["-af", "lowpass=f=1800,afade=t=in:d=0.5", "-c:a", "aac", "-b:a", "64k", "-shortest"]
        else:
            args += ["-an"]
        args += ["-movflags", "+faststart", str(out)]
        _run(args, cwd=td)
    return out


def probe(video: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    data = json.loads(r.stdout)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return {
        "duration_s": round(float(data.get("format", {}).get("duration", 0) or 0), 2),
        "width": v.get("width"),
        "height": v.get("height"),
        "has_audio": a,
        "size_bytes": int(data.get("format", {}).get("size", 0) or 0),
    }


def extract_frames(video: Path, out_dir: Path, count: int = 4) -> list[Path]:
    info = probe(video)
    dur = max(info["duration_s"], 0.5)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(count):
        t = dur * (i + 0.5) / count
        f = out_dir / f"frame_{i + 1:02d}.png"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(f)])
        frames.append(f)
    return frames


def transcode_preview(src: Path, dest: Path) -> Path:
    """Make a small public display rendition, preserving audio and stripping source metadata."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-map_metadata", "-1",
          "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2",
          "-c:v", "libx264", "-preset", "medium", "-crf", "28",
          "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dest)])
    return dest


def crop_image_to_aspect(src: Path, aspect: str, dest: Path) -> Path:
    """Center-crop a source image to the channel aspect before image-to-video."""
    aw, ah = (int(x) for x in aspect.split(":"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"crop='if(gt(iw/ih,{aw}/{ah}),ih*{aw}/{ah},iw)':'if(gt(iw/ih,{aw}/{ah}),ih,iw*{ah}/{aw})'"
    )
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, str(dest)])
    return dest


def crop_video_to_aspect(src: Path, aspect: str, dest: Path) -> Path:
    """Center-crop a rendered clip to the channel aspect (e.g. LTX 16:9/9:16 render -> 1:1 PDP)."""
    aw, ah = (int(x) for x in aspect.split(":"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"crop='trunc(if(gt(iw/ih,{aw}/{ah}),ih*{aw}/{ah},iw)/2)*2':"
        f"'trunc(if(gt(iw/ih,{aw}/{ah}),ih,iw*{ah}/{aw})/2)*2'"
    )
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-c:a", "copy", str(dest)])
    return dest

def image_size(path: Path) -> tuple[int, int] | None:
    """Read PNG/JPEG dimensions without ffmpeg (None if unknown format)."""
    data = Path(path).read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            seg = int.from_bytes(data[i + 2:i + 4], "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
            i += 2 + seg
    return None


def matches_aspect(size: tuple[int, int] | None, aspect: str, tol: float = 0.01) -> bool:
    if not size:
        return False
    aw, ah = (int(x) for x in aspect.split(":"))
    return abs(size[0] / size[1] - aw / ah) <= tol * (aw / ah)