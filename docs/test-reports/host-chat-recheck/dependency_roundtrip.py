"""Independent e8d51ea reproduction. Only mutates a newly created temp workspace."""
from pathlib import Path
import json,sys,tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from plugin_mcp import call_tool
from planning_editor import editable_table
from serve_dashboard import parse,flatten
PLAN='''# 图书项目规划书
## 项目目标
帮助管理员登记并导出本地图书目录。
## 范围边界
本期仅管理本机图书，不提供在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 依赖 | 采用 |
|---|---|---|---|---|---|---|
| F01 | 无 | 图书管理 | 维护本地图书目录 | 可登记并找到图书 | 无 | 是 |
| F01-01 | F01 | 登记图书 | 输入名称保存图书 | 保存后列表可见图书 | 无 | 是 |
| F02 | 无 | 导出图书 | 下载图书清单 | 文件能打开并包含图书 | F01-01 | 是 |
'''
workspace=str(Path(tempfile.mkdtemp(prefix='review-dependency-'))/'workspace')
project=call_tool('create_project',{'workspace':workspace,'name':'独立核对临时图书项目'},'codex')['project']
def call(action,**payload):
    return call_tool(action,{'workspace':workspace,'project_id':project['id'],**payload},'codex')
r=call('read_project')['plan']['revision']
call('save_plan',content=PLAN,revision=r)
r=call('read_project')['plan']['revision']
addition={'key':'N1','parent':'F01','功能名称':'备份图书','说明':'生成图书备份','验收标准':'备份能完整还原所有图书'}
# Known next F number is rejected before additions are processed.
try:
    call('edit_features',revision=r,updates=[{'id':'F02','fields':{'依赖':'F01-02'}}],additions=[addition])
except Exception as exc:
    print('EXPLICIT_F_DEPENDENCY:',type(exc).__name__,str(exc))
preview=call('edit_features',revision=r,updates=[{'id':'F02','fields':{'依赖':'N1'}}],additions=[addition])
print('PREVIEW:',json.dumps({'mapping':preview['mapping'],'F02依赖':next(r['依赖'] for r in editable_table(preview['content'])['rows'] if r['编号']=='F02')},ensure_ascii=False))
call('save_plan',content=preview['content'],revision=preview['revision'])
candidate=call('generate_ledger')
saved=call('save_ledger',content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
ledger=call('read_project')['ledger']['content']
item=next(i for g in parse(ledger) for i in flatten(g['items']) if i['id']=='F02')
print('FINAL_LEDGER:',json.dumps({'saved':saved['saved'],'F02依赖':item['fields']['依赖'],'expected':'F01-02'},ensure_ascii=False))
assert saved['saved'] and item['fields']['依赖']=='N1'
print('TEMP_WORKSPACE:',workspace)
