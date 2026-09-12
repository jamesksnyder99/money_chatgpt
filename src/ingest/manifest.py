from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ingest.paths import MANIFEST, ensure_dirs


class Manifest:
    def __init__(self, path: Path = MANIFEST) -> None:
        self.path = path
        self._lock = threading.Lock()
        ensure_dirs()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._ok = self._load_ok()

    def _load_ok(self) -> set[tuple[str, str, str, str, str, str]]:
        keys: set[tuple[str, str, str, str, str, str]] = set()
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok"):
                    keys.add(self._key(row))
        return keys

    @staticmethod
    def _key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
        return (
            str(row.get("endpoint") or ""),
            str(row.get("symbol") or ""),
            str(row.get("start_date") or ""),
            str(row.get("end_date") or ""),
            str(row.get("interval") or ""),
            str(row.get("venue") or ""),
        )

    def already_ok(
        self,
        *,
        endpoint: str,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "",
        venue: str = "",
    ) -> bool:
        return (
            endpoint,
            symbol,
            start_date,
            end_date,
            interval,
            venue,
        ) in self._ok

    def append(
        self,
        *,
        endpoint: str,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        interval: str = "",
        venue: str = "",
        row_count: int = 0,
        elapsed_s: float = 0.0,
        ok: bool,
        error_class: str = "",
        error_message: str = "",
    ) -> None:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "interval": interval,
            "venue": venue,
            "row_count": int(row_count),
            "elapsed_s": round(float(elapsed_s), 4),
            "ok": bool(ok),
            "error_class": error_class,
            "error_message": str(error_message)[:500],
        }
        line = json.dumps(row, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            if ok:
                self._ok.add(self._key(row))
