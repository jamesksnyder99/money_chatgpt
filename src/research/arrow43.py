"""Arrow 43 — clock split. Three frozen clock books. No door search."""

from __future__ import annotations

import math
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import NYSE_EARLY_CLOSE, study_sessions, virgin_study_sessions
from ingest.paths import BARS_DIR, FULL_ELIGIBILITY, FULL_IWM, REPORTS, VIRGIN_ELIGIBILITY, VIRGIN_IWM
from ingest.progress import Progress
from research.arrow20 import _iso
from research.arrow23 import _summarize_adv
from research.book import borrow_blocks_short, daily_close_drawdown
from research.clock import (
    combined_study_sessions,
    is_is_session,
    next_session,
    session_bar_path,
    split_is_oos,
    tape_root,
)
from research.combine import combine_books
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, signed_pnl
from research.fills import is_tradeable
from research.signals import MINUTE_1559, RTH_OPEN, bar_time

ET = ZoneInfo("America/New_York")
SEAT_FLOOR = 100.0
NOTIONAL = 2_000.0
CAP_NAMES = 25
MIN_PX = 10.0
MAX_PX = 80.0
MIN_PDV = 10_000_000.0
FUSE_FRAC = 0.08
RTH_END = time(16, 0)
IDS = ("on_long", "on_short", "rth_long")


def _clock(ts: datetime) -> time:
    return bar_time(ts)


def _read_bars(session: date, symbol: str) -> pl.DataFrame | None:
    p = session_bar_path(session, symbol)
    if not p.exists():
        return None
    try:
        df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
    except Exception:  # noqa: BLE001
        return None
    if df.height == 0:
        return None
    return df


def _rth_rows(df: pl.DataFrame) -> list[dict]:
    out = []
    for rec in df.sort("bar_start").iter_rows(named=True):
        ts = rec["bar_start"]
        t = _clock(ts)
        if t < RTH_OPEN or t >= RTH_END:
            continue
        if not is_tradeable(rec["open"], rec["close"], rec["volume"]):
            continue
        out.append(rec)
    return out


def first_rth(df: pl.DataFrame) -> dict | None:
    rows = _rth_rows(df)
    if not rows:
        return None
    for rec in rows:
        if _clock(rec["bar_start"]) == RTH_OPEN:
            return rec
    return rows[0]


def last_rth(df: pl.DataFrame, session: date | None = None) -> dict | None:
    rows = _rth_rows(df)
    if not rows:
        return None
    early = NYSE_EARLY_CLOSE.get(session) if session is not None else None
    if early is not None:
        keep = [r for r in rows if _clock(r["bar_start"]) < early]
        if keep:
            return keep[-1]
    want = MINUTE_1559
    for rec in reversed(rows):
        if _clock(rec["bar_start"]) == want:
            return rec
    return rows[-1]


def notional_shares(price: float) -> int:
    if not math.isfinite(price) or price <= 0:
        return 0
    n = math.floor(NOTIONAL / price)
    return n if n >= 1 else 0


def _pack(pnl: float, side: int, shares: int, entry_px: float, exit_px: float, entry_ts, exit_ts, tag: str, symbol: str) -> dict:
    minutes = (exit_ts - entry_ts).total_seconds() / 60.0 if entry_ts and exit_ts else 0.0
    return {
        "pnl": pnl,
        "win": pnl > 0,
        "risk": 0.0,
        "side": side,
        "shares": shares,
        "entry_px": entry_px,
        "exit_px": exit_px,
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "tag": tag,
        "symbol": symbol,
        "r": 0.0,
        "minutes": minutes,
        "mfe_ext": 0.0,
        "mfe_r": 0.0,
        "reached_1r": False,
    }


def rth_long_exit(df: pl.DataFrame, entry: dict, last: dict) -> tuple[datetime, float, str]:
    """Shop fuse: flatten if the name is -8% from the 09:30 fill. Not a trade stop."""
    entry_px = float(entry["open"])
    fuse = entry_px * (1.0 - FUSE_FRAC)
    entry_ts = entry["bar_start"]
    last_ts = last["bar_start"]
    last_px = float(last["close"])
    for rec in _rth_rows(df):
        ts = rec["bar_start"]
        if ts < entry_ts:
            continue
        o = float(rec["open"])
        lo = float(rec["low"])
        if ts == entry_ts:
            if lo <= fuse + 1e-12:
                fill = o if o <= fuse + 1e-12 else fuse
                return ts, fill, "fuse"
            continue
        if ts > last_ts:
            break
        if o <= fuse + 1e-12:
            return ts, o, "fuse"
        if lo <= fuse + 1e-12:
            return ts, fuse, "fuse"
    return last_ts, last_px, "time"


def rth_marked_trough(df: pl.DataFrame, entry: dict, exit_ts: datetime, shares: int) -> float:
    """Intraday trough in dollars from the 09:30 fill (long)."""
    entry_px = float(entry["open"])
    entry_ts = entry["bar_start"]
    worst = 0.0
    for rec in _rth_rows(df):
        ts = rec["bar_start"]
        if ts < entry_ts or ts > exit_ts:
            continue
        mark = float(rec["low"])
        pnl = (mark - entry_px) * shares
        worst = min(worst, pnl)
    return worst


def on_fill(today: pl.DataFrame, nxt: pl.DataFrame | None, session: date, nxt_session: date | None, side: int, prior_close: float | None, prior_dv: float, symbol: str) -> dict | None:
    if nxt is None or nxt_session is None:
        return None
    ent = last_rth(today, session)
    ex = first_rth(nxt)
    if ent is None or ex is None:
        return None
    if side < 0 and borrow_blocks_short(
        (float(ent["close"]) / float(prior_close) - 1.0) if prior_close and prior_close > 0 else None,
        prior_dv,
    ):
        return None
    entry_px = float(ent["close"])
    exit_px = float(ex["open"])
    shares = notional_shares(entry_px)
    if shares < 1:
        return None
    pnl = signed_pnl(side, shares, entry_px, exit_px)
    tag = "on_long" if side > 0 else "on_short"
    return _pack(pnl, side, shares, entry_px, exit_px, ent["bar_start"], ex["bar_start"], tag, symbol)


def rth_fill(today: pl.DataFrame, session: date, prior_dv: float, symbol: str) -> dict | None:
    ent = first_rth(today)
    last = last_rth(today, session)
    if ent is None or last is None:
        return None
    entry_px = float(ent["open"])
    shares = notional_shares(entry_px)
    if shares < 1:
        return None
    exit_ts, exit_px, tag = rth_long_exit(today, ent, last)
    pnl = signed_pnl(1, shares, entry_px, exit_px)
    rec = _pack(pnl, 1, shares, entry_px, exit_px, ent["bar_start"], exit_ts, tag, symbol)
    rec["intraday_trough"] = rth_marked_trough(today, ent, exit_ts, shares)
    return rec


def _elig_frame() -> pl.DataFrame:
    cols = ["symbol", "session_date", "prior_close", "prior_dollar_volume"]
    frames = []
    v_dates = set(virgin_study_sessions())
    f_dates = set(study_sessions())
    if VIRGIN_ELIGIBILITY.exists():
        v = pl.read_parquet(VIRGIN_ELIGIBILITY)
        keep = [c for c in cols if c in v.columns]
        v = v.select(keep).filter(pl.col("session_date").is_in(list(v_dates)))
        frames.append(v)
    if FULL_ELIGIBILITY.exists():
        f = pl.read_parquet(FULL_ELIGIBILITY)
        keep = [c for c in cols if c in f.columns]
        f = f.select(keep).filter(pl.col("session_date").is_in(list(f_dates)))
        frames.append(f)
    if not frames:
        raise FileNotFoundError("missing virgin/full eligibility")
    elig = pl.concat(frames, how="diagonal_relaxed")
    return elig.filter(
        pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= MIN_PX)
        & (pl.col("prior_close") <= MAX_PX)
        & (pl.col("prior_dollar_volume") >= MIN_PDV)
    )


def _by_sess(elig: pl.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for rec in elig.select("session_date", "symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True):
        iso = _iso(rec["session_date"])
        out.setdefault(iso, []).append(
            {
                "symbol": str(rec["symbol"]),
                "prior_close": float(rec["prior_close"]),
                "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
            }
        )
    for iso, rows in out.items():
        rows.sort(key=lambda h: h["prior_dv"], reverse=True)
    return out


def _top25(names: list[dict]) -> list[dict]:
    return names[:CAP_NAMES]


def load_combined_iwm() -> dict[str, pl.DataFrame]:
    out: dict[str, pl.DataFrame] = {}
    for root in (VIRGIN_IWM, FULL_IWM):
        if not root.exists():
            continue
        for p in root.glob("*.parquet"):
            out[p.stem] = pl.read_parquet(p)
    return out


def _session_job(args: tuple) -> dict:
    iso, names, nxt_iso, nxt_date, session, do_char = args
    empty_tr = {k: [] for k in IDS}
    out = {
        "session": iso,
        "trades": empty_tr,
        "char_co": [],
        "char_oc": [],
        "n_elig": len(names),
    }
    if not names:
        return out
    nxt_d = date.fromisoformat(nxt_iso) if nxt_iso else None
    want_char = [h["symbol"] for h in names] if do_char else []
    want_book = [h["symbol"] for h in _top25(names)]
    want = list(dict.fromkeys(want_char + want_book))
    today: dict[str, pl.DataFrame] = {}
    nxt: dict[str, pl.DataFrame] = {}
    for sym in want:
        df = _read_bars(session, sym)
        if df is not None:
            today[sym] = df
        if nxt_d is not None and (do_char or sym in want_book):
            nd = _read_bars(nxt_d, sym)
            if nd is not None:
                nxt[sym] = nd
    if do_char:
        for h in names:
            sym = h["symbol"]
            df = today.get(sym)
            if df is None:
                continue
            last = last_rth(df, session)
            first = first_rth(df)
            if first is not None and last is not None and float(first["open"]) > 0:
                oc = float(last["close"]) / float(first["open"]) - 1.0
                out["char_oc"].append(oc)
            if last is not None and nxt_d is not None:
                nd = nxt.get(sym)
                if nd is None:
                    continue
                nxt_open = first_rth(nd)
                if nxt_open is not None and float(last["close"]) > 0:
                    co = float(nxt_open["open"]) / float(last["close"]) - 1.0
                    out["char_co"].append(co)
    trades = {k: [] for k in IDS}
    for h in _top25(names):
        sym = h["symbol"]
        df = today.get(sym)
        if df is None:
            continue
        ol = on_fill(df, nxt.get(sym), session, nxt_d, 1, h["prior_close"], h["prior_dv"], sym)
        if ol:
            trades["on_long"].append(ol)
        os_ = on_fill(df, nxt.get(sym), session, nxt_d, -1, h["prior_close"], h["prior_dv"], sym)
        if os_:
            trades["on_short"].append(os_)
        rl = rth_fill(df, session, h["prior_dv"], sym)
        if rl:
            trades["rth_long"].append(rl)
    out["trades"] = trades
    return out


def _daily_and_trades(chunks: dict, sessions: list[date], name: str):
    rows = []
    for d in sessions:
        iso = d.isoformat()
        rec = chunks.get(iso) or {}
        tr = list((rec.get("trades") or {}).get(name) or [])
        pnl = sum(t["pnl"] for t in tr)
        troughs = [float(t.get("intraday_trough") or 0.0) for t in tr]
        rows.append(
            {
                "session": iso,
                "pnl": pnl,
                "trades": tr,
                "peak": len(tr),
                "mean_conc": float(len(tr)),
                "intraday_dd": min(troughs) if troughs else 0.0,
            }
        )
    isos = {d.isoformat() for d in sessions}
    daily = [float(r["pnl"]) for r in rows]
    trades = [t for r in rows for t in r["trades"]]
    sm = _summarize_adv(daily, trades, len(sessions))
    sm["peak_conc"] = max((r["peak"] for r in rows), default=0)
    sm["mean_conc"] = (sum(r["mean_conc"] for r in rows) / len(rows)) if rows else 0.0
    sm["daily_close_dd"] = daily_close_drawdown(daily)
    if name == "rth_long":
        sm["intraday_dd"] = min((r["intraday_dd"] for r in rows), default=0.0)
    else:
        sm["intraday_dd"] = min(daily) if daily else 0.0
    sm["worst_day"] = min(daily) if daily else 0.0
    sm["n_sess_traded"] = sum(1 for r in rows if r["trades"])
    return sm, daily, trades, {r["session"]: r["pnl"] for r in rows if r["session"] in isos}


def _iwm_px(df: pl.DataFrame | None, ts, *, use_open: bool) -> float | None:
    """Price on IWM at ts. Prefer at-or-after; fall back to last tradeable at-or-before."""
    if df is None or df.height == 0 or ts is None:
        return None
    times = df["bar_start"].to_list()
    opens = df["open"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    last = None
    for t, o, c, v in zip(times, opens, closes, vols):
        if not is_tradeable(o, c, v):
            continue
        px = float(o if use_open else c)
        if t <= ts:
            last = px
        if t >= ts:
            return px
    return last


def _alpha(trades, sessions, iwm):
    """IWM alpha; overnight exit is the next session, so look up that day's bench."""
    by_day = {d.isoformat(): 0.0 for d in sessions}
    skips = 0
    n_ok = 0
    for t in trades:
        ets, xts = t.get("entry_ts"), t.get("exit_ts")
        if ets is None or xts is None:
            skips += 1
            continue
        e_iso = ets.date().isoformat() if hasattr(ets, "date") else str(ets)[:10]
        x_iso = xts.date().isoformat() if hasattr(xts, "date") else str(xts)[:10]
        e = _iwm_px(iwm.get(e_iso), ets, use_open=(t.get("tag") != "on_long" and t.get("tag") != "on_short"))
        # overnight books fill the close; RTH and overnight exits at an open or close:
        # on_* exit is next 09:30 open; rth_long exit is last RTH close (or fuse).
        x_open = t.get("tag") in {"on_long", "on_short"} or t.get("tag") == "fuse"
        x = _iwm_px(iwm.get(x_iso), xts, use_open=x_open)
        if e is None or x is None or e <= 0:
            skips += 1
            continue
        iwm_ret = x / e - 1.0
        a = float(t["pnl"]) - int(t["side"]) * int(t["shares"]) * float(t["entry_px"]) * iwm_ret
        by_day[e_iso] = by_day.get(e_iso, 0.0) + a
        n_ok += 1
    per = (sum(by_day.get(d.isoformat(), 0.0) for d in sessions) / len(sessions)) if sessions else 0.0
    return per, skips, n_ok


def _month_lines(daily: list[float], sessions: list[date]) -> str:
    buckets: dict[str, list[float]] = defaultdict(list)
    for d, v in zip(sessions, daily):
        buckets[f"{d.year:04d}-{d.month:02d}"].append(float(v))
    bits = []
    for key in sorted(buckets):
        xs = buckets[key]
        n = len(xs)
        mean = sum(xs) / n if n else 0.0
        bits.append(f"{key} n={n} $/day={mean:.2f}")
    return "; ".join(bits)


def _fmt_book(sm: dict) -> list[str]:
    return [
        (
            f"    n={sm['n_trades']}  n/sess={sm['trades_per_sess']:.2f}  hit={sm['hit_rate']:.3f}  "
            f"avgR=n/a (no stop)  PF={sm['pf_s']}"
        ),
        (
            f"    avgWin$={sm['avg_win']:.2f}  avgLoss$={sm['avg_loss']:.2f}  "
            f"$/day={sm['per_day']:.2f}  std={sm['std_day']:.2f}  se={sm['se_day']:.2f}  "
            f"t={sm['t_stat']:.2f}  ci95=[{sm['ci_lo']:.2f},{sm['ci_hi']:.2f}]"
        ),
        (
            f"    daily-close DD$={sm['daily_close_dd']:.2f}  trough$={sm['intraday_dd']:.2f}  "
            f"peak_conc={sm['peak_conc']}  mean_conc={sm['mean_conc']:.2f}  worst_day$={sm['worst_day']:.2f}"
        ),
    ]


def _char_block(co: dict[str, list[float]], oc: dict[str, list[float]]) -> list[str]:
    lines = ["character IS only (eligible universe, not the 25-name cap). Description. Does not pick a book."]

    def _stats(xs: list[float]) -> str:
        if not xs:
            return "n=0"
        n = len(xs)
        mean = sum(xs) / n
        hit = sum(1 for x in xs if x > 0) / n
        return f"n={n} mean={mean:.5f} hit={hit:.3f}"

    all_co = [x for xs in co.values() for x in xs]
    all_oc = [x for xs in oc.values() for x in xs]
    lines.append(f"  close→open  {_stats(all_co)}")
    lines.append(f"  09:30→close {_stats(all_oc)}")
    for key in sorted(set(co) | set(oc)):
        lines.append(f"  {key}  close→open {_stats(co.get(key) or [])}  09:30→close {_stats(oc.get(key) or [])}")
    return lines


def run_arrow43(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 43 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow43 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "clock split. three books on_long / on_short / rth_long. "
        "No FLY. No 08:00. No conjunction. No flush wash. Did not retune frozen books. "
        "No new ingest. Did not touch Lab A data/bars. No Arrow 44.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    print(
        f"eligibility prior_close [$10,$80] PDV>=$10M name-days={elig.height} "
        f"unique={elig['symbol'].n_unique()} cap={CAP_NAMES} notional=${NOTIONAL:.0f}",
        flush=True,
    )
    nxt_map = {d: next_session(d, study) for d in study}
    jobs = []
    for d in study:
        iso = d.isoformat()
        nxt = nxt_map[d]
        jobs.append(
            (
                iso,
                by.get(iso, []),
                nxt.isoformat() if nxt else None,
                nxt,
                d,
                is_is_session(d),
            )
        )
    print(f"character IS then three ids IS+OOS sessions={len(jobs)}", flush=True)
    prog = Progress(len(jobs), "arrow43")
    prog.start_heartbeat()
    chunks: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_session_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            chunks[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    co_m: dict[str, list[float]] = defaultdict(list)
    oc_m: dict[str, list[float]] = defaultdict(list)
    for d in is_sess:
        rec = chunks.get(d.isoformat()) or {}
        key = f"{d.year:04d}-{d.month:02d}"
        co_m[key].extend(rec.get("char_co") or [])
        oc_m[key].extend(rec.get("char_oc") or [])

    iwm = load_combined_iwm()
    results = []
    maps = {}
    dailies = {}
    for name in IDS:
        sm_is, day_is, tr_is, map_is = _daily_and_trades(chunks, is_sess, name)
        sm_oos, day_oos, tr_oos, map_oos = _daily_and_trades(chunks, oos_sess, name)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        results.append(
            {
                "name": name,
                "is": sm_is,
                "oos": sm_oos,
                "day_is": day_is,
                "day_oos": day_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
            }
        )
        maps[name] = {**map_is, **map_oos}
        dailies[name] = (day_is, day_oos)

    comb = combine_books(maps["on_long"], maps["on_short"], maps["rth_long"])
    seats = [r["name"] for r in results if r["seat"]]
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red). Slate $200 is not this arrow's job."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 43 clock book has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS. "
            "Slate $200 is not this arrow's job."
        )
    honesty = (
        "Overnight has no stop. $2,000 × 25 is $50k deployed. Costs on a 25-name overnight book "
        "can dominate the gap. Did not glue on_long and rth_long into always-in. "
        "Did not retune B|conj|atr1559|lock or flush|max6|repaired. Combined of the three is a side "
        "line only (same names, different clocks — not a diversified slate). "
        "Odd months IS, even months OOS, split on entry session. Combined dollars are not EV. No Arrow 44."
    )
    lines = [
        "Arrow 43 — clock split (IS / OOS)",
        verdict,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "EV = expected value; RTH = regular trading hours (09:30–16:00 ET); "
        "IWM = iShares Russell 2000 ETF; SSR = Short Sale Restriction.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)} odd months  "
        f"OOS n={len(oos_sess)} even months",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: common stock, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"rank PDV cap {CAP_NAMES}  ${NOTIONAL:.0f} notional/name (no stop-based $200 size)",
        "on_long: buy last tradeable RTH minute close; sell next 09:30 open. on_short: opposite; borrow proxy. "
        "rth_long: buy 09:30 open; sell last RTH close; fuse −8% from fill (shop fuse, not a trade stop).",
        "No FLY cell. No 08:00 hot gate. No conjunction. No flush wash. No new ingest.",
        "",
    ]
    lines.extend(_char_block(co_m, oc_m))
    lines.append("")
    lines.append(
        f"{'id':<12} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'seat':>5}"
    )
    for r in results:
        for split, sm, a, skip, n_a, months in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"]),
        ):
            flag = "YES" if r["seat"] and split == "OOS" else ("—" if split == "IS" else "NO")
            if split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<12} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {flag:>5}"
            )
            lines.extend(_fmt_book(sm))
            trough_note = (
                "intraday trough = marked RTH low vs 09:30 fill"
                if r["name"] == "rth_long"
                else "overnight trough = close-to-open gap (no mark while shut)"
            )
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  {trough_note}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    lines.append("combined of the three (side line, not a slate):")
    lines.append(
        f"  all-session $/day={comb['per_day']:.2f}  n_days={comb['n']}  "
        f"maxDD$={comb['max_dd']:.2f}  NOT EV"
    )
    c01 = comb["corr"].get((0, 1), 0.0)
    c02 = comb["corr"].get((0, 2), 0.0)
    c12 = comb["corr"].get((1, 2), 0.0)
    lines.append(
        f"  corr daily PnL  on_long vs on_short={c01:.3f}  on_long vs rth_long={c02:.3f}  "
        f"on_short vs rth_long={c12:.3f}"
    )
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow43_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow43_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 43",
        "",
        verdict,
        "",
        "Clock split. Three frozen books: on_long, on_short, rth_long. "
        "Odd months IS, even months OOS, split on entry session. Combined virgin Jan–May + full Jun–Aug. "
        "Did not retune B|conj|atr1559|lock or flush|max6|repaired. No new ingest. "
        "Did not touch Lab A data/bars. Combined of the three is a side line, not a slate. No Arrow 44.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']}  "
            f"{'SEAT' if r['seat'] else 'no seat'}"
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
