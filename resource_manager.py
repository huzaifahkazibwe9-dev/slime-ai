"""Low-power resource and operating-mode manager for Slime AI.

This module does not start background services, timers, or game actions.
It only controls whether Python work is permitted.
"""

from enum import Enum
from time import monotonic


class Mode(str, Enum):
    IDLE = "IDLE"
    ANALYSE = "ANALYSE"
    PLAY = "PLAY"
    LEARN = "LEARN"
    PAUSED = "PAUSED"


class ResourceManager:
    def __init__(self):
        self.mode = Mode.IDLE
        self.game_taps_enabled = False
        self.task_started_at = None
        self.last_task_duration = 0.0

    def set_mode(self, mode):
        try:
            new_mode = Mode(str(mode).upper())
        except ValueError:
            raise ValueError(f"Unknown operating mode: {mode}")

        if new_mode == Mode.PLAY and not self.game_taps_enabled:
            raise PermissionError(
                "PLAY mode blocked: actual game taps are disabled."
            )

        if self.mode == Mode.PAUSED and new_mode != Mode.IDLE:
            raise RuntimeError("Resume to IDLE before starting another mode.")

        self.mode = new_mode
        self.task_started_at = (
            monotonic()
            if new_mode in {Mode.ANALYSE, Mode.PLAY, Mode.LEARN}
            else None
        )
        return self.status()

    def pause(self):
        self._finish_task()
        self.mode = Mode.PAUSED
        return self.status()

    def resume(self):
        self.mode = Mode.IDLE
        self.task_started_at = None
        return self.status()

    def stop(self):
        self._finish_task()
        self.mode = Mode.IDLE
        return self.status()

    def can_process(self, task):
        task = str(task).upper()

        if self.mode == Mode.PAUSED:
            return False

        if task == "ANALYSE":
            return self.mode == Mode.ANALYSE

        if task == "LEARN":
            return self.mode == Mode.LEARN

        if task == "PLAY":
            return (
                self.mode == Mode.PLAY
                and self.game_taps_enabled
            )

        return False

    def _finish_task(self):
        if self.task_started_at is not None:
            self.last_task_duration = max(
                0.0, monotonic() - self.task_started_at
            )
        self.task_started_at = None

    def status(self):
        return {
            "mode": self.mode.value,
            "game_taps_enabled": self.game_taps_enabled,
            "background_loop": False,
            "timer_running": False,
            "last_task_seconds": round(self.last_task_duration, 3),
        }


if __name__ == "__main__":
    manager = ResourceManager()

    print("SLIME AI RESOURCE MANAGER TEST")
    print("=" * 38)

    assert manager.mode == Mode.IDLE
    assert not manager.can_process("ANALYSE")
    print("[PASS] Starts in IDLE")

    manager.set_mode("ANALYSE")
    assert manager.can_process("ANALYSE")
    assert not manager.can_process("PLAY")
    print("[PASS] ANALYSE mode")

    manager.pause()
    assert not manager.can_process("ANALYSE")
    assert not manager.can_process("LEARN")
    print("[PASS] PAUSED blocks processing")

    manager.resume()
    assert manager.mode == Mode.IDLE
    print("[PASS] Resume returns to IDLE")

    try:
        manager.set_mode("PLAY")
    except PermissionError:
        print("[PASS] PLAY blocked while taps are disabled")
    else:
        raise AssertionError("PLAY safety lock failed")

    manager.stop()
    print("[PASS] Stop returns to IDLE")
    print("\nFinal status:", manager.status())
    print("\nALL RESOURCE MANAGER TESTS PASSED")
