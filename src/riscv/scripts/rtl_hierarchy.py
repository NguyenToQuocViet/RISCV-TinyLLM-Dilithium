#------------------------------------------------------------------------------
# Module      : rtl_hierarchy
# Description : Print the RTL module hierarchy elaborated by Verilator.
# Author      : Viet Nguyen To Quoc
# Date        : 2026-10-28
#------------------------------------------------------------------------------
"""Print the instance tree of rtl/*.sv using `verilator --json-only`.

Usage (from src/riscv):
    python scripts/rtl_hierarchy.py                    # tree for every top module
    python scripts/rtl_hierarchy.py alu                # what alu contains (downwards)
    python scripts/rtl_hierarchy.py --parents alu      # who instantiates alu (upwards)

Hierarchy comes from Verilator elaboration, not from text matching. The
regex below only lists candidate module names to use as --top-module.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RISCV_DIR = Path(__file__).resolve().parents[1]
RTL_DIR = RISCV_DIR / "rtl"
MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)


def rtl_files():
    # package first so Verilator sees its types before the users
    files = sorted(RTL_DIR.glob("*.sv"))
    return sorted(files, key=lambda p: (not p.name.endswith("_pkg.sv"), p.name))


def module_names(files):
    names = []
    for f in files:
        names += MODULE_RE.findall(f.read_text())
    return names


def elaborate(top, files, workdir):
    """Return {module: [(instance, child_module), ...]} reachable from top."""
    cmd = ["verilator", "--json-only", "--Wno-fatal", "-Mdir", workdir,
           "--top-module", top] + [str(f) for f in files]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=RISCV_DIR)
    out = Path(workdir) / f"V{top}.tree.json"
    if res.returncode != 0 or not out.exists():
        sys.exit(f"verilator failed for top '{top}':\n{res.stderr}")

    tree = json.loads(out.read_text())
    by_addr = {}

    def index(node):
        if isinstance(node, dict):
            if "addr" in node:
                by_addr[node["addr"]] = node
            for v in node.values():
                index(v)
        elif isinstance(node, list):
            for v in node:
                index(v)

    def cells(node, found):
        if isinstance(node, dict):
            if node.get("type") == "CELL":
                found.append(node)
            for v in node.values():
                cells(v, found)
        elif isinstance(node, list):
            for v in node:
                cells(v, found)

    index(tree)
    hier = {}
    for node in by_addr.values():
        if node.get("type") != "MODULE" or node["origName"].startswith("@"):
            continue
        found = []
        cells(node.get("stmtsp", []), found)
        hier[node["origName"]] = [
            (c["name"], by_addr[c["modp"]]["origName"]) for c in found
        ]
    return hier


def print_tree(hier, mod, indent=0, inst=None):
    label = f"{inst} : {mod}" if inst else mod
    print("  " * indent + label)
    for child_inst, child_mod in hier.get(mod, []):
        print_tree(hier, child_mod, indent + 1, child_inst)


def print_parents(hier, mod):
    print(mod)
    found = sorted((p, i) for p, insts in hier.items() for i, c in insts if c == mod)
    for parent, inst in found:
        print(f"  <- {parent} ({inst})")
    if not found:
        print("  <- (not instantiated in rtl/)")


def main():
    files = rtl_files()
    names = module_names(files)
    args = sys.argv[1:]
    parents = bool(args) and args[0] == "--parents"
    wanted = args[1:] if parents else args
    if parents and not wanted:
        sys.exit("usage: rtl_hierarchy.py --parents <module> [<module> ...]")
    unknown = [w for w in wanted if w not in names]
    if unknown:
        sys.exit(f"unknown module(s): {', '.join(unknown)}")

    with tempfile.TemporaryDirectory() as workdir:
        # elaborate every module as top, merge; a module is a root if no
        # other module instantiates it
        hier = {}
        for top in names:
            hier.update(elaborate(top, files, workdir))

    if parents:
        for mod in wanted:
            print_parents(hier, mod)
        return

    children = {c for insts in hier.values() for _, c in insts}
    roots = wanted or [m for m in names if m not in children]
    for root in roots:
        print_tree(hier, root)


if __name__ == "__main__":
    main()
