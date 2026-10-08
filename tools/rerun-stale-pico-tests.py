"""Re-run host tests whose recorded source hashes no longer match the recovery tree (a later patch touched a shared file).

Each tools/test-pico-*.py writes out/phoenix-kernel-recovery/<dir>/result.json with the sha256 of the sources it exercised.
After a later patch edits one of those files the old result is stale; this script finds those results, maps them back to the
test script that writes <dir>, re-runs it, and reports which ones still pass. Nothing touches the device."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
OUT=BASE/'out/phoenix-kernel-recovery';TOOLS=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def writers():
    m={}
    for t in sorted(TOOLS.glob('test-*.py')):
        for d in re.findall(r"out/phoenix-kernel-recovery/([A-Za-z0-9_.-]+-tests)",t.read_text(errors='replace')):
            m.setdefault(d,t)
        for d in re.findall(r"OUT\s*/\s*'([A-Za-z0-9_.-]+-tests)'",t.read_text(errors='replace')):
            m.setdefault(d,t)
    return m
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dry-run',action='store_true');a=ap.parse_args()
    w=writers();stale=[];unknown=[]
    for r in sorted(OUT.glob('*-tests/result.json')):
        try:res=json.loads(r.read_text())
        except Exception:continue
        bad=[n for n,h in res.get('sources',{}).items() if sha(SOURCE/n)!=h]
        if bad:(stale if r.parent.name in w else unknown).append((r.parent.name,bad))
    report={'stale':{d:b for d,b in stale},'no_writer':{d:b for d,b in unknown},'rerun':{}}
    if not a.dry_run:
        for d,_ in stale:
            p=subprocess.run([sys.executable,str(w[d])],capture_output=True,text=True,timeout=1800)
            report['rerun'][d]={'script':w[d].name,'exit_code':p.returncode,'tail':(p.stdout+p.stderr)[-400:] if p.returncode else ''}
    print(json.dumps(report,indent=2))
    raise SystemExit(1 if any(v['exit_code'] for v in report['rerun'].values()) or unknown else 0)
if __name__=='__main__':main()
