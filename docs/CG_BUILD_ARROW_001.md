# CG Build Arrow 001 — isolate and reproduce frozen hold-short-for-fade parent

Read, in this order:

1. `AGENTS.md`
2. `docs/CHATGPT_LAB_PROTOCOL.md`
3. `SOURCE_MONEY_COMMIT.txt`
4. `docs/SUCCESS.md`
5. `docs/DATA_CONTRACT.md`
6. `reports/arrow65_results.txt`
7. `reports/arrow66_results.txt`
8. `reports/arrow70_results.txt`
9. `src/research/arrow65.py`
10. `src/research/arrow66.py`
11. `src/research/arrow70.py`

This is **bootstrap + reproduction only**. Do not optimize. Do not invent an Arrow 002. Do not modify `C:\Users\james\Money`.

## Objective

Prove that `C:\Users\james\money_chatgpt` is a self-contained research lab and that the copied code/data can reproduce the frozen **hold short for fade** parent before we repair or extend it.

Working parent definition for this arrow:

- Wednesday signal;
- eligible common-stock field used by the inherited Wednesday H10 work (`$10–$80` prior close, prior-day dollar volume at least `$10M`, inherited ETP denylist);
- rank the eight largest 15-session close-to-close returns (the inherited IWM subtraction is a common scalar and does not change the rank);
- fill next session last regular-hours trade / inherited `nextrth` implementation;
- `$4,000` nominal ticket per selected name;
- ten trading-session hold from fill;
- inherited modeled transaction costs;
- marked-to-market daily equity using the Arrow 65+ plumbing.

Do not change any of those rules in this arrow.

## Step 0 — pull and prove repository isolation

Start with:

- `git pull --ff-only`;
- print `git rev-parse --show-toplevel`;
- print `git remote -v`;
- confirm the root is exactly `C:\Users\james\money_chatgpt` and the remote is `jamesksnyder99/money_chatgpt`.

Fail immediately if the active working tree is `C:\Users\james\Money`.

Do not run any command that writes to `C:\Users\james\Money`.

## Step 1 — verify local data copy

The lab is expected to have local ignored copies under `data/` of:

- `data/virgin/`;
- `data/full/`;
- `data/meta/`;
- `data/ref/`;
- `data/calendar/`.

Verify each exists. Report file count and byte size for each.

Also verify:

- no directory under those five trees is a junction/symbolic link/reparse-point target back into `C:\Users\james\Money`;
- `git status --short --ignored` shows the market-data trees are ignored rather than staged/tracked;
- the expected virgin/full study windows needed by Arrows 65/66/70 are present.

If the data copy is incomplete, do **not** silently fall back to `Money`. Stop the research run after writing a short diagnostic report.

## Step 2 — create a fresh lab virtual environment if needed

Use a repository-local `.venv/` under `money_chatgpt`.

Install only from the inherited dependency specification plus any package already clearly required by the inherited code/tests. Do not copy or expose credentials. No new market-data pull is authorized in this arrow.

## Step 3 — inherited test baseline

Run the inherited test suite before changing research code.

Record:

- Python version;
- dependency install result;
- total tests passed / failed / skipped;
- wall time.

If inherited tests fail because the copied snapshot already expected a local-only dependency or fixture, diagnose and minimally repair only the lab environment/test plumbing. Do not change strategy economics to make tests pass.

## Step 4 — reproduce the frozen parent

Use the inherited research entrypoint(s) rather than rewriting the engine if possible.

Reproduce these specific checkpoints from the inherited reports:

### Arrow 66-style 2026 split checkpoints

Frozen `h10_4k` should be in the neighborhood of:

- IS MTM: `$401.16/day`, `n=116`;
- OOS MTM: `$260.36/day`, `n=113`;
- OOS marked-to-market drawdown approximately `-$8,013.49`;
- all-session / reported peak live exposure approximately `$91,206`.

These are reproduction targets, not pass/fail tolerances by themselves. Explain any difference exactly.

### Arrow 70-style continuous-year checkpoint

For the fixed `$4,000` Wednesday H10 parent over 2025-09-02 through 2026-08-31, reproduce the inherited flat-ticket continuous-year neighborhood:

- total MTM profit approximately `$51,855.71`;
- MTM approximately `$206.60/day` over 251 NYSE sessions;
- maximum marked-to-market drawdown approximately `-$20,033.68`;
- worst marked day approximately `-$6,607.31`;
- 376 completed trades;
- reported peak live exposure approximately `$102,922`.

Also reprint the 12 inherited monthly MTM contributions for reconciliation.

Do not treat this year as fresh validation. It is a reproduction of already-seen research.

## Step 5 — canonical lab baseline artifact

Create `reports/cg_arrow001_baseline.txt` containing:

1. repository root + current lab commit at start;
2. source Money commit from `SOURCE_MONEY_COMMIT.txt`;
3. data-tree counts/sizes and isolation checks;
4. Python/test results;
5. exact commands used to reproduce the parent;
6. the Arrow 66-style IS/OOS reconciliation;
7. the Arrow 70-style continuous-year reconciliation;
8. monthly MTM table;
9. any discrepancies, with likely cause and whether they block research;
10. a clear final verdict:
   - `REPRODUCED` if the copied lab reproduces the inherited parent closely enough that remaining differences are explained and immaterial;
   - `BLOCKED` if it does not.

Also create `reports/cg_arrow001_commands.txt` with the exact command lines used, one per line, so the run can be repeated.

## Step 6 — lab guard tests

Add focused tests if needed so future work cannot accidentally regress isolation. At minimum cover:

- the lab path resolution points inside `money_chatgpt`, not `Money`;
- data directories remain Git-ignored;
- the frozen parent identifiers/parameters used by the reproduction are unchanged.

Do not make tests depend on a hard-coded username if an equivalent repository-relative assertion is possible.

## Step 7 — commit and push

Before committing:

- inspect `git status`;
- inspect staged filenames;
- verify no parquet, credentials, `.env`, API keys, or local proprietary data will be committed;
- do not commit `.venv/` or caches.

Commit code/tests/reports/manifest-style text needed for audit and push to `origin/main`.

Suggested commit message:

`CG Arrow 001: isolate lab and reproduce fade parent`

## Report back

In the pushed report and terminal summary, state only the important facts:

- isolation PASS/FAIL;
- tests PASS/FAIL and count;
- reproduction verdict;
- inherited vs reproduced continuous-year `$ / day`, max drawdown, trade count, and peak exposure;
- any blocker.

No optimization. No new strategy. No Arrow 002.
