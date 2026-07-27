"""
AI CAM 4.0 Post-processor Intermediate Representation.

Segments are an intermediate form between ToolpathData and machine-specific
G-code. Each IRSegment captures a single machine operation with all context
needed for any post-processor to render it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kernel.types import ToolpathData


class SegmentType(Enum):
    """Machine operation types."""
    RAPID = auto()       # G0 — rapid positioning
    LINEAR = auto()      # G1 — linear interpolation
    ARC_CW = auto()      # G2 — circular interpolation clockwise
    ARC_CCW = auto()     # G3 — circular interpolation counter-clockwise
    DRILL = auto()       # G81–G89 canned drilling cycles
    RETRACT = auto()     # Z retract / clearance move
    SPINDLE_ON = auto()  # M03 / M04
    SPINDLE_OFF = auto() # M05
    COOLANT_ON = auto()  # M08
    COOLANT_OFF = auto() # M09
    TOOL_CHANGE = auto()  # M06
    PROGRAM_START = auto() # Program header
    PROGRAM_END = auto()   # M30 / M02
    COMMENT = auto()       # Parenthetical or semicolon comment
    DWELL = auto()         # G04


@dataclass(slots=True)
class IRSegment:
    """
    Intermediate representation of a single machine operation.

    All coordinates are in machine units (mm for metric, inches for inch).
    Feed rates are in units/min. Spindle speed is in RPM.
    """
    segment_type: SegmentType

    # Coordinates (used by motion segments)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    i: float = 0.0      # Arc center X offset
    j: float = 0.0      # Arc center Y offset
    k: float = 0.0      # Arc center Z offset

    # Machine parameters
    feed: float = 0.0           # Feed rate (mm/min)
    spindle_speed: float = 0.0  # RPM
    spindle_direction: int = 1  # 1=CW, -1=CCW
    dwell_ms: float = 0.0      # Dwell time (ms)

    # Tool
    tool_number: str = ""       # e.g. "1" for T1
    tool_name: str = ""         # e.g. "10mm End Mill"

    # Metadata
    comment: str = ""
    source_move_index: int = -1

    @property
    def is_motion(self) -> bool:
        """True if this segment involves tool motion."""
        return self.segment_type in (
            SegmentType.RAPID,
            SegmentType.LINEAR,
            SegmentType.ARC_CW,
            SegmentType.ARC_CCW,
            SegmentType.DRILL,
            SegmentType.RETRACT,
        )


def segments_to_ir(toolpath: ToolpathData) -> list[IRSegment]:
    """
    Convert a ToolpathData into a list of IRSegments.

    This inserts machine-level operations (tool change, spindle on, coolant)
    at the appropriate points, wrapping the raw motion moves.
    """
    from kernel.types import MoveType

    segments: list[IRSegment] = []

    # Program start
    segments.append(IRSegment(
        segment_type=SegmentType.PROGRAM_START,
        comment=f"AI CAM 4.0 — {toolpath.name}",
    ))

    # Tool change
    segments.append(IRSegment(
        segment_type=SegmentType.TOOL_CHANGE,
        tool_number=toolpath.tool.tool_id.replace("T", ""),
        tool_name=toolpath.tool.name,
        comment=f"Tool: {toolpath.tool.tool_id} {toolpath.tool.name} "
                f"D={toolpath.tool.diameter:.1f}mm",
    ))

    # Spindle on
    first_feed_move = next(
        (m for m in toolpath.moves if m.is_cutting), None
    )
    spindle_speed = first_feed_move.spindle_speed if first_feed_move else 0
    segments.append(IRSegment(
        segment_type=SegmentType.SPINDLE_ON,
        spindle_speed=spindle_speed,
        spindle_direction=1,
        comment=f"Spindle CW {spindle_speed:.0f} RPM",
    ))

    # Coolant on (if any cutting move uses coolant)
    has_coolant = any(m.coolant for m in toolpath.moves if m.is_cutting)
    if has_coolant:
        segments.append(IRSegment(
            segment_type=SegmentType.COOLANT_ON,
            comment="Coolant ON",
        ))

    # Convert motion moves
    for idx, move in enumerate(toolpath.moves):
        type_map = {
            MoveType.RAPID: SegmentType.RAPID,
            MoveType.LINEAR: SegmentType.LINEAR,
            MoveType.ARC_CW: SegmentType.ARC_CW,
            MoveType.ARC_CCW: SegmentType.ARC_CCW,
            MoveType.DRILL: SegmentType.DRILL,
            MoveType.RETRACT: SegmentType.RETRACT,
        }
        seg_type = type_map.get(move.move_type, SegmentType.LINEAR)

        seg = IRSegment(
            segment_type=seg_type,
            x=move.end.x,
            y=move.end.y,
            z=move.end.z,
            feed=move.feed,
            spindle_speed=move.spindle_speed,
            source_move_index=idx,
        )

        # Arc center offset (relative to start of move)
        if move.arc_center is not None:
            # Get previous position
            prev_x = toolpath.moves[idx - 1].end.x if idx > 0 else 0.0
            prev_y = toolpath.moves[idx - 1].end.y if idx > 0 else 0.0
            prev_z = toolpath.moves[idx - 1].end.z if idx > 0 else 0.0
            seg.i = move.arc_center.x - prev_x
            seg.j = move.arc_center.y - prev_y
            seg.k = move.arc_center.z - prev_z

        segments.append(seg)

    # Program end
    segments.append(IRSegment(
        segment_type=SegmentType.SPINDLE_OFF,
        comment="Spindle OFF",
    ))
    if has_coolant:
        segments.append(IRSegment(
            segment_type=SegmentType.COOLANT_OFF,
            comment="Coolant OFF",
        ))
    segments.append(IRSegment(
        segment_type=SegmentType.PROGRAM_END,
        comment="End of program",
    ))

    return segments
