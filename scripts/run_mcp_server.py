"""Portable stdio launcher for the sku-to-scene MCP server (stdlib only).

MCP hosts (GitHub Copilot app/CLI, VS Code) start servers without an activated virtualenv. This launcher is the
configured entry point: it runs the server with the repository's own .venv interpreter, never whatever `python`
happens to be first on PATH. Override with SKU2SCENE_PYTHON=<path to interpreter>.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP_HINT = (
    "sku-to-scene MCP: no project virtualenv found at {venv}.\n"
    "Set it up once from the repo root:\n"
    "  python -m venv .venv\n"
    "  Windows: .venv\\Scripts\\python -m pip install -e .\n"
    "  macOS/Linux: .venv/bin/python -m pip install -e .\n"
    "or set SKU2SCENE_PYTHON to an interpreter that has the package installed.\n"
)


def venv_python() -> Path:
    override = os.environ.get("SKU2SCENE_PYTHON")
    if override:
        return Path(override)
    venv = REPO_ROOT / ".venv"
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main() -> int:
    py = venv_python()
    if not py.is_file():
        sys.stderr.write(SETUP_HINT.format(venv=py))
        return 1
    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # Inherit stdin/stdout/stderr so the MCP stdio stream passes straight through to the server process.
    return subprocess.call([str(py), "-m", "sku_to_scene.mcp_server", *sys.argv[1:]], cwd=REPO_ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
