from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


class Progress:
    def __init__(self, total: int, job_name: str) -> None:
        self.total = max(0, total)
        self.job_name = job_name
        self.done = 0
        self.rows = 0
        self.fails = 0
        self.last_item = ""
        self.t0 = time.monotonic()
        self._lock = threading.Lock()
        self._recent: deque[float] = deque(maxlen=200)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start_heartbeat(self, every_s: float = 15 * 60) -> None:
        self._thread = threading.Thread(target=self._loop, args=(every_s,), daemon=True)
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()

    def _loop(self, every_s: float) -> None:
        while not self._stop.wait(every_s):
            self.heartbeat()

    def mark(self, item: str, rows: int = 0, elapsed_s: float = 0.0, ok: bool = True) -> None:
        with self._lock:
            self.done += 1
            self.rows += int(rows)
            if not ok:
                self.fails += 1
            self.last_item = item
            if elapsed_s > 0:
                self._recent.append(elapsed_s)

    def snapshot(self) -> str:
        with self._lock:
            elapsed = time.monotonic() - self.t0
            remaining = max(0, self.total - self.done)
            mean = sum(self._recent) / len(self._recent) if self._recent else 0.0
            eta_s = mean * remaining
            eta = f"{eta_s / 60:.1f}m" if eta_s else "n/a"
            now = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
            return (
                f"{now} elapsed={elapsed:.0f}s {self.job_name} "
                f"{self.done}/{self.total} last={self.last_item} "
                f"rows_written={self.rows} eta={eta} (estimate) fails={self.fails}"
            )

    def heartbeat(self) -> None:
        print(self.snapshot(), flush=True)
