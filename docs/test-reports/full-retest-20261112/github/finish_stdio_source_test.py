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
  self.p=subprocess.Popen([spec['command'],*args],cwd=BASE,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','GIT_TRACE':str(BASE/'git-trace.log')},bufsize=0);self.i=0;self.buf=b''
  self.send('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'independent-static-source-retest','version':'1'}})
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
def last_progress():
 return [f['params'] for f in E['calls'][-1]['frames'] if f.get('method')=='notifications/progress']
def reject(name, tool, **args):
 result=c.call(tool,expect_error=True,project_id=pid,**args)
 E.setdefault('rejections',{})[name]={'result':result,'progress':last_progress()}
 assert result['code']==(400 if name=='invalid_line' else 409),(name,result)
 return result
def save(candidate, error_name=None):
 args=dict(content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
 return reject(error_name,'save_ledger',**args) if error_name else c.call('save_ledger',project_id=pid,**args)
def unchanged(name):
 current=c.call('read_project',project_id=pid)
 assert current['ledger']==baseline,(name,'ledger changed')
 E.setdefault('unchanged_after_rejection',[]).append(name)
def git(*args, env=None):
 return subprocess.check_output(['git','-c','core.hooksPath=/dev/null',*args],cwd=cache,text=True,env=env).strip()
def activity_detail(expected):
 history=c.call('history',project_id=pid)
 records=[r for r in history['records'] if r['title']=='源码核对资料已准备']
 assert records and expected in records[0]['detail'],records[0] if records else history
 E.setdefault('source_preparation_logs',[]).append(records[0])
try:
 pid=E['project_id'];prepared=E['prepared'];repo='jonschlinkert/is-number'
 source=prepared['sources']['repositories'][0];cache=pathlib.Path(source['path']);original_commit=source['commit']
 assert original_commit=='98e8ff1da1a89f93d1397a24d7413ed15421c139','Live source moved after static review; must reread before submission'
 E['blob_verification']=[]
 for snippet in prepared['sources']['snippets']:
  raw=subprocess.check_output(['git','show',original_commit+':'+snippet['path']],cwd=cache,text=True)
  numbered='\n'.join(str(n)+': '+line for n,line in enumerate(raw.splitlines(),1) if snippet['start']<=n<=snippet['end'])
  assert numbered==snippet['text'],snippet['path']
  E['blob_verification'].append({'path':snippet['path'],'start':snippet['start'],'end':snippet['end'],'matches_git_blob':True})
 E['clone_verification']={'head':git('rev-parse','HEAD'),'shallow':git('rev-parse','--is-shallow-repository'),'origin':git('config','--get','remote.origin.url'),'no_checkout':not (cache/'index.js').exists()}
 assert E['clone_verification']['head']==original_commit
 assert E['clone_verification']['shallow']=='true' and E['clone_verification']['no_checkout']
 assert source['state']=='已克隆新缓存'
 activity_detail('已读取 1 个参考仓库的固定提交，共 4 个源码片段')
 trace=BASE/'git-trace.log';before_trace=trace.read_text() if trace.exists() else ''
 reused=c.call('prepare_source_review',project_id=pid);reuse_progress=last_progress();delta=trace.read_text()[len(before_trace):]
 assert reused['binding']==prepared['binding']
 assert reused['sources']['repositories'][0]['state']=='已克隆，使用本地提交'
 assert reused['sources']['snippets']==prepared['sources']['snippets']
 assert 'clone' not in delta and 'fetch' not in delta and delta
 assert all('克隆仓库' not in p.get('message','') for p in reuse_progress)
 E['cache_reuse']={'binding_unchanged':True,'snippets_unchanged':True,'source':reused['sources']['repositories'][0],'progress':reuse_progress,'git_trace':delta}
 activity_detail('已读取 1 个参考仓库的固定提交，共 4 个源码片段')
 report={'features':[{'id':'F01','status':'有源码依据','finding':'由独立测试 Agent /root/retest_12_sources 静态阅读本次返回的固定提交源码：index.js 第 11-12 行用 typeof 与 num-num===0 接受有限数字并排除 NaN/Infinity；第 14-15 行要求字符串 trim 后非空，再将数值转换结果交给有限性判断；第 17 行返回 false。test.js 第 32-44 行列出数值字符串，第 102-104 行断言该组应为数值，第 109-114 行列出空白与空字符串反例。未运行参考项目或其测试；本条不是本项目实现证据或独立开发验收，未查看的行为保持待确认。','evidence':[{'repository':repo,'path':'index.js','line':11},{'repository':repo,'path':'index.js','line':12},{'repository':repo,'path':'index.js','line':14},{'repository':repo,'path':'index.js','line':15},{'repository':repo,'path':'index.js','line':17},{'repository':repo,'path':'test.js','line':104},{'repository':repo,'path':'test.js','line':113}]}]}
 E['actual_static_report']=report
 bad=json.loads(json.dumps(report));bad['features'][0]['evidence'][0]['line']=99999
 reject('invalid_line','submit_source_review',review_id=prepared['review_id'],report=bad)
 c.call('submit_source_review',project_id=pid,review_id=prepared['review_id'],report=report)
 candidate=c.call('generate_ledger',project_id=pid)
 saved=save(candidate);E['initial_saved_ledger']=saved
 assert saved['summary']['done']==0
 current=c.call('read_project',project_id=pid);baseline=current['ledger']
 assert '[x]' not in baseline['content']
 E['initial_ledger_content']=baseline['content']
 stale=c.call('generate_ledger',project_id=pid)
 c.call('save_plan',project_id=pid,revision=current['plan']['revision'],content=current['plan']['content'].replace('空字符串返回假','空字符串与 Infinity 返回假'))
 reject('plan_stale_report_generation','generate_ledger')
 reject('plan_stale_ticket','submit_source_review',review_id=prepared['review_id'],report=report)
 save(stale,'plan_stale_candidate');unchanged('plan_stale_binding')
 fresh=c.call('prepare_source_review',project_id=pid)
 c.call('submit_source_review',project_id=pid,review_id=fresh['review_id'],report=report)
 stale_report_candidate=c.call('generate_ledger',project_id=pid)
 newer_report=dict(report);newer_report=json.loads(json.dumps(report));newer_report['features'][0]['finding']+=' 补充核对：Infinity 的静态排除依据同 index.js 第 12 行。'
 c.call('submit_source_review',project_id=pid,review_id=fresh['review_id'],report=newer_report)
 save(stale_report_candidate,'replaced_report_stale_candidate');unchanged('source_report_revision')
 valid=c.call('generate_ledger',project_id=pid)
 tree=git('rev-parse','HEAD^{tree}')
 fixture_env={**os.environ,'GIT_AUTHOR_NAME':'Source drift fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Source drift fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'}
 fixture_commit=git('commit-tree',tree,'-p',original_commit,'-m','TEST ONLY: cache HEAD drift, no reference code execution',env=fixture_env)
 E['test_induced_source_drift']={'original_real_github_commit':original_commit,'fixture_commit':fixture_commit,'scope':'Temporary local commit with unchanged GitHub tree; used only to invalidate bindings; never submitted as real GitHub source or implementation evidence'}
 git('update-ref','HEAD',fixture_commit,original_commit)
 try:
  reject('source_stale_report_generation','generate_ledger')
  reject('source_stale_ticket','submit_source_review',review_id=fresh['review_id'],report=newer_report)
  save(valid,'source_stale_candidate');unchanged('source_commit_binding')
 finally:
  git('update-ref','HEAD',original_commit,fixture_commit)
 assert git('rev-parse','HEAD')==original_commit
 valid=c.call('generate_ledger',project_id=pid)
 missing=cache.with_name(cache.name+'-test-held')
 cache.rename(missing)
 try:
  reject('missing_cache_report_generation','generate_ledger')
  assert not cache.exists(),'generate_ledger silently recloned missing cache'
  unchanged('missing_cache_no_hidden_clone')
 finally:
  missing.rename(cache)
 current=c.call('read_project',project_id=pid)
 c.call('select_references',project_id=pid,revision=current['references']['revision'],selected=[])
 reject('selection_stale_ticket','submit_source_review',review_id=fresh['review_id'],report=newer_report)
 save(valid,'selection_stale_candidate');unchanged('reference_selection_binding')
 empty=c.call('prepare_source_review',project_id=pid)
 assert empty['sources']['repositories']==[] and empty['sources']['snippets']==[]
 activity_detail('未选择参考仓库，本次无源码证据')
 current=c.call('read_project',project_id=pid)
 c.call('select_references',project_id=pid,revision=current['references']['revision'],selected=[repo])
 finalprep=c.call('prepare_source_review',project_id=pid)
 c.call('submit_source_review',project_id=pid,review_id=finalprep['review_id'],report=newer_report)
 finalcandidate=c.call('generate_ledger',project_id=pid)
 finalsave=save(finalcandidate);assert finalsave['summary']['done']==0
 E['final_saved_ledger']=finalsave
 E['final_prepared_sources']=finalprep['sources']['repositories']
 history=c.call('history',project_id=pid)
 failures=[r for r in history['records'] if r.get('state')=='failed']
 assert len(failures)==len(E['rejections']),(len(failures),len(E['rejections']))
 assert all(not any(token in r['title'] for token in ['save_','generate_','submit_','prepare_']) for r in failures)
 E['failure_activity_records']=failures
 E['result']='PASS';E['finished_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 E['limits']=['Real MCP stdio from current Codex ZIP, not an actual Codex/Claude natural-language host session','Only public jonschlinkert/is-number; four bounded static snippets; no downloaded repository code, package installation, benchmark, or tests executed','Temporary local synthetic commit used only for source-binding drift rejection, then restored; no fabricated model or development-review claims','No browser, no UI verification; source test task only; no source, project ledger or git commit changes in product repository']
 print(json.dumps({'result':E['result'],'base':str(BASE),'calls':len([r for r in E['calls'] if r['request']['method']=='tools/call']),'rejections':{k:{'code':v['result']['code'],'final_progress':v['progress'][-1]['progress']} for k,v in E['rejections'].items()},'clone':E['clone_verification'],'preparation_logs':E['source_preparation_logs'],'saved_summary':finalsave['summary'],'limits':E['limits']},ensure_ascii=False,indent=2))
except Exception as exc:E['failure']=repr(exc);raise
finally:c.close()
