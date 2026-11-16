from sku_to_scene.media import probe, render_placeholder, transcode_preview


def test_display_rendition_preserves_audio_and_portrait_aspect(tmp_path):
    source = render_placeholder(tmp_path / "source.mp4", "TEST ONLY", aspect="9:16", duration=1, audio=True)
    output = transcode_preview(source, tmp_path / "preview.mp4")
    media = probe(output)
    assert media["has_audio"]
    assert max(media["width"], media["height"]) <= 1280
    assert abs(media["width"] / media["height"] - 9 / 16) < 0.01
    assert abs(media["duration_s"] - 1) < 0.2
