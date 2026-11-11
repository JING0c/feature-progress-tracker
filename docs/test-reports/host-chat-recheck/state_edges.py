"""All mutations are public MCP calls against temporary projects, never checkout."""
import sys,tempfile,json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from plugin_mcp import call_tool
from serve_dashboard import parse,flatten
PLAN='''# 测试项目规划书
## 项目目标与场景
帮助测试员保存订单并查看处理结果。
## 范围与边界
本期仅管理本地订单，不涉及在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |
|---|---|---|---|---|---|
| F01 | 无 | 保存订单 | 输入信息并保存 | 保存后能读取订单 | 是 |
'''
TREE=PLAN.replace('| F01 | 无 | 保存订单 | 输入信息并保存 | 保存后能读取订单 | 是 |',
 '| F01 | 无 | 订单管理 | 管理本地订单 | 可以保存与读取订单 | 是 |\n| F01-01 | F01 | 保存订单 | 保存输入信息 | 保存后可读取 | 是 |')
REVIEW={'reviewer':'reviewer-B','score':95,'conclusion':'通过','evidence':'reports/acceptance.md','reason':'独立核对保存读取结果'}
class Fixture:
 def __init__(self,folder):
  self.ws=str(Path(folder)/'ws');self.p=call_tool('create_project',{'workspace':self.ws,'name':'测试项目'},'codex')['project']
 def call(self,action,**kw):return call_tool(action,dict(workspace=self.ws,project_id=self.p['id'],**kw),'codex')
 def plan(self,text):return self.call('save_plan',content=text,revision=self.call('read_project')['plan']['revision'])
 def ledger(self):
  c=self.call('generate_ledger');return self.call('save_ledger',content=c['content'],revision=c['ledger_revision'],plan_revision=c['plan_revision'],source_revision=c['source_revision'])
 def update(self,changes,review=None):
  kw=dict(feature_id='F01',revision=self.call('read_project')['ledger']['revision'],changes=changes)
  if review is not None:kw['review']=review
  return self.call('update_feature_progress',**kw)
 def item(self):return parse(self.call('read_project')['ledger']['content'])[0]['items'][0]
 def setup(self):
  self.plan(PLAN);self.ledger();self.update({'执行 Agent':'developer-A','实现证据':'commit abc，保存读取正常'})
with tempfile.TemporaryDirectory(prefix='review-stale-plan-') as tmp:
 f=Fixture(tmp);f.setup()
 f.plan(PLAN.replace('| 是 |','| 否 |').replace('保存后能读取订单','保存后须加密订单'))
 result=f.update({'状态':'已完成'},REVIEW);item=f.item()
 print(json.dumps({'case':'completion_against_stale_plan','saved_plan_adopted':False,'saved_plan_acceptance':'保存后须加密订单','actual_ledger_acceptance':item['fields']['验收'],'actual_checked':item['checked'],'actual_summary':result['summary']},ensure_ascii=False))
with tempfile.TemporaryDirectory(prefix='review-review-status-') as tmp:
 f=Fixture(tmp);f.setup();f.update({'状态':'已完成'},REVIEW)
 result=f.update({'状态':'待审核'});item=f.item()
 print(json.dumps({'case':'explicit_review_status','requested':'待审核','actual_status':item['fields']['状态'],'actual_checked':item['checked'],'actual_summary':result['summary']},ensure_ascii=False))
with tempfile.TemporaryDirectory(prefix='review-tree-leaves-') as tmp:
 f=Fixture(tmp);f.plan(TREE);initial=f.ledger()
 # save_plan is the public complete-plan tool. Parent remains adopted while its
 # historical child is excluded; save_plan, generate_ledger and save_ledger all accept it.
 declined=TREE.replace('| F01-01 | F01 | 保存订单 | 保存输入信息 | 保存后可读取 | 是 |','| F01-01 | F01 | 保存订单 | 保存输入信息 | 保存后可读取 | 否 |')
 f.plan(declined);intermediate=f.ledger();f.plan(TREE);restored=f.ledger()
 groups=parse(f.call('read_project')['ledger']['content'])
 print(json.dumps({'case':'readopt_child_after_parent_becomes_leaf','initial_total':initial['summary']['total'],'declined_total':intermediate['summary']['total'],'readopted_total':restored['summary']['total'],'expected_readopted_total':1,'actual_group_roots':[{'id':i['id'],'children':[ch['id'] for ch in i['children']]} for i in groups[0]['items']]},ensure_ascii=False))
