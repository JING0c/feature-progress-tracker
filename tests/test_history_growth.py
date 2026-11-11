"""History snapshots retain evidence without copying other history containers."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from plugin_mcp import call_tool
from planning_operations import history_text, ledger_from_plan, valid_ledger_transition
from project_progress import update_progress
from serve_dashboard import flatten, parse, prepare_ledger


PLAN = '''# 测试项目规划书
## 项目目标与场景
帮助测试员保存订单并查看处理结果。
## 范围与边界
本期仅管理本地订单，不涉及在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |
|---|---|---|---|---|---|
| F01 | 无 | 保存订单 | 输入信息并保存 | 保存后能读取订单 | 是 |
'''
NESTED_PLAN = PLAN + '''| F01-01 | F01 | 订单流程 | 处理订单 | 流程返回结果 | 是 |
| F01-01-01 | F01-01 | 查询订单 | 查询订单详情 | 查询返回详情 | 是 |
'''
HISTORY_FIELDS = {'进度更新历史', '规划同步历史'}


def items(content):
    return {item['id']: item for group in parse(content) for item in flatten(group['items'])}


class HistoryGrowthTests(unittest.TestCase):
    def assert_snapshot_has_no_histories(self, snapshot):
        self.assertFalse(HISTORY_FIELDS.intersection(snapshot['fields']))
        for child in snapshot.get('children', []):
            self.assert_snapshot_has_no_histories(child)

    def test_public_mcp_repeated_progress_and_requirement_saves_grow_linearly(self):
        # Copying either history into the other makes save_ledger fail by round 6.
        with tempfile.TemporaryDirectory(prefix='history-growth-') as tmp:
            workspace = str(Path(tmp) / 'workspace')
            project = call_tool('create_project', {'workspace': workspace, 'name': '测试项目'}, 'codex')['project']

            def call(action, **values):
                return call_tool(action, {'workspace': workspace, 'project_id': project['id'], **values}, 'codex')

            def save_plan(content):
                call('save_plan', content=content, revision=call('read_project')['plan']['revision'])

            def save_candidate():
                candidate = call('generate_ledger')
                try:
                    call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                         plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])
                except ValueError as exc:
                    self.fail('Normal repeated history updates must remain saveable: ' + str(exc))
                content = call('read_project')['ledger']['content']
                self.assertEqual(content, candidate['content'])
                return content

            save_plan(PLAN)
            content = save_candidate()
            sizes = [len(content)]
            for number in range(1, 9):
                call('update_feature_progress', revision=call('read_project')['ledger']['revision'],
                     feature_id='F01', changes={'实现证据': '实现第' + str(number) + '轮'})
                save_plan(PLAN.replace('保存后能读取订单', '保存后能读取订单第' + str(number) + '版'))
                content = save_candidate()
                sizes.append(len(content))

            # Each equally sized edit must add roughly a snapshot, not copy the archive.
            growth = [after - before for before, after in zip(sizes, sizes[1:])]
            self.assertLessEqual(max(growth), 2 * min(growth), sizes)
            current = items(content)['F01']
            progress_history = json.loads(current['fields']['进度更新历史'])
            plan_history = json.loads(current['fields']['规划同步历史'])
            self.assertEqual(len(progress_history), 8)
            self.assertEqual(len(plan_history), 8)
            self.assertEqual([entry['fields']['实现证据'] for entry in plan_history],
                             ['实现第' + str(number) + '轮' for number in range(1, 9)])
            for snapshot in plan_history + [entry['before'] for entry in progress_history]:
                self.assert_snapshot_has_no_histories(snapshot)

    def test_parent_and_child_snapshots_keep_evidence_without_cross_history(self):
        original = ledger_from_plan(NESTED_PLAN, '', parse)['content']
        content = update_progress(original, 'F01-01', {'实现证据': '父功能实施记录'}, 'implementer')['content']
        content = update_progress(content, 'F01-01-01', {'实现证据': '子功能实施记录'}, 'implementer')['content']
        changed_plan = NESTED_PLAN.replace('流程返回结果', '流程返回完整结果').replace('查询返回详情', '查询返回完整详情')
        synced = ledger_from_plan(changed_plan, content, parse)['content']
        prepare_ledger(synced, content)
        parent = items(synced)['F01-01']
        archived = json.loads(parent['fields']['规划同步历史'])[-1]
        self.assertEqual(archived['fields']['实现证据'], '父功能实施记录')
        self.assertEqual(archived['children'][0]['fields']['实现证据'], '子功能实施记录')
        with self.subTest(operation='plan_sync'):
            self.assert_snapshot_has_no_histories(archived)
        updated = update_progress(synced, 'F01-01-01', {'实现证据': '更新子功能实施记录'}, 'implementer')['content']
        with self.subTest(operation='progress_update'):
            self.assert_snapshot_has_no_histories(json.loads(items(updated)['F01-01-01']['fields']['进度更新历史'])[-1]['before'])

    def test_legacy_nested_archives_remain_exact_and_preserve_original_review(self):
        # Old releases stored JSON histories inside snapshots. Those existing
        # archives remain authoritative, including evidence only found in them.
        original = ledger_from_plan(PLAN, '', parse)['content']
        accepted = copy.deepcopy(items(original)['F01'])
        accepted['checked'] = True
        accepted['fields'].update({'状态': '已完成', '执行 Agent': 'original-implementer',
                                  '实现证据': 'original-commit; preserved | evidence',
                                  '审核 Agent': 'original-reviewer', '评分': '96',
                                  '审核结论': '通过', '审核证据': 'original-independent-report'})
        old_plan_archive = [accepted]
        old_progress_snapshot = copy.deepcopy(accepted)
        old_progress_snapshot['fields']['规划同步历史'] = history_text(old_plan_archive)
        old_progress_archive = [{'actor': 'old-host', 'reason': '旧进度变更', 'before': old_progress_snapshot}]
        original += '  - 规划同步历史：' + history_text(old_plan_archive) + '\n'
        original += '  - 进度更新历史：' + history_text(old_progress_archive) + '\n'
        before = items(original)['F01']

        updated = update_progress(original, 'F01', {'实现证据': 'current-commit'}, 'current-host')['content']
        changed_plan = PLAN.replace('保存后能读取订单', '保存后能读取完整订单')
        synced = ledger_from_plan(changed_plan, updated, parse)['content']
        self.assertTrue(valid_ledger_transition(items(updated)['F01'], items(synced)['F01']))
        prepare_ledger(synced, updated)
        current = items(synced)['F01']
        progress_history = json.loads(current['fields']['进度更新历史'])
        plan_history = json.loads(current['fields']['规划同步历史'])
        self.assertEqual(progress_history[:-1], old_progress_archive)
        self.assertEqual(plan_history[:-1], old_plan_archive)
        self.assertEqual(progress_history[0]['before']['fields']['审核证据'], 'original-independent-report')
        self.assertEqual(plan_history[0]['fields']['实现证据'], 'original-commit; preserved | evidence')
        self.assertEqual(items(original)['F01'], before)
        self.assert_snapshot_has_no_histories(progress_history[-1]['before'])
        self.assert_snapshot_has_no_histories(plan_history[-1])


if __name__ == '__main__':
    unittest.main()
