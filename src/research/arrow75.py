"""Arrow 75 — home hour, January / February 2026. Long and short are separate."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from ingest.calendar import NYSE_EARLY_CLOSE
from ingest.paths import BARS_DIR, FULL_BARS, REPORTS
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import SEAT_FLOOR, _clock, _read_bars
from research.arrow44 import MIN_PDV, MIN_PX, MAX_PX, _by_sess, _month_lines
from research.arrow45 import _daily_and_trades
from research.arrow47 import _short_n
from research.arrow48 import _wins_losses
from research.arrow51 import _ci_note
from research.arrow57 import _fmt_book57, _long_n, select_losers, select_winners
from research.arrow74 import NOTIONAL, _elig_janfeb
from research.book import daily_close_drawdown
from research.clock import (
    arrow74_february,
    arrow74_january,
    arrow74_sessions,
    arrow75_feature_sessions,
    feature_sessions,
    session_shift,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.fills import is_tradeable
from research.signals import RTH_OPEN

ET = ZoneInfo("America/New_York")
RTH_END = time(16, 0)
N_SLOT = 8
HOME_LOOK = 10
HOME_MIN_DAYS = 8
LEFT_LB = 15
CONTROL_ID = "short_left"
LONG_ID = "long_left"
# name, rank (left/morn), side, days (all/wed), hours (all/open)
EXPERIMENTS = (
    ("short_left", "left", "short", "all", "all"),
    ("long_left", "left", "long", "all", "all"),
    ("short_morn", "morn", "short", "all", "all"),
    ("long_morn", "morn", "long", "all", "all"),
    ("short_left_wed", "left", "short", "wed", "all"),
    ("short_left_open", "left", "short", "all", "open"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
# last bucket 14:30–15:59 is 90 minutes; others are 60.
BUCKETS = (
    ("0930", time(9, 30), time(10, 30)),
    ("1030", time(10, 30), time(11, 30)),
    ("1130", time(11, 30), time(12, 30)),
    ("1230", time(12, 30), time(13, 30)),
    ("1330", time(13, 30), time(14, 30)),
    ("1430", time(14, 30), time(16, 0)),
)
BUCKET_IDS = tuple(b[0] for b in BUCKETS)
BUCKET_OPEN = {b[0]: b[1] for b in BUCKETS}
BUCKET_END = {b[0]: b[2] for b in BUCKETS}


def prior_n(d: date, n: int, sessions: list[date]) -> list[date] | None:
    """Prior n sessions strictly before d. Does not include d."""
    prev = [x for x in sessions if x < d]
    if len(prev) < n:
        return None
    return prev[-n:]


def bucket_of(t: time) -> str | None:
    for name, lo, hi in BUCKETS:
        if lo <= t < hi:
            return name
    return None


def morn_last_ok(ts: datetime, bucket_open: time) -> bool:
    """morn last print must be strictly before H starts."""
    return _clock(ts) < bucket_open


def bucket_last_minute(hi: time) -> time:
    if hi == time(16, 0):
        return time(15, 59)
    return time(hi.hour, hi.minute - 1) if hi.minute else time(hi.hour - 1, 59)


def extract_home_day(session: date, symbol: str) -> dict | None:
    df = _read_bars(session, symbol)
    if df is None:
        return None
    early = NYSE_EARLY_CLOSE.get(session)
    bstat = {
        b[0]: {"open_px": None, "high": None, "low": None, "first": None, "last": None, "n": 0}
        for b in BUCKETS
    }
    px0930 = None
    last_rth = None
    rth_high = None
    rth_low = None
    last_before = {b[0]: None for b in BUCKETS}
    for rec in df.sort("bar_start").iter_rows(named=True):
        ts = rec["bar_start"]
        t = _clock(ts)
        if t < RTH_OPEN or t >= RTH_END:
            continue
        if early is not None and t >= early:
            continue
        op, cl, vol = rec["open"], rec["close"], rec["volume"]
        if not is_tradeable(op, cl, vol):
            continue
        px = float(cl)
        if px <= 0:
            continue
        hi = float(rec["high"]) if rec.get("high") is not None else px
        lo = float(rec["low"]) if rec.get("low") is not None else px
        opx = float(op) if op is not None and float(op) > 0 else px
        if px0930 is None:
            px0930 = (ts, px)
        last_rth = (ts, px)
        rth_high = hi if rth_high is None else max(rth_high, hi)
        rth_low = lo if rth_low is None else min(rth_low, lo)
        for bid, lo_t, _hi_t in BUCKETS:
            if t < lo_t:
                last_before[bid] = (ts, px)
        bid = bucket_of(t)
        if bid is None:
            continue
        st = bstat[bid]
        if st["first"] is None:
            st["first"] = (ts, px)
            st["open_px"] = opx
        st["last"] = (ts, px)
        st["high"] = hi if st["high"] is None else max(st["high"], hi)
        st["low"] = lo if st["low"] is None else min(st["low"], lo)
        st["n"] += 1
    scores: dict[str, float | None] = {}
    for bid, st in bstat.items():
        if st["n"] < 1 or not st["open_px"] or st["open_px"] <= 0:
            scores[bid] = None
        else:
            scores[bid] = (float(st["high"]) - float(st["low"])) / float(st["open_px"])
    rth_range = None
    if rth_high is not None and rth_low is not None:
        rth_range = float(rth_high) - float(rth_low)
    return {
        "scores": scores,
        "bstat": bstat,
        "px0930": px0930,
        "last_rth": last_rth,
        "last_before": last_before,
        "rth_range": rth_range,
    }


def home_hour_of(looks: list[dict | None]) -> str | None:
    """Largest sum of (high−low)/open over prior days. Ties: earlier bucket. Not T."""
    scores = {b: 0.0 for b in BUCKET_IDS}
    have = {b: 0 for b in BUCKET_IDS}
    for ex in looks:
        if ex is None:
            continue
        for b, sc in ex["scores"].items():
            if sc is not None:
                scores[b] += float(sc)
                have[b] += 1
    best = None
    best_sc = None
    for b in BUCKET_IDS:
        if have[b] == 0:
            continue
        if best is None or scores[b] > best_sc + 1e-12:
            best, best_sc = b, scores[b]
    if best is None or have[best] < HOME_MIN_DAYS:
        return None
    return best


def _extract_job(args: tuple) -> tuple[str, str, dict | None]:
    iso, symbol = args
    return iso, symbol, extract_home_day(date.fromisoformat(iso), symbol)


def peak_live_by_hour(trades: list[dict]) -> float:
    by: dict[tuple[str, str], float] = {}
    for t in trades:
        iso = t["signal"].isoformat() if isinstance(t.get("signal"), date) else str(t.get("signal"))[:10]
        hr = str(t.get("hour") or "")
        by[(iso, hr)] = by.get((iso, hr), 0.0) + abs(float(t["shares"]) * float(t["entry_px"]))
    return max(by.values()) if by else 0.0


def run_arrow75(*, workers: int | None = None) -> int:
    jan = arrow74_january()
    feb = arrow74_february()
    sess = arrow74_sessions()
    feats = arrow75_feature_sessions()
    if any(d.month == 3 for d in sess):
        raise RuntimeError("Arrow 75 must not score March")
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 2, 3)) == FULL_BARS:
        raise RuntimeError("Arrow 75 must not read Lab A data/bars/ or data/full/")
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    print(
        f"research start mode=arrow75 workers={workers} cpu={cpu} "
        f"window={sess[0]}..{sess[-1]} n={len(sess)} jan n={len(jan)} feb n={len(feb)} "
        f"feats={feats[0]}..{feats[-1]} "
        f"jan_tape={tape_root(date(2026, 1, 2))} feb_tape={tape_root(date(2026, 2, 3))}",
        flush=True,
    )
    print(
        "Home hour January / February 2026. Long and short are separate engines. "
        "Did not retune Wednesday H10. Did not use February to pick a bucket or n. "
        "Last RTH bucket 14:30–15:59 is 90 minutes; others are 60. "
        "No new ingest. No Arrow 76.",
        flush=True,
    )
    elig = _elig_janfeb(sess)
    by = _by_sess(elig)
    need: set[tuple[str, str]] = set()
    for d in sess:
        for h in by.get(d.isoformat(), []):
            sym = h["symbol"]
            need.add((d.isoformat(), sym))
            prior = prior_n(d, HOME_LOOK, feats)
            if prior:
                for p in prior:
                    need.add((p.isoformat(), sym))
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            if t1 is not None:
                need.add((t1.isoformat(), sym))
            if t16 is not None:
                need.add((t16.isoformat(), sym))
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"home look={HOME_LOOK} min_days={HOME_MIN_DAYS} n={N_SLOT} ${NOTIONAL:.0f} "
        f"extract_jobs={len(need)}",
        flush=True,
    )
    cache: dict[tuple[str, str], dict] = {}
    prog = Progress(len(need), "arrow75")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_extract_job, job) for job in sorted(need)]
        for i, fut in enumerate(as_completed(futs), 1):
            iso, symbol, got = fut.result()
            if got is not None:
                cache[(iso, symbol)] = got
            prog.mark(str(i), rows=1)
            if i % 64 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0}
        for d in sess
    }
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    hours_fired: dict[str, set[tuple[str, str]]] = {k: set() for k in IDS}
    jan_home: dict[str, int] = {b: 0 for b in BUCKET_IDS}
    jan_fracs: list[float] = []
    jan_n_home = 0

    for d in sess:
        names = by.get(d.isoformat(), [])
        by_h: dict[str, list[dict]] = {b: [] for b in BUCKET_IDS}
        for h in names:
            prior = prior_n(d, HOME_LOOK, feats)
            if prior is None:
                continue
            looks = [cache.get((p.isoformat(), h["symbol"])) for p in prior]
            hh = home_hour_of(looks)
            if hh is None:
                continue
            today = cache.get((d.isoformat(), h["symbol"]))
            if today is None:
                continue
            row = {**h, "home": hh, "today": today}
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            left = None
            if t1 is not None and t16 is not None:
                a = cache.get((t1.isoformat(), h["symbol"]))
                b = cache.get((t16.isoformat(), h["symbol"]))
                if (
                    a
                    and b
                    and a.get("last_rth")
                    and b.get("last_rth")
                    and b["last_rth"][1] > 0
                ):
                    left = a["last_rth"][1] / b["last_rth"][1] - 1.0
            row["left"] = left
            by_h[hh].append(row)
            if d.month == 1:
                jan_home[hh] += 1
                jan_n_home += 1
                st = today["bstat"].get(hh) or {}
                rr = today.get("rth_range")
                if rr and rr > 0 and st.get("high") is not None and st.get("low") is not None:
                    jan_fracs.append((float(st["high"]) - float(st["low"])) / rr)
        chunks[d.isoformat()]["n_res"] = sum(len(v) for v in by_h.values())
        for bid, cohort in by_h.items():
            if len(cohort) < N_SLOT:
                continue
            lo_t = BUCKET_OPEN[bid]
            for name, rank, side, days, hours in EXPERIMENTS:
                if days == "wed" and d.weekday() != 2:
                    continue
                if hours == "open" and bid != "0930":
                    continue
                keyed = []
                for row in cohort:
                    today = row["today"]
                    if rank == "left":
                        val = row.get("left")
                    elif bid == "0930":
                        px = today.get("px0930")
                        pc = row.get("prior_close")
                        val = (
                            px[1] / float(pc) - 1.0
                            if px is not None and pc and float(pc) > 0
                            else None
                        )
                    else:
                        px0 = today.get("px0930")
                        last_b = (today.get("last_before") or {}).get(bid)
                        if (
                            px0 is not None
                            and last_b is not None
                            and px0[1] > 0
                            and morn_last_ok(last_b[0], lo_t)
                        ):
                            val = last_b[1] / px0[1] - 1.0
                        else:
                            val = None
                    if val is None:
                        continue
                    keyed.append({**row, "rankv": val})
                if len(keyed) < N_SLOT:
                    continue
                if side == "short":
                    picks = select_winners(keyed, N_SLOT, "rankv")
                else:
                    picks = select_losers(keyed, N_SLOT, "rankv")
                hour_key = (d.isoformat(), bid)
                for row in picks:
                    st = row["today"]["bstat"][bid]
                    ent = st.get("first")
                    ex = st.get("last")
                    if ent is None or ex is None:
                        continue
                    if side == "short":
                        tr = _short_n(row, ent, ex, bid, NOTIONAL)
                    else:
                        tr = _long_n(row, ent, ex, bid, NOTIONAL)
                    if tr is None:
                        continue
                    last_min = bucket_last_minute(BUCKET_END[bid])
                    tr["signal"] = d
                    tr["fill_date"] = d
                    tr["exit_date"] = d
                    tr["hour"] = bid
                    tr["exit_partial"] = _clock(ex[0]) != last_min
                    chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                    trades_all[name].append(tr)
                    hours_fired[name].add(hour_key)

    n_jan_home = sum(jan_home.values())
    dist = ", ".join(f"{b}={jan_home[b]}" for b in BUCKET_IDS)
    mean_frac = (sum(jan_fracs) / len(jan_fracs)) if jan_fracs else None
    naive = 60.0 / 390.0
    clock_real = mean_frac is not None and mean_frac > naive * 1.25
    char_line = (
        f"January home-hour distribution (name-days n={n_jan_home}): {dist}. "
        f"Last bucket 14:30–15:59 is 90 minutes; others 60. "
        f"Mean fraction of that day's RTH range in estimated home hour="
        + (f"{mean_frac:.3f}" if mean_frac is not None else "n/a")
        + f" (naive 60/390={naive:.3f}). Clock concentrated: {'yes' if clock_real else 'no'}. "
        "Description. Does not pick an id. Did not use February to pick a bucket."
    )
    print(char_line, flush=True)

    def _score_month(name: str, month_sess: list[date]) -> dict:
        mset = set(month_sess)
        weeks = sorted({t["signal"] for t in trades_all[name] if t["signal"] in mset})
        sm_ent, daily, tr = _daily_and_trades(chunks, month_sess, name, weeks)
        sm_ent["n_win"], sm_ent["n_loss"] = _wins_losses(tr)
        sm_ent["daily_close_dd"] = daily_close_drawdown(daily)
        sm_ent["worst_day"] = min(daily) if daily else 0.0
        n_hr = sum(1 for iso, _h in hours_fired[name] if date.fromisoformat(iso) in mset)
        return {
            "sm": sm_ent,
            "tr": tr,
            "peak": peak_live_by_hour(tr),
            "n_sess": len(month_sess),
            "n_days": len(weeks),
            "n_hours": n_hr,
            "months": _month_lines(daily, month_sess),
        }

    results = []
    for name, rank, side, days, hours in EXPERIMENTS:
        jan_s = _score_month(name, jan)
        feb_s = _score_month(name, feb)
        results.append(
            {
                "name": name,
                "rank": rank,
                "side": side,
                "days": days,
                "hours": hours,
                "jan": jan_s,
                "feb": feb_s,
                "peak_all": peak_live_by_hour(trades_all[name]),
                "n_hours_all": len(hours_fired[name]),
                "ci_jan_ex": jan_s["sm"]["ci_lo"] > 0 or jan_s["sm"]["ci_hi"] < 0,
                "ci_feb_ex": feb_s["sm"]["ci_lo"] > 0 or feb_s["sm"]["ci_hi"] < 0,
            }
        )

    def _green(pack: dict) -> bool:
        return pack["sm"]["per_day"] > 0

    jan_print = [r["name"] for r in results if r["jan"]["sm"]["n_trades"] > 0]
    jan_green = [r["name"] for r in results if _green(r["jan"])]
    feb_green = [r["name"] for r in results if _green(r["feb"])]
    short0 = next(r for r in results if r["name"] == CONTROL_ID)
    long1 = next(r for r in results if r["name"] == LONG_ID)
    first_para = (
        f"{char_line} January prints: {', '.join(jan_print) if jan_print else 'none'}. "
        f"January green: {', '.join(jan_green) if jan_green else 'none'}. "
        f"February green (survive): {', '.join(feb_green) if feb_green else 'none'}. "
        f"Long_left Jan ${long1['jan']['sm']['per_day']:.2f} Feb ${long1['feb']['sm']['per_day']:.2f} "
        f"vs short_left Jan ${short0['jan']['sm']['per_day']:.2f} Feb ${short0['feb']['sm']['per_day']:.2f}."
    )
    sniff = (
        "VERDICT: SNIFF — two months is not a seat. February is one look, not a $200 slate pass. "
        "Did not treat January/February as the shop IS/OOS split. Did not score March–August."
    )
    honesty = (
        "Home hour. Each name has a usual RTH hour from the prior 10 sessions, not T. "
        "Score = sum of (high−low)/open in the bucket. Ties: earlier bucket. "
        "Skip the name if fewer than 8 of the 10 days have that bucket. "
        "Last bucket 14:30–15:59 is 90 minutes. "
        "Long and short are separate engines. Did not retune Wednesday H10. "
        "left = 15-session close-to-close ending prior session. "
        "morn = 09:30 first RTH to last print before H; for 09:30, morn is prior-close to 09:30 (gap). "
        "Did not use a stamp from inside H to rank morn. "
        "Fill = first print at or after bucket open. Exit = last print of that bucket. $3,000. "
        "Did not use February to pick a bucket or n. "
        "Do not call a CI that includes 0 EV. Do not call February a $200 slate pass. "
        "No new ingest. Did not touch Lab A data/bars/ or data/full/. No Arrow 76."
    )
    lines = [
        "Arrow 75 — home hour, January / February 2026",
        first_para,
        sniff,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"window n={len(sess)} {sess[0]}..{sess[-1]}  jan n={len(jan)}  feb n={len(feb)}  "
        f"(March not scored)",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"feb_tape={tape_root(date(2026, 2, 3))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"home look={HOME_LOOK} min_days={HOME_MIN_DAYS} n={N_SLOT} ${NOTIONAL:.0f}",
        "Peak live = |shares × entry| per hour (hours do not overlap). "
        "$/day = total PnL / NYSE sessions in that month.",
        "",
        f"{'id':<16} {'month':<4} {'$/day':>9} {'n':>6} {'hrs':>5} {'hit':>6} {'t':>6}",
    ]
    for r in results:
        for label, pack, ci_ex in (
            ("Jan", r["jan"], r["ci_jan_ex"]),
            ("Feb", r["feb"], r["ci_feb_ex"]),
        ):
            sm = pack["sm"]
            lines.append(
                f"{r['name']:<16} {label:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{pack['n_hours']:5d} {sm['hit_rate']:6.3f} {sm['t_stat']:6.2f}"
            )
            lines.extend(_fmt_book57(sm))
            lines.append(
                f"    $/day={sm['per_day']:.2f} (total PnL / n={pack['n_sess']} sessions)  "
                f"rank={r['rank']} side={r['side']} days={r['days']} hours={r['hours']}  "
                f"n_hours={pack['n_hours']}  peak live ${pack['peak']:.0f}  "
                f"all ${r['peak_all']:.0f}{_ci_note(sm)}"
            )
            lines.append(f"    months: {pack['months']}")
            if ci_ex:
                lines.append(f"    {label} CI excludes 0.")
            else:
                lines.append(f"    {label} CI includes 0 — not EV.")
    lines.append(
        "    Did not call February a $200 slate pass. Two months is a sniff, not a seat. No Arrow 76."
    )
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow75_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow75_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 75",
        "",
        first_para,
        "",
        sniff,
        f"short_left Jan ${short0['jan']['sm']['per_day']:.2f} n={short0['jan']['sm']['n_trades']} "
        f"hrs={short0['jan']['n_hours']}  Feb ${short0['feb']['sm']['per_day']:.2f} n="
        f"{short0['feb']['sm']['n_trades']}. "
        f"long_left Jan ${long1['jan']['sm']['per_day']:.2f} Feb ${long1['feb']['sm']['per_day']:.2f}. "
        "Did not use February to pick a bucket. No Arrow 76.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 75"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
