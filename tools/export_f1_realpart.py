#!/usr/bin/env python3
"""Export path for F1 (adaptive roughing) on the real part — P5/6 glue.

Card ``t_96921586`` [F360RE-P5/6], plan row
``Fusion 360 RE/docs/p5-execution-plan.md:343``:

    the exported program re-parses through `AI CAM 4.0/kernel/gcode.py`
    with exit 0

This script is the *export path* half of that gate.  One command walks the
plan §3.4 happy path end to end and exits 0:

    STL -> kernel.stl.parse_stl
       -> kernel.strategies.adaptive_engagement   (F1, landed by P5/3)
       -> simulation.SimulationEngine             (stock actually gets cut)
       -> post.ir.segments_to_ir
       -> post.fanuc.FanucRenderer.render_to_file (the app's own export API,
                                                   same bytes as the GUI's
                                                   File -> Export G-code)
       -> .nc file on disk
       -> kernel.gcode.parse_gcode re-reads the written bytes (self-check)

Usage
-----

Full export::

    ./.venv/Scripts/python.exe tools/export_f1_realpart.py \
        --stl "<part>.stl" --out "<program>.nc"

Gate P5/6-2 on any existing program (exit 0 = re-parsed)::

    ./.venv/Scripts/python.exe tools/export_f1_realpart.py \
        --parse-only "<program>.nc"

Parameters (declared, not discovered — see the report for sources)
------------------------------------------------------------------

========  =============================================================
tool      D = 3.175 mm, 2-flute  (EXP-034's tool, ``#1 - O3.175mm flat``)
stepover  0.4 x D = 1.27 mm     (const_engagement default, card t_68c215ec)
stepdown  1.0 mm                (P5/3's real-part e2e)
feed      1000 mm/min           (adaptive.md R8 ``tool_feedCutting``)
spindle   12000 rpm             (EXP-034 posted ``S12000``)
clearance stock top + 5.0 mm    (DERIVED — see below)
sim       2.0 mm/cell — P5/3 measured that 0.5 mm needs ~33 GB here
          (O(moves x cells) frame snapshots), 2.0 mm runs in ~2 GB
========  =============================================================

Why the clearance is derived, not typed
---------------------------------------

``OperationParams.clearance_height`` is an **absolute Z plane**
(``kernel/strategies/base.py:29``, used verbatim by F1's link rapids at
``kernel/strategies/adaptive_engagement.py:439`` and ``:488``), and the
post's end-of-program retract is a second absolute plane
(``FanucRenderer(retract_z=...)``, ``post/fanuc.py:133``).  Passing a bare
``5.0`` for the S1 part (whose stock top sits at Z 53.345 in the STL frame)
puts the XY link rapids 48 mm *inside* the stock — measured in the first
export of this card, kept as
``Fusion 360 RE/tests/p5_evidence/p5_6_export_run1_clearance5_superseded.nc``
(``G00 X1282.700 Y12.700 Z5.000``).  This glue therefore derives

    clearance_z = stock.max.z + 5.0
    FanucRenderer(retract_z=clearance_z, safe_z=clearance_z)

and the export **refuses to write** a program whose XY-traversing rapid sits
below the stock top (``find_rapid_clearance_violations``).  Only rapid
planes change: ``clearance_height`` is read at the two ``_rapid`` call sites
only, so levels / rings / moves / feeds / the simulated cut are identical.

Scope: path-limited glue only.  It wires modules that already exist; no file
under ``kernel/``, ``post/``, ``simulation/`` or ``app/`` is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    # Invoked as `python tools/export_f1_realpart.py`: sys.path[0] is this
    # file's own directory, so put the repo root there for kernel/post/... .
    # (Importing the module instead leaves __package__ == "tools" and this
    # block is skipped.)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from kernel.gcode import (  # noqa: E402
    SUPPORTED_GCODES,
    SUPPORTED_MCODES,
    parse_gcode,
    summary,
)
from kernel.stl import parse_stl  # noqa: E402
from kernel.strategies import get_strategy  # noqa: E402
from kernel.strategies.base import OperationParams  # noqa: E402
from kernel.types import BBox, ToolDef, Vec3  # noqa: E402
from post.fanuc import FanucRenderer  # noqa: E402
from post.ir import segments_to_ir  # noqa: E402
from simulation.engine import SimulationEngine, StockModel  # noqa: E402

STRATEGY = "adaptive_engagement"
TOOL_DIAMETER_MM = 3.175
TOOL_ID = "T01"
STEPOVER_FRACTION = 0.4
STEPDOWN_MM = 1.0
FEED_MM_MIN = 1000.0
SPINDLE_RPM = 12000.0
CLEARANCE_ABOVE_STOCK_MM = 5.0   # derived: clearance_z = stock top + this
SIM_RESOLUTION_MM = 2.0

# post/fanuc.py's mandatory safety blocks (also asserted by the GUI export's
# integration tests) — a program missing one of these is not exportable.
MANDATORY_BLOCKS = ("O0001", "M06", "M03", "M30", "G21", "G90")


class ExportError(RuntimeError):
    """A pipeline stage failed; the CLI reports it and exits non-zero."""


def find_rapid_clearance_violations(
    text: str, stock_top: float, eps: float = 1e-9
) -> list[str]:
    """Return every XY-traversing rapid that sits below the stock top.

    ``OperationParams.clearance_height`` is an absolute Z plane, so a caller
    that passes a bare ``5.0`` for a part whose stock top is at 53.345 gets
    link rapids *inside* the stock.  This is the export-time guard: modal Z
    is tracked across blocks (``parse_gcode``), so a ``G00 X.. Y..`` block
    without its own Z word is judged by the Z in effect.

    Z-only rapids are deliberately not judged: F1's ``_rapid(entry, z_prev)``
    (adaptive_engagement.py:440) lands on the previously cleared level
    surface, which is its documented entry strategy, not a traverse.
    """
    violations: list[str] = []
    modal_z: float | None = None
    for cmd in parse_gcode(text):
        if "Z" in cmd.params:
            modal_z = cmd.params["Z"]
        if cmd.command != "G0":
            continue
        if "X" not in cmd.params and "Y" not in cmd.params:
            continue  # Z-only rapid: lands on the cleared level, not a traverse
        z_here = cmd.params.get("Z", modal_z)
        if z_here is None:
            violations.append(
                f"line {cmd.line_number}: XY rapid with unknown Z: "
                f"{cmd.raw.strip()!r}"
            )
        elif z_here < stock_top - eps:
            violations.append(
                f"line {cmd.line_number}: XY rapid at Z{z_here:g} below "
                f"stock top Z{stock_top:g}: {cmd.raw.strip()!r}"
            )
    return violations


def export_program(stl_path: Path, out_path: Path, sim_resolution: float) -> dict:
    """Walk STL -> strategy -> simulation -> .nc -> re-parse.

    Returns a stats dict; raises ExportError if any stage fails its check.
    """
    t0 = time.time()
    if not stl_path.is_file():
        raise ExportError(f"STL not found: {stl_path}")

    # ---- STL -> stock ----------------------------------------------------
    mesh = parse_stl(str(stl_path))
    verts = np.asarray(mesh["vertices"], dtype=float)
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    stock = BBox(
        min=Vec3(float(lo[0]), float(lo[1]), float(lo[2])),
        max=Vec3(float(hi[0]), float(hi[1]), float(hi[2])),
    )
    if not (stock.size.x > 0 and stock.size.y > 0 and stock.size.z > 0):
        raise ExportError(f"degenerate stock bbox: {stock}")

    # ---- strategy (F1, P5/3) --------------------------------------------
    tool = ToolDef(
        tool_id=TOOL_ID,
        name="3.175mm flat end mill",
        diameter=TOOL_DIAMETER_MM,
        flute_count=2,  # EXP-034's tool is a 2-flute 1/8 in flat
    )
    # clearance_height is an ABSOLUTE Z plane, not "above stock" — derive it
    # so link rapids stay above the stock for any part (module docstring).
    clearance_z = stock.max.z + CLEARANCE_ABOVE_STOCK_MM
    operation = OperationParams(
        strategy=STRATEGY,
        stock=stock,
        tool=tool,
        stepover=STEPOVER_FRACTION,
        stepdown=STEPDOWN_MM,
        feed_rate=FEED_MM_MIN,
        spindle_speed=SPINDLE_RPM,
        clearance_height=clearance_z,
        top_of_stock=stock.max.z,
        bottom_of_stock=stock.min.z,
    )
    tp = get_strategy(STRATEGY).run(operation)
    if not tp.moves:
        raise ExportError("strategy produced no moves")

    # ---- simulation (stock must actually be cut) -------------------------
    model = StockModel(
        origin_x=stock.min.x,
        origin_y=stock.min.y,
        width_x=stock.size.x,
        width_y=stock.size.y,
        top_z=stock.max.z,
        resolution=sim_resolution,
    )
    engine = SimulationEngine(stock=model, cutter_diameter=TOOL_DIAMETER_MM)
    frames = engine.simulate_to_frames(tp)
    if len(frames) != len(tp.moves):
        raise ExportError(
            f"simulation frames {len(frames)} != moves {len(tp.moves)}"
        )
    final_mean = float(frames[-1].zmap.mean())
    if not final_mean < model.top_z:
        raise ExportError(
            f"simulation removed no material (final mean {final_mean} "
            f"!= below top {model.top_z})"
        )
    del frames  # free the frame snapshots before the (large) program text

    # ---- IR -> Fanuc -> file (post/fanuc.py's export API) ---------------
    renderer = FanucRenderer(retract_z=clearance_z, safe_z=clearance_z)
    segments = segments_to_ir(tp)
    gcode = renderer.render(segments)
    violations = find_rapid_clearance_violations(gcode, stock.max.z)
    if violations:
        raise ExportError(
            f"{len(violations)} XY rapid(s) below stock top "
            f"Z{stock.max.z:g} — refusing to write "
            f"{out_path}: " + "; ".join(violations[:3])
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    renderer.render_to_file(segments, str(out_path))
    if not out_path.is_file():
        raise ExportError(f"renderer did not write {out_path}")
    if out_path.read_text(encoding="utf-8") != gcode:
        raise ExportError(
            f"{out_path} does not byte-match renderer.render() output"
        )
    raw = out_path.read_bytes()
    if not raw:
        raise ExportError(f"wrote an empty program: {out_path}")

    # ---- self-check: re-read the written bytes through kernel/gcode.py ---
    text = raw.decode("utf-8", errors="replace")
    commands = parse_gcode(text)
    if not commands:
        raise ExportError("kernel.gcode.parse_gcode found no commands")
    motion = Counter(c.command for c in commands)
    for needed in ("G0", "G1"):
        if motion.get(needed, 0) == 0:
            raise ExportError(f"re-parse found no {needed} blocks")
    missing = [b for b in MANDATORY_BLOCKS if b not in text]
    if missing:
        raise ExportError(f"missing mandatory blocks: {missing}")

    return {
        "stl": str(stl_path),
        "triangles": len(mesh["faces"]),
        "stock_min": (float(lo[0]), float(lo[1]), float(lo[2])),
        "stock_max": (float(hi[0]), float(hi[1]), float(hi[2])),
        "clearance_z": clearance_z,
        "rapid_clearance_violations": len(violations),
        "levels": tp.params.get("levels"),
        "rings_per_level": tp.params.get("rings_per_level"),
        "moves": len(tp.moves),
        "feed_vocabulary": tp.params.get("feed_vocabulary"),
        "feed_histogram": tp.params.get("feed_histogram"),
        "sim_grid": f"{model.rows} x {model.cols} @ {sim_resolution} mm",
        "sim_final_mean_z": final_mean,
        "out": str(out_path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "lines": text.count("\n"),
        "reparse_commands": len(commands),
        "reparse_histogram": dict(sorted(motion.items())),
        "elapsed_s": time.time() - t0,
    }


def reparse_program(path: Path) -> dict:
    """Re-parse an existing .nc through kernel/gcode.py (gate P5/6-2)."""
    if not path.is_file():
        raise ExportError(f"program not found: {path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    commands = parse_gcode(text)
    if not commands:
        raise ExportError(
            f"kernel.gcode.parse_gcode found no commands in {path}"
        )
    histogram = Counter(c.command for c in commands)
    feeds = sorted({c.params["F"] for c in commands if "F" in c.params})
    spindles = sorted({c.params["S"] for c in commands if "S" in c.params})
    unsupported = sorted(
        {
            c.command
            for c in commands
            if (c.command.startswith("G") and c.command not in SUPPORTED_GCODES)
            or (c.command.startswith("M") and c.command not in SUPPORTED_MCODES)
        }
    )
    return {
        "path": str(path),
        "bytes": len(raw),
        "lines": len(text.splitlines()),
        "commands": len(commands),
        "histogram": dict(sorted(histogram.items())),
        "feeds": feeds,
        "spindles": spindles,
        # kernel/gcode.py is a NO-TOUCH file: its SUPPORTED_* sets are a
        # census input, never a gate. The parser accepts every G/M word it
        # sees; only the *sets* are narrower.
        "unsupported_by_set": unsupported,
        "summary": summary(commands),
    }


def _fmt(value) -> str:
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="export_f1_realpart.py",
        description=(
            "F1 export path: STL -> adaptive_engagement -> simulation -> "
            ".nc -> kernel.gcode re-parse (P5/6)."
        ),
    )
    parser.add_argument("--stl", type=Path, help="input STL (export mode)")
    parser.add_argument("--out", type=Path, help="output .nc (export mode)")
    parser.add_argument(
        "--sim-resolution",
        type=float,
        default=SIM_RESOLUTION_MM,
        help=f"simulation cell size in mm (default {SIM_RESOLUTION_MM})",
    )
    parser.add_argument(
        "--parse-only",
        type=Path,
        metavar="PROGRAM_NC",
        help="skip the pipeline: re-parse this program via kernel/gcode.py",
    )
    args = parser.parse_args(argv)

    try:
        if args.parse_only is not None:
            stats = reparse_program(args.parse_only)
            print(f"[parse] file               : {stats['path']}")
            print(f"[parse] bytes / lines      : {stats['bytes']} / {stats['lines']}")
            print(f"[parse] commands parsed    : {stats['commands']}")
            print(stats["summary"])
            print(f"[parse] feed words (F)     : {stats['feeds']}")
            print(f"[parse] spindle words (S)  : {stats['spindles']}")
            print(
                "[parse] not in kernel.gcode SUPPORTED_* sets (info, not gated) "
                f": {stats['unsupported_by_set']}"
            )
            print("PARSE_EXIT=0")
            return 0

        if args.stl is None or args.out is None:
            parser.error("--stl and --out are required unless --parse-only is given")

        stats = export_program(args.stl, args.out, args.sim_resolution)
        print(f"[export] stl               : {stats['stl']}")
        print(f"[export] triangles         : {_fmt(stats['triangles'])}")
        print(
            "[export] stock bbox        : "
            f"{stats['stock_min']} .. {stats['stock_max']}"
        )
        print(
            "[export] clearance plane   : "
            f"Z{stats['clearance_z']:.3f} (stock top + "
            f"{CLEARANCE_ABOVE_STOCK_MM:g} mm; XY rapids checked: "
            f"{stats['rapid_clearance_violations']} violations)"
        )
        print(f"[export] strategy          : {STRATEGY}")
        print(
            f"[export] levels / rings    : {stats['levels']} / "
            f"{stats['rings_per_level']}"
        )
        print(f"[export] moves             : {stats['moves']}")
        print(f"[export] feed vocabulary   : {stats['feed_vocabulary']}")
        print(f"[export] feed histogram    : {stats['feed_histogram']}")
        print(f"[export] sim grid          : {stats['sim_grid']}")
        print(
            "[export] sim final mean z  : "
            f"{stats['sim_final_mean_z']:.4f} (stock top cut)"
        )
        print(f"[export] program           : {stats['out']}")
        print(
            f"[export] program bytes     : {stats['bytes']} "
            f"({stats['lines']} lines)"
        )
        print(f"[export] program sha256    : {stats['sha256']}")
        print(
            f"[export] re-parse          : kernel.gcode -> "
            f"{stats['reparse_commands']} commands "
            f"{stats['reparse_histogram']}"
        )
        print(f"[export] elapsed           : {stats['elapsed_s']:.2f}s")
        print("EXPORT_EXIT=0")
        return 0
    except ExportError as exc:
        print(f"EXPORT_ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
