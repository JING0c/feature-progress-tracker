#!/usr/bin/env python3
"""Repair integration through actual ZIP stdio and HTTP; fixture analysis is not a model run."""
import hashlib, io, json, os, pathlib, select, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request, zipfile
BASE=pathlib.Path(__file__).resolve().parent
ROOT=pathlib.Path('/Users/olcgb/code/protuct_plan')
E={'reviewer':'/root','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'artifacts':{},'hosts':{},'calls':[],'http':[],'limitations':['No real Claude CLI installation/upgrade/session','No real model or natural-language host conversation','No GitHub/network/source-review rerun; these two repairs concern local conversion','No browser visual QA']}
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
PLAN='''# 阅读清单规划书
## 项目目标与场景
让读者保存本地图书清单。
## 范围与边界
本期管理本地图书；此为隔离测试，不选外部参考。
## 功能规划与验收
| 采用 | 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 所需技术 | 前期准备 | 备注 | 责任组 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 是 | F01 | 无 | 图书管理 | 维护本地图书 | 可保存并查到图书 | 高 | 无 | Python | 测试书目 | 根模块备注 | 阅读组 |
| 是 | F01-01 | F01 | 添加图书 | 录入标题并保存记录 | 保存后重启能读取新记录 | 高 | 无 | SQLite | 三本测试书目 | 手工备注保留 | 阅读组 |
'''
GOAL1='让读者保存本地图书清单。'
GOAL2='帮助读者按标题和作者快速查找已保存的图书。'
clients=[]
try:
 for host in ('codex','claude'):
  archive=ROOT/'dist'/('feature-progress-tracker-'+host+'.zip')
  with zipfile.ZipFile(archive) as z:z.extractall(BASE/host)
  inventory=json.loads((BASE/host/'package-inventory.json').read_text())
  actual=files(BASE/host)
  assert {k:v for k,v in actual.items() if k!='package-inventory.json'}==inventory['files_sha256']
  for name in actual:
   if name.startswith('runtime/scripts/'):
    assert (ROOT/'scripts'/pathlib.Path(name).name).read_bytes()==(BASE/host/name).read_bytes()
  E['artifacts'][host]={'sha256':digest(archive.read_bytes()),'source_bytes_match':True,'inventory_matches':True}
  c=Client(host);clients.append(c)
  project=c.call('create_project',name='目标与详情复验-'+host)['project'];pid=project['id']
  def call(name,**args):return c.call(name,project_id=pid,**args)
  initial=call('read_project')
  call('save_plan',content=PLAN,revision=initial['plan']['revision'])
  first=call('generate_ledger');assert '目标：'+GOAL1 in first['content'],first['content']
  assert call('read_project')['ledger']['content']==initial['ledger']['content'],'preview wrote ledger'
  call('save_ledger',content=first['content'],revision=first['ledger_revision'],plan_revision=first['plan_revision'],source_revision=first['source_revision'])
  now=call('read_project')
  old_history=call('history');old_version=old_history['versions'][-1]['id']
  old_snapshot=call('history',version_id=old_version)['version']
  preview=call('edit_features',revision=now['plan']['revision'],additions=[{'key':'N1','parent':'F01','功能名称':'搜索图书','说明':'按标题搜索已保存的图书。','验收标准':'结果匹配标题关键词。','所需技术':'SQLite','前期准备':'含不同书名的数据'},{'key':'N2','parent':'N1','功能名称':'筛选作者','说明':'在搜索结果中按作者筛选。','验收标准':'仅显示选中作者的书籍。'}])
  assert call('read_project')['plan']['content']==now['plan']['content']
  call('save_plan',content=preview['content'].replace(GOAL1,GOAL2),revision=preview['revision'])
  now=call('read_project')
  advice=call('record_suggestions',revision=now['plan']['revision'],analyst='本轮代码集成测试夹具，非模型建议',suggestions=[{'title':'拒绝空标题','reason':'验证采纳后验收同步','changes':[{'action':'update','id':'F01-01','fields':{'验收标准':'拒绝空标题，保存后重启能读取新记录'}}]}])
  adopted=call('preview_suggestions',revision=now['plan']['revision'],suggestion_id=advice['id'],selected=[advice['suggestions'][0]['id']])
  assert call('read_project')['plan']['content']==now['plan']['content']
  call('save_plan',content=adopted['content'],revision=adopted['revision'])
  candidate=call('generate_ledger');assert '目标：'+GOAL2 in candidate['content'] and GOAL1 not in candidate['content']
  assert GOAL1 in call('read_project')['ledger']['content'],'unsaved goal overwrote ledger'
  call('save_ledger',content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
  saved=call('read_project');assert '目标：'+GOAL2 in saved['ledger']['content'] and '待规划' not in saved['ledger']['content']
  assert '拒绝空标题' in saved['ledger']['content'] and 'F01-02-01' in saved['ledger']['content']
  assert old_snapshot['content']==call('history',version_id=old_version)['version']['content']
  exported=call('export_project',format='xlsx')
  book=pathlib.Path(exported['path']).read_bytes();validate_xlsx(book)
  (BASE/(host+'-export.xlsx')).write_bytes(book)
  viewer=c.call('open_dashboard',port=0);url=urllib.parse.urlsplit(viewer['url']);base=url.scheme+'://'+url.netloc;q='?project='+pid
  before=md_hashes(c.ws)
  for path in ('/api/plan/table','/api/plan','/api/ledger/info','/api/ledger'):
   with urllib.request.urlopen(base+path+q,timeout=5) as r:data=json.loads(r.read())
   (BASE/(host+'-'+path.rsplit('/',1)[-1]+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
   E['http'].append({'host':host,'path':path,'status':200})
   if path=='/api/plan/table':
    model=data;listing=next(s for s in model['sheets'] if s.get('kind')=='feature-list')
    row=next(r for r in listing['rows'] if r.get('feature_id')=='F01-01');col=listing['columns']
    assert col.count('采用')==1 and col.count('所需技术')==1 and col.count('前期准备')==1,col
    intro=row['cells'][col.index('功能介绍')]
    assert '所需技术：' not in intro and '前期准备：' not in intro and '采用：' not in intro,intro
    assert '手工备注保留' in intro and '阅读组' in intro,intro
    assert row['cells'][col.index('所需技术')]=='SQLite'
    assert row['cells'][col.index('前期准备')]=='三本测试书目'
  assert before==md_hashes(c.ws),'view mutated project'
  with zipfile.ZipFile(io.BytesIO(book)) as z:
   import xml.etree.ElementTree as ET
   ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
   sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'));rows=[[ ''.join(cell.itertext()) for cell in r] for r in sheet.findall('s:sheetData/s:row',ns)]
   assert rows[0].count('采用')==1 and rows[0].count('所需技术')==1,rows[0]
   feature=next(r for r in rows[1:] if any('F01-01' in v for v in r))
   assert feature[rows[0].index('所需技术')]=='SQLite'
   assert feature[rows[0].index('前期准备')]=='三本测试书目'
   assert '所需技术：' not in feature[rows[0].index('功能介绍')]
  E['hosts'][host]={'result':'PASS','workspace':str(c.ws),'package':str(c.root),'project_id':pid,'project':project,'goal_first':GOAL1,'goal_final':GOAL2,'initial_preview_not_saved':True,'goal_preview_not_saved':True,'old_snapshot_unchanged':True,'details_and_xlsx_structured_once':True,'summary':saved['project'].get('summary'),'fixture_analysis_not_model':True}
  for n in ('项目规划书.md','功能执行情况.md'):shutil.copy2(pathlib.Path(project['directory'])/n,BASE/(host+'-'+n))
  assert c.call('stop_dashboard')['stopped']
 E['result']='PASS'
except Exception as error:
 E['result']='FAIL';E['error']=str(error);raise
finally:
 for c in clients:
  try:c.call('stop_dashboard');c.close()
  except Exception as error:E.setdefault('cleanup_errors',[]).append(str(error))
 (BASE/'integration-evidence.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'result':E['result'],'tools_calls':sum(c['method']=='tools/call' for c in E['calls']),'http':len(E['http']),'fixtures':E['hosts']},ensure_ascii=False,indent=2))
