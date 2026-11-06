import copy
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
  plan=e.select_feature(BASE,'F02',False)
  old=o.ledger_from_plan(plan,'',d.parse)['content'].replace('- [ ] F01-01','- [x] F01-01').replace('状态：未开始','状态：已完成').replace('审核 Agent：待审核','审核 Agent：B').replace('评分：待审核','评分：95')
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

 def test_existing_requirements_and_metadata_are_updated_without_losing_execution(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content'].replace('执行 Agent：待分配','执行 Agent：A').replace('实现证据：无','实现证据：已有提交abc')
  rows=e.editable_table(BASE)['rows'];rows[1].update({'验收标准':'失败显示原因并允许重试','说明':'提交并反馈异常','优先级':'高','依赖':'F02','所需技术':'本地接口','前期准备':'准备异常数据','备注':'仅本地'})
  result=o.ledger_from_plan(e.replace_features(BASE,rows),old,d.parse)
  item={i['id']:i for g in d.parse(result['content']) for i in d.flatten(g['items'])}['F01-01']
  self.assertEqual(item['fields']['验收'],'失败显示原因并允许重试')
  self.assertEqual(item['fields']['说明'],'提交并反馈异常')
  self.assertEqual(item['fields']['优先级'],'高')
  self.assertEqual(item['fields']['依赖'],'F02')
  self.assertEqual(item['fields']['所需技术'],'本地接口')
  self.assertEqual(item['fields']['前期准备'],'准备异常数据')
  self.assertEqual(item['fields']['备注'],'仅本地')
  self.assertEqual(item['fields']['执行 Agent'],'A')
  self.assertEqual(item['fields']['实现证据'],'已有提交abc')
  self.assertEqual(item['fields']['状态'],'未开始')
  self.assertFalse(item['checked'])
  self.assertEqual(o.ledger_from_plan(e.replace_features(BASE,rows),result['content'],d.parse)['content'],result['content'])
 def test_changed_acceptance_reopens_completed_preserving_exact_audit_history(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content'].replace('- [ ] F01-01','- [x] F01-01').replace('状态：未开始','状态：已完成',1).replace('审核 Agent：待审核','审核 Agent：B',1).replace('评分：待审核','评分：95',1).replace('实现证据：无','实现证据：提交abc;测试通过',1)
  old=old.replace('  - 问题：无','  - 问题：无\n  - 审核结论：原标准通过\n  - 自定义：保留信息\n  - 备注性原文',1)
  before=d.parse(old)[0]['items'][0]
  rows=e.editable_table(BASE)['rows'];rows[1]['验收标准']='失败必须显示原因'
  result=o.ledger_from_plan(e.replace_features(BASE,rows),old,d.parse)
  after=d.parse(result['content'])[0]['items'][0]
  self.assertEqual(after['fields']['验收'],'失败必须显示原因')
  self.assertFalse(after['checked'])
  self.assertEqual(after['fields']['状态'],'进行中')
  self.assertEqual(after['fields']['审核 Agent'],'待审核')
  self.assertEqual(after['fields']['评分'],'待审核')
  self.assertEqual(after['fields']['实现证据'],'提交abc;测试通过')
  self.assertEqual(after['notes'],before['notes'])
  self.assertEqual(after['fields']['自定义'],'保留信息')
  history=json.loads(after['fields']['规划同步历史'])
  self.assertEqual(history[-1]['fields'],before['fields'])
  self.assertEqual(history[-1]['notes'],before['notes'])
  self.assertTrue(history[-1]['checked'])
  self.assertTrue(o.valid_ledger_transition(before,after))
  for key,value in [('实现证据','伪造证据'),('评分','100'),('规划同步历史','[]')]:
   forged=copy.deepcopy(after);forged['fields'][key]=value
   self.assertFalse(o.valid_ledger_transition(before,forged),key)
 def test_metadata_only_change_keeps_completion_and_second_conversion_is_identical(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content'].replace('- [ ] F01-01','- [x] F01-01').replace('状态：未开始','状态：已完成',1).replace('审核 Agent：待审核','审核 Agent：B',1).replace('评分：待审核','评分：95',1)
  rows=e.editable_table(BASE)['rows'];rows[1].update({'优先级':'低','备注':'下季度安排'})
  text=e.replace_features(BASE,rows);result=o.ledger_from_plan(text,old,d.parse)
  before=d.parse(old)[0]['items'][0];after=d.parse(result['content'])[0]['items'][0]
  self.assertEqual(after['fields']['优先级'],'低')
  self.assertEqual(after['fields']['备注'],'下季度安排')
  self.assertTrue(after['checked']);self.assertEqual(after['fields']['状态'],'已完成')
  self.assertEqual(after['fields']['评分'],'95')
  self.assertTrue(o.valid_ledger_transition(before,after))
  self.assertEqual(o.ledger_from_plan(text,result['content'],d.parse)['content'],result['content'])
 def test_pending_review_reopens_and_blocked_state_is_preserved(self):
  for status,want in [('待审核','进行中'),('受阻','受阻')]:
   old=o.ledger_from_plan(BASE,'',d.parse)['content'].replace('状态：未开始','状态：'+status,1)
   rows=e.editable_table(BASE)['rows'];rows[1]['说明']='变更后的提交方式'
   after=d.parse(o.ledger_from_plan(e.replace_features(BASE,rows),old,d.parse)['content'])[0]['items'][0]
   self.assertEqual(after['fields']['状态'],want)
   self.assertEqual(after['fields']['说明'],'变更后的提交方式')
 def test_changed_child_reopens_completed_ancestor_without_losing_structure(self):
  plan=o.merge_proposal(BASE,proposal([feature('N1','F01-01','确认结果')]))['content']
  old=o.ledger_from_plan(plan,'',d.parse)['content'].replace('- [ ]','- [x]').replace('状态：未开始','状态：已完成').replace('审核 Agent：待审核','审核 Agent：B').replace('评分：待审核','评分：95')
  rows=e.editable_table(plan)['rows'];next(r for r in rows if r['编号']=='F01-01-01')['验收标准']='失败展示具体原因'
  result=o.ledger_from_plan(e.replace_features(plan,rows),old,d.parse)
  before=d.parse(old)[0]['items'][0];after=d.parse(result['content'])[0]['items'][0]
  self.assertFalse(after['checked']);self.assertEqual(after['fields']['状态'],'进行中')
  self.assertEqual(after['children'][0]['id'],'F01-01-01')
  self.assertFalse(after['children'][0]['checked'])
  self.assertEqual(after['children'][0]['fields']['验收'],'失败展示具体原因')
  self.assertTrue(o.valid_ledger_transition(before,after))
  history=json.loads(after['fields']['规划同步历史'])
  self.assertEqual(history[-1]['children'][0]['id'],'F01-01-01')
  self.assertEqual(history[-1]['children'][0]['fields']['验收'],'返回对应订单或无结果提示')
  forged=copy.deepcopy(after);forged['children']=[]
  self.assertFalse(o.valid_ledger_transition(before,forged))
 def test_sync_keeps_non_feature_examples_and_prose_untouched(self):
  suffix='\n## 大功能 说明文字\n- [ ] F01-01 示例｜状态：未开始\n  - 验收：示例文字\n'
  old=o.ledger_from_plan(BASE,'',d.parse)['content']+suffix
  rows=e.editable_table(BASE)['rows'];rows[1]['验收标准']='返回编号并显示结果'
  result=o.ledger_from_plan(e.replace_features(BASE,rows),old,d.parse)['content']
  self.assertTrue(result.endswith(suffix))
 def test_multiple_changes_preserve_history_and_json_separators(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content'].replace('实现证据：无','实现证据：提交abc;测试通过',1).replace('  - 问题：无','  - 问题：无\n  - 原注释 | 原注释；继续',1)
  rows=e.editable_table(BASE)['rows'];rows[1]['验收标准']='第一次新验收'
  first=o.ledger_from_plan(e.replace_features(BASE,rows),old,d.parse)['content']
  rows[1]['验收标准']='第二次新验收'
  second=o.ledger_from_plan(e.replace_features(BASE,rows),first,d.parse)['content']
  before=d.parse(old)[0]['items'][0];middle=d.parse(first)[0]['items'][0];after=d.parse(second)[0]['items'][0]
  history=json.loads(after['fields']['规划同步历史'])
  self.assertEqual(len(history),2)
  self.assertEqual(history[0]['fields'],before['fields'])
  self.assertEqual(history[0]['notes'],['原注释 | 原注释；继续'])
  self.assertEqual(history[1]['fields']['验收'],'第一次新验收')
  self.assertNotIn('规划同步历史',history[1]['fields'])
  self.assertTrue(o.valid_ledger_transition(middle,after))
  forged=copy.deepcopy(after);forged['fields']['规划同步历史']=json.dumps(history[1:],ensure_ascii=False)
  self.assertFalse(o.valid_ledger_transition(middle,forged))
 def test_reopened_history_stays_protected_on_later_submissions(self):
  old=o.ledger_from_plan(BASE,'',d.parse)['content'].replace('- [ ] F01-01','- [x] F01-01').replace('状态：未开始','状态：已完成',1).replace('审核 Agent：待审核','审核 Agent：B',1).replace('评分：待审核','评分：95',1).replace('实现证据：无','实现证据：提交abc',1)
  rows=e.editable_table(BASE)['rows'];rows[1]['验收标准']='失败必须显示原因'
  reopened=o.ledger_from_plan(e.replace_features(BASE,rows),old,d.parse)['content']
  d.prepare_ledger(reopened,old)
  history_line=next(line for line in reopened.splitlines() if '规划同步历史：' in line)
  for changed in (reopened.replace(history_line+'\n',''),reopened.replace('"评分":"95"','"评分":"100"'),reopened.replace('实现证据：提交abc','实现证据：伪造证据')):
   with self.subTest(changed=changed):
    with self.assertRaises(d.RequestError):d.prepare_ledger(changed,reopened)
  rows[1]['验收标准']='再次变更验收'
  again=o.ledger_from_plan(e.replace_features(BASE,rows),reopened,d.parse)['content']
  self.assertEqual(d.prepare_ledger(again,reopened)['summary']['done'],0)
