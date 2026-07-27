"""
AI CAM 4.0 Heidenhain Post-processor.

Generates Heidenhain conversational-format TNC programs (.H, .HMB).
Uses Q parameters for canned cycles and BLK FORM for stock definition.
"""

from __future__ import annotations

from post.ir import IRSegment, SegmentType, SegmentType as ST
from post.fanuc import BaseRenderer


class HeidenhainRenderer(BaseRenderer):
    """
    Heidenhain iTNC / TNC conversational G-code renderer.

    Output format: Heidenhain ISO (H format) with:
    - BEGIN PGM
    - BLK FORM 0.1 / 0.2 for stock definition
    - TOOL CALL
    - L (linear) / C (circular) moves
    - CYCL CALL
    - END PGM
    """

    name = "heidenhain"
    extension = ".h"

    def __init__(
        self,
        program_name: str = "AICAM",
        retract_z: float = 50.0,
        stock_min: tuple[float, float, float] = (-50.0, -50.0, 0.0),
        stock_max: tuple[float, float, float] = (50.0, 50.0, 20.0),
    ) -> None:
        self.program_name = program_name
        self.retract_z = retract_z
        self.stock_min = stock_min
        self.stock_max = stock_max

    def render(self, segments: list[IRSegment]) -> str:
        lines: list[str] = []

        # ---- Program header ----
        lines.append(f"0  BEGIN PGM {self.program_name} MM")
        lines.append("")

        # Stock definition (BLK FORM)
        lines.append("1  BLK FORM 0.1 Z X+{:0.2f} Y+{:0.2f} Z+{:0.2f}".format(
            *self.stock_min
        ))
        lines.append("2  BLK FORM 0.2 Z X+{:0.2f} Y+{:0.2f} Z+{:0.2f}".format(
            *self.stock_max
        ))
        lines.append("")

        line_num = 10
        current_tool = ""

        for seg in segments:
            if seg.segment_type == SegmentType.PROGRAM_START:
                if seg.comment:
                    lines.append(f"(*) {seg.comment}")
                continue

            elif seg.segment_type == SegmentType.TOOL_CHANGE:
                if seg.tool_number:
                    lines.append(
                        f"{line_num:2d} TOOL CALL {seg.tool_number} Z"
                    )
                    line_num += 1
                    current_tool = seg.tool_number
                continue

            elif seg.segment_type == SegmentType.SPINDLE_ON:
                # Heidenhain uses S in TOOL CALL; standalone M03
                lines.append(
                    f"{line_num:2d} S{seg.spindle_speed:.0f} M3"
                )
                line_num += 1
                continue

            elif seg.segment_type == SegmentType.SPINDLE_OFF:
                lines.append(f"{line_num:2d} M5")
                line_num += 1
                continue

            elif seg.segment_type == SegmentType.COOLANT_ON:
                lines.append(f"{line_num:2d} M8")
                line_num += 1
                continue

            elif seg.segment_type == SegmentType.COOLANT_OFF:
                lines.append(f"{line_num:2d} M9")
                line_num += 1
                continue

            elif seg.segment_type == SegmentType.PROGRAM_END:
                lines.append(
                    f"{line_num:2d} END PGM {self.program_name} MM"
                )
                line_num += 1
                continue

            elif seg.segment_type == SegmentType.DWELL:
                lines.append(
                    f"{line_num:2d} dwell F{seg.dwell_ms / 1000:.3f}"
                )
                line_num += 1
                continue

            elif seg.segment_type == SegmentType.COMMENT:
                if seg.comment:
                    lines.append(f"{line_num:2d} ; {seg.comment}")
                    line_num += 1
                continue

            # ---- Motion segments ----
            if not seg.is_motion:
                continue

            # Heidenhain uses R0 for rapid, Fnnn for feed
            if seg.segment_type == SegmentType.RAPID:
                lines.append(
                    f"{line_num:2d} L X+{seg.x:.3f} Y+{seg.y:.3f} "
                    f"Z+{seg.z:.3f} R0 FMAX M"
                )
            elif seg.segment_type == SegmentType.LINEAR:
                feed_str = f"F{seg.feed:.0f}" if seg.feed > 0 else "FMAX"
                lines.append(
                    f"{line_num:2d} L X+{seg.x:.3f} Y+{seg.y:.3f} "
                    f"Z+{seg.z:.3f} {feed_str} M"
                )
            elif seg.segment_type == SegmentType.ARC_CW:
                feed_str = f"F{seg.feed:.0f}" if seg.feed > 0 else "FMAX"
                # Heidenhain: C R (radius) or DR+ (center offset)
                lines.append(
                    f"{line_num:2d} C X+{seg.x:.3f} Y+{seg.y:.3f} "
                    f"Z+{seg.z:.3f} DR+ I+{seg.i:.3f} J+{seg.j:.3f} "
                    f"{feed_str} M"
                )
            elif seg.segment_type == SegmentType.ARC_CCW:
                feed_str = f"F{seg.feed:.0f}" if seg.feed > 0 else "FMAX"
                lines.append(
                    f"{line_num:2d} C X+{seg.x:.3f} Y+{seg.y:.3f} "
                    f"Z+{seg.z:.3f} DR- I+{seg.i:.3f} J+{seg.j:.3f} "
                    f"{feed_str} M"
                )
            elif seg.segment_type == SegmentType.RETRACT:
                lines.append(
                    f"{line_num:2d} L Z+{seg.z:.3f} R0 FMAX M"
                )
            elif seg.segment_type == SegmentType.DRILL:
                feed_str = f"F{seg.feed:.0f}" if seg.feed > 0 else "FMAX"
                lines.append(
                    f"{line_num:2d} CYCL DEF 200 DRILL"
                )
                line_num += 1
                lines.append(
                    f"{line_num:2d} Q200=+{self.retract_z:.3f}  (SET-UP CLEARANCE)"
                )
                line_num += 1
                lines.append(
                    f"{line_num:2d} Q201=+{seg.z:.3f}  (DEPTH)"
                )
                line_num += 1
                lines.append(
                    f"{line_num:2d} Q206=F{seg.feed:.0f}  (FEED)"
                )
                line_num += 1
                lines.append(
                    f"{line_num:2d} CYCL CALL M"
                )

            line_num += 1

        return "\n".join(lines) + "\n"
