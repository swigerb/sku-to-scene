import asyncio

from sku_to_scene import lto


def test_lto_drafts_stop_for_selection_then_hero(settings):
    sess = lto.lto_drafts(settings=settings)
    assert sess["status"] == "awaiting_selection" and "final" not in sess
    assert [d["model"] for d in sess["drafts"]] == ["minimax-h3-max-turbo", "ltx-2.5-fast", "minimax-h3-max-turbo"]
    c = sess["costs"]
    assert c["turbo_drafts_estimate_usd"] * 2 == c["same_turbo_drafts_on_h3_max_usd"]
    # Scripted rehearsal values are labelled and never approve publication.
    assert all(d["qa"]["measured"] is False and not d["qa"]["publish_approved"] for d in sess["drafts"])
    assert [d["qa"]["verdict"] for d in sess["drafts"]] == ["pass", "pass", "fail"]

    out = lto.lto_hero(2, sess["session_id"], settings=settings)
    f = out["final"]
    assert (f["model"], f["mode"], f["audio"]) == ("kling-v3-pro", "image-to-video", True)
    assert f["payload"]["duration"] == "8" and f["payload"]["generate_audio"] is True
    assert out["provenance"] == ["simulated"] and out["status"] == "hero_rendered"
    assert lto.load_session(None, settings)["selected_variant"] == 2


def test_mcp_server_lists_tools():
    from sku_to_scene.mcp_server import server

    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"generate_video", "route_brief", "estimate_cost", "lto_draft_concepts", "lto_render_hero",
            "reroll_clip", "evaluate_brand_compliance", "cost_report", "foundry_readiness"} <= names
