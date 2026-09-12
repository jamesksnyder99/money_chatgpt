"""Arrow 64 — group leftover versus SIC2. Long and short are separate engines."""

from __future__ import annotations

import os
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import BARS_DIR, REPORTS, SECTOR_SIC
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, load_combined_iwm
from research.arrow44 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _iwm_last_close,
    _last_close,
    _month_lines,
)
from research.arrow45 import _daily_and_trades
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import peak_live_notional
from research.arrow57 import _long_n
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
FROZEN_ASOF = date(2026, 9, 11)
CONTROL_ID = "short_iwm_fri"
SIC_FRI = "short_sic_fri"
LONG_ID = "long_sic_fri"
WED_ID = "short_sic_wed"
NOTIONAL = 3000.0
NOTIONAL_4K = 4000.0
N_SLOT = 8
MIN_RESIDUAL = 16
MIN_PEER = 8
LB = 15
HOLD = 10
# name, side, rank (iwm/sic), weekday (Mon=0), n, notional
EXPERIMENTS = (
    ("short_iwm_fri", "short", "iwm", 4, 8, 3000.0),
    ("short_sic_fri", "short", "sic", 4, 8, 3000.0),
    ("long_sic_fri", "long", "sic", 4, 8, 3000.0),
    ("short_sic_wed", "short", "sic", 2, 8, 3000.0),
    ("short_sic_fri_n15", "short", "sic", 4, 15, 3000.0),
    ("short_sic_fri_4k", "short", "sic", 4, 8, 4000.0),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
FRI_IDS = tuple(e[0] for e in EXPERIMENTS if e[3] == 4)


def group_residual(name_ret: float, peer_rets: list[float]) -> float | None:
    """Name return minus median of other same-sic2 names. Not IWM."""
    if len(peer_rets) < MIN_PEER:
        return None
    return float(name_ret) - float(statistics.median(peer_rets))


def attach_group_residuals(rows: list[dict]) -> list[dict]:
    """Drop a name from group ids when it has fewer than 8 sic2 peers."""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        s2 = r.get("sic2")
        if s2:
            by[str(s2)].append(r)
    out: list[dict] = []
    for group in by.values():
        for r in group:
            peers = [float(x["name_ret"]) for x in group if x["symbol"] != r["symbol"]]
            res = group_residual(float(r["name_ret"]), peers)
            if res is None:
                continue
            out.append({**r, "residual": res, "peer_n": len(peers)})
    return out


def select_shorts(rows: list[dict], n: int) -> list[dict]:
    ranked = sorted(
        (r for r in rows if r.get("residual") is not None),
        key=lambda r: (-float(r["residual"]), r["symbol"]),
    )
    return ranked[: max(0, int(n))]


def select_longs(rows: list[dict], n: int) -> list[dict]:
    ranked = sorted(
        (r for r in rows if r.get("residual") is not None),
        key=lambda r: (float(r["residual"]), r["symbol"]),
    )
    return ranked[: max(0, int(n))]


def load_sic2() -> dict[str, str]:
    """Frozen Arrow 63 map. Do not hit SEC."""
    if not SECTOR_SIC.exists():
        raise FileNotFoundError(f"missing {SECTOR_SIC}; Arrow 63 map required")
    df = pl.read_parquet(SECTOR_SIC)
    asofs = []
    if "asof" in df.columns:
        asofs = [a for a in df["asof"].unique().to_list() if a is not None]
    if asofs:
        got = asofs[0]
        got_d = got if isinstance(got, date) and not isinstance(got, datetime) else (
            got.date() if hasattr(got, "date") else date.fromisoformat(str(got)[:10])
        )
        if got_d != FROZEN_ASOF:
            raise RuntimeError(f"SIC map asof={got_d} is not frozen {FROZEN_ASOF}; do not refresh")
    out: dict[str, str] = {}
    for rec in df.select("symbol", "sic2").iter_rows(named=True):
        s2 = rec.get("sic2")
        if s2 is None or str(s2).strip() == "":
            continue
        out[str(rec["symbol"]).upper().strip()] = str(s2).strip()
    if not out:
        raise RuntimeError("SIC map has no sic2 rows")
    return out


def _fmt_book64(sm: dict) -> list[str]:
    return _fmt_book48(sm)


def _trade(h: dict, side: str, tag: str, notional: float, closes_x: dict):
    ent = h.get("now")
    ex = closes_x.get(h["symbol"])
    if ent is None or ex is None:
        return None
    if side == "short":
        return _short_n(h, ent, ex, tag, notional)
    return _long_n(h, ent, ex, tag, notional)


def _rebalance_job(args: tuple) -> dict:
    (
        iso,
        look15_iso,
        exit10_iso,
        names,
        iwm_l15,
        iwm1,
        wd,
    ) = args
    session = date.fromisoformat(iso)
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "picks": {k: [] for k in IDS},
        "n_elig": len(names),
        "n_mapped": len(names),
        "n_mapped_ret": 0,
        "n_group": 0,
        "peer_ns": [],
        "n_res_iwm": 0,
        "n_res_sic": 0,
        "skipped": "no_names",
        "wd": wd,
    }
    if not names or look15 is None:
        empty["skipped"] = "look"
        return empty
    iwm_ret = None
    if iwm_l15 is not None and iwm1 is not None and iwm_l15 > 0 and iwm1 > 0:
        iwm_ret = iwm1 / iwm_l15 - 1.0
    rows = []
    closes_x: dict[str, tuple] = {}
    for h in names:
        sym = h["symbol"]
        now = _last_close(session, sym)
        if now is None:
            continue
        a15 = _last_close(look15, sym)
        if a15 is None:
            continue
        if a15[1] <= 0 or now[1] <= 0:
            continue
        nr = now[1] / a15[1] - 1.0
        rec = {**h, "name_ret": nr, "now": now}
        rows.append(rec)
        if ex10 is not None:
            cx = _last_close(ex10, sym)
            if cx is not None:
                closes_x[sym] = cx
    trades = {k: [] for k in IDS}
    picks = {k: [] for k in IDS}
    iwm_rows = []
    if iwm_ret is not None:
        iwm_rows = [{**r, "residual": float(r["name_ret"]) - float(iwm_ret)} for r in rows]
    group_rows = attach_group_residuals(rows)
    out = {
        "session": iso,
        "trades": trades,
        "picks": picks,
        "n_elig": int(names[0]["n_elig"]) if names and "n_elig" in names[0] else len(names),
        "n_mapped": len(names),
        "n_mapped_ret": len(rows),
        "n_group": len(group_rows),
        "peer_ns": [int(r["peer_n"]) for r in group_rows],
        "n_res_iwm": len(iwm_rows),
        "n_res_sic": len(group_rows),
        "skipped": "",
        "wd": wd,
    }
    want = FRI_IDS if wd == 4 else (WED_ID,)
    for name, side, rank, _wd, n_take, notional in EXPERIMENTS:
        if name not in want:
            continue
        pool = iwm_rows if rank == "iwm" else group_rows
        if len(pool) < MIN_RESIDUAL:
            continue
        chosen = select_longs(pool, n_take) if side == "long" else select_shorts(pool, n_take)
        picks[name] = [h["symbol"] for h in chosen]
        for h in chosen:
            tr = _trade(h, side, name, notional, closes_x)
            if tr:
                trades[name].append(tr)
    return out


def run_arrow64(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 64 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow64 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "group leftover versus SIC2. Long and short are separate engines. "
        "Did not retune leftover pair, MAX, volume-pace, day-two, same-slot, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. Did not call SEC. No new ingest. No Arrow 65.",
        flush=True,
    )
    sic2 = load_sic2()
    print(
        f"SIC map {SECTOR_SIC} asof={FROZEN_ASOF} mapped={len(sic2)} (frozen; did not hit SEC)",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    for d in study:
        wd = d.weekday()
        if wd not in (2, 4):
            continue
        look15 = session_shift(d, -LB, feats)
        e10 = session_shift(d, HOLD, feats)
        if look15 is None or e10 is None:
            continue
        if not (tape_root(e10) / e10.isoformat()).exists():
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        raw = list(by.get(d.isoformat(), []))
        mapped = []
        for h in raw:
            s2 = sic2.get(str(h["symbol"]).upper())
            if not s2:
                continue
            mapped.append({**h, "sic2": s2, "n_elig": len(raw)})
        if wd == 4:
            for name in FRI_IDS:
                usable[name].append(d)
        else:
            usable[WED_ID].append(d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                e10.isoformat(),
                mapped,
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
                wd,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} + sic2  "
        f"name-days={elig.height} jobs={len(jobs)} fri={len(usable[CONTROL_ID])} "
        f"wed={len(usable[WED_ID])} n<=8 (id4 n=15) lb={LB} hold={HOLD} ${NOTIONAL:.0f} "
        f"(id5 ${NOTIONAL_4K:.0f})  long and short separate",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow64")
    prog.start_heartbeat()
    recs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_rebalance_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            recs[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    for iso, rec in recs.items():
        chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})
        chunks[iso]["trades"] = rec.get("trades") or {k: [] for k in IDS}
        chunks[iso]["n_res"] = rec.get("n_res_sic") or 0

    is_fridays = [d for d in usable[CONTROL_ID] if is_is_session(d)]
    mapped_ns = []
    elig_ns = []
    peer_ns = []
    overlap = []
    for d in is_fridays:
        rec = recs.get(d.isoformat()) or {}
        if rec.get("n_mapped"):
            mapped_ns.append(int(rec["n_mapped"]))
        if rec.get("n_elig"):
            elig_ns.append(int(rec["n_elig"]))
        peer_ns.extend(list(rec.get("peer_ns") or []))
        a = set((rec.get("picks") or {}).get(CONTROL_ID) or [])
        b = set((rec.get("picks") or {}).get(SIC_FRI) or [])
        if a and b:
            overlap.append(len(a & b))
    mean_mapped = (sum(mapped_ns) / len(mapped_ns)) if mapped_ns else 0.0
    mean_elig = (sum(elig_ns) / len(elig_ns)) if elig_ns else 0.0
    mean_peer = (sum(peer_ns) / len(peer_ns)) if peer_ns else 0.0
    if overlap:
        mean_ov = sum(overlap) / len(overlap)
        ov_line = (
            f"id0 IWM-eight vs id1 SIC-eight IS Friday overlap: mean {mean_ov:.2f}/8 "
            f"(n_fridays={len(overlap)})."
        )
    else:
        mean_ov = 0.0
        ov_line = "id0 IWM-eight vs id1 SIC-eight IS Friday overlap: n=0."
    char_lines = [
        "IS character: SIC-mapped leftover field. Description. Does not pick an id.",
        f"  mean SIC-mapped eligible names per Friday={mean_mapped:.1f} "
        f"(Arrow 52 wall-eligible mean={mean_elig:.1f}, n_fridays={len(mapped_ns)})",
        f"  mean sic2 peers per name that kept a group residual={mean_peer:.2f} (n={len(peer_ns)})",
        f"  {ov_line}",
    ]

    results = []
    day0_is = day0_oos = day1_is = day1_oos = day2_is = day2_oos = None
    ctrl_is = ctrl_oos = None
    for name, side, rank, wd, n_take, notional in EXPERIMENTS:
        weeks = usable[name]
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        peak_is = peak_live_notional(tr_is, is_sess)
        peak_oos = peak_live_notional(tr_oos, oos_sess)
        peak = max(peak_is, peak_oos)
        theoretical = 2.0 * float(n_take) * float(notional)
        fits = peak <= ACCOUNT + 1e-12
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = (
            sm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_is["per_day"] >= 0.0 and fits
        )
        if name == CONTROL_ID:
            ctrl_is, ctrl_oos = sm_is["per_day"], sm_oos["per_day"]
            day0_is, day0_oos = day_is, day_oos
        if name == SIC_FRI:
            day1_is, day1_oos = day_is, day_oos
        if name == LONG_ID:
            day2_is, day2_oos = day_is, day_oos
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = sm_is["per_day"] > ctrl_is + 1e-12 and sm_oos["per_day"] > ctrl_oos + 1e-12
        results.append(
            {
                "name": name,
                "side": side,
                "rank": rank,
                "wd": wd,
                "n_take": n_take,
                "notional": notional,
                "is": sm_is,
                "oos": sm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
                "slate": slate,
                "lift_both": lift_both,
                "oos_excludes": sm_oos["ci_lo"] > 0 or sm_oos["ci_hi"] < 0,
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
                "n_reb": len(weeks),
                "peak_live": peak,
                "peak_live_is": peak_is,
                "peak_live_oos": peak_oos,
                "theoretical": theoretical,
                "fits": fits,
            }
        )

    corr01_is = _pearson(day0_is or [], day1_is or [])
    corr01_oos = _pearson(day0_oos or [], day1_oos or [])
    corr12_is = _pearson(day1_is or [], day2_is or [])
    corr12_oos = _pearson(day1_oos or [], day2_oos or [])
    corr_line = (
        f"Pearson daily PnL {CONTROL_ID} vs {SIC_FRI} IS={corr01_is:.3f} OOS={corr01_oos:.3f}; "
        f"{SIC_FRI} vs {LONG_ID} IS={corr12_is:.3f} OOS={corr12_oos:.3f} (entry-session series)."
    )
    short_seats = [r["name"] for r in results if r["seat"] and r["side"] == "short"]
    long_seats = [r["name"] for r in results if r["seat"] and r["side"] == "long"]
    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    if slates:
        verdict = (
            "VERDICT: SLATE — "
            + ", ".join(slates)
            + f" (OOS >= ${FAILURE_LINE:.0f}/day, IS not red, peak live <= ${ACCOUNT:.0f})."
        )
    elif seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 64 engine has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    both_s = ", ".join(both) if both else "none"
    short_s = ", ".join(short_seats) if short_seats else "none"
    long_s = ", ".join(long_seats) if long_seats else "none"
    wed_r = next(r for r in results if r["name"] == WED_ID)
    fri_r = next(r for r in results if r["name"] == SIC_FRI)
    wd_line = (
        f"Wednesday short_sic_wed IS ${wed_r['is']['per_day']:.2f} OOS ${wed_r['oos']['per_day']:.2f}. "
        f"Friday short_sic_fri IS ${fri_r['is']['per_day']:.2f} OOS ${fri_r['oos']['per_day']:.2f}."
    )
    lead = (
        f"SIC-mapped Friday field mean {mean_mapped:.1f} names vs Arrow 52 wall-eligible mean "
        f"{mean_elig:.1f}. {ov_line} Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS "
        f"not red: {seat_s}. Slate ${FAILURE_LINE:.0f}: {slate_s}. Short seats: {short_s}. "
        f"Long seats: {long_s}. A long id is not judged as a failed short. {wd_line} "
        f"Group ids that lift $/day versus id 0 on both IS and OOS: {both_s}."
    )
    honesty = (
        "Group leftover versus SIC2. Hotel 6 of 7. "
        "Long and short are separate engines. Did not build them as a sign flip of one door. "
        "Did not retune the Wednesday leftover paper book, the Friday+Wednesday pair, MAX, "
        "volume-pace, day-two, same-slot, Arrow 43 clocks, or frozen B|conj|atr1559|lock / "
        "flush|max6|repaired. Rings locked from IS; OOS is one look for the family. "
        "Did not drop an id after seeing OOS. Did not use an OOS month to pick a threshold. "
        "Did not call SEC. Did not refresh the 2026-09-11 SIC map. "
        "A group id beats control only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and peak live <= $100k. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry. "
        "Combined dollars are not EV. Id 5 is the paper ticket size, diagnostic. No Arrow 65."
    )
    lines = [
        "Arrow 64 — group leftover versus SIC2 (IS / OOS)",
        verdict,
        lead,
        *char_lines,
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Engines that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and peak live fit: {slate_s}.",
        f"Group ids that lift $/day versus {CONTROL_ID} on both IS and OOS: {both_s}.",
        f"Short seats: {short_s}. Long seats: {long_s}. A long id is not judged as a failed short.",
        wd_line,
        corr_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; SIC = Standard Industrial Classification; "
        "RTH = regular trading hours; EV = expected value; SSR = Short Sale Restriction; "
        "CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"friday rebalances={len(usable[CONTROL_ID])}  wednesday rebalances={len(usable[WED_ID])}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}, sic2 mapped  "
        f"skip no-sic2  n<=8 (id4 n=15)  lb={LB} hold={HOLD} ${NOTIONAL:.0f}/name "
        f"(id5 ${NOTIONAL_4K:.0f})  enter last RTH  peers>=8 same sic2",
        "IWM residual = name 15-session return − IWM. Group residual = name − median of other "
        "same-sic2 names that session. Skip a rebalance if fewer than 16 names have the id's residual.",
        "",
        *char_lines,
        "",
        f"{'id':<20} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'side':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months_s, peak_s in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"], r["peak_live_is"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"], r["peak_live_oos"]),
        ):
            if split == "OOS" and r["slate"]:
                flag = "SLATE"
            elif split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<20} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} "
                f"{r['side']:>6} {flag:>5}"
            )
            lines.extend(_fmt_book64(sm))
            wd = "Friday" if r["wd"] == 4 else "Wednesday"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_slot<={r['n_take']} notional=${r['notional']:.0f}  {r['side']}  "
                f"{wd}  rank={r['rank']}  lb={LB} hold={HOLD}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  two-cohort ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  rebalances={r['n_reb']}"
            )
            lines.append(f"    months: {months_s}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow64_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow64_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 64",
        "",
        verdict,
        "",
        lead,
        char_lines[1],
        char_lines[2],
        char_lines[3],
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}. Slate ${FAILURE_LINE:.0f}: {slate_s}. "
        f"Short: {short_s}. Long: {long_s}. Lift-both vs id0: {both_s}.",
        corr_line,
        wd_line,
        "Group leftover versus SIC2. Long and short are separate engines. "
        "Did not retune leftover pair, MAX, or frozen B/flush. Did not call SEC. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 65.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            f"peak_live ${r['peak_live']:.0f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
            + ("  OOS CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
