"""Writing an old candidate must not bypass the current source review boundary."""
import json
import concurrent.futures
import time
import unittest
from pathlib import Path
import test_references_history as history
import test_research_editor as workflow


class LedgerCommitGateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = history.ReferencesHistoryHttpTest('test_explicit_empty_selection_is_supported_without_changing_feature_adoption')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        self.project = f.project('commit-gate')
        self.suffix = '?project=' + self.project['id']
        self.assertEqual(f.save(self.project, generate=True)[0], 200)
        f.refs(self.project)
        self.assertEqual(f.select(self.project, ['org/two'])[0], 200)
        fake = f.fake_bin / 'git'
        fake.write_text('#!/usr/bin/python3\nimport sys,pathlib\na=sys.argv\n'
                        'if "clone" in a:pathlib.Path(a[-1]).mkdir()\n'
                        'elif "config" in a:print("https://github.com/org/two.git")\n'
                        'elif "rev-parse" in a:print("a"*40)\n'
                        'elif "ls-tree" in a:print("src/app.py\\0",end="")\n'
                        'elif "cat-file" in a:print(30)\n'
                        'elif "show" in a:print("def book():\\n    return True")\n')
        fake.chmod(0o755)
        rows = workflow.editor.editable_table(workflow.PLAN)['rows']
        f.fake_reply.write_text(json.dumps({'features': [
            {'id': r['编号'], 'status': '部分依据', 'finding': '只有示例入口',
             'evidence': [{'repository': 'org/two', 'path': 'src/app.py', 'line': 1}]}
            for r in rows]}))
        self.assertEqual(f.request('/api/research/source-check' + self.suffix, {})[0], 200)
        revision = f.request('/api/plan' + self.suffix)[1]['revision']
        code, candidate = f.request('/api/ledger/generate' + self.suffix, {'revision': revision})
        self.assertEqual(code, 200, candidate)
        self.payload = {'content': candidate['content'], 'revision': candidate['ledger_revision'],
                        'plan_revision': revision, 'source_revision': candidate.get('source_revision')}
        self.before = Path(self.project['ledger_path']).read_bytes()
        f.fake_prompt.unlink()

    def assert_rejected_without_write(self):
        for route in ('/api/ledger/preview', '/api/ledger/save'):
            code, data = self.fixture.request(route + self.suffix, self.payload)
            self.assertEqual(code, 409, data)
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(), self.before)
        self.assertFalse(self.fixture.fake_prompt.exists(), 'saving must not invoke Codex')

    def test_reference_change_blocks_old_candidate(self):
        self.assertEqual(self.fixture.select(self.project, ['org/one'])[0], 200)
        self.assert_rejected_without_write()

    def test_deselecting_references_also_invalidates_old_candidate(self):
        self.assertEqual(self.fixture.select(self.project, [])[0], 200)
        self.assert_rejected_without_write()

    def test_missing_binding_cannot_bypass_selected_reference_gate(self):
        self.payload.pop('source_revision')
        self.assert_rejected_without_write()

    def test_missing_both_bindings_without_research_cannot_save_stale_plan(self):
        # Markdown is editable outside the HTTP service. Missing reference data
        # must not turn a legacy candidate without bindings into a valid one.
        Path(self.project['directory'], 'GitHub参考项目.md').unlink()
        plan = Path(self.project['plan_path'])
        plan.write_text(plan.read_text() + '\n## 新增边界\n导出前必须校验必填项。\n')
        self.payload.pop('plan_revision')
        self.payload.pop('source_revision')
        self.assert_rejected_without_write()

    def assert_external_change_during_source_validation_is_rejected(self, path, content):
        # Pause the first git config call, after the handler has read the plan,
        # research and report. File signals make the interleaving deterministic;
        # the short polling interval does not determine when the edit occurs.
        f = self.fixture
        entered = f.fake_bin / 'source-validation-entered'
        release = f.fake_bin / 'source-validation-release'
        fake = f.fake_bin / 'git'
        original = fake.read_text()
        gate = ('if "config" in a:\n'
                ' import time\n'
                f' pathlib.Path({str(entered)!r}).write_text("entered")\n'
                ' deadline=time.monotonic()+10\n'
                f' while not pathlib.Path({str(release)!r}).exists():\n'
                '  if time.monotonic()>deadline:raise RuntimeError("test signal timed out")\n'
                '  time.sleep(0.01)\n')
        self.assertIn('a=sys.argv\n', original)
        fake.write_text(original.replace('a=sys.argv\n', 'a=sys.argv\n' + gate, 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(f.request, '/api/ledger/save' + self.suffix, self.payload)
            try:
                deadline = time.monotonic() + 5
                while not entered.exists() and not future.done() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(entered.exists(), 'save did not enter the source-validation barrier')
                path.write_text(content)
            finally:
                release.write_text('continue')
            code, data = future.result(timeout=8)
        self.assertEqual(code, 409, data)
        self.assertEqual(path.read_text(), content, 'save must not undo the external edit')
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(), self.before)
        self.assertFalse(f.fake_prompt.exists(), 'saving must not invoke Codex')

    def test_external_plan_edit_during_source_validation_blocks_save(self):
        plan = Path(self.project['plan_path'])
        self.assert_external_change_during_source_validation_is_rejected(
            plan, plan.read_text() + '\n## 新增边界\n导出前必须校验必填项。\n')

    def test_external_reference_edit_during_source_validation_blocks_save(self):
        path = Path(self.project['directory'], 'GitHub参考项目.md')
        record = history.research.read_research(path.read_text())
        record['repositories'][0]['selected'] = True
        record['repositories'][1]['selected'] = False
        self.assert_external_change_during_source_validation_is_rejected(
            path, history.research.research_markdown(record))

    def test_external_report_edit_during_source_validation_blocks_save(self):
        path = Path(self.project['directory'], '规划源码核对.md')
        content = path.read_text()
        self.assertIn('只有示例入口', content)
        self.assert_external_change_during_source_validation_is_rejected(
            path, content.replace('只有示例入口', '新增证据限制，需重新确认'))

    def test_plan_save_rechecks_ids_reserved_after_suggestion_preview(self):
        f = self.fixture
        f.fake_reply.write_text(json.dumps({'suggestions': [{
            'title': '新增导出', 'reason': '新增需求', 'changes': [
                {'action': 'add', 'id': 'F02', 'fields': {
                    '上级编号': '无', '功能名称': '导出', '说明': '新导出',
                    '验收标准': '按新规则导出'}},
                {'action': 'add', 'id': 'F02-01', 'fields': {
                    '上级编号': 'F02', '功能名称': '导出CSV', '说明': '新功能',
                    '验收标准': '导出失败可重试'}}]}]}, ensure_ascii=False))
        revision = self.payload['plan_revision']
        code, record = f.request('/api/plan/suggestions' + self.suffix, {'revision': revision})
        self.assertEqual(code, 200, record)
        code, preview = f.request('/api/plan/suggestions/preview' + self.suffix, {
            'revision': revision, 'suggestion_id': record['id'], 'selected': ['S01']})
        self.assertEqual(code, 200, preview)
        plan = Path(self.project['plan_path'])
        before_plan = plan.read_bytes()
        ledger = Path(self.project['ledger_path'])
        newly_reserved = ('# 功能执行情况\n## 大功能 F02：导出\n'
                          '- [x] F02-01 导出CSV｜状态：已完成\n'
                          '  - 验收：导出旧格式。\n'
                          '  - 审核 Agent：独立审核员；评分：95\n')
        ledger.write_text(newly_reserved)
        code, data = f.request('/api/plan/save' + self.suffix, {
            'revision': revision, 'content': preview['content'], 'source': '功能表编辑'})
        self.assertEqual(code, 409, data)
        self.assertEqual(plan.read_bytes(), before_plan)
        self.assertEqual(ledger.read_text(), newly_reserved)

    def test_source_report_deleted_after_preview_blocks_save(self):
        self.assertEqual(self.fixture.request('/api/ledger/preview' + self.suffix, self.payload)[0], 200)
        Path(self.project['directory'], '规划源码核对.md').unlink()
        self.assert_rejected_without_write()

    def test_valid_binding_can_save_without_model(self):
        code, data = self.fixture.request('/api/ledger/save' + self.suffix, self.payload)
        self.assertEqual(code, 200, data)
        self.assertGreater(data['summary']['total'], 0)
        self.assertFalse(self.fixture.fake_prompt.exists())
