# Agent rules

- Never print, log, commit, or echo `.env` or credential values.
- Stocks Professional only unless the user says otherwise. No options, no bulk/flat files, no streaming. Sub-minute bars only when the user asks for that tape.
- Prefer the official `thetadata` Python SDK (HTTPS/gRPC). Do not launch Theta Terminal unless asked.
- Follow `docs/DATA_CONTRACT.md`. Universe is the eligibility rules in the active brief, not an arbitrary 50-name cap.
- Economic rule is `docs/SUCCESS.md` (two floors: slate $200/day, seat $100/day with IS not red / OOS green / low correlation / joint risk that fits $100k). Goal $300–$500 net per trading day on $100k. Do not optimize for pretty backtests that cannot clear the floors.
- Language from Arrow 43 on: IS = in-sample (odd months), OOS = out-of-sample (even months). Do not use develop / holdout as names for new work.
- **Granularity law:** the finest tape we actually possess is foundational for reading and acting. Today that is one-minute bars; if a 1-second or 10-second tape is added, that becomes the default. A higher timeframe (5-minute, 15-minute, etc.) is allowed only when a scored comparison shows it is superior for execution or computation (for example anti-twitch). Do not treat “one-minute” as the identity of the law.
- Keep live pulls resumable. Pilot (5 symbols × 5 days) before a full ingest.
- Parallelize by default: multi-core workers for local compute, parquet, tape replay, validation, and independent subprocesses. Theta pulls use up to 8 concurrent requests (Pro cap) with backoff on 429. Serial loops need a reason.
- Long jobs: stdout heartbeat at least every 15 minutes with an ETA estimate. Soft time budgets are hints, not kill switches — checkpoint and resume.
- Do not commit `data/`, parquet, or secrets. Manifests and reports may be committed if they contain no credentials.
- Every new or changed file Build commits is audited by Grok before the next arrow is written. Prefer small, reviewable commits over one opaque dump.
- Expand acronyms on first use in briefs and reports.
- Standing SOP: the detailed instruction set is the `docs/BUILD_ARROW_XX.md` on Git. The paste to Build is a short pointer at that file. Do not treat a long chat paste as the spec.
