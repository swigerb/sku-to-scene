# Overview video: web rendition

The browser demo's **Watch overview** dialog plays a same-origin web copy of the release video, so it streams and shows captions in every browser. Release download URLs are served as attachments and don't include CORS headers.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `sku-to-scene-sizzle-720p.mp4` | 9,525,554 | `2eaa7f4ca518eaa4452a9404809c70622a40fcfbf947e9290d954fb3938f6299` |
| `sku-to-scene-sizzle.vtt` | 3,282 | `2b56d08fe54c534201ec536c0f69e0b70e0fa113282a3a4900169b4eddd0ddb2` |

## Source

- **Video:** release [`media-v1`](https://github.com/swigerb/sku-to-scene/releases/tag/media-v1) asset `sku-to-scene-sizzle.mp4` (1920×1080, 60 fps, 23,373,288 bytes, SHA-256 `e460fa38ea7e26c544936751656b87ae6b7e19572f23686b41a011423a3c0e42`).
- **Captions:** the release asset `sku-to-scene-sizzle.srt`, converted to WebVTT. All 40 cues keep identical text and millisecond timings. Only the formatting changed: a `WEBVTT` header, no cue numbers, a `.` decimal separator and short `mm:ss.ttt` timestamps.
- **Poster:** at build time, `scripts/build_site.py` copies `docs/images/sku-to-scene-sizzle-thumbnail.png` to `sizzle/sku-to-scene-sizzle-poster.png`.

## Encoding

ffmpeg settings:

- Video: H.264 at 1280×720, 30 fps, CRF 24.
- Audio: AAC at 128 kbps.
- `+faststart`, so the browser can start playback before the whole file has downloaded.

The release copy is an edited compilation:

- It contains earlier cached Foundry product renders.
- It is narrated by the Microsoft Ava AI voice (`en-US-AvaNeural`).
- It has an original synthesized score.
- The original clip audio is muted.
- No new Foundry renders were made for it.

This rendition changes only resolution, frame rate and compression.

This file is documentation only. `scripts/build_site.py` publishes only the `.mp4` and `.vtt`.
