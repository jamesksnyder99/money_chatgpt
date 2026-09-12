# money

Theta Data stock research workspace (Stocks Professional).

v1 corpus and ingest rules: [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).
Build notes: [`docs/BUILD.md`](docs/BUILD.md).

Put credentials in `.env` at the repo root. Never commit that file.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\smoke_theta.py
```
