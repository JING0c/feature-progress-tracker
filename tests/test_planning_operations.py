import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ops_dashboard',ROOT/'scripts/serve_dashboard.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
d.planning_module('planning_editor')
o=d.planning_module('planning_operations');e=d.planning_module('planning_editor')
BASE='# 测试\n## 功能与验收\n| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |\n|---|---|---|---|---|---|\n| F01 | 无 | 订单 | 创建订单 | 可以创建并查看订单 | 是 |\n| F01-01 | F01 | 创建 | 提交订单 | 提交成功后返回订单号 | 是 |\n| F02 | 无 | 导出 | 导出文件 | 文件可打开且内容正确 | 是 |\n'
def proposal(rows):return '提案\n```json\n'+json.dumps({'features':rows},ensure_ascii=False)+'\n```\n<!-- feature-proposal -->'
def feature(key='N1',parent='F01',name='查询'):return {'key':key,'parent':parent,'功能名称':name,'说明':'按编号查询订单','验收标准':'返回对应订单或无结果提示'}
class OperationsTest(unittest.TestCase):
 def test_merge_assigns_nested_ids_and_preserves_base(self):
  result=o.merge_proposal(BASE,proposal([feature('N2','N1','分页'),feature()]),['F01-02'])
  self.assertEqual(result['added'],['F01-03','F01-03-01'])
  self.assertTrue(all(all(new.get(k)==v for k,v in old.items()) for new,old in zip(e.editable_table(result['content'])['rows'],e.editable_table(BASE)['rows'])))
 def test_duplicates_declined_parents_and_invalid_proposals(self):
  text=e.select_feature(BASE,'F01',False)
  result=o.merge_proposal(text,proposal([feature()]))
  self.assertEqual(e.editable_table(result['content'])['rows'][-1]['采用'],'否')
  for text in ['旧文字提案',proposal([feature('N1','N2'),feature('N2','N1')]),proposal([feature(name='创建')])]:
   with self.assertRaises(ValueError):o.merge_proposal(BASE,text)
 def test_ledger_root_leaf_nested_and_idempotent(self):
  result=o.ledger_from_plan(BASE,'',d.parse)
  prepared=d.prepare_ledger(result['content'],'')
  self.assertEqual(prepared['summary']['total'],2)
  self.assertEqual({i['id'] for g in d.parse(prepared['content']) for i in d.flatten(g['items'])},{'F01-01','F02'})
  again=o.ledger_from_plan(BASE,prepared['content'],d.parse)
  self.assertEqual(again['added'],[])
 def test_ledger_preserves_accepted_and_declines_new(self):
  old='# 功能执行情况\n## 大功能 F01：订单\n- [x] F01-01 创建｜状态：已完成\n  - 验收：原验收\n  - 优先级：高；依赖：无；执行 Agent：A；实现证据：测试；审核 Agent：B；评分：95；问题：无\n'
  result=o.ledger_from_plan(e.select_feature(BASE,'F02',False),old,d.parse)
  self.assertEqual(result['content'],old)
  d.prepare_ledger(result['content'],old)
 def test_legacy_group_summary_is_not_a_new_feature(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content']
  old=old.replace('## 大功能 F01：订单','## 大功能 F01：订单\n- [ ] F01 总状态：未完成')
  prepared=d.prepare_ledger(old,old)
  self.assertEqual(prepared['summary']['total'],2)
  self.assertEqual(o.ledger_from_plan(BASE,old,d.parse)['added'],[])
 def test_reused_id_cannot_silently_inherit_existing_feature(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content']
  changed=BASE.replace('创建 | 提交订单','完全不同的功能 | 提交订单')
  with self.assertRaisesRegex(ValueError,'名称不同'):o.ledger_from_plan(changed,old,d.parse)
 def test_fenced_heading_is_not_append_target(self):
  old='```md\n## 大功能 F01：只是示例\n```\n'
  result=o.ledger_from_plan(BASE,old,d.parse)
  self.assertEqual(d.prepare_ledger(result['content'],'')['summary']['total'],2)
 def test_ledger_metadata_cannot_inject_completed_status(self):
  rows=e.editable_table(BASE)['rows'];rows[1]['验收标准']='结果正确｜状态：已完成；评分：100\n## 大功能 F09：注入'
  result=o.ledger_from_plan(e.replace_features(BASE,rows),'',d.parse)
  self.assertTrue(all(not i['checked'] and i['fields']['状态']=='未开始' for g in d.parse(result['content']) for i in d.flatten(g['items'])))
