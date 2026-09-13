"""Inspect every staged/public-push byte without printing matched secrets."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
ALLOWED=re.compile(r"^(reports/cg_arrow003[^/]*\.(?:json|jsonl|md|csv|txt)|src/research/cg_arrow003[^/]*\.py|scripts/cg_arrow003[^/]*\.py|tests/test_cg_arrow003[^/]*\.py)$")
PATTERNS={
    "private key":rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "AWS access id":rb"AKIA[0-9A-Z]{16}",
    "GitHub credential":rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "OpenAI credential":rb"sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}",
    "assigned credential":rb"(?im)^\s*(?:THETA_API_KEY|API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD)\s*=\s*[^\s#]{8,}",
    "credentialed URL":rb"https?://[^\s/:]+:[^\s/@]+@",
    "private account assignment":rb"(?i)(?:account_number|account_id|broker_account)\s*[=:]\s*[\"']?[A-Z0-9]{6,}",
}


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base",help="Review committed push diff from this base instead of the index")
    args=parser.parse_args()
    revision=[args.base,"HEAD"] if args.base else ["--cached"]
    names=git("diff",*revision,"--name-only","--diff-filter=ACMR").decode().splitlines()
    issues=[]
    total=0
    schema_keys=set()
    for name in names:
        if not ALLOWED.fullmatch(name):issues.append((name,"unexpected path"))
        body=git("show",f"HEAD:{name}" if args.base else f":{name}")
        total+=len(body)
        if len(body)>20_000_000:issues.append((name,"unexpectedly large artifact"))
        if b"\x00" in body:issues.append((name,"binary content"))
        for label,pattern in PATTERNS.items():
            if re.search(pattern,body):issues.append((name,label))
        if name.startswith("reports/"):
            if name.endswith(".json"):
                obj=json.loads(body)
                if isinstance(obj,dict):schema_keys.update(obj)
            if re.search(rb'"(?:api_key|access_token|password|private_key|account_number)"\s*:',body,re.I):
                issues.append((name,"sensitive report field"))
            # Execution ledgers and vendor bars stay local; metrics and spec fields
            # may legitimately contain words such as volume or terminal_tickets.
            if re.search(rb'"(?:bar_start|bid_price|ask_price|entry_px|exit_ts|entry_ts)"\s*:',body):
                issues.append((name,"raw market/execution payload field"))
    print(json.dumps({"review":"committed push diff" if args.base else "staged bytes",
                      "files":len(names),"bytes_inspected":total,"issues":issues,
                      "result":"PASS" if not issues else "BLOCKED"},indent=2))
    if issues:raise SystemExit(1)


if __name__=="__main__":main()
