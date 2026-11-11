"""Read-only checkout review: writes only within TemporaryDirectory; all operations use public MCP call_tool."""
import sys,tempfile,json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from plugin_mcp import call_tool
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
def size(text):return {'chars':len(text),'utf8_bytes':len(text.encode())}
print('initial_plan',json.dumps(size(PLAN)))
with tempfile.TemporaryDirectory(prefix='review-history-') as tmp:
 ws=str(Path(tmp)/'ws')
 p=call_tool('create_project',{'workspace':ws,'name':'测试项目'},'codex')['project']
 def call(a,**kw):return call_tool(a,dict(workspace=ws,project_id=p['id'],**kw),'codex')
 def saveplan(text):return call('save_plan',content=text,revision=call('read_project')['plan']['revision'])
 def savecandidate(c):return call('save_ledger',content=c['content'],revision=c['ledger_revision'],plan_revision=c['plan_revision'],source_revision=c['source_revision'])
 saveplan(PLAN);savecandidate(call('generate_ledger'))
 print('round 0 saved',json.dumps(size(Path(p['ledger_path']).read_text())))
 for n in range(1,9):
  d=call('read_project')['ledger']
  call('update_feature_progress',revision=d['revision'],feature_id='F01',changes={'实现证据':'实现第'+str(n)+'轮'})
  print('round',n,'after_progress',json.dumps(size(Path(p['ledger_path']).read_text())),flush=True)
  saveplan(PLAN.replace('保存后能读取订单','保存后能读取订单第'+str(n)+'版'))
  c=call('generate_ledger')
  print('round',n,'generated_candidate',json.dumps(size(c['content'])),flush=True)
  try:savecandidate(c)
  except ValueError as exc:
   print('round',n,'SAVE_FAILED',type(exc).__name__,str(exc),flush=True)
   print('ledger_still_readable',size(call('read_project')['ledger']['content']))
   break
  print('round',n,'saved',json.dumps(size(Path(p['ledger_path']).read_text())),flush=True)
