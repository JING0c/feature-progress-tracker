"""Adoption changes must reconcile existing tracking without erasing its audit."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import planning_editor as editor
import planning_operations as operations
from project_progress import update_progress
from project_service import ProjectService
import serve_dashboard as dashboard


PLAN = '''# 订单项目规划书
## 项目目标与场景
帮助店员创建订单并查看处理结果。
## 范围与边界
本期仅管理本地订单，不涉及在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |
|---|---|---|---|---|---|
| F01 | 无 | 订单管理 | 管理订单生命周期 | 创建后可以找到订单 | 是 |
| F01-01 | F01 | 创建订单 | 确认商品与数量 | 可创建订单并返回编号 | 是 |
| F01-01-01 | F01-01 | 选择商品 | 查看并选择商品 | 可以选择一件商品 | 是 |
| F01-01-02 | F01-01 | 确认数量 | 输入商品数量 | 正整数数量可以保存 | 是 |
| F02 | 无 | 导出订单 | 下载本地订单清单 | 导出文件可打开且内容正确 | 是 |
'''


def items(content):
    return {i['id']: i for group in dashboard.parse(content) for i in dashboard.flatten(group['items'])}


def sync(plan, existing=''):
    candidate = operations.ledger_from_plan(plan, existing, dashboard.parse)
    return dashboard.prepare_ledger(candidate['content'], existing)


def accepted_tree():
    content = sync(PLAN)['content']
    review = {'reviewer':'reviewer-acceptance', 'score':95, 'conclusion':'通过',
              'evidence':'reports/acceptance.md', 'reason':'独立验证订单正常流程与边界输入'}
    for identity in ('F01-01-01', 'F01-01-02', 'F01-01'):
        content = update_progress(content, identity,
                                  {'状态':'已完成', '执行 Agent':'developer-orders', '实现证据':'commit abc123，订单用例通过'},
                                  'codex', review)['content']
    return content


class AdoptionLedgerTests(unittest.TestCase):
    def test_cancel_parent_cascades_and_retains_execution_and_review_history(self):
        old = accepted_tree(); before = items(old)
        changed = sync(editor.select_feature(PLAN, 'F01', False), old)
        self.assertEqual(changed['summary']['total'], 1)
        self.assertEqual(changed['summary']['done'], 0)
        after = items(changed['content'])
        self.assertEqual(set(after), set(before))
        for identity in ('F01-01', 'F01-01-01', 'F01-01-02'):
            self.assertEqual(after[identity]['fields']['状态'], '已取消')
            self.assertFalse(after[identity]['checked'])
            for key in ('执行 Agent', '实现证据', '审核 Agent', '评分', '审核结论', '进度更新历史'):
                self.assertEqual(after[identity]['fields'][key], before[identity]['fields'][key])
            history = json.loads(after[identity]['fields']['规划同步历史'])
            self.assertEqual(history[-1]['fields'], before[identity]['fields'])
            self.assertTrue(history[-1]['checked'])
        self.assertEqual(after['F02'], before['F02'])
        self.assertEqual(sync(editor.select_feature(PLAN, 'F01', False), changed['content'])['content'], changed['content'])

    def test_cancel_child_reopens_accepted_parent_and_keeps_sibling_accepted(self):
        old = accepted_tree()
        changed = sync(editor.select_feature(PLAN, 'F01-01-01', False), old)
        after = items(changed['content'])
        self.assertEqual(changed['summary']['total'], 2)
        self.assertEqual(changed['summary']['done'], 1)
        self.assertEqual(after['F01-01']['fields']['状态'], '进行中')
        self.assertFalse(after['F01-01']['checked'])
        self.assertEqual(after['F01-01-01']['fields']['状态'], '已取消')
        self.assertTrue(after['F01-01-02']['checked'])

    def test_readopt_completed_function_requires_new_review_and_keeps_old_snapshot(self):
        old = accepted_tree()
        cancelled = sync(editor.select_feature(PLAN, 'F01', False), old)['content']
        restored = sync(PLAN, cancelled)
        after = items(restored['content'])
        self.assertEqual(restored['summary']['total'], 3)
        self.assertEqual(restored['summary']['done'], 0)
        for identity in ('F01-01', 'F01-01-01', 'F01-01-02'):
            self.assertEqual(after[identity]['fields']['状态'], '进行中')
            self.assertEqual(after[identity]['fields']['审核 Agent'], '待审核')
            self.assertFalse(after[identity]['checked'])
            history = json.loads(after[identity]['fields']['规划同步历史'])
            self.assertTrue(history[0]['checked'])
            self.assertEqual(history[0]['fields']['评分'], '95')
        self.assertEqual(sync(PLAN, restored['content'])['content'], restored['content'])

    def test_readopt_restores_prior_work_state_and_does_not_reopen_manual_cancellation(self):
        for status in ('未开始', '进行中', '受阻', '已取消'):
            with self.subTest(status=status):
                old = sync(PLAN)['content']
                old = update_progress(old, 'F02', {'状态':status}, 'codex')['content']
                cancelled = sync(editor.select_feature(PLAN, 'F02', False), old)['content']
                self.assertEqual(items(cancelled)['F02']['fields']['状态'], '已取消')
                after = items(sync(PLAN, cancelled)['content'])['F02']
                self.assertEqual(after['fields']['状态'], status)
                self.assertFalse(after['checked'])

    def test_removed_old_branch_is_archived_and_excluded_not_erased(self):
        old = accepted_tree()
        rows = [row for row in editor.editable_table(PLAN)['rows'] if row['编号'] == 'F02']
        changed = sync(editor.replace_features(PLAN, rows), old)
        self.assertEqual(changed['summary']['total'], 1)
        self.assertEqual(set(items(changed['content'])), set(items(old)))
        for identity in ('F01-01', 'F01-01-01', 'F01-01-02'):
            self.assertEqual(items(changed['content'])[identity]['fields']['状态'], '已取消')
            self.assertIn('规划同步历史', items(changed['content'])[identity]['fields'])

    def test_removed_children_leave_adopted_parent_as_one_active_leaf(self):
        old = accepted_tree()
        rows = [row for row in editor.editable_table(PLAN)['rows']
                if row['编号'] not in ('F01-01-01', 'F01-01-02')]
        changed = sync(editor.replace_features(PLAN, rows), old)
        self.assertEqual(changed['summary']['total'], 2)
        self.assertEqual(changed['summary']['done'], 0)
        parent = items(changed['content'])['F01-01']
        self.assertEqual(parent['fields']['状态'], '进行中')
        self.assertEqual(len(parent['children']), 2, 'retained children remain available as historical records')
        review = {'reviewer':'new-reviewer', 'score':90, 'conclusion':'通过',
                  'evidence':'reports/revised-parent.md', 'reason':'独立验证收缩后的父功能验收'}
        accepted = update_progress(changed['content'], 'F01-01', {'状态':'已完成'}, 'codex', review)
        self.assertEqual(accepted['summary']['total'], 2)
        self.assertEqual(accepted['summary']['done'], 1)
        self.assertTrue(items(accepted['content'])['F01-01']['checked'])
        self.assertTrue(all(child['fields']['状态'] == '已取消' for child in parent['children']))

    def test_all_declined_can_cancel_existing_ledger_but_cannot_create_empty_tracking(self):
        declined = editor.select_feature(editor.select_feature(PLAN, 'F01', False), 'F02', False)
        changed = sync(declined, accepted_tree())
        self.assertEqual(changed['summary']['total'], 0)
        self.assertEqual(changed['summary']['done'], 0)
        with self.assertRaises(ValueError):
            sync(declined)

    def test_cancelled_history_cannot_be_rewritten_to_forge_acceptance(self):
        old = accepted_tree()
        cancelled = sync(editor.select_feature(PLAN, 'F01', False), old)['content']
        restored = sync(PLAN, cancelled)['content']
        before = items(cancelled)['F01-01-01']; after = items(restored)['F01-01-01']
        self.assertTrue(operations.valid_ledger_transition(before, after))
        for key, value in [('实现证据', 'invented'), ('评分', '100'), ('规划同步历史', '[]')]:
            forged = copy.deepcopy(after); forged['fields'][key] = value
            self.assertFalse(operations.valid_ledger_transition(before, forged))

    def test_host_generate_save_read_summary_matches_changed_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = ProjectService(str(Path(tmp) / 'workspace'), actor='codex')
            project = service.call('create_project', {'name':'订单项目'})['project']
            def call(action, **payload):
                return service.call(action, {'project_id':project['id'], **payload})
            def save_candidate():
                candidate = call('generate_ledger')
                result = call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                              plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])
                return candidate, result
            call('save_plan', content=PLAN, revision=call('read_project')['plan']['revision'])
            self.assertEqual(save_candidate()[1]['summary']['total'], 3)
            preview = call('edit_features', revision=call('read_project')['plan']['revision'],
                           selections=[{'id':'F01','selected':False}])
            call('save_plan', content=preview['content'], revision=preview['revision'])
            candidate, saved = save_candidate()
            self.assertEqual(candidate['summary']['total'], 1)
            self.assertEqual(saved['summary']['total'], 1)
            read = call('read_project')
            self.assertEqual(dashboard.summarize(dashboard.parse(read['ledger']['content']))['total'], 1)
            self.assertEqual(service.store.overview()['projects'][0]['summary']['total'], 1)


if __name__ == '__main__':
    unittest.main()
