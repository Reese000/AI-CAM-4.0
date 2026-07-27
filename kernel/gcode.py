"""
G-code parser for AI CAM 4.0 kernel.

Parses G-code text into structured command objects.
Supports common G/M codes used in CNC milling.

Usage:
    from kernel.gcode import parse_gcode
    commands = parse_gcode(gcode_text)
    for cmd in commands:
        print(f"Line {cmd.line}: {cmd.command} {cmd.params}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Supported G-codes and M-codes
SUPPORTED_GCODES = {
    "G0", "G1", "G2", "G3", "G28", "G90", "G91",
    "G17", "G18", "G19",  # Plane selection
    "G40", "G41", "G42",  # Cutter compensation
    "G43", "G49",  # Tool length compensation
    "G54",  # Work coordinate system
    "G80",  # Cancel canned cycle
}

SUPPORTED_MCODES = {
    "M03", "M04", "M05",  # Spindle
    "M06",  # Tool change
    "M08", "M09",  # Coolant
    "M30",  # Program end
    "M00", "M01",  # Program stop
}


@dataclass
class GCodeCommand:
    """A single parsed G-code command.

    Attributes:
        command: The G/M code (e.g., 'G1', 'M03').
        params: Dict of parameters (e.g., {'X': 10.0, 'Y': 20.0, 'F': 1000.0}).
        line_number: Line number in the source text (1-indexed).
        comment: Inline comment if present.
        raw: Raw text of the line (stripped).
    """

    command: str
    params: dict[str, float] = field(default_factory=dict)
    line_number: int = 0
    comment: str = ""
    raw: str = ""

    def __repr__(self) -> str:
        param_str = " ".join(f"{k}{v}" for k, v in self.params.items())
        return f"GCodeCommand({self.command} {param_str} @ line {self.line_number})"


# Regex to parse a G-code line
# Matches: optional N-word, G/M code, parameters, inline comment
_LINE_PATTERN = re.compile(
    r"^(?:N\d+\s+)?"           # Optional line number
    r"([GM]\d+\.?\d*)"         # G/M code (e.g., G1, G01, M3)
    r"(.*)$",                   # Rest of line (params + comment)
    re.IGNORECASE,
)

_PARAM_PATTERN = re.compile(
    r"([A-Z])"                  # Parameter letter
    r"(-?[\d.]+(?:[eE][+-]?\d+)?)"  # Parameter value (with optional exponent)
    r"(?=\s|[A-Z]|$)",          # Followed by space, letter, or end
    re.IGNORECASE,
)

_COMMENT_PATTERN = re.compile(
    r"[;(](.*?)[)]?$",          # Semicolon or parenthesized comment
    re.IGNORECASE,
)


def parse_gcode(text: str) -> list[GCodeCommand]:
    """Parse G-code text into a list of GCodeCommand objects.

    Args:
        text: G-code source text (multi-line string).

    Returns:
        List of GCodeCommand objects in order.
    """
    commands: list[GCodeCommand] = []
    active_command = ""  # Modal tracking for G0/G1/G2/G3

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Skip empty lines
        if not line:
            continue

        # Extract comment
        comment = ""
        comment_match = _COMMENT_PATTERN.search(line)
        if comment_match:
            comment = comment_match.group(1).strip() if comment_match.group(1) else ""
            # Remove comment from line
            line = _COMMENT_PATTERN.sub("", line).strip()

        if not line:
            continue

        # Parse the line
        match = _LINE_PATTERN.match(line)
        if match:
            command = match.group(1).upper()
            rest = match.group(2)

            # Normalize G01 → G1, G00 → G0, M03 → M03
            if command.startswith("G"):
                code_num = command[1:]
                # Remove leading zeros but keep at least one digit
                code_num = str(int(code_num))
                command = f"G{code_num}"
            elif command.startswith("M"):
                code_num = command[1:]
                code_num = str(int(code_num))
                command = f"M{code_num}"

            # Parse parameters
            params = _parse_params(rest)

            # Track modal G-code
            if command in ("G0", "G1", "G2", "G3"):
                active_command = command

            cmd = GCodeCommand(
                command=command,
                params=params,
                line_number=line_num,
                comment=comment,
                raw=raw_line,
            )
            commands.append(cmd)

    return commands


def _parse_params(text: str) -> dict[str, float]:
    """Extract parameter letter-value pairs from the remainder of a G-code line.

    Handles parameter words like X10.0 Y20.0 F1000.
    """
    params: dict[str, float] = {}
    for match in _PARAM_PATTERN.finditer(text):
        letter = match.group(1).upper()
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        params[letter] = value
    return params


# ---------------------------------------------------------------------------
# Helper functions for common G-code patterns
# ---------------------------------------------------------------------------

def is_rapid_move(cmd: GCodeCommand) -> bool:
    """Check if a command is a rapid move (G0)."""
    return cmd.command == "G0"


def is_linear_move(cmd: GCodeCommand) -> bool:
    """Check if a command is a linear feed move (G1)."""
    return cmd.command == "G1"


def is_arc_move(cmd: GCodeCommand) -> bool:
    """Check if a command is an arc move (G2 or G3)."""
    return cmd.command in ("G2", "G3")


def is_spindle_on(cmd: GCodeCommand) -> bool:
    """Check if a command starts the spindle (M3/M03 or M4/M04)."""
    return cmd.command in ("M3", "M4", "M03", "M04")


def is_spindle_off(cmd: GCodeCommand) -> bool:
    """Check if a command stops the spindle (M5/M05)."""
    return cmd.command in ("M5", "M05")


def is_tool_change(cmd: GCodeCommand) -> bool:
    """Check if a command is a tool change (M6/M06)."""
    return cmd.command in ("M6", "M06")


def is_program_end(cmd: GCodeCommand) -> bool:
    """Check if a command ends the program (M30)."""
    return cmd.command == "M30"


def get_position(cmd: GCodeCommand) -> dict[str, float] | None:
    """Extract XYZ position from a command, if present."""
    result = {}
    for axis in ("X", "Y", "Z"):
        if axis in cmd.params:
            result[axis] = cmd.params[axis]
    return result if result else None


def get_feed(cmd: GCodeCommand) -> float | None:
    """Extract feed rate from a command, if present."""
    return cmd.params.get("F")


def get_spindle_speed(cmd: GCodeCommand) -> float | None:
    """Extract spindle speed from a command, if present."""
    return cmd.params.get("S")


def summary(commands: list[GCodeCommand]) -> str:
    """Generate a summary of parsed G-code commands.

    Returns:
        Multi-line string with statistics and command breakdown.
    """
    if not commands:
        return "No commands parsed."

    command_counts: dict[str, int] = {}
    for cmd in commands:
        command_counts[cmd.command] = command_counts.get(cmd.command, 0) + 1

    total = len(commands)
    lines = [f"G-code Summary ({total} commands):"]
    for code in sorted(command_counts.keys()):
        lines.append(f"  {code}: {command_counts[code]}")

    return "\n".join(lines)
