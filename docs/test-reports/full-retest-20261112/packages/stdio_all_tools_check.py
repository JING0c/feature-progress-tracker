#!/usr/bin/env python3
"""Independent final ZIP review. Local deterministic tools only; no real model or Claude host."""
import hashlib, io, json, os, pathlib, select, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request, zipfile
BASE=pathlib.Path(__file__).resolve().parent
ROOT=pathlib.Path('/Users/olcgb/code/protuct_plan')
E={'reviewer':'/root/retest_12_packages','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'artifacts':{},'hosts':{},'calls':[],'http':[],'limitations':['No real Claude CLI installation/upgrade/session','No real model or natural-language host conversation','Live GitHub query only checks empty-result search; no repository README or source download','No browser visual QA']}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def files(root):return {str(p.relative_to(root)):digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def md_hashes(ws):return {str(p.relative_to(ws)):digest(p.read_bytes()) for p in ws.rglob('*.md')}
def validate_xlsx(raw):
 with zipfile.ZipFile(io.BytesIO(raw)) as book:
  assert book.testzip() is None
  names=book.namelist();assert '[Content_Types].xml' in names and 'xl/workbook.xml' in names
  content='\n'.join(book.read(n).decode() for n in names if n.endswith('.xml'))
  for name in ('图书管理','添加图书','搜索图书','拒绝空标题'):assert name in content,name
 return {'sha256':digest(raw),'zip_members':len(names),'expected_feature_and_acceptance_text':True}
class Client:
 def __init__(self,host):
  self.host=host;self.id=0;self.ws=pathlib.Path(tempfile.mkdtemp(prefix=host+'-workspace-',dir=BASE));self.root=BASE/host
  spec=json.loads((self.root/'.mcp.json').read_text())['mcpServers']['feature-progress-tracker']
  args=[a.replace('${PLUGIN_ROOT}',str(self.root)).replace('${CLAUDE_PLUGIN_ROOT}',str(self.root)) for a in spec['args']]
  env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')};env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',CODEX_HOME=str(BASE/(host+'-isolated-home')))
  self.p=subprocess.Popen([shutil.which(spec['command']),*args],cwd=BASE,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
  self.buffer=b''
  result=self.send('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'independent-current-zip-review','version':'1'}})['result']
  assert result['serverInfo']['version']=='0.2.0'
  self.p.stdin.write((json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n').encode());self.p.stdin.flush()
 def line(self):
  deadline=time.monotonic()+60
  while b'\n' not in self.buffer:
   remaining=deadline-time.monotonic()
   assert remaining>0,'MCP response timeout'
   ready,_,_=select.select([self.p.stdout],[],[],remaining)
   assert ready,'MCP response timeout'
   chunk=os.read(self.p.stdout.fileno(),65536)
   if not chunk:raise RuntimeError('MCP closed: '+self.p.stderr.read().decode())
   self.buffer+=chunk
  line,self.buffer=self.buffer.split(b'\n',1);return json.loads(line)
 def send(self,method,params=None):
  self.id+=1;ident=self.id
  self.p.stdin.write((json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params or {}},ensure_ascii=False)+'\n').encode());self.p.stdin.flush()
  frames=[]
  while True:
   frame=self.line();frames.append(frame)
   if frame.get('id')==ident:
    self.lastframes=frames
    with (BASE/'stdio-raw-transcript.jsonl').open('a') as rawlog:rawlog.write(json.dumps({'host':self.host,'request':{'jsonrpc':'2.0','id':ident,'method':method,'params':params or {}},'frames':frames},ensure_ascii=False)+'\n')
    E['calls'].append({'host':self.host,'method':method,'tool':(params or {}).get('name'),'response_sha256':digest(json.dumps(frames,sort_keys=True,ensure_ascii=False).encode()),'progress':[f['params']['progress'] for f in frames if f.get('method')=='notifications/progress'],'is_error':frame.get('result',{}).get('isError',False),'result_keys':sorted(frame.get('result',{}).get('structuredContent',frame.get('result',{})).keys())})
    return frame
 def call(self,tool_name,expect_error=False,**args):
  result=self.send('tools/call',{'name':tool_name,'arguments':{'workspace':str(self.ws),**args},'_meta':{'progressToken':self.host+str(self.id)}})['result']
  assert bool(result.get('isError'))==expect_error,result
  prog=E['calls'][-1]['progress'];assert prog and prog[-1]==(100 if not expect_error else prog[-1])
  assert not expect_error or prog[-1]<100,prog
  return result.get('structuredContent',result)
 def close(self):
  self.p.stdin.close();self.p.wait(timeout=10)
  assert self.p.returncode==0,self.p.returncode
  err=self.p.stderr.read().decode();assert err=='',err
clients=[]
try:
 for name in ('codex','claude','marketplace'):
  archive=ROOT/'dist'/('feature-progress-tracker-'+name+'.zip')
  rebuilt=BASE/'rebuilt-dist'/archive.name
  raw=archive.read_bytes();assert raw==rebuilt.read_bytes(),'Final ZIP differs from current source rebuild'
  E['artifacts'][name]={'path':str(archive),'sha256':digest(raw),'byte_identical_to_current_source_rebuild':True}
  if name!='marketplace':
   with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(BASE/name)
 with zipfile.ZipFile(ROOT/'dist/feature-progress-tracker-marketplace.zip') as z:
  for host in ('codex','claude'):
   package=BASE/host;inventory=json.loads((package/'package-inventory.json').read_text());actual=files(package)
   assert inventory['version']=='0.2.0'
   assert {k:v for k,v in actual.items() if k!='package-inventory.json'}==inventory['files_sha256']
   for name,h in actual.items():assert digest(z.read('plugins/'+host+'/'+name))==h
   for name in actual:
    if name.startswith('runtime/scripts/'): assert (ROOT/'scripts'/pathlib.Path(name).name).read_bytes()==(package/name).read_bytes()
   assert all(not any(s in name for s in ('.env','__pycache__','planning_agent.py')) for name in actual)
   E['artifacts'][host].update(inventory_files=len(inventory['files_sha256']),all_inventory_hashes_match=True,marketplace_bytes_match=True,runtime_source_bytes_match=True)
 for host in ('codex','claude'):
  c=Client(host);clients.append(c)
  tools=c.send('tools/list')['result']['tools'];names=[t['name'] for t in tools]
  assert len(names)==18 and len(set(names))==18
  project=c.call('create_project',name='独立制品复核-'+host)['project'];pid=project['id']
  assert c.call('list_projects')['projects'][0]['id']==pid
  before=c.call('read_project',project_id=pid)
  plan='''# 独立制品项目规划书
## 项目目标
帮助管理员整理和查看个人借阅图书。
## 项目范围
本地单用户图书管理，本期不需要联网登录。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 | 依赖 |
|---|---|---|---|---|---|---|
| F01 | 无 | 图书管理 | 保存并检索图书信息 | 保存后可找到图书 | 是 | 无 |
| F01-01 | F01 | 添加图书 | 输入图书标题保存记录 | 重启后能读取新记录 | 是 | 无 |
'''
  c.call('save_plan',project_id=pid,revision=before['plan']['revision'],content=plan)
  current=c.call('read_project',project_id=pid)
  preview=c.call('edit_features',project_id=pid,revision=current['plan']['revision'],additions=[{'key':'N1','parent':'F01','功能名称':'搜索图书','说明':'输入关键字查询目录','验收标准':'已添加书籍能被查询'}])
  assert preview['saved'] is False
  assert c.call('read_project',project_id=pid)['plan']['content']==current['plan']['content']
  c.call('save_plan',project_id=pid,revision=preview['revision'],content=preview['content'])
  c.call('save_plan',expect_error=True,project_id=pid,revision=current['plan']['revision'],content=plan)
  current=c.call('read_project',project_id=pid)
  assert '搜索图书' in current['plan']['content']
  suggestion=c.call('record_suggestions',project_id=pid,revision=current['plan']['revision'],analyst='独立测试脚本构造的建议，非模型输出',suggestions=[{'title':'空值校验','reason':'输入可能为空','changes':[{'action':'update','id':'F01-01','fields':{'验收标准':'拒绝空标题，保存后重启能读取新记录'}}]}])
  selected=c.call('preview_suggestions',project_id=pid,revision=current['plan']['revision'],suggestion_id=suggestion['id'],selected=[suggestion['suggestions'][0]['id']])
  assert selected['saved'] is False
  assert c.call('read_project',project_id=pid)['plan']['content']==current['plan']['content']
  c.call('save_plan',project_id=pid,revision=selected['revision'],content=selected['content'])
  searched=c.call('search_references',project_id=pid,query='codex-independent-repair-package-regression-lnzb5nik-765de4bfc70f462b9ef629a03d17b530 in:name')
  assert searched['repositories']==[],searched
  selected_refs=c.call('select_references',project_id=pid,revision=searched['revision'],selected=[])
  assert selected_refs['selection_confirmed'] is True and selected_refs['repositories']==[]
  prepared=c.call('prepare_source_review',project_id=pid)
  c.call('submit_source_review',project_id=pid,review_id=prepared['review_id'],report={'features':[{'id':f['编号'],'status':'未找到依据','finding':'独立协议验证场景没有选择外部参考仓库，不代表实现验收','evidence':[]} for f in prepared['features']]})
  candidate=c.call('generate_ledger',project_id=pid)
  ledger=c.call('save_ledger',project_id=pid,content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
  c.call('update_feature_progress',project_id=pid,revision=ledger['revision'],feature_id='F01-01',changes={'状态':'待审核','执行 Agent':'fixture-only-developer','实现证据':'仅验证工具工作流，不声明真实实现或验收'})
  history=c.call('history',project_id=pid);assert len(history['versions'])==3
  records=history['records']
  prepared_records=[r for r in records if r['title']=='源码核对资料已准备']
  assert len(prepared_records)==1,prepared_records
  assert prepared_records[0]['detail']=='未选择参考仓库，本次无源码证据；等待当前宿主提交逐项核对报告。',prepared_records
  assert not any('已读取固定提交源码' in r['detail'] or ('已读取' in r['detail'] and '固定提交' in r['detail']) for r in prepared_records)
  assert any(r['title']=='保存规划失败' and r['state']=='failed' for r in records)
  (BASE/(host+'-history-records.json')).write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
  exported=c.call('export_project',project_id=pid,format='xlsx');xlsx=validate_xlsx(pathlib.Path(exported['path']).read_bytes())
  viewer=c.call('open_dashboard',port=0);parsed=urllib.parse.urlsplit(viewer['url']);base=parsed.scheme+'://'+parsed.netloc;q='?project='+urllib.parse.quote(pid)
  hashes_before=md_hashes(c.ws)
  http_data={}
  for path in ('/','/api/runtime','/api/projects','/planning'+q,'/api/project'+q,'/api/plan'+q,'/api/plan/table'+q,'/api/ledger/info'+q,'/api/ledger'+q,'/api/plan/history'+q,'/api/plan/export'+q):
   with urllib.request.urlopen(base+path,timeout=5) as response:
    raw=response.read();assert response.status==200
    (BASE/(host+'-http-'+str(len(E['http']))+'.body')).write_bytes(raw)
    E['http'].append({'host':host,'path':path,'status':response.status,'length':len(raw),'sha256':digest(raw)})
    if '/api/' in path and '/export' not in path:http_data[path.split('?')[0]]=json.loads(raw)
    if '/export' in path:validate_xlsx(raw)
  assert http_data['/api/runtime']['workspace']==str(c.ws.resolve())
  assert '拒绝空标题' in http_data['/api/plan']['content']
  assert 'F01-01' in json.dumps(http_data['/api/ledger'],ensure_ascii=False)
  assert '搜索图书' in json.dumps(http_data['/api/plan/table'],ensure_ascii=False)
  for path in ('/api/plan/save','/api/projects/create','/api/plan/chat','/api/ledger/save'):
   request=urllib.request.Request(base+path+q,data=b'{}',headers={'Content-Type':'application/json'},method='POST')
   try:urllib.request.urlopen(request,timeout=5);raise AssertionError('Write endpoint accepted')
   except urllib.error.HTTPError as error:
    payload=json.loads(error.read());assert error.code==410 and payload['code']=='host_conversation_required'
    E['http'].append({'host':host,'path':path,'method':'POST','status':error.code,'code':payload['code']})
  assert hashes_before==md_hashes(c.ws),'Read-only HTTP changed Markdown data'
  assert c.call('stop_dashboard')['stopped']
  c.call('create_project',expect_error=True,name='bad',unexpected=True)
  assert c.send('ping')['result']=={}
  E['hosts'][host]={'result':'PASS','project_id':pid,'workspace':str(c.ws),'tool_count':18,'tool_names':names,'full_chain':True,'source_review_history_truthful':True,'chinese_save_failure_title':True,'called_tool_names':sorted({item['tool'] for item in E['calls'] if item['host']==host and item['tool']}),'live_empty_reference_search_and_empty_selection':True,'initial_and_suggestion_previews_not_saved':True,'stale_save_rejected':True,'history_versions':len(history['versions']),'mcp_export':xlsx,'http_markdown_unchanged':True,'http_write_attempts_rejected':4,'viewer_stopped':True}
  if host=='codex':
   current=c.call('read_project',project_id=pid)
   preview=c.call('edit_features',project_id=pid,revision=current['plan']['revision'],additions=[{'key':'N2','parent':'F01-02','功能名称':'筛选作者','说明':'在搜索图书结果中按作者筛选','验收标准':'选择作者后仅展示该作者的图书，清除筛选后恢复搜索结果'}])
   assert preview['saved'] is False and preview['mapping']['N2']=='F01-02-01',preview
   c.call('save_plan',project_id=pid,revision=preview['revision'],content=preview['content'],note='独立浏览器复核夹具：添加搜索图书下的筛选作者子功能')
   prepared=c.call('prepare_source_review',project_id=pid)
   c.call('submit_source_review',project_id=pid,review_id=prepared['review_id'],report={'features':[{'id':f['编号'],'status':'未找到依据','finding':'独立协议与浏览器测试数据，没有选择外部参考仓库，不代表实现验收','evidence':[]} for f in prepared['features']]})
   candidate=c.call('generate_ledger',project_id=pid)
   c.call('save_ledger',project_id=pid,content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
   saved=c.call('read_project',project_id=pid)
   assert '筛选作者' in saved['plan']['content'] and 'F01-02-01' in saved['ledger']['content'],saved
   empty=c.call('create_project',name='待规划空项目-codex-browser')['project']
   (BASE/'browser-fixture.json').write_text(json.dumps({'workspace':str(c.ws),'package':str(c.root),'planned_project_id':pid,'empty_project_id':empty['id'],'planned_project':saved['project'],'empty_project':empty,'child_id':'F01-02-01','child_name':'筛选作者','service_state':'stopped; parent may start for browser validation'},ensure_ascii=False,indent=2)+'\n')
 for host,details in E['hosts'].items():
  assert set(details['tool_names'])==set(details['called_tool_names']),details
 E['result']='PASS'
except Exception as error:
 E['result']='FAIL';E['error']=str(error);raise
finally:
 for client in clients:
  try:
   client.call("stop_dashboard")
   client.close()
  except Exception as close_error:E.setdefault('cleanup_errors',[]).append(str(close_error))
 (BASE/'stdio-all-tools-evidence.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'result':E['result'],'hosts':{h:v['result'] for h,v in E['hosts'].items()},'calls':len(E['calls']),'http_requests':len(E['http']),'evidence':str(BASE/'stdio-all-tools-evidence.json')},ensure_ascii=False,indent=2))
