"""Public review of staged or pending-push bytes; never print secret matches."""
import argparse,json,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALLOWED=re.compile(r'^(reports/cg_arrow004[^/]*\.(?:json|jsonl|md|txt|csv)|src/research/cg_arrow004[^/]*\.py|scripts/cg_arrow004[^/]*\.py|tests/test_cg_arrow004[^/]*\.py)$')
PATTERNS={
 'private key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 'AWS credential':rb'AKIA[0-9A-Z]{16}',
 'GitHub credential':rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
 'OpenAI credential':rb'sk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}',
 'credential assignment':rb'(?im)^\s*(?:THETA_API_KEY|API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD)\s*=\s*[^\s#]{8,}',
 'credentialed URL':rb'https?://[^\s/:]+:[^\s/@]+@',
 'private account identifier':rb'(?i)(?:account_number|account_id|broker_account)\s*[=:]\s*["\x27]?[A-Z0-9]{6,}',
}
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def main():
    p=argparse.ArgumentParser();p.add_argument('--base');a=p.parse_args();rev=[a.base,'HEAD'] if a.base else ['--cached']
    names=git('diff',*rev,'--name-only','--diff-filter=ACMR').decode().splitlines();issues=[];total=0
    for n in names:
        if not ALLOWED.fullmatch(n):issues.append((n,'unexpected path'))
        b=git('show',f'HEAD:{n}' if a.base else f':{n}');total+=len(b)
        if b'\x00' in b or len(b)>15_000_000:issues.append((n,'binary or unnecessarily large'))
        for label,pattern in PATTERNS.items():
            if re.search(pattern,b):issues.append((n,label))
        if n.startswith('reports/'):
            if re.search(rb'"(?:bar_start|bid_price|ask_price|entry_px|original_entry|original_shares|preorder_price|api_key|password|access_token)"\s*:',b,re.I):issues.append((n,'raw market/position or sensitive payload field'))
            if n.endswith('.json'):json.loads(b)
            elif n.endswith('.jsonl'):
                for line in b.splitlines():json.loads(line)
    print(json.dumps({'review':'push diff' if a.base else 'staged bytes','files':len(names),'bytes':total,'issues':issues,'result':'PASS' if not issues else 'BLOCKED'},indent=2))
    if issues:raise SystemExit(1)
if __name__=='__main__':main()
