"""
AI CAM 4.0 Kernel Types — Core data structures for the CAM engine.

Zero Qt/PySide imports. Pure Python + NumPy.

Provides:
  Vec3, BBox, Transform — geometry primitives
  ToolDef, Material — tooling & material definitions
  MoveType, Move, ToolpathData — canonical toolpath format
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Vec3:
    """Immutable 3D vector with operator support."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    @classmethod
    def from_array(cls, arr: np.ndarray | list[float]) -> Vec3:
        arr = np.asarray(arr, dtype=np.float64)
        return cls(float(arr[0]), float(arr[1]), float(arr[2]))

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec3:
        if scalar == 0.0:
            raise ZeroDivisionError("Cannot divide Vec3 by zero")
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def length(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def length_squared(self) -> float:
        return self.x ** 2 + self.y ** 2 + self.z ** 2

    def normalized(self) -> Vec3:
        ln = self.length()
        if ln < 1e-12:
            return Vec3(0.0, 0.0, 0.0)
        return Vec3(self.x / ln, self.y / ln, self.z / ln)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def distance_to(self, other: Vec3) -> float:
        return (self - other).length()

    def lerp(self, other: Vec3, t: float) -> Vec3:
        return Vec3(
            self.x + (other.x - self.x) * t,
            self.y + (other.y - self.y) * t,
            self.z + (other.z - self.z) * t,
        )

    def __repr__(self) -> str:
        return f"Vec3({self.x:.6f}, {self.y:.6f}, {self.z:.6f})"

    def __iter__(self):  # type: ignore
        yield self.x
        yield self.y
        yield self.z

    def __getitem__(self, index: int) -> float:
        return (self.x, self.y, self.z)[index]


# ---------------------------------------------------------------------------
# BBox — Axis-aligned bounding box
# ---------------------------------------------------------------------------

@dataclass(frozen=False, slots=True)
class BBox:
    """
    Axis-aligned bounding box.

    Attributes:
        min: Minimum corner (Vec3)
        max: Maximum corner (Vec3)
    """

    min: Vec3 = field(default_factory=lambda: Vec3(float("inf"), float("inf"), float("inf")))
    max: Vec3 = field(default_factory=lambda: Vec3(float("-inf"), float("-inf"), float("-inf")))

    @classmethod
    def from_points(cls, points: list[Vec3] | np.ndarray) -> BBox:
        """Create bounding box from a collection of points."""
        if isinstance(points, np.ndarray):
            if points.size == 0:
                return cls(min=Vec3(0, 0, 0), max=Vec3(0, 0, 0))
            min_pt = Vec3(float(points[:, 0].min()), float(points[:, 1].min()), float(points[:, 2].min()))
            max_pt = Vec3(float(points[:, 0].max()), float(points[:, 1].max()), float(points[:, 2].max()))
            return cls(min=min_pt, max=max_pt)
        if not points:
            return cls(min=Vec3(0, 0, 0), max=Vec3(0, 0, 0))
        min_pt = Vec3(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
        max_pt = Vec3(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
        return cls(min=min_pt, max=max_pt)

    @property
    def center(self) -> Vec3:
        return Vec3(
            (self.min.x + self.max.x) / 2,
            (self.min.y + self.max.y) / 2,
            (self.min.z + self.max.z) / 2,
        )

    @property
    def size(self) -> Vec3:
        return Vec3(
            self.max.x - self.min.x,
            self.max.y - self.min.y,
            self.max.z - self.min.z,
        )

    @property
    def volume(self) -> float:
        s = self.size
        return s.x * s.y * s.z

    def expand(self, point: Vec3) -> BBox:
        """Return new BBox expanded to include the given point."""
        return BBox(
            min=Vec3(
                min(self.min.x, point.x),
                min(self.min.y, point.y),
                min(self.min.z, point.z),
            ),
            max=Vec3(
                max(self.max.x, point.x),
                max(self.max.y, point.y),
                max(self.max.z, point.z),
            ),
        )

    def contains(self, point: Vec3) -> bool:
        return (
            self.min.x <= point.x <= self.max.x
            and self.min.y <= point.y <= self.max.y
            and self.min.z <= point.z <= self.max.z
        )

    def __repr__(self) -> str:
        return f"BBox(min={self.min}, max={self.max})"


# ---------------------------------------------------------------------------
# Transform — Rotation + Translation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Transform:
    """3D rigid-body transform: rotation (3×3) + translation."""

    rotation: np.ndarray = field(default_factory=lambda: np.eye(3, dtype=np.float64))
    translation: Vec3 = field(default_factory=Vec3)

    @classmethod
    def identity(cls) -> Transform:
        return cls()

    @classmethod
    def from_translation(cls, x: float, y: float, z: float) -> Transform:
        return cls(translation=Vec3(x, y, z))

    @classmethod
    def from_euler(cls, rx: float, ry: float, rz: float, translation: Vec3 | None = None) -> Transform:
        """Create from Euler angles (radians) in XYZ order."""
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)
        rot = np.array([
            [cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz],
            [cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz],
            [-sy, sx * cy, cx * cy],
        ], dtype=np.float64)
        return cls(rotation=rot, translation=translation or Vec3())

    def apply_to_point(self, point: Vec3) -> Vec3:
        """Apply transform to a point (rotation + translation)."""
        arr = self.rotation @ point.to_array()
        return Vec3(arr[0], arr[1], arr[2]) + self.translation

    def apply_to_vector(self, vector: Vec3) -> Vec3:
        """Apply rotation to a vector (no translation)."""
        arr = self.rotation @ vector.to_array()
        return Vec3(arr[0], arr[1], arr[2])

    def compose(self, other: Transform) -> Transform:
        """Compose: self * other (apply other first, then self)."""
        new_rot = self.rotation @ other.rotation
        new_trans = self.rotation @ other.translation.to_array() + self.translation.to_array()
        return Transform(rotation=new_rot, translation=Vec3(new_trans[0], new_trans[1], new_trans[2]))

    def inverse(self) -> Transform:
        inv_rot = self.rotation.T
        inv_trans = -(inv_rot @ self.translation.to_array())
        return Transform(rotation=inv_rot, translation=Vec3(inv_trans[0], inv_trans[1], inv_trans[2]))

    def __repr__(self) -> str:
        return f"Transform(translation={self.translation})"


# ---------------------------------------------------------------------------
# Material & Tool definitions
# ---------------------------------------------------------------------------

class Material(Enum):
    """Material identifiers for strategy selection."""
    ALUMINUM = auto()
    STEEL = auto()
    STAINLESS = auto()
    TITANIUM = auto()
    PLASTIC = auto()
    BRASS = auto()
    COPPER = auto()
    GRAPHITE = auto()


@dataclass(frozen=True, slots=True)
class ToolDef:
    """Cutter definition."""

    tool_id: str = "T01"
    name: str = "End Mill"
    diameter: float = 10.0       # mm
    flute_length: float = 30.0   # mm
    overall_length: float = 75.0 # mm
    flute_count: int = 4
    corner_radius: float = 0.0   # mm (0 = flat endmill)
    taper_angle: float = 0.0     # degrees (0 = no taper)
    material: str = "carbide"

    @property
    def radius(self) -> float:
        return self.diameter / 2.0

    @property
    def effective_radius(self) -> float:
        return self.diameter / 2.0


# ---------------------------------------------------------------------------
# Toolpath data — the canonical format that flows through the system
# ---------------------------------------------------------------------------

class MoveType(Enum):
    """Types of tool motion."""
    RAPID = auto()      # G0 — rapid positioning
    LINEAR = auto()     # G1 — linear feed
    ARC_CW = auto()     # G2 — arc clockwise
    ARC_CCW = auto()    # G3 — arc counter-clockwise
    DRILL = auto()      # G81-G89 canned cycles
    RETRACT = auto()    # Z retract (special rapid)


@dataclass(slots=True)
class Move:
    """Single tool motion."""

    move_type: MoveType
    end: Vec3
    feed: float = 0.0          # mm/min (0 = rapid)
    spindle_speed: float = 0.0 # RPM
    coolant: bool = False
    arc_center: Vec3 | None = None  # For arc moves
    arc_plane: str = "XY"          # Arc plane: XY, XZ, YZ

    @property
    def is_cutting(self) -> bool:
        return self.move_type in (
            MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW, MoveType.DRILL
        )


@dataclass(slots=True)
class ToolpathData:
    """
    Canonical toolpath format — produced by strategies, consumed by
    simulation, post-processors, and the viewport.

    Uses a flat list of Move objects, each with type, endpoint, and
    machine parameters. This is the single source of truth — no wrapping.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Toolpath"
    tool: ToolDef = field(default_factory=ToolDef)
    material: Material = Material.ALUMINUM
    moves: list[Move] = field(default_factory=list)
    strategy: str = ""          # Strategy name that generated this
    params: dict[str, Any] = field(default_factory=dict)  # Strategy params

    # Metadata
    total_length: float = 0.0   # Total cutting distance (mm)
    estimated_time: float = 0.0 # Estimated machining time (minutes)
    bounding_box: BBox | None = None

    def __post_init__(self) -> None:
        if not self.total_length and self.moves:
            self._compute_metadata()

    def _compute_metadata(self) -> None:
        bb = None
        for move in self.moves:
            if bb is None:
                bb = BBox(min=move.end, max=move.end)
            else:
                bb = bb.expand(move.end)
        self.bounding_box = bb

    @property
    def start_point(self) -> Vec3 | None:
        return self.moves[0].end if self.moves else None

    @property
    def end_point(self) -> Vec3 | None:
        return self.moves[-1].end if self.moves else None

    def __len__(self) -> int:
        return len(self.moves)

    def __getitem__(self, index: int) -> Move:
        return self.moves[index]

    def __repr__(self) -> str:
        return (
            f"ToolpathData(name={self.name!r}, moves={len(self.moves)}, "
            f"strategy={self.strategy!r})"
        )
