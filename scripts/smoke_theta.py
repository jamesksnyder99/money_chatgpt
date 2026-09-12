"""One-shot Theta Data access test. Prints a compact PASS/FAIL report."""

from __future__ import annotations

import sys
import threading
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from theta.client import auth_mode, get_client  # noqa: E402

LIST_TIMEOUT_S = 20
HISTORY_START = date(2026, 8, 31)
HISTORY_END = date(2026, 9, 4)
FALLBACK_START = date(2026, 9, 2)
FALLBACK_END = date(2026, 9, 4)


def _df_len(df) -> int:
    height = getattr(df, "height", None)
    if height is not None:
        return int(height)
    return len(df)


def _cols(df) -> list[str]:
    return list(getattr(df, "columns", []))


def _cell(df, col: str):
    return df[col][0]


def _first_tickers(df, n: int = 5) -> list[str]:
    cols = _cols(df)
    col = "symbol" if "symbol" in cols else cols[0]
    head = df[col].head(n)
    to_list = getattr(head, "to_list", None)
    if callable(to_list):
        return [str(x) for x in to_list()]
    return [str(x) for x in list(head)]


def _last_date_close(df) -> tuple[object, object]:
    last = df.tail(1)
    cols = _cols(last)
    date_val = None
    for name in ("created", "date", "last_trade"):
        if name in cols:
            date_val = _cell(last, name)
            break
    close_val = None
    for name in ("close", "Close"):
        if name in cols:
            close_val = _cell(last, name)
            break
    return date_val, close_val


def _snapshot_fields(df) -> dict[str, object]:
    last = df.head(1)
    cols = _cols(last)
    wanted = ("bid", "ask", "timestamp", "created", "date", "last_trade")
    return {name: _cell(last, name) for name in wanted if name in cols}


def _list_symbols(client):
    box: dict[str, object] = {}

    def run() -> None:
        try:
            box["df"] = client.stock_list_symbols()
        except Exception as exc:  # noqa: BLE001 — report class/message only
            box["err"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=LIST_TIMEOUT_S)
    if thread.is_alive():
        raise TimeoutError(f"stock_list_symbols exceeded {LIST_TIMEOUT_S}s")
    if "err" in box:
        raise box["err"]  # type: ignore[misc]
    return box["df"]


def main() -> int:
    step1_ok = False
    step3_ok = False

    print("=== Theta Data smoke test ===")

    try:
        client = get_client()
        mode = auth_mode()
        print(f"auth_mode: {mode}")
        step1_ok = True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL step1 {type(exc).__name__}: {exc}")
        print("RESULT: FAIL")
        return 1

    try:
        symbols = _list_symbols(client)
        tickers = _first_tickers(symbols, 5)
        print(f"LIST: count={_df_len(symbols)} first5={tickers}")
    except Exception as exc:  # noqa: BLE001
        print(f"LIST: skipped ({type(exc).__name__}: {exc}); fallback EOD ping")
        try:
            ping = client.stock_history_eod(
                symbol="AAPL",
                start_date=FALLBACK_START,
                end_date=FALLBACK_END,
            )
            print(f"LIST fallback: AAPL EOD rows={_df_len(ping)}")
        except Exception as ping_exc:  # noqa: BLE001
            print(f"LIST fallback FAIL {type(ping_exc).__name__}: {ping_exc}")

    try:
        eod = client.stock_history_eod(
            symbol="AAPL",
            start_date=HISTORY_START,
            end_date=HISTORY_END,
        )
        rows = _df_len(eod)
        if rows == 0:
            print("HISTORY: rows=0")
            print("RESULT: FAIL")
            return 1
        last_date, last_close = _last_date_close(eod)
        print(f"HISTORY: rows={rows} last_date={last_date} close={last_close}")
        step3_ok = True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL step3 {type(exc).__name__}: {exc}")
        print("RESULT: FAIL")
        return 1

    try:
        quote = client.stock_snapshot_quote(symbol=["AAPL"])
        fields = _snapshot_fields(quote)
        print(f"SNAPSHOT: {fields}")
    except Exception as exc:  # noqa: BLE001
        print(f"SNAPSHOT: {type(exc).__name__}: {exc} (not a hard fail)")

    if step1_ok and step3_ok:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
