"""
AI CAM 4.0 Fanuc Post-processor — G-code renderer for Fanuc controllers.

Produces standard Fanuc G-code with all mandatory safety blocks:
O0001, M06, M03, F, M08, M30.

Output format: .nc files suitable for direct transfer to Fanuc CNC controls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from post.ir import IRSegment, SegmentType

if TYPE_CHECKING:
    pass


class BaseRenderer:
    """Abstract base for all post-processor renderers."""

    name: str = "base"
    extension: str = ".nc"

    def render(self, segments: list[IRSegment]) -> str:
        raise NotImplementedError

    def render_to_file(self, segments: list[IRSegment], path: str) -> None:
        output = self.render(segments)
        with open(path, "w", encoding="utf-8") as f:
            f.write(output)


class FanucRenderer(BaseRenderer):
    """
    Fanuc-compatible G-code renderer.

    Generates standard G-code with:
    - Program number (O0001)
    - Metric mode (G21)
    - Absolute positioning (G90)
    - Tool change (M06)
    - Spindle start (M03)
    - Feed rate (F)
    - Coolant (M08)
    - Program end (M30)
    """

    name = "fanuc"
    extension = ".nc"

    def __init__(
        self,
        program_number: int = 1,
        retract_z: float = 50.0,
        safe_z: float = 5.0,
    ) -> None:
        self.program_number = program_number
        self.retract_z = retract_z
        self.safe_z = safe_z

    def render(self, segments: list[IRSegment]) -> str:
        lines: list[str] = []

        # ---- Mandatory safety header ----
        lines.append(f"O{self.program_number:04d}")
        lines.append("(AI CAM 4.0 — Fanuc G-code)")
        lines.append("(Generated post-processor)")
        lines.append("")

        # Initialization block
        lines.append("(=== SAFETY BLOCK ===)")
        lines.append("G21          (Metric mode)")
        lines.append("G90          (Absolute positioning)")
        lines.append("G17          (XY plane select)")
        lines.append("G40          (Cancel cutter comp)")
        lines.append("G49          (Cancel tool length offset)")
        lines.append("G80          (Cancel canned cycles)")
        lines.append("G94          (Feed per minute)")
        lines.append("")

        current_tool = ""
        current_spindle = 0.0
        current_feed = 0.0
        coolant_on = False
        prev_x = None
        prev_y = None
        prev_z = None

        for seg in segments:
            if seg.segment_type == SegmentType.PROGRAM_START:
                if seg.comment:
                    lines.append(f"({seg.comment})")
                lines.append("")
                continue

            elif seg.segment_type == SegmentType.TOOL_CHANGE:
                if seg.tool_number:
                    lines.append(f"(Tool: {seg.comment})")
                    lines.append(f"T{seg.tool_number} M06")
                    current_tool = seg.tool_number
                lines.append("")
                continue

            elif seg.segment_type == SegmentType.SPINDLE_ON:
                lines.append(f"(Spindle ON)")
                direction = "M03" if seg.spindle_direction >= 1 else "M04"
                lines.append(f"S{seg.spindle_speed:.0f} {direction}")
                current_spindle = seg.spindle_speed
                lines.append("")
                continue

            elif seg.segment_type == SegmentType.SPINDLE_OFF:
                lines.append("M05          (Spindle OFF)")
                lines.append("")
                continue

            elif seg.segment_type == SegmentType.COOLANT_ON:
                lines.append("M08          (Coolant ON)")
                coolant_on = True
                lines.append("")
                continue

            elif seg.segment_type == SegmentType.COOLANT_OFF:
                lines.append("M09          (Coolant OFF)")
                coolant_on = False
                lines.append("")
                continue

            elif seg.segment_type == SegmentType.PROGRAM_END:
                lines.append("(=== PROGRAM END ===)")
                lines.append("G00 Z{:.3f}  (Retract to safe Z)".format(self.retract_z))
                lines.append("G00 X0 Y0   (Return to home)")
                lines.append("M30          (Program end and rewind)")
                lines.append("%")
                continue

            elif seg.segment_type == SegmentType.DWELL:
                lines.append(f"G04 P{seg.dwell_ms:.0f}  (Dwell {seg.dwell_ms:.0f}ms)")
                continue

            elif seg.segment_type == SegmentType.COMMENT:
                if seg.comment:
                    lines.append(f"({seg.comment})")
                continue

            # ---- Motion segments ----
            if not seg.is_motion:
                continue

            # Build coordinate string
            coords = self._format_coords(seg, prev_x, prev_y, prev_z)

            if seg.segment_type == SegmentType.RAPID:
                line = f"G00 {coords}"
            elif seg.segment_type == SegmentType.LINEAR:
                # Feed rate — only emit when changed
                f_str = ""
                if seg.feed > 0 and seg.feed != current_feed:
                    f_str = f" F{seg.feed:.1f}"
                    current_feed = seg.feed
                line = f"G01 {coords}{f_str}"
            elif seg.segment_type == SegmentType.ARC_CW:
                line = f"G02 {coords}{self._format_arc(seg)}"
            elif seg.segment_type == SegmentType.ARC_CCW:
                line = f"G03 {coords}{self._format_arc(seg)}"
            elif seg.segment_type == SegmentType.DRILL:
                line = f"G81 {coords} R{self.safe_z:.3f}"
            elif seg.segment_type == SegmentType.RETRACT:
                line = f"G00 Z{seg.z:.3f}"
            else:
                line = f"G01 {coords}"

            lines.append(line)
            prev_x, prev_y, prev_z = seg.x, seg.y, seg.z

        return "\n".join(lines) + "\n"

    def _format_coords(
        self,
        seg: IRSegment,
        prev_x: float | None,
        prev_y: float | None,
        prev_z: float | None,
    ) -> str:
        """Format X/Y/Z coordinates, suppressing axis if unchanged."""
        parts: list[str] = []
        if prev_x is None or abs(seg.x - prev_x) > 1e-6:
            parts.append(f"X{seg.x:.3f}")
        if prev_y is None or abs(seg.y - prev_y) > 1e-6:
            parts.append(f"Y{seg.y:.3f}")
        if prev_z is None or abs(seg.z - prev_z) > 1e-6:
            parts.append(f"Z{seg.z:.3f}")
        return " ".join(parts)

    def _format_arc(self, seg: IRSegment) -> str:
        """Format arc I/J/K offsets."""
        parts: list[str] = []
        if abs(seg.i) > 1e-6:
            parts.append(f"I{seg.i:.3f}")
        if abs(seg.j) > 1e-6:
            parts.append(f"J{seg.j:.3f}")
        if abs(seg.k) > 1e-6:
            parts.append(f"K{seg.k:.3f}")
        if seg.feed > 0:
            parts.append(f"F{seg.feed:.1f}")
        return " " + " ".join(parts) if parts else ""
