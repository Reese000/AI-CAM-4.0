"""
AI CAM 4.0 — Input Handler
===========================

Maps mouse and keyboard events to camera actions.
Separates input logic from the GL widget (shell.py) for testability.

Key bindings:
    Left mouse drag  → Orbit
    Right mouse drag → Pan
    Scroll wheel     → Zoom
    F                → Frame all (focus on scene)
    R                → Reset camera to default
    1/3/7            → Standard views (front/right/top)

All methods are pure — they take event data and return action objects.
No Qt imports needed (stateless input mapping).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from app.viewport.camera import OrbitCamera
from app.viewport.gl_constants import CAMERA_DEFAULT_DISTANCE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------
class ActionType(enum.Enum):
    """Types of input actions the viewport can process."""
    NONE = "none"
    ORBIT = "orbit"
    PAN = "pan"
    ZOOM = "zoom"
    RESET = "reset"
    FRAME = "frame"
    VIEW_FRONT = "view_front"
    VIEW_RIGHT = "view_right"
    VIEW_TOP = "view_top"
    VIEW_ISO = "view_iso"


@dataclass
class InputAction:
    """Result of processing an input event."""
    action_type: ActionType = ActionType.NONE
    delta_x: float = 0.0
    delta_y: float = 0.0
    factor: float = 1.0


@dataclass
class InputHandler:
    """Processes raw input events and converts to camera actions.

    Attributes:
        camera: The orbit camera to control.
        mouse_sensitivity: Multiplier for mouse deltas.
        invert_y: Whether to invert vertical mouse axis.
        _last_mouse_x: Previous mouse X for delta calculation.
        _last_mouse_y: Previous mouse Y for delta calculation.
        _is_orbiting: True while left mouse is held.
        _is_panning: True while right mouse is held.
    """

    camera: OrbitCamera
    mouse_sensitivity: float = 1.0
    invert_y: bool = False

    # Internal state
    _last_mouse_x: float = 0.0
    _last_mouse_y: float = 0.0
    _is_orbiting: bool = False
    _is_panning: bool = False

    def __post_init__(self) -> None:
        """Validate camera reference."""
        if self.camera is None:
            raise ValueError("InputHandler requires a valid OrbitCamera instance")

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------
    def handle_mouse_press(
        self, button: int, x: float, y: float
    ) -> InputAction:
        """Process mouse button press.

        Args:
            button: Qt mouse button (1=left, 2=right, 4=middle).
            x: Mouse X position.
            y: Mouse Y position.

        Returns:
            InputAction with action_type NONE (press starts a gesture).
        """
        self._last_mouse_x = x
        self._last_mouse_y = y

        if button == 1:  # Left button → orbit
            self._is_orbiting = True
            self._is_panning = False
            logger.debug("Orbit started at (%.0f, %.0f)", x, y)
        elif button == 2:  # Right button → pan
            self._is_panning = True
            self._is_orbiting = False
            logger.debug("Pan started at (%.0f, %.0f)", x, y)
        elif button == 4:  # Middle button → also pan
            self._is_panning = True
            self._is_orbiting = False

        return InputAction(action_type=ActionType.NONE)

    def handle_mouse_release(
        self, button: int, x: float, y: float
    ) -> InputAction:
        """Process mouse button release.

        Args:
            button: Qt mouse button (1=left, 2=right, 4=middle).
            x: Mouse X position.
            y: Mouse Y position.

        Returns:
            InputAction with action_type NONE.
        """
        if button == 1:
            self._is_orbiting = False
        elif button in (2, 4):
            self._is_panning = False

        return InputAction(action_type=ActionType.NONE)

    def handle_mouse_move(
        self, x: float, y: float
    ) -> InputAction:
        """Process mouse movement while a button is held.

        Args:
            x: Current mouse X position.
            y: Current mouse Y position.

        Returns:
            InputAction with ORBIT, PAN, or NONE.
        """
        delta_x = (x - self._last_mouse_x) * self.mouse_sensitivity
        delta_y = (y - self._last_mouse_y) * self.mouse_sensitivity

        self._last_mouse_x = x
        self._last_mouse_y = y

        if abs(delta_x) < 0.001 and abs(delta_y) < 0.001:
            return InputAction(action_type=ActionType.NONE)

        if self.invert_y:
            delta_y = -delta_y

        if self._is_orbiting:
            self.camera.orbit(delta_x, delta_y)
            return InputAction(
                action_type=ActionType.ORBIT,
                delta_x=delta_x,
                delta_y=delta_y,
            )
        elif self._is_panning:
            self.camera.pan(delta_x, delta_y)
            return InputAction(
                action_type=ActionType.PAN,
                delta_x=delta_x,
                delta_y=delta_y,
            )

        return InputAction(action_type=ActionType.NONE)

    def handle_wheel(self, delta_x: float, delta_y: float) -> InputAction:
        """Process mouse wheel / scroll event.

        Args:
            delta_x: Horizontal scroll delta.
            delta_y: Vertical scroll delta (positive = zoom in).

        Returns:
            InputAction with ZOOM type.
        """
        # Use vertical scroll for zoom (most common)
        if abs(delta_y) > abs(delta_x):
            zoom_delta = delta_y
        else:
            zoom_delta = delta_x

        if abs(zoom_delta) > 0.001:
            self.camera.zoom(zoom_delta)
            return InputAction(
                action_type=ActionType.ZOOM,
                factor=zoom_delta,
            )

        return InputAction(action_type=ActionType.NONE)

    # ------------------------------------------------------------------
    # Keyboard events
    # ------------------------------------------------------------------
    def handle_key_press(self, key: str) -> InputAction:
        """Process keyboard press.

        Args:
            key: Key identifier string (e.g. 'f', 'r', '1', '3', '7').

        Returns:
            InputAction for the mapped key, or NONE if unmapped.
        """
        key_lower = key.lower()

        if key_lower == "f":
            return InputAction(action_type=ActionType.FRAME)

        elif key_lower == "r":
            self._reset_camera()
            return InputAction(action_type=ActionType.RESET)

        elif key_lower == "1":
            self._set_view_front()
            return InputAction(action_type=ActionType.VIEW_FRONT)

        elif key_lower == "3":
            self._set_view_right()
            return InputAction(action_type=ActionType.VIEW_RIGHT)

        elif key_lower == "7":
            self._set_view_top()
            return InputAction(action_type=ActionType.VIEW_TOP)

        elif key_lower == "0":
            self._set_view_iso()
            return InputAction(action_type=ActionType.VIEW_ISO)

        elif key_lower == "escape":
            # Cancel any active gesture
            self._is_orbiting = False
            self._is_panning = False
            return InputAction(action_type=ActionType.NONE)

        return InputAction(action_type=ActionType.NONE)

    def handle_key_release(self, key: str) -> InputAction:
        """Process keyboard release. Currently a no-op for most keys."""
        return InputAction(action_type=ActionType.NONE)

    # ------------------------------------------------------------------
    # View presets
    # ------------------------------------------------------------------
    def _reset_camera(self) -> None:
        """Reset camera to default position looking at origin."""
        self.camera.target = np.zeros(3, dtype=np.float32)
        self.camera.distance = CAMERA_DEFAULT_DISTANCE
        self.camera.azimuth = 0.785  # ~45 deg
        self.camera.elevation = 0.523  # ~30 deg
        self.camera.fov = 45.0
        self.camera._dirty = True
        logger.debug("Camera reset to defaults")

    def _set_view_front(self) -> None:
        """Set camera to front view (looking along -Z)."""
        self.camera.azimuth = 0.0
        self.camera.elevation = 0.0
        self.camera._dirty = True
        logger.debug("View set to front")

    def _set_view_right(self) -> None:
        """Set camera to right view (looking along -X)."""
        self.camera.azimuth = math.pi / 2.0
        self.camera.elevation = 0.0
        self.camera._dirty = True
        logger.debug("View set to right")

    def _set_view_top(self) -> None:
        """Set camera to top view (looking down -Y)."""
        self.camera.azimuth = 0.0
        self.camera.elevation = math.pi / 2.0 - 0.01
        self.camera._dirty = True
        logger.debug("View set to top")

    def _set_view_iso(self) -> None:
        """Set camera to isometric view."""
        self.camera.azimuth = 0.785
        self.camera.elevation = 0.615  # ~35.26 deg (true isometric)
        self.camera._dirty = True
        logger.debug("View set to isometric")

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    @property
    def is_interacting(self) -> bool:
        """True if a mouse gesture is active (orbit or pan)."""
        return self._is_orbiting or self._is_panning

    @property
    def interaction_mode(self) -> str:
        """Return current interaction mode as a readable string."""
        if self._is_orbiting:
            return "Orbit"
        elif self._is_panning:
            return "Pan"
        return "Idle"


# Need math for view presets
import math  # noqa: E402 (imported after class definition to keep clean separation)
