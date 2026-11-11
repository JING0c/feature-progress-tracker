import pathlib, tempfile, json, os, subprocess, zipfile, hashlib, select, time, sys, shutil
ROOT=pathlib.Path('/Users/olcgb/code/protuct_plan')
BASE=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(tempfile.mkdtemp(prefix='fpt-live-github-'))
BASE.mkdir(exist_ok=True)
EFILE=BASE/'evidence.json'; E=json.loads(EFILE.read_text()) if EFILE.exists() else {'calls':[],'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'limits':['Static code read only; no downloaded code executed','MCP stdio integration, not real Claude CLI host session']}
ZIP=ROOT/'dist/feature-progress-tracker-codex.zip'; PKG=BASE/'package'; WS=BASE/'workspace'; WS.mkdir(exist_ok=True)
if not PKG.exists():
 with zipfile.ZipFile(ZIP) as z:z.extractall(PKG)
E['zip']={'path':str(ZIP),'sha256':hashlib.sha256(ZIP.read_bytes()).hexdigest()};E['workspace']=str(WS);E['claude_cli']=shutil.which('claude')
class Client:
 def __init__(self):
  spec=json.loads((PKG/'.mcp.json').read_text())['mcpServers']['feature-progress-tracker'];args=[a.replace('${PLUGIN_ROOT}',str(PKG)) for a in spec['args']]
  self.p=subprocess.Popen([spec['command'],*args],cwd=BASE,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','CODEX_HOME':str(BASE/'isolated-codex-home')},bufsize=0);self.i=0;self.buf=b''
  self.send('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'live-github-acceptance','version':'1'}})
  self.p.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');self.p.stdin.flush()
 def send(self,m,p=None):
  self.i+=1; start=time.monotonic(); request={'jsonrpc':'2.0','id':self.i,'method':m,'params':p or {}};frames=[]
  self.p.stdin.write((json.dumps(request,ensure_ascii=False)+'\n').encode());self.p.stdin.flush()
  while True:
   if b'\n' not in self.buf:
    ready,_,_=select.select([self.p.stdout],[],[],150)
    if not ready:raise TimeoutError('MCP tool timeout')
    chunk=os.read(self.p.stdout.fileno(),65536)
    if not chunk:raise RuntimeError(self.p.stderr.read().decode())
    self.buf+=chunk
    continue
   line,self.buf=self.buf.split(b'\n',1);frame=json.loads(line);frames.append(frame)
   if frame.get('id')==self.i:
    E['calls'].append({'request':request,'frames':frames,'elapsed_seconds':round(time.monotonic()-start,3)})
    EFILE.write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n')
    return frame['result']
 def call(self,tool_name,expect_error=False,**args):
  result=self.send('tools/call',{'name':tool_name,'arguments':{'workspace':str(WS),**args},'_meta':{'progressToken':tool_name+'-'+str(len(E['calls']))}})
  assert bool(result.get('isError'))==expect_error,(tool_name,result)
  progress=[f['params']['progress'] for f in E['calls'][-1]['frames'] if f.get('method')=='notifications/progress'];assert progress and progress==sorted(progress) and (progress[-1]<100 if expect_error else progress[-1]==100),progress
  return result.get('structuredContent',result)
 def close(self):
  self.p.stdin.close();self.p.wait(timeout=10);E['server_exit_code']=self.p.returncode;E['stderr']=self.p.stderr.read().decode();EFILE.write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n')
c=Client()
try:
 phase=sys.argv[2] if len(sys.argv)>2 else 'search'
 if phase=='search':
  p=c.call('create_project',name='真实 GitHub 源码核对隔离测试')['project'];E['project_id']=p['id']
  result=c.call('search_references',project_id=p['id'],query='is-number in:name user:jonschlinkert')
  print(json.dumps({'base':str(BASE),'references':result},ensure_ascii=False,indent=2))
 elif phase=='prepare':
  pid=E['project_id'];current=c.call('read_project',project_id=pid);print('READ_KEYS',list(current))
  refs=current['references'];c.call('select_references',project_id=pid,revision=refs['revision'],selected=['jonschlinkert/is-number'])
  plan='''# 数值识别工具项目规划书\n## 项目目标\n为调用方识别数值或可转换为有限数值的字符串。\n## 项目范围\n仅研究 JavaScript 参数识别规则，源码作为参考，不执行参考代码。\n## 功能规划与验收\n| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 | 依赖 |\n|---|---|---|---|---|---|---|\n| F01 | 无 | 数值识别 | 识别有限数字和非空数值字符串 | 数字和数值字符串返回真，空字符串返回假 | 是 | 无 |\n'''
  saved=c.call('save_plan',project_id=pid,revision=current['plan']['revision'],content=plan);prepared=c.call('prepare_source_review',project_id=pid);E['prepared']=prepared
  print(json.dumps({'base':str(BASE),'prepared':prepared},ensure_ascii=False,indent=2))
 elif phase=='finish':
  pid=E['project_id'];prepared=E['prepared'];repo='jonschlinkert/is-number'
  report={'features':[{'id':'F01','status':'有源码依据','finding':'静态阅读 index.js 第 10-18 行：数字分支用 num-num===0 排除 NaN 与无穷大；字符串必须 trim 后非空且转数值后有限，否则返回 false。test.js 第 32-44、102-105、109-114 行另有数值字符串与空字符串用例。未执行该仓库代码，本报告不表示本项目已实现或通过运行验收。','evidence':[{'repository':repo,'path':'index.js','line':11},{'repository':repo,'path':'index.js','line':14},{'repository':repo,'path':'index.js','line':17},{'repository':repo,'path':'test.js','line':104}]}]}
  bad=json.loads(json.dumps(report));bad['features'][0]['evidence'][0]['line']=99999
  E['invalid_line_rejected']=c.call('submit_source_review',expect_error=True,project_id=pid,review_id=prepared['review_id'],report=bad)
  submitted=c.call('submit_source_review',project_id=pid,review_id=prepared['review_id'],report=report)
  candidate=c.call('generate_ledger',project_id=pid)
  saved=c.call('save_ledger',project_id=pid,content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
  current=c.call('read_project',project_id=pid);before=current['ledger'];E['saved_ledger']=saved
  stale=c.call('generate_ledger',project_id=pid)
  c.call('save_plan',project_id=pid,revision=current['plan']['revision'],content=current['plan']['content'].replace('空字符串返回假','空字符串与 Infinity 返回假'))
  E['stale_report_generation_rejected']=c.call('generate_ledger',expect_error=True,project_id=pid)
  E['stale_ticket_rejected']=c.call('submit_source_review',expect_error=True,project_id=pid,review_id=prepared['review_id'],report=report)
  E['stale_ledger_save_rejected']=c.call('save_ledger',expect_error=True,project_id=pid,content=stale['content'],revision=stale['ledger_revision'],plan_revision=stale['plan_revision'],source_revision=stale['source_revision'])
  after=c.call('read_project',project_id=pid);assert after['ledger']==before,'stale rejection modified ledger'
  E['ledger_unchanged_after_rejections']=True;E['report']=report
  source=prepared['sources']['repositories'][0];sourcepath=source['path']
  E['clone_verification']={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=sourcepath,text=True).strip(),'shallow':subprocess.check_output(['git','rev-parse','--is-shallow-repository'],cwd=sourcepath,text=True).strip(),'status':subprocess.check_output(['git','status','--porcelain'],cwd=sourcepath,text=True).strip()}
  assert E['clone_verification']['head']==source['commit'] and E['clone_verification']['shallow']=='true'
  E['result']='PASS';E['finished_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
  print(json.dumps({'base':str(BASE),'result':E['result'],'clone':E['clone_verification'],'rejects':{k:v for k,v in E.items() if 'rejected' in k},'tool_calls':len([x for x in E['calls'] if x['request']['method']=='tools/call']),'claude_cli':E['claude_cli']},ensure_ascii=False,indent=2))
 elif phase=='verify':
  source=E['prepared']['sources']['repositories'][0];path=pathlib.Path(source['path']);commit=source['commit']
  assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()==commit
  assert subprocess.check_output(['git','rev-parse','--is-shallow-repository'],cwd=path,text=True).strip()=='true'
  assert not (path/'index.js').exists(),'third party worktree unexpectedly checked out'
  raw=subprocess.check_output(['git','show',commit+':index.js'],cwd=path,text=True)
  expected=next(x for x in E['prepared']['sources']['snippets'] if x['path']=='index.js')['text']
  assert '\n'.join(str(n+1)+': '+line for n,line in enumerate(raw.splitlines()))==expected
  assert E['ledger_unchanged_after_rejections'] and E['saved_ledger']['summary']['done']==0
  for key in ('stale_report_generation_rejected','stale_ticket_rejected','stale_ledger_save_rejected'):assert E[key]['code']==409
  assert E['invalid_line_rejected']['code']==400
  c.call('read_project',project_id=E['project_id'])
  E['harness_correction']='Initial clean-worktree assertion was invalid: product intentionally clones with --no-checkout. Reverified shallow HEAD and exact blob excerpt; no product failure.'
  E['prior_harness_failure']=E.pop('failure',None);E['result']='PASS';E['finished_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());E['clone_verification']['no_checkout_confirmed']=True;E['clone_verification']['excerpt_matches_git_blob']=True
  print(json.dumps({'result':E['result'],'base':str(BASE),'source':source,'tool_calls':len([x for x in E['calls'] if x['request']['method']=='tools/call']),'limits':E['limits'],'claude_cli':E['claude_cli']},ensure_ascii=False,indent=2))
except Exception as exc:E['failure']=repr(exc);raise
finally:c.close()
