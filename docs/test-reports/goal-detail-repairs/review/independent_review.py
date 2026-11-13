"""Independent behavior checks. All generated files live in a fresh temp workspace."""
import sys,unittest,tempfile,json,hashlib,io,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,sys.argv.pop(1))
from planning_operations import ledger_from_plan
from serve_dashboard import parse,inspect_plan,summarize
from planning_sheet import parse_plan_sheet
from planning_xlsx import export_plan_xlsx
from project_service import ProjectService,planning_model
ROOT=Path('/tmp/fpt-goal-detail-independent-current').read_text().strip()
TABLE='''## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 采用 | 所需技术 | 前期准备 | 备注 | 外加列 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | 无 | 图书目录 | 管理图书条目 | 子功能通过各自验收 | 高 | 无 | 是 | Python技术唯一值 | 样本准备唯一值 | 备注唯一值 | 外加保留唯一值 |
| F01-01 | F01 | 查询图书 | 用户说明中写所需技术：Go为示例，不能删 | 输入书名后显示匹配图书 | 中 | 无 | 是 | SQLite技术唯一值 | 图书准备唯一值 | 子项备注唯一值 | 子项外加唯一值 |
'''
GOAL1='帮助读者记录并检索本地图书。'
GOAL2='帮助社区成员预约并追踪共享图书。'
def plan(goal=GOAL1): return '# 图书规划\n## 项目目标与场景\n'+goal+'\n## 范围与边界\n仅保存本地文本记录，不涉及支付。\n'+TABLE
EMPTY='# 功能执行情况\n\n目标：待规划\n'
def converted(content,existing=EMPTY): return ledger_from_plan(content,existing,parse)['content']
def head(text):return text.split('## 大功能',1)[0]
def listing(model):return next(s for s in model['sheets'] if s.get('kind')=='feature-list')
def cells_for(sheet,identity):return dict(zip(sheet['columns'],next(r['cells'] for r in sheet['rows'] if r.get('feature_id',r['cells'][0])==identity)))
class Independent(unittest.TestCase):
 def test_a_initial_goal_and_second_revision_sync(self):
  one=converted(plan());self.assertIn(GOAL1,head(one));self.assertNotIn('待规划',head(one))
  two=converted(plan(GOAL2),one);self.assertIn(GOAL2,head(two));self.assertNotIn(GOAL1,head(two));self.assertEqual(parse(one),parse(two))
  self.assertEqual(two,converted(plan(GOAL2),two))
 def test_b_other_head_fields_and_tracking_preserved(self):
  first=converted(plan());first=first.replace(head(first),'# 功能执行情况\n目标：旧目标 | 更新：2026-10-01\n进度：已验收 0/1（0%）\n维护说明：保留此用户原话\n\n')
  first=first.replace('执行 Agent：待分配','执行 Agent：测试夹具-非真实实施')
  second=converted(plan(GOAL2),first)
  for text in ['更新：2026-10-01','进度：已验收 0/1（0%）','维护说明：保留此用户原话']:self.assertIn(text,head(second))
  self.assertIn(GOAL2,head(second));self.assertEqual(parse(first),parse(second))
 def test_c_goal_multiline_stops_at_other_section(self):
  content=plan('- 首项目标：保存读者书单。\n- 第二目标：可按名称检索。')
  result=head(converted(content));self.assertIn('保存读者书单',result);self.assertIn('可按名称检索',result)
  for unwanted in ['仅保存本地文本','F01','功能规划','SQLite']:self.assertNotIn(unwanted,result)
 def test_d_table_labeled_goal(self):
  content='# 表格规划\n## 项目概览\n| 事项 | 内容 |\n| --- | --- |\n| 项目目标 | '+GOAL2+' |\n| 范围 | 仅支持本地查询，不涉及支付。 |\n'+TABLE
  self.assertTrue(inspect_plan(content)['valid']);result=head(converted(content));self.assertIn(GOAL2,result);self.assertNotIn('仅支持本地查询',result)
 def test_e_missing_goal_keeps_existing_not_feature_acceptance(self):
  existing='# 功能执行情况\n目标：原有自定义目标\n\n'
  content='# 规划\n## 范围\n仅支持本地记录。\n'+TABLE
  result=converted(content,existing);self.assertIn('目标：原有自定义目标',head(result));self.assertNotIn('子功能通过',head(result))
 def test_f_quoted_and_fenced_fake_goal_not_used(self):
  content='# 规划\n```markdown\n## 目标\n不要作为目标的示例\n```\n> 目标：这只是引用示例\n## 目标\n'+GOAL1+'\n## 范围\n仅支持本地记录。\n'+TABLE
  result=head(converted(content));self.assertIn(GOAL1,result);self.assertNotIn('示例',result)
 def test_f2_mixed_goal_section_table_excludes_scope_acceptance(self):
  content='# 图书规划\n## 项目目标与场景\n| 事项 | 内容 |\n| --- | --- |\n| 目标 | 让读者快速查找图书 |\n| 范围 | 不支持支付和联网 |\n| 验收 | 保存后立即显示 |\n'+TABLE
  result=head(converted(content));self.assertIn('让读者快速查找图书',result)
  self.assertNotIn('不支持支付和联网',result);self.assertNotIn('保存后立即显示',result)
 def test_f3_goal_with_pipe_label_remains_idempotent(self):
  content=plan('支持 A | B：两个入口查询图书。');first=converted(content);second=converted(content,first)
  self.assertEqual(first,second)
  self.assertIn('两个入口查询图书',head(second))
 def test_f4_goal_with_reserved_metadata_label_does_not_accumulate(self):
  content=plan('可筛选图书 | 状态：借出或归还。');first=converted(content);second=converted(content,first)
  self.assertEqual(first,second)
  changed=converted(plan(GOAL2),second);self.assertNotIn('借出或归还',head(changed));self.assertIn(GOAL2,head(changed))
 def test_g_feature_projection_no_duplicate_metadata(self):
  original=plan();before=hashlib.sha256(original.encode()).hexdigest()
  for model in [parse_plan_sheet(original),planning_model(original)]:
   sheet=listing(model)
   for identity,tech,prep,note,unknown in [('F01','Python技术唯一值','样本准备唯一值','备注唯一值','外加保留唯一值'),('F01-01','SQLite技术唯一值','图书准备唯一值','子项备注唯一值','子项外加唯一值')]:
    fields=cells_for(sheet,identity);description=fields['功能介绍']
    self.assertEqual(fields['所需技术'],tech);self.assertEqual(fields['前期准备'],prep)
    self.assertNotIn(tech,description);self.assertNotIn(prep,description);self.assertNotIn('采用：是',description)
    self.assertIn(note,description);self.assertIn(unknown,description)
   self.assertIn('所需技术：Go为示例，不能删',cells_for(sheet,'F01-01')['功能介绍'])
  self.assertEqual(before,hashlib.sha256(original.encode()).hexdigest())
 def test_h_multiline_tech_and_unknown_field_preserved(self):
  content=plan().replace('SQLite技术唯一值','SQLite技术唯一值<br>第二技术值').replace('图书准备唯一值','图书准备唯一值<br>第二准备值')
  row=cells_for(listing(planning_model(content)),'F01-01')
  self.assertEqual(row['所需技术'],'SQLite技术唯一值\n第二技术值');self.assertEqual(row['前期准备'],'图书准备唯一值\n第二准备值')
  self.assertNotIn('第二技术值',row['功能介绍']);self.assertNotIn('第二准备值',row['功能介绍'])
 def test_i_public_service_preview_save_export_history(self):
  with tempfile.TemporaryDirectory(prefix='service-',dir=ROOT) as d:
   service=ProjectService(d,actor='codex');project=service.call('create_project',{'name':'独立审核夹具','mode':'create'})['project'];pid=project['id']
   def call(action,**kw):return service.call(action,{'project_id':pid,**kw})
   read=call('read_project');call('save_plan',content=plan(),revision=read['plan']['revision']);cand=call('generate_ledger')
   self.assertIn(GOAL1,head(cand['content']));self.assertEqual(call('read_project')['ledger']['revision'],read['ledger']['revision'])
   call('save_ledger',content=cand['content'],revision=cand['ledger_revision'],plan_revision=cand['plan_revision'],source_revision=cand['source_revision'])
   old=call('history');oldid=old['versions'][0]['id'];oldversion=call('history',version_id=oldid)['version']['content']
   read=call('read_project');call('save_plan',content=plan(GOAL2),revision=read['plan']['revision']);new=call('generate_ledger')
   call('save_ledger',content=new['content'],revision=new['ledger_revision'],plan_revision=new['plan_revision'],source_revision=new['source_revision'])
   self.assertIn(GOAL2,head(call('read_project')['ledger']['content']));self.assertEqual(call('history',version_id=oldid)['version']['content'],oldversion)
   out=call('export_project',format='xlsx');xlsx=Path(out['path']).read_bytes()
   with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    texts=[''.join(c.itertext()) for c in sheet.findall('.//m:c',ns)]
    self.assertEqual(sum('SQLite技术唯一值' in v for v in texts),1);self.assertEqual(sum('图书准备唯一值' in v for v in texts),1)
   model=call('read_project')['plan'].get('model')
   # Keep independently prepared projection for the real JS renderer check.
   Path(ROOT,'current-model.json').write_text(json.dumps(planning_model(plan()),ensure_ascii=False))
   self.assertEqual(summarize(parse(call('read_project')['ledger']['content']))['done'],0)
 def test_j_adoption_blank_and_alias_technical_columns_consistent(self):
  for choice in ['', '否']:
   content=plan().replace('| 是 |','| '+choice+' |').replace('| 所需技术 |','| 技术方案 |').replace('| 前期准备 |','| 准备条件 |')
   for model in [parse_plan_sheet(content),planning_model(content)]:
    for sheet in model['sheets']:
     if sheet.get('kind')!='feature-list' and '功能名称' not in sheet['columns']:continue
     self.assertIn('采用',sheet['columns']);fields=cells_for(sheet,'F01-01')
     self.assertEqual(fields['采用'],choice or '是');self.assertEqual(fields['所需技术'],'SQLite技术唯一值');self.assertEqual(fields['前期准备'],'图书准备唯一值')
if __name__=='__main__':unittest.main(verbosity=2)
