# money_chatgpt — ChatGPT / Codex research protocol

This repository is an independent research laboratory cloned from `jamesksnyder99/money`.
The source snapshot is recorded in `SOURCE_MONEY_COMMIT.txt`.

## Roles

- **ChatGPT** is research director and auditor. ChatGPT writes the detailed research arrows in GitHub, reviews Codex commits/reports, interprets results, and decides the next arrow.
- **Codex (C)** is the local execution agent. C pulls the current `main`, reads the active arrow, performs the prescribed work, runs tests, writes code/reports, commits, and pushes to `main` unless an arrow explicitly says otherwise.
- **User** normally relays only a short pointer telling C which arrow to read. The detailed specification lives in GitHub, not in the chat paste.

## Shared-control workflow

1. ChatGPT audits the latest `main` in GitHub.
2. ChatGPT writes one new `docs/CG_BUILD_ARROW_XXX.md` and pushes it to GitHub.
3. User gives C a short pointer: pull `main`, read `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, and the named arrow, then execute it completely.
4. C starts by `git pull --ff-only` and confirms the active repository is `C:\Users\james\money_chatgpt`.
5. C performs the work only in `money_chatgpt`, runs the prescribed tests, writes audit-friendly reports, commits all intended tracked changes, and pushes to `origin/main`.
6. ChatGPT reviews the pushed commit and results before writing the next arrow.

Do not chain arrows autonomously. One completed, pushed arrow is a checkpoint for audit.

## Isolation rule — absolute

`C:\Users\james\Money` is source provenance only and is **out of bounds for writes**.

C must not edit, commit, checkout, clean, reset, fetch into, generate reports in, write caches in, or otherwise modify the original Money repository or its data.

For this laboratory:

- Code, tests, reports, and manifests belong under `C:\Users\james\money_chatgpt`.
- Market data used by the lab must be local copies under `money_chatgpt\data\` or newly acquired directly into the lab.
- Do not use junctions, symbolic links, or hard links that make lab writes touch `Money`.
- Do not import data by writing back into `Money`.
- If a required input is absent from the lab, stop that branch and report the missing input; do not silently read a mutable source copy unless the active arrow explicitly authorizes a read-only provenance check.

## Git / public-repository safety

The GitHub repository is public by user choice.

Never commit or print:

- `.env` or credentials;
- API keys or tokens;
- parquet market data;
- private account identifiers;
- local secrets;
- proprietary data files not already intended for public release.

The inherited `.gitignore` is necessary but not sufficient. Before every push, inspect `git status` and the staged diff for public safety.

## Research governance

- Preserve the frozen parent/control exactly unless the active arrow explicitly changes it.
- Reproduce before repairing; repair before optimizing.
- One change at a time when causal attribution matters.
- No hindsight deletion of losing dates, trades, or months.
- Do not use a previously inspected slice as fresh validation.
- Report negative findings with the same prominence as positive findings.
- Prefer interpretable state machines and economic mechanisms over opaque parameter sweeps.
- Costs, borrow assumptions, capital use, and marked-to-market (MTM) risk are part of strategy economics.
- A variant is not better merely because it is smoother after taking less exposure. Include exposure-matched controls where relevant.
- A different name, weekday, or threshold is not automatically an orthogonal engine. Orthogonality requires a meaningfully different economic mechanism and should ultimately be checked on synchronized portfolio returns.

## Hold-short-for-fade working name

In this lab, **hold short for fade** refers to the Money research lineage beginning with the Arrow 44 residual-winner short idea and evolving into the Wednesday, eight-name, 15-session lookback, delayed-fill, ten-session-hold parent studied in Arrows 65–73.

The inherited Money reports may use names such as `leftover`, `Wednesday H10`, `h10_4k`, or related identifiers. Lab reports should always include a short plain-English description next to opaque IDs.

## Arrow numbering

Lab arrows use `CG_BUILD_ARROW_001.md`, `CG_BUILD_ARROW_002.md`, and so on. Do not reuse the inherited Money Arrow numbers.
