from pathlib import Path
import subprocess, os, json, hashlib, time, concurrent.futures
ROOT=Path(__file__).resolve().parent
REPO=Path('/Users/olcgb/code/protuct_plan')
NODE='/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node'
env=os.environ.copy();env['TMPDIR']=str(ROOT/'tmp');env['PYTHONDONTWRITEBYTECODE']='1'
def snapshot():
 files=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).split(b'\0')
 return {os.fsdecode(p):hashlib.sha256((REPO/os.fsdecode(p)).read_bytes()).hexdigest() for p in files if p and (REPO/os.fsdecode(p)).is_file()}
(ROOT/'tracked-before.json').write_text(json.dumps(snapshot(),ensure_ascii=False,indent=2))
commands=[('01-unittest',['python3','-B','-m','unittest','discover','-s','tests','-v'])]
js=sorted(REPO.glob('tests/*.cjs'));assert len(js)==8,len(js)
commands.extend((f'{i:02d}-{p.stem}',[NODE,str(p.relative_to(REPO))]) for i,p in enumerate(js,2))
commands.extend([
 ('10-diff-check',['git','diff','--check']),
 ('11-history-acceptance',['python3','-B','docs/test-reports/host-chat-repairs/history_acceptance_audit.py']),
 ('12-r345-adversarial',['python3','-B','docs/test-reports/host-chat-repairs/adversarial_r345_review.py']),
 ('13-usability-boundaries',['python3','-B','docs/test-reports/usability-repairs/review_usability_repairs.py']),
 ('14-usability-dom',[NODE,'docs/test-reports/usability-repairs/review_usability_repairs.cjs'])])
def run(pair):
 name,args=pair;start=time.monotonic()
 try:
  proc=subprocess.run(args,cwd=REPO,env=env,capture_output=True,timeout=240)
  (ROOT/(name+'.stdout.log')).write_bytes(proc.stdout);(ROOT/(name+'.stderr.log')).write_bytes(proc.stderr)
  result={'name':name,'command':args,'cwd':str(REPO),'exit_code':proc.returncode,'seconds':round(time.monotonic()-start,3)}
 except subprocess.TimeoutExpired as exc:
  (ROOT/(name+'.stdout.log')).write_bytes(exc.stdout or b'');(ROOT/(name+'.stderr.log')).write_bytes(exc.stderr or b'')
  result={'name':name,'command':args,'cwd':str(REPO),'exit_code':124,'seconds':round(time.monotonic()-start,3),'error':'timeout after 240s'}
 print(json.dumps(result,ensure_ascii=False),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(run,commands))
after=snapshot();(ROOT/'tracked-after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2))
before=json.loads((ROOT/'tracked-before.json').read_text())
report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'root':str(ROOT),'command_count':len(commands),'commands':results,'tracked_changed':[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)],'git_status':subprocess.check_output(['git','status','--short'],cwd=REPO,text=True)}
(ROOT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('REPORT='+str(ROOT/'summary.json'))
raise SystemExit(any(r['exit_code'] for r in results))
