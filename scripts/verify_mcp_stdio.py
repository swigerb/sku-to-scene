"""End-to-end MCP stdio check using the exact launcher configured in .mcp.json.

Starts the configured command in a de-activated environment (no VIRTUAL_ENV, no .venv on PATH, no PYTHONPATH),
then performs initialize -> tools/list -> tools/call over stdio, as the Copilot app would.

  python scripts/verify_mcp_stdio.py      (needs the `mcp` package in the interpreter running this script)
"""
from __future__ import annotations

import anyio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent


def deactivated_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")}
    venv = str(REPO_ROOT / ".venv").lower()
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if not p.lower().startswith(venv))
    env.setdefault("SKU2SCENE_MOCK_LATENCY_SCALE", "0")
    return env


async def run() -> int:
    cfg = json.loads((REPO_ROOT / ".mcp.json").read_text())["mcpServers"]["sku-to-scene"]
    print(f"configured launcher: {cfg['command']} {' '.join(cfg['args'])}")
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"],
                                   env={**deactivated_env(), **cfg.get("env", {})}, cwd=str(REPO_ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"initialize: {init.server_info.name} (protocol {init.protocol_version})")
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            print(f"tools/list: {len(tools)} tools -> {', '.join(tools)}")
            res = await session.call_tool("list_models", {})
            text = "".join(getattr(c, "text", "") for c in res.content)
            print(f"tools/call list_models: isError={res.is_error}, {len(text)} chars")
            res2 = await session.call_tool("estimate_cost", {"model": "minimax-h3-max-turbo", "duration": 6,
                                                             "resolution": "768P"})
            print(f"tools/call estimate_cost: isError={res2.is_error} -> "
                  f"{''.join(getattr(c, 'text', '') for c in res2.content)[:160]}")
            ok = not res.is_error and not res2.is_error and "generate_video" in tools and "kling" in text.lower()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(anyio.run(run))
