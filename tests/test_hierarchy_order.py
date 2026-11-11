"""Ledger hierarchy must survive preserved records appearing before their parent."""
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from plugin_mcp import call_tool
from serve_dashboard import flatten, parse, summarize


TREE_PLAN = '''# 订单项目规划书
## 项目目标与场景
帮助测试员保存订单并查看处理结果。
## 范围与边界
本期仅管理本地订单，不涉及在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |
|---|---|---|---|---|---|
| F01 | 无 | 订单管理 | 管理本地订单 | 可以保存与读取订单 | 是 |
| F01-01 | F01 | 保存订单 | 保存输入信息 | 保存后可读取 | 是 |
'''


class HierarchyOrderTests(unittest.TestCase):
    def test_child_before_parent_keeps_fields_notes_and_one_active_leaf(self):
        groups = parse('''## 大功能 F01：订单
- [ ] F01-01 保存订单｜状态：进行中
  - 验收：保存后可读取；失败时可重试
  - 子项补充说明
- [ ] F01 订单管理｜状态：未开始
  - 验收：可以保存与读取订单
  - 父项补充说明
''')
        self.assertEqual([item['id'] for item in groups[0]['items']], ['F01'])
        parent = groups[0]['items'][0]
        self.assertEqual(parent['fields']['验收'], '可以保存与读取订单')
        self.assertEqual(parent['notes'], ['父项补充说明'])
        self.assertEqual([child['id'] for child in parent['children']], ['F01-01'])
        child = parent['children'][0]
        self.assertEqual(child['fields']['验收'], '保存后可读取；失败时可重试')
        self.assertEqual(child['notes'], ['子项补充说明'])
        self.assertEqual(summarize(groups)['total'], 1)
        self.assertEqual(summarize(groups)['working'], 1)

    def test_deep_hierarchy_has_the_same_parents_for_every_record_order(self):
        identities = ('F01', 'F01-01', 'F01-01-01', 'F01-01-01-01', 'F01-02')
        expected = {'F01': None, 'F01-01': 'F01', 'F01-01-01': 'F01-01',
                    'F01-01-01-01': 'F01-01-01', 'F01-02': 'F01'}
        for order in itertools.permutations(identities):
            with self.subTest(order=order):
                groups = parse('## 大功能 F01：订单\n' + ''.join(
                    f'- [ ] {identity} 功能 {identity}｜状态：未开始\n' for identity in order))
                actual = {item['id']: None for item in groups[0]['items']}
                for item in flatten(groups[0]['items']):
                    actual.update({child['id']: item['id'] for child in item['children']})
                self.assertEqual(actual, expected)
                self.assertEqual(summarize(groups)['total'], 2)

    def test_multiple_roots_and_siblings_retain_their_source_order(self):
        groups = parse('''## 大功能 F01：混合旧记录
- [ ] F02-02 第二根的第二子项
- [ ] F01-02 第一根的第二子项
- [ ] F02 第二根
- [ ] F01-01 第一根的第一子项
- [ ] F01 第一根
- [ ] F02-01 第二根的第一子项
''')
        self.assertEqual([item['id'] for item in groups[0]['items']], ['F02', 'F01'])
        self.assertEqual([item['id'] for item in groups[0]['items'][0]['children']], ['F02-02', 'F02-01'])
        self.assertEqual([item['id'] for item in groups[0]['items'][1]['children']], ['F01-02', 'F01-01'])
        self.assertEqual(summarize(groups)['total'], 4)

    def test_missing_direct_parent_does_not_attach_to_a_distant_ancestor(self):
        groups = parse('''## 大功能 F01：订单
- [ ] F01-01-01 未找到直接父项
- [ ] F01 仍是独立根项
''')
        self.assertEqual([item['id'] for item in groups[0]['items']], ['F01-01-01', 'F01'])
        self.assertTrue(all(not item['children'] for item in groups[0]['items']))
        self.assertEqual(summarize(groups)['total'], 2)

    def test_parent_links_never_cross_sections_or_include_fenced_examples(self):
        groups = parse('''## 大功能 F01：第一个分组
- [ ] F01 第一个分组的父项
## 普通说明
- [ ] F01-99 不属于任何分组
## 大功能 F01：第二个分组
- [ ] F01-01 第二个分组的子项
  - 子项说明
```markdown
- [ ] F01 代码块中的父项
  - 不是真实备注
```
## 大功能 F02：第三个分组
- [ ] F01 另一个分组的同编号父项
''')
        self.assertEqual([[item['id'] for item in group['items']] for group in groups],
                         [['F01'], ['F01-01'], ['F01']])
        self.assertTrue(all(not item['children'] for group in groups for item in group['items']))
        self.assertEqual(groups[1]['items'][0]['notes'], ['子项说明'])
        self.assertEqual(summarize(groups)['total'], 3)

    def test_duplicate_records_remain_visible_to_duplicate_id_validation(self):
        groups = parse('''## 大功能 F01：订单
- [ ] F01-01 保留旧子项
- [ ] F01 父项
- [ ] F01-01 重复子项
''')
        self.assertEqual([item['id'] for item in flatten(groups[0]['items'])],
                         ['F01', 'F01-01', 'F01-01'])
        self.assertEqual([item['name'] for item in groups[0]['items'][0]['children']],
                         ['保留旧子项', '重复子项'])

    def test_public_mcp_readoption_counts_one_leaf_and_preserves_child_history(self):
        with tempfile.TemporaryDirectory(prefix='hierarchy-readoption-') as folder:
            workspace = str(Path(folder) / 'workspace')
            project = call_tool('create_project', {'workspace': workspace, 'name': '订单测试'}, 'codex')['project']

            def call(action, **payload):
                return call_tool(action, {'workspace': workspace, 'project_id': project['id'], **payload}, 'codex')

            def save_plan(content):
                call('save_plan', content=content, revision=call('read_project')['plan']['revision'])

            def save_ledger():
                candidate = call('generate_ledger')
                return call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                            plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])

            save_plan(TREE_PLAN)
            initial = save_ledger()
            call('update_feature_progress', feature_id='F01-01', revision=initial['revision'],
                 changes={'状态': '进行中', '执行 Agent': 'developer-orders', '实现证据': 'commit abc，保存读取已验证'})
            declined = TREE_PLAN.replace('保存后可读取 | 是 |', '保存后可读取 | 否 |')
            save_plan(declined)
            intermediate = save_ledger()
            cancelled_text = call('read_project')['ledger']['content']
            # This is the real persisted order that previously made the parser
            # count the re-adopted parent and child as two unrelated leaves.
            self.assertLess(cancelled_text.index('- [ ] F01-01 '), cancelled_text.index('- [ ] F01 '))
            save_plan(TREE_PLAN)
            restored = save_ledger()
            saved = call('read_project')['ledger']['content']
            groups = parse(saved)
            self.assertEqual([initial['summary']['total'], intermediate['summary']['total'], restored['summary']['total']],
                             [1, 1, 1])
            self.assertEqual([item['id'] for item in groups[0]['items']], ['F01'])
            child = groups[0]['items'][0]['children'][0]
            self.assertEqual(child['id'], 'F01-01')
            self.assertEqual(child['fields']['状态'], '进行中')
            self.assertEqual(child['fields']['实现证据'], 'commit abc，保存读取已验证')
            history = json.loads(child['fields']['规划同步历史'])
            self.assertEqual([entry['fields']['状态'] for entry in history], ['进行中', '已取消'])
            self.assertEqual(json.loads(child['fields']['进度更新历史'])[0]['before']['fields']['状态'], '未开始')
            self.assertEqual(summarize(groups)['total'], 1)
            self.assertEqual(save_ledger()['revision'], restored['revision'])


if __name__ == '__main__':
    unittest.main()
