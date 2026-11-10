"""3D Agent toolbox: engineering tools served over MCP (stdio).

Each module in tb/ exposes register(mcp). A module that fails to import is
skipped and reported by toolbox_status, so one missing optional route never
takes the whole server down.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server import MCPServer  # noqa: E402

MODULES = ["cad", "check", "drawings", "materials", "rules", "standards", "fea",
           "electronics", "sourcing", "bom", "make", "sources"]

mcp = MCPServer("3d-agent-toolbox")
_loaded: dict[str, str] = {}

for _name in MODULES:
    try:
        importlib.import_module(f"tb.{_name}").register(mcp)
        _loaded[_name] = "ok"
    except Exception as e:  # noqa: BLE001 - reported, not fatal
        _loaded[_name] = f"unavailable: {type(e).__name__}: {e}"


@mcp.tool()
def toolbox_status() -> dict:
    """Which tool groups loaded and which optional external programs are installed."""
    from tb.common import ROOT, which

    programs = {n: which(n) for n in ["kicad-cli", "ngspice", "ccx", "prusa-slicer", "orca-slicer",
                                      "FreeCADCmd", "openscad", "dot", "wireviz"]}
    return {"ok": True, "root": str(ROOT), "modules": _loaded, "programs": programs}


if __name__ == "__main__":
    mcp.run()
