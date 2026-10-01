"""Integration test: the F1 export-path CLI (P5/6 glue).

Card ``t_96921586`` [F360RE-P5/6] — ``tools/export_f1_realpart.py`` must walk
the plan §3.4 happy path (STL -> strategy -> simulation -> .nc) and the
written program must re-parse through ``kernel/gcode.py`` with exit 0
(``Fusion 360 RE/docs/p5-execution-plan.md:343``, stage S4).

The CLI is exercised as a subprocess — the very command the card quotes —
on a small ASCII plate so the whole walk stays well inside the 30 s test
timeout (``pyproject.toml: timeout = 30``).

The three feed values asserted in the posted program are the measured R8
vocabulary ``{feed/3, 0.9*feed, feed}`` at feed = 1000, at the post's 0.1
mm/min precision (``post/fanuc.py``: ``f" F{seg.feed:.1f}"``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.export_f1_realpart import find_rapid_clearance_violations

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "tools" / "export_f1_realpart.py"

# (x0, y0, z0) -> (x1, y1, z1) of the plate the STL describes.
PLATE = (0.0, 0.0, 0.0, 100.0, 60.0, 12.0)

# R8's measured triplet at feed = 1000, as the post prints them.
VOCABULARY_F_WORDS = {333.3, 900.0, 1000.0}


def write_plate_stl(path: Path) -> Path:
    """Write the test plate as an ASCII STL the kernel can parse."""
    x0, y0, z0, x1, y1, z1 = PLATE
    p000, p100, p110, p010 = (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)
    p001, p101, p111, p011 = (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)
    quads = [
        ((0.0, 0.0, 1.0), [p001, p101, p111, p011]),  # +Z
        ((0.0, 0.0, -1.0), [p000, p010, p110, p100]),  # -Z
        ((1.0, 0.0, 0.0), [p100, p110, p111, p101]),   # +X
        ((-1.0, 0.0, 0.0), [p000, p001, p011, p010]),  # -X
        ((0.0, 1.0, 0.0), [p010, p011, p111, p110]),   # +Y
        ((0.0, -1.0, 0.0), [p000, p100, p101, p001]),  # -Y
    ]
    lines = ["solid plate"]
    for normal, corners in quads:
        lines.append("  facet normal {} {} {}".format(*[f"{v:g}" for v in normal]))
        lines.append("    outer loop")
        for corner in corners:
            lines.append("      vertex {} {} {}".format(*[f"{v:g}" for v in corner]))
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid plate")
    path.write_text("\n".join(lines) + "\n")
    return path


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=25,
    )


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    """Run the export CLI once for the module and share its result."""
    tmp = tmp_path_factory.mktemp("export_cli")
    stl = write_plate_stl(tmp / "plate.stl")
    out = tmp / "plate_f1.nc"
    proc = run_cli(
        "--stl", str(stl), "--out", str(out), "--sim-resolution", "1.0"
    )
    return stl, out, proc


class TestExportPath:
    """STL -> strategy -> simulation -> .nc -> re-parse, one command, exit 0."""

    def test_one_command_walks_the_happy_path_and_exits_zero(self, exported):
        stl, out, proc = exported
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        assert "EXPORT_EXIT=0" in proc.stdout
        assert out.is_file() and out.stat().st_size > 0
        # The self-check inside the CLI re-read the written bytes.
        assert "re-parse          : kernel.gcode ->" in proc.stdout
        # Provenance lines the evidence report quotes.
        assert str(stl) in proc.stdout
        assert str(out) in proc.stdout
        assert "program sha256    : " in proc.stdout

    def test_posted_program_has_the_mandatory_blocks_and_vocabulary(self, exported):
        _, out, proc = exported
        assert proc.returncode == 0, proc.stderr
        text = out.read_text(encoding="utf-8")
        for mandatory in ("O0001", "M06", "M03", "M30", "G21", "G90"):
            assert mandatory in text, f"missing {mandatory}"
        f_words = {
            float(tok[1:])
            for line in text.splitlines()
            for tok in line.split()
            if tok.startswith("F")
            and tok[1:].replace(".", "", 1).replace("-", "", 1).isdigit()
        }
        assert f_words, "posted program carries no feed word"
        # Never a value outside the measured three (R8: the feed-optimisation
        # group selects, it never scales).
        assert f_words <= VOCABULARY_F_WORDS, f"off-vocabulary: {f_words}"
        # Plunge (feed/3), reduced (0.9*feed) and cutting (feed) arms are all
        # exercised by this plate — same contract as the P5/3 integration test.
        assert f_words == VOCABULARY_F_WORDS, f"arms missing: {f_words}"

    def test_parse_only_gate_re_parses_the_written_program(self, exported):
        _, out, proc = exported
        assert proc.returncode == 0, proc.stderr
        reparsed = run_cli("--parse-only", str(out))
        assert reparsed.returncode == 0, (
            f"stdout:\n{reparsed.stdout}\nstderr:\n{reparsed.stderr}"
        )
        assert "PARSE_EXIT=0" in reparsed.stdout
        assert "commands parsed    : " in reparsed.stdout

    def test_parse_only_is_not_vacuous(self, tmp_path):
        """A file with no commands must NOT exit 0 (negative control)."""
        empty = tmp_path / "nothing.nc"
        empty.write_text("%\n(T1 D=3.175 - comment only)\n%\n")
        reparsed = run_cli("--parse-only", str(empty))
        assert reparsed.returncode != 0, (
            "parse gate passed on a program with zero commands"
        )
        assert "EXPORT_ERROR" in reparsed.stderr

    def test_exported_program_has_no_sub_stock_xy_rapids(self, exported):
        """Export-time invariant: XY rapids never traverse inside the stock.

        ``clearance_height`` is an absolute Z plane, so the glue derives it
        as stock top + 5.0 mm; this asserts the result on the written bytes
        (modal Z tracked), for both the entry rapid and the end-of-program
        ``G00 X0 Y0`` home move.
        """
        _, out, proc = exported
        assert proc.returncode == 0, proc.stderr
        text = out.read_text(encoding="utf-8")
        stock_top = PLATE[5]
        violations = find_rapid_clearance_violations(text, stock_top)
        assert violations == [], violations
        # the derived plane itself: stock top 12.0 + 5.0 = Z17.000
        assert f"Z{stock_top + 5.0:.3f}" in text
        assert "clearance plane   : Z17.000" in proc.stdout

    def test_clearance_guard_catches_a_sub_stock_rapid(self):
        """Negative control: a rapid inside the stock must be reported.

        A guard that never fires is not a guard — the first export of this
        card shipped exactly this shape (``G00 X.. Y.. Z5.000`` against a
        stock top at Z53.345) and was re-exported only because this check
        exists.
        """
        bad = (
            "G21\n"
            "G00 X10.000 Y10.000 Z5.000\n"   # own Z, below stock top
            "G01 Z1.000 F1000.0\n"           # sets modal Z inside the stock
            "G00 X20.000\n"                  # no Z word: judged by modal Z
            "M30\n"
        )
        violations = find_rapid_clearance_violations(bad, stock_top=12.0)
        assert len(violations) == 2, violations
        assert "below stock top" in violations[0]

    def test_clearance_guard_catches_a_modal_rapid(self):
        """Round-2 hardening: a rapid with no G word of its own is judged too.

        ``kernel.gcode.parse_gcode`` skips G/M-less lines, so the round-1
        (parse-based) guard was blind to exactly this shape — a modal
        continuation while the motion mode is still G0, at a stale modal Z.
        The guard now reads the raw text with its own modal-state reader.
        """
        program = (
            "G21\n"
            "G00 X10.000 Y10.000 Z17.000\n"  # rapid above the stock top 12.0
            "G00 Z5.000\n"                   # Z-only rapid: deliberately skipped
            "X20.000 Y10.000\n"              # modal G0 continuation at Z5 -> violation
            "G01 Z1.000 F1000.0\n"           # feed mode; sets modal Z1
            "M30\n"
        )
        violations = find_rapid_clearance_violations(program, stock_top=12.0)
        assert len(violations) == 1, violations
        assert "below stock top" in violations[0]
