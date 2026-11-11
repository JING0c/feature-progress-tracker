"""Independent R1/R2 review: public MCP mutations of isolated temp projects.
Synthetic review fields test storage/gates, not actual model/browser acceptance.
Optional --scripts selects another read-only source checkout for replay.
"""
import argparse, copy, json, sys, tempfile
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--scripts', default=str(Path(__file__).resolve().parents[3] / 'scripts')); p.add_argument('--rounds', type=int, default=24)
a=p.parse_args(); sys.path.insert(0, a.scripts)
from plugin_mcp import call_tool
from planning_operations import history_text
from planning_editor import editable_table, replace_features
from serve_dashboard import parse, flatten, RequestError
ROOT=Path(tempfile.mkdtemp(prefix='independent-history-acceptance-'))
PLAN='''# 订单规划书
## 项目目标
帮助测试员保存和查询本地订单。
## 范围与边界
仅测试本地订单，不处理支付或远程数据。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 | 优先级 | 依赖 | 所需技术 | 前期准备 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| F01 | 无 | 订单管理 | 管理订单 | 可保存和查询订单 | 是 | 中 | 无 | Python | 本地文件 | |
| F01-01 | F01 | 保存流程 | 完成保存流程 | 流程有结果 | 是 | 中 | 无 | Python | 本地文件 | |
| F01-01-01 | F01-01 | 保存订单 | 保存本地订单 | 保存后可读取 | 是 | 中 | 无 | Python | 本地文件 | |
| F02 | 无 | 导出订单 | 导出本地文件 | 文件可以打开 | 是 | 中 | 无 | Python | 本地文件 | |
'''
REVIEW={'reviewer':'fixture-reviewer-B','score':95,'conclusion':'通过','evidence':'synthetic-fixture-only','reason':'fixture gate validation only'}
HISTORY={'规划同步历史','进度更新历史'}
RESULTS=[]
def items(text): return {i['id']:i for g in parse(text) for i in flatten(g['items'])}
def clean(snapshot):
 assert not HISTORY.intersection(snapshot['fields']), snapshot['id']
 for child in snapshot.get('children',[]): clean(child)
class F:
 def __init__(self,name,plan=PLAN):
  self.ws=str(ROOT/name); self.p=call_tool('create_project',{'workspace':self.ws,'name':name},'codex')['project']; self.plan(plan); self.sync()
 def call(self,name,**kw): return call_tool(name,{'workspace':self.ws,'project_id':self.p['id'],**kw},'codex')
 def read(self): return self.call('read_project')
 def plan(self,text): return self.call('save_plan',content=text,revision=self.read()['plan']['revision'])
 def change(self,identity='F01-01-01',**fields):
  text=self.read()['plan']['content']; rows=editable_table(text)['rows']; next(r for r in rows if r['编号']==identity).update(fields); return self.plan(replace_features(text,rows))
 def sync(self):
  c=self.call('generate_ledger'); return self.call('save_ledger',content=c['content'],revision=c['ledger_revision'],plan_revision=c['plan_revision'],source_revision=c['source_revision'])
 def update(self,identity='F01-01-01',changes=None,review=None):
  kw={'feature_id':identity,'revision':self.read()['ledger']['revision'],'changes':changes or {'状态':'进行中'}}
  if review is not None: kw['review']=review
  return self.call('update_feature_progress',**kw)
 def implement(self,identity='F01-01-01',n=0):return self.update(identity,{'执行 Agent':'fixture-developer-A','实现证据':f'synthetic-commit-{n}'})
 def complete(self,identity='F01-01-01'):return self.update(identity,{'状态':'已完成'},REVIEW)
 def ledger(self):return Path(self.p['ledger_path'])
 def assert_reject(self,fn,contains=None):
  old=self.ledger().read_bytes()
  try:fn()
  except (ValueError,RequestError) as exc:
   assert self.ledger().read_bytes()==old,'rejected call wrote ledger'
   if contains:assert contains in str(exc),(contains,str(exc))
   return {'error':str(exc),'code':getattr(exc,'code',400),'ledger_unchanged':True}
  raise AssertionError('operation unexpectedly succeeded')
 def current(self):return items(self.ledger().read_text())
def record(case, fn):
 try: RESULTS.append({'case':case,'result':fn(),'passed':True})
 except Exception as exc: RESULTS.append({'case':case,'passed':False,'error':repr(exc)}); print(json.dumps(RESULTS[-1],ensure_ascii=False),flush=True)

def rounds():
 f=F('repeated'); sizes=[f.ledger().stat().st_size]
 for n in range(1,a.rounds+1):
  f.implement(n=n); f.complete(); f.implement('F01-01',n); f.complete('F01-01')
  before=f.current(); f.change(验收标准=f'保存后可读取版本{n:02d}'); f.sync(); now=f.current()
  assert not now['F01-01']['checked'] and not now['F01-01-01']['checked']
  assert now['F01-01']['fields']['审核 Agent']=='待审核'
  for identity in ('F01-01','F01-01-01'):
   oldarchive=json.loads(now[identity]['fields']['规划同步历史'])[-1]
   assert oldarchive['fields']['审核证据']=='synthetic-fixture-only'
   assert oldarchive['fields']['实现证据']==f'synthetic-commit-{n}'
   for s in json.loads(now[identity]['fields']['规划同步历史']):clean(s)
   for e in json.loads(now[identity]['fields']['进度更新历史']):clean(e['before'])
  sizes.append(f.ledger().stat().st_size)
 assert f.sync()['revision']==f.read()['ledger']['revision']
 increments=[b-a for a,b in zip(sizes,sizes[1:])]
 assert max(increments[1:])<min(increments[1:])*1.1, increments
 return {'rounds':a.rounds,'bytes':sizes,'increments':increments,'last_summary':f.sync()['summary']}
record('24_rounds_parent_child_review_requirement_history',rounds)

def legacy():
 f=F('legacy'); f.implement(); f.complete(); base=f.current()['F01-01-01']
 legacy_plan=[copy.deepcopy(base)]; legacy_plan[0]['fields']['审核证据']='legacy-only reviewer evidence | ; preserved'
 legacy_progress=[{'actor':'legacy-fixture-host','reason':'legacy nested history','before':copy.deepcopy(base)}]
 legacy_progress[0]['before']['fields']['规划同步历史']=history_text(legacy_plan)
 # Seed only an isolated legacy fixture on disk. Subsequent actual operations all use MCP.
 text=f.ledger().read_text(); block='  - 规划同步历史：'+history_text(legacy_plan)+'\n'+'  - 进度更新历史：'+history_text(legacy_progress)+'\n'
 target='    - 验收：保存后可读取\n'; assert target in text
 # Replace pre-existing progress field for this item using parser-aware record editing.
 from planning_operations import replace_item_records
 modified=copy.deepcopy(base); modified['fields']['规划同步历史']=history_text(legacy_plan); modified['fields']['进度更新历史']=history_text(legacy_progress)
 f.ledger().write_text(replace_item_records(text,{'F01-01-01':modified}))
 for n in range(1,13):
  f.implement(n=n); f.change(验收标准=f'旧数据升级后的验收{n:02d}'); f.sync()
  current=f.current()['F01-01-01']; ph=json.loads(current['fields']['规划同步历史']); uh=json.loads(current['fields']['进度更新历史'])
  assert ph[0]==legacy_plan[0] and uh[0]==legacy_progress[0]
  for s in ph[1:]:clean(s)
  for e in uh[1:]:clean(e['before'])
 return {'rounds':12,'legacy_plan_exact':True,'legacy_progress_exact':True,'legacy_evidence':json.loads(f.current()['F01-01-01']['fields']['规划同步历史'])[0]['fields']['审核证据'],'bytes':f.ledger().stat().st_size}
record('legacy_nested_archives_preserved_after_12_saves',legacy)

def requirements():
 out=[]
 for key,new in [('验收标准','保存必须加密'),('说明','需要保留完整输入'),('依赖','F02'),('所需技术','SQLite'),('前期准备','建立数据库')]:
  f=F('requirement-'+key); f.implement(); f.change(**{key:new}); out.append({'field':key,**f.assert_reject(f.complete,'同步')}); f.sync(); assert f.complete()['summary']['done']==1
 return out
record('all_material_requirement_fields_block_stale_completion',requirements)

def metadata():
 f=F('metadata'); f.implement(); f.change(备注='仅备注补充',优先级='高'); f.change('F02',验收标准='文件可以打开并含日期'); r=f.complete(); assert r['summary']['done']==1
 return {'unrelated_and_metadata_change_allows_target_completion':True}
record('nonmaterial_metadata_unrelated_branch_allow_completion',metadata)

def adoption():
 f=F('adoption'); f.implement(); f.complete(); f.implement('F01-01'); f.complete('F01-01')
 accepted=f.current(); checks=[]
 for cycle in range(3):
  f.change(采用='否'); checks.append(f.assert_reject(f.complete,'同步')); f.sync(); assert not f.current()['F01-01']['checked']
  f.change(采用='是'); checks.append(f.assert_reject(f.complete,'同步')); f.sync(); now=f.current()
  assert not now['F01-01-01']['checked'] and now['F01-01-01']['fields']['审核 Agent']=='待审核'
  checks.append(f.assert_reject(lambda:f.complete('F01-01'),'子功能'))
  f.complete(); f.complete('F01-01')
 return {'cycles':3,'rejections':checks,'current_summary':f.sync()['summary']}
record('adoption_restore_revokes_parent_child_approval',adoption)

def parent_restore():
 f=F('parent-restore'); f.implement(); f.complete(); f.implement('F01-01'); f.complete('F01-01')
 f.change(采用='否'); f.change('F01-01',采用='否'); f.sync()
 # Parent off through full plan must also have child off. Re-adoption both then sync.
 text=f.read()['plan']['content']; rows=editable_table(text)['rows'];
 for row in rows:
  if row['编号'].startswith('F01-01'):row['采用']='是'
 f.plan(replace_features(text,rows)); f.sync()
 now=f.current(); assert not now['F01-01']['checked'] and not now['F01-01-01']['checked']
 assert all(now[x]['fields']['审核 Agent']=='待审核' for x in ('F01-01','F01-01-01'))
 f.complete(); f.complete('F01-01')
 f.update('F01-01',{'状态':'已取消'}); f.change(验收标准='父项取消期间新增加密要求'); rej=f.assert_reject(lambda:f.complete('F01-01'),'同步')
 f.sync(); assert not f.current()['F01-01-01']['checked']; f.update('F01-01',{'状态':'进行中'}); f.complete(); f.complete('F01-01')
 return {'cancelled_requirement_rejected':rej,'summary':f.sync()['summary']}
record('parent_scope_restore_and_manual_cancel_requirement_change',parent_restore)

def child_addition():
 f=F('child-addition'); f.implement(); f.complete(); f.implement('F01-01'); f.complete('F01-01')
 text=f.read()['plan']['content']; rows=editable_table(text)['rows']; row=copy.deepcopy(rows[2]);row.update({'编号':'F01-01-02','功能名称':'校验订单','说明':'检查输入','验收标准':'缺少名称提示'}); rows.append(row); f.plan(replace_features(text,rows))
 rejected=f.assert_reject(lambda:f.complete('F01-01'),'同步'); sync_rej=f.assert_reject(f.sync)
 return {'completion_rejected':rejected,'accepted_topology_sync_rejected':sync_rej}
record('accepted_parent_new_child_rejects_stale_review',child_addition)

report={'root':str(ROOT),'source':a.scripts,'cases':RESULTS}; (ROOT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2)); print('REPORT='+str(ROOT/'report.json'));sys.exit(1 if any(not r['passed'] for r in RESULTS) else 0)
