"""Regressions captured from two real Codex planning sessions."""
import importlib.util
from pathlib import Path
import unittest

import test_projects as project_tests
from ledger_context_fixture import legacy_no_reference_context

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rules_dashboard', ROOT / 'scripts/serve_dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


class IssueRulesTest(unittest.TestCase):
    def test_negated_issue_phrases_keep_actual_issues_visible(self):
        for value in ('暂无已知问题。', '无已知额外问题。', '目前暂无已知问题！', '未发现问题', '暂无争议', '无新增待确认事项。'):
            with self.subTest(value=value):
                self.assertFalse(dashboard.has_issue(value))
        for value in ('无法保存', '无权限导出', '暂无已知问题；但备份规则待确认', '未发现问题，但需要核对编号', '没有处理超时', '待确认备份方式'):
            with self.subTest(value=value):
                self.assertTrue(dashboard.has_issue(value))

    def test_real_generated_ledgers_have_correct_issue_totals(self):
        for name, total, issues in [('library', 13, 10), ('equipment', 19, 9)]:
            content = (ROOT / f'tests/fixtures/{name}-real-ledger.md').read_text()
            groups = dashboard.parse_document(content)
            self.assertEqual(dashboard.summarize(groups)['total'], total)
            self.assertEqual(dashboard.summarize(groups)['issues'], issues)
            nodes = [i for g in groups for i in dashboard.leaves(g['items'])]
            self.assertEqual(sum(i['issue'] for i in nodes), issues)
            self.assertTrue(all(i['dispute'] is False for i in nodes))


class SummarySaveTest(project_tests.ManagerTest):
    # Reuse server helpers without rerunning the inherited unrelated checks.
    test_project_isolation_external_edits_and_restart = None
    test_unknown_scope_and_conflict_fail_closed = None
    test_existing_acceptance_survives_and_fabrication_is_rejected = None
    test_registry_and_cross_document_collisions_are_rejected = None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved = None

    def test_real_summary_preview_and_save_preserve_original(self):
        p = self.register('summary')
        path = Path(p['ledger_path'])
        original = path.read_text()
        content = (ROOT / 'tests/fixtures/equipment-real-ledger.md').read_text()
        revision = self.request('/api/ledger/info?project=' + p['id'])[1]['revision']
        endpoint = '?project=' + p['id']
        context = legacy_no_reference_context(self.request('/api/plan' + endpoint)[1]['revision'])
        existing_files = set(path.parent.glob('*.md'))
        status, preview = self.request('/api/ledger/preview' + endpoint, {'content': content, 'revision': revision, **context})
        self.assertEqual(status, 200, preview)
        expected = content.replace('已验收 0/20 个最细功能点', '已验收 0/19 个最细功能点')
        self.assertEqual(preview['content'], expected)
        self.assertEqual(preview['summary']['total'], 19)
        self.assertEqual(preview['summary']['issues'], 9)
        self.assertEqual(len(preview['adjustments']), 1)
        self.assertEqual(path.read_text(), original)
        self.assertEqual(set(path.parent.glob('*.md')), existing_files)
        status, saved = self.request('/api/ledger/save' + endpoint, {'content': content, 'revision': revision, **context})
        self.assertEqual(status, 200, saved)
        self.assertEqual(path.read_text(), expected)
        self.assertEqual(Path(saved['source_backup']).read_text(), content)
        self.assertEqual(Path(saved['backup']).read_text(), original)
        self.assertEqual(saved['adjustments'], preview['adjustments'])
        self.assertEqual(saved['count'], 21)
        status, second = self.request('/api/ledger/save' + endpoint, {'content': expected, 'revision': saved['revision'], **context})
        self.assertEqual(status, 200, second)
        self.assertIsNone(second['source_backup'])
        self.assertEqual(second['adjustments'], [])

    def test_preview_scope_revision_and_invalid_content_are_protected(self):
        p = self.register('protected')
        raw = project_tests.ledger('test')
        self.assertEqual(self.request('/api/ledger/preview', {'content': raw})[0], 400)
        self.assertEqual(self.request('/api/ledger/preview?project=missing', {'content': raw})[0], 404)
        endpoint = '/api/ledger/preview?project=' + p['id']
        context = legacy_no_reference_context(self.request('/api/plan?project=' + p['id'])[1]['revision'])
        self.assertEqual(self.request(endpoint, {'content': raw, **context}, {'X-Planning-Token': 'bad'})[0], 403)
        self.assertEqual(self.request(endpoint, {'content': raw, 'revision': 'old', **context})[0], 409)
        self.assertEqual(self.request(endpoint, {'content': '普通回复', **context})[0], 400)
        self.assertEqual(self.request(endpoint, {'content': raw, **context})[0], 200)

    def test_summary_counts_leaf_acceptance_and_skips_non_header_text(self):
        p = self.register('scoped-summary')
        item = project_tests.ledger('main', '已完成', True)
        content = item.replace('## 大功能', '进度：已验收 0/20（0%）；待审核 5；受阻 6\n\n## 大功能', 1)
        content += project_tests.ledger('cancelled', '已取消').replace('F01', 'F02')
        child = project_tests.ledger('child').split('## 大功能 F01：child\n')[1].replace('F01-01', 'F02-01-01')
        content += child + '\n## 历史\n进度：已验收 0/20\n> 进度：已验收 0/20\n'
        content = '# 示例\n```md\n' + project_tests.ledger('example').replace('F01', 'F09') + '进度：已验收 0/20\n```\n\n' + content
        Path(p['ledger_path']).write_text(content)
        context = legacy_no_reference_context(self.request('/api/plan?project=' + p['id'])[1]['revision'])
        status, preview = self.request('/api/ledger/preview?project=' + p['id'], {'content': content, **context})
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview['summary']['total'], 1)
        self.assertEqual(preview['summary']['done'], 1)
        self.assertIn('进度：已验收 1/1（100%）；待审核 0；受阻 0', preview['content'])
        self.assertIn('## 历史\n进度：已验收 0/20\n> 进度：已验收 0/20', preview['content'])
        self.assertIn('进度：已验收 0/20\n```', preview['content'])

    def test_only_named_completion_percentage_is_rewritten(self):
        p = self.register('safe-header')
        content = project_tests.ledger('task').replace('## 大功能', '进度：已验收 0 / 20 个最细功能点（50%）；估算误差（10%）；待审核 3\n> 进度：已验收 0/40\n\n## 大功能', 1)
        context = legacy_no_reference_context(self.request('/api/plan?project=' + p['id'])[1]['revision'])
        status, preview = self.request('/api/ledger/preview?project=' + p['id'], {'content': content, **context})
        self.assertEqual(status, 200, preview)
        self.assertIn('进度：已验收 0 / 1 个最细功能点（0%）；估算误差（10%）；待审核 3', preview['content'])
        self.assertIn('> 进度：已验收 0/40', preview['content'])

    def test_inline_history_and_prose_are_not_normalized(self):
        p = self.register('history-header')
        content = project_tests.ledger('task').replace('## 大功能', '进度：已验收 0/20；历史快照：已验收 1/8（12.5%）；受阻 6\n进度：已验收 0/20，历史为已验收 1/8\n\n## 大功能', 1)
        context = legacy_no_reference_context(self.request('/api/plan?project=' + p['id'])[1]['revision'])
        status, preview = self.request('/api/ledger/preview?project=' + p['id'], {'content': content, **context})
        self.assertEqual(status, 200, preview)
        self.assertIn('进度：已验收 0/1；历史快照：已验收 1/8（12.5%）；受阻 6', preview['content'])
        self.assertIn('进度：已验收 0/20，历史为已验收 1/8', preview['content'])


if __name__ == '__main__':
    unittest.main()
