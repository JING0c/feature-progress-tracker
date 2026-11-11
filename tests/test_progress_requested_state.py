"""Explicit reopening states survive revocation of an old independent review."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from plugin_mcp import call_tool
from project_progress import update_progress
from test_project_progress import BASE, REVIEW, items


PLAN = '''# 订单规划书
## 项目目标与场景
帮助店员保存并读取订单。
## 范围与边界
仅处理本地订单，不包括在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |
|---|---|---|---|---|---|
| F01 | 无 | 保存订单 | 输入并保存订单 | 保存后可以读取订单 | 是 |
'''


class ProgressRequestedStateTests(unittest.TestCase):
    def accepted_tree(self):
        content = BASE
        for identity in ('F01-01-01', 'F01-01-02', 'F01-01'):
            content = update_progress(content, identity, {'状态': '已完成'}, 'implementer', REVIEW)['content']
        return content

    def assert_review_revoked_and_archived(self, before, after):
        self.assertFalse(after['checked'])
        self.assertEqual(after['fields']['审核 Agent'], '待审核')
        self.assertEqual(after['fields']['评分'], '待审核')
        self.assertEqual(after['fields']['审核证据'], '待审核')
        self.assertNotEqual(after['fields']['审核结论'], '通过')
        history = json.loads(after['fields']['进度更新历史'])
        self.assertEqual(history[:-1], json.loads(before['fields']['进度更新历史']))
        snapshot = history[-1]['before']
        self.assertTrue(snapshot['checked'])
        for field in ('执行 Agent', '实现证据', '审核 Agent', '评分', '评分理由', '审核结论', '审核证据'):
            self.assertEqual(snapshot['fields'][field], before['fields'][field], field)

    def test_explicit_noncomplete_states_survive_review_revocation(self):
        content = self.accepted_tree()
        before = items(content)
        for status in ('未开始', '进行中', '待审核', '受阻', '已取消'):
            with self.subTest(status=status):
                result = update_progress(content, 'F01-01-01', {'状态': status}, 'implementer')
                after = items(result['content'])
                self.assertEqual(after['F01-01-01']['fields']['状态'], status)
                self.assert_review_revoked_and_archived(before['F01-01-01'], after['F01-01-01'])
                self.assertEqual(after['F01-01']['fields']['状态'], '进行中')
                self.assert_review_revoked_and_archived(before['F01-01'], after['F01-01'])
                self.assertEqual(after['F01-01-02'], before['F01-01-02'])

    def test_evidence_only_edit_still_reopens_completed_feature_and_parent_to_working(self):
        content = self.accepted_tree()
        result = update_progress(content, 'F01-01-01', {'实现证据': '提交def，需重新独立复验'}, 'implementer')
        before, after = items(content), items(result['content'])
        self.assertEqual(after['F01-01-01']['fields']['实现证据'], '提交def，需重新独立复验')
        for identity in ('F01-01', 'F01-01-01'):
            self.assertEqual(after[identity]['fields']['状态'], '进行中')
            self.assert_review_revoked_and_archived(before[identity], after[identity])

    def test_pending_parent_still_reopens_to_working_when_child_requests_review(self):
        content = self.accepted_tree().replace('- [x] F01-01 订单流程｜状态：已完成',
                                                '- [ ] F01-01 订单流程｜状态：待审核')
        result = update_progress(content, 'F01-01-01', {'状态': '待审核'}, 'implementer')
        after = items(result['content'])
        self.assertEqual(after['F01-01-01']['fields']['状态'], '待审核')
        self.assertEqual(after['F01-01']['fields']['状态'], '进行中')
        self.assertFalse(after['F01-01']['checked'])

    def test_public_mcp_explicit_review_state_is_saved_and_counted_as_review(self):
        with tempfile.TemporaryDirectory(prefix='requested-progress-state-') as tmp:
            workspace = str(Path(tmp) / 'workspace')
            project = call_tool('create_project', {'workspace': workspace, 'name': '订单'}, 'codex')['project']

            def call(action, **values):
                return call_tool(action, {'workspace': workspace, 'project_id': project['id'], **values}, 'codex')

            call('save_plan', content=PLAN, revision=call('read_project')['plan']['revision'])
            candidate = call('generate_ledger')
            saved = call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                         plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])
            accepted = call('update_feature_progress', feature_id='F01', revision=saved['revision'],
                            changes={'状态': '已完成', '执行 Agent': 'implementer-A', '实现证据': '提交abc，订单测试通过'},
                            review=REVIEW)
            before = items(call('read_project')['ledger']['content'])['F01']
            reopened = call('update_feature_progress', feature_id='F01', revision=accepted['revision'],
                            changes={'状态': '待审核'})
            after = items(call('read_project')['ledger']['content'])['F01']
            self.assertEqual(after['fields']['状态'], '待审核')
            self.assertEqual(reopened['summary']['review'], 1)
            self.assertEqual(reopened['summary']['working'], 0)
            self.assertEqual(reopened['summary']['done'], 0)
            self.assert_review_revoked_and_archived(before, after)


if __name__ == '__main__':
    unittest.main()
