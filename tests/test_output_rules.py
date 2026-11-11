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


# 旧网页编排集成类已归档到 legacy_web/test_output_rules.py。


if __name__ == '__main__':
    unittest.main()
