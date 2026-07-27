"""
AI CAM 4.0 Simulation Controller — Qt-backed playback of simulation frames.

Pre-computes ALL frames at load time for O(1) random access (seek).
Exposes play/pause/stop/seek/set_speed with a state_changed signal.

Zero GL calls — the controller only owns data and timing.
"""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from simulation.engine import SimulationFrame


class SimState(Enum):
    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()


class SimulationController(QObject):
    """
    Drives simulation playback through a pre-computed list of frames.

    All frames are loaded at once (from the FrameWorker or directly) so
    that seek() is O(1). A QTimer advances the current index at the
    configured speed.
    """

    # Signals
    state_changed = Signal(str)       # "idle" | "playing" | "paused" | "stopped"
    frame_changed = Signal(int)       # Current frame index
    frame_ready = Signal(object)      # SimulationFrame
    progress = Signal(float)          # 0.0 – 1.0

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._frames: list[SimulationFrame] = []
        self._index: int = 0
        self._speed: float = 1.0       # 0.1x – 10x
        self._state: SimState = SimState.IDLE

        # Timer for playback
        self._timer = QTimer(self)
        self._timer.setTimerType(QTimer.PreciseTimer)
        self._timer.timeout.connect(self._advance)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state.name.lower()

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def speed(self) -> float:
        return self._speed

    def load_frames(self, frames: list[SimulationFrame]) -> None:
        """
        Replace the frame buffer. Resets to frame 0 and stops playback.
        All frames must be pre-computed — no lazy loading.
        """
        self._stop_internal()
        self._frames = list(frames)
        self._index = 0
        self._set_state(SimState.IDLE)
        if self._frames:
            self.frame_ready.emit(self._frames[0])
            self.frame_changed.emit(0)

    @Slot()
    def play(self) -> None:
        """Start or resume playback."""
        if not self._frames:
            return
        if self._index >= len(self._frames):
            self._index = 0
        self._set_state(SimState.PLAYING)
        self._start_timer()

    @Slot()
    def pause(self) -> None:
        """Pause playback at the current frame."""
        if self._state == SimState.PLAYING:
            self._timer.stop()
            self._set_state(SimState.PAUSED)

    @Slot()
    def stop(self) -> None:
        """Stop playback and reset to frame 0."""
        self._stop_internal()
        self._index = 0
        self._set_state(SimState.STOPPED)
        if self._frames:
            self.frame_ready.emit(self._frames[0])
            self.frame_changed.emit(0)
        self._set_state(SimState.IDLE)

    @Slot(int)
    def seek(self, index: int) -> None:
        """
        Jump to a specific frame. O(1) since frames are in memory.
        Clamps to [0, frame_count - 1].
        """
        if not self._frames:
            return
        self._index = max(0, min(index, len(self._frames) - 1))
        self.frame_ready.emit(self._frames[self._index])
        self.frame_changed.emit(self._index)
        self.progress.emit(self._index / max(1, len(self._frames) - 1))

    @Slot(float)
    def set_speed(self, speed: float) -> None:
        """
        Set playback speed multiplier.
        Accepts 0.1 to 10.0. Values outside are clamped.
        """
        self._speed = max(0.1, min(10.0, speed))
        # If playing, restart timer with new interval
        if self._state == SimState.PLAYING:
            self._start_timer()

    def clear(self) -> None:
        """Release all frames and reset."""
        self._stop_internal()
        self._frames.clear()
        self._index = 0
        self._set_state(SimState.IDLE)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_timer(self) -> None:
        """Start or restart the advancement timer based on current speed."""
        # Base interval: 33ms (~30 fps). Speed multiplier adjusts this.
        interval = max(1, int(33 / self._speed))
        self._timer.start(interval)

    @Slot()
    def _advance(self) -> None:
        """Advance to the next frame. Called by timer."""
        if self._index < len(self._frames) - 1:
            self._index += 1
            self.frame_ready.emit(self._frames[self._index])
            self.frame_changed.emit(self._index)
            total = max(1, len(self._frames) - 1)
            self.progress.emit(self._index / total)
        else:
            # Reached end — stop
            self._timer.stop()
            self._set_state(SimState.IDLE)

    def _stop_internal(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def _set_state(self, state: SimState) -> None:
        if self._state != state:
            self._state = state
            self.state_changed.emit(state.name.lower())
