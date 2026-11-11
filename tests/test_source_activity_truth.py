"""Activity describes actual source evidence and keeps failed writes truthful."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_service import ProjectService
from serve_dashboard import RequestError
import planning_activity
import planning_research
from test_project_service import PLAN


class SourceActivityTruthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / '管理目录'
        self.service = ProjectService(str(self.workspace))
        self.project = self.service.call('create_project', {'name': '图书角'})['project']
        self.root = Path(self.project['directory'])
        revision = self.call('read_project')['plan']['revision']
        self.call('save_plan', content=PLAN, revision=revision)

    def call(self, action, **payload):
        return self.service.call(action, {'project_id': self.project['id'], **payload})

    def refs(self, names, selected=True, confirmed=True):
        record = {'version': 1, 'completed': True, 'selection_confirmed': confirmed,
                  'query': 'library', 'repositories': [{'name': name, 'selected': selected} for name in names]}
        (self.root / 'GitHub参考项目.md').write_text(planning_research.research_markdown(record), encoding='utf-8')

    def source_cache(self, name, files):
        cache = self.root / '.reference-code' / name.replace('/', '--')
        cache.mkdir(parents=True)
        self.git(cache, 'init', '-q')
        self.git(cache, 'remote', 'add', 'origin', 'https://github.com/' + name + '.git')
        for filename, content in files.items():
            path = cache / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        self.git(cache, 'add', '.')
        self.git(cache, 'commit', '-qm', 'source fixture')
        return cache

    def git(self, cache, *args):
        return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                               '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args],
                              cwd=cache, check=True, capture_output=True, text=True).stdout.strip()

    def test_no_selected_references_does_not_claim_commits_were_read(self):
        for explicit_decline in (False, True):
            with self.subTest(explicit_decline=explicit_decline):
                if explicit_decline:
                    self.refs(['fixture/books'], selected=False)
                prepared = self.call('prepare_source_review')
                record = planning_activity.read(self.project)[-1]
                self.assertEqual(prepared['sources']['repositories'], [])
                self.assertEqual(prepared['sources']['snippets'], [])
                self.assertEqual(record['state'], 'success')
                self.assertIn('未选择参考仓库', record['detail'])
                self.assertIn('无源码证据', record['detail'])
                self.assertNotIn('已读取固定提交', record['detail'])
                self.assertEqual(prepared['binding']['commits'], {})

    def test_repository_without_supported_source_reports_no_usable_snippets(self):
        self.refs(['fixture/docs'])
        self.source_cache('fixture/docs', {'README.md': '# Documentation only\n'})
        prepared = self.call('prepare_source_review')
        record = planning_activity.read(self.project)[-1]
        self.assertEqual(len(prepared['sources']['repositories']), 1)
        self.assertEqual(prepared['sources']['snippets'], [])
        self.assertIn('1 个参考仓库', record['detail'])
        self.assertIn('无可用源码片段', record['detail'])
        self.assertNotIn('已读取固定提交', record['detail'])
        self.assertIn('等待', record['detail'])
        with self.assertRaises(RequestError):
            self.call('generate_ledger')

    def test_read_sources_report_actual_repository_and_snippet_counts(self):
        self.refs(['fixture/books', 'fixture/search'])
        first = self.source_cache('fixture/books', {'books.py': 'BOOKS = []\n', 'src/save.py': 'def save():\n    pass\n'})
        second = self.source_cache('fixture/search', {'search.py': 'def search():\n    return []\n'})
        prepared = self.call('prepare_source_review')
        record = planning_activity.read(self.project)[-1]
        self.assertEqual(len(prepared['sources']['repositories']), 2)
        self.assertEqual(len(prepared['sources']['snippets']), 3)
        self.assertIn('已读取 2 个参考仓库的固定提交', record['detail'])
        self.assertIn('3 个源码片段', record['detail'])
        self.assertIn('等待当前宿主提交逐项核对报告', record['detail'])
        self.assertEqual(prepared['binding']['commits'], {'fixture/books': self.git(first, 'rev-parse', 'HEAD'),
                                                         'fixture/search': self.git(second, 'rev-parse', 'HEAD')})
        self.assertFalse((self.root / '规划源码核对.md').exists())

    def test_source_read_failure_after_an_earlier_repository_never_records_success(self):
        self.refs(['fixture/books', 'fixture/broken'])
        self.source_cache('fixture/books', {'books.py': 'BOOKS = []\n'})
        (self.root / '.reference-code' / 'fixture--broken').mkdir()
        previous = planning_activity.read(self.project)
        before_plan = Path(self.project['plan_path']).read_bytes()
        with self.assertRaises(ValueError) as error:
            self.call('prepare_source_review')
        records = planning_activity.read(self.project)
        self.assertEqual(records[:-1], previous)
        self.assertEqual(records[-1]['state'], 'failed')
        self.assertEqual(records[-1]['title'], '准备源码核对失败')
        self.assertEqual(records[-1]['detail'], str(error.exception))
        self.assertEqual(Path(self.project['plan_path']).read_bytes(), before_plan)
        self.assertFalse((self.workspace / '.feature-progress-tracker' / 'source-reviews').exists())
        self.assertFalse((self.root / '规划源码核对.md').exists())

    def test_source_timeout_records_failure_and_preserves_the_original_error(self):
        self.refs(['fixture/books'])
        previous = planning_activity.read(self.project)
        timeout = subprocess.TimeoutExpired(['git', 'clone'], 180)
        with patch('project_service.source.git', side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired) as error:
                self.call('prepare_source_review')
        self.assertIs(error.exception, timeout)
        records = planning_activity.read(self.project)
        self.assertEqual(records[:-1], previous)
        self.assertEqual(records[-1]['state'], 'failed')
        self.assertEqual(records[-1]['title'], '准备源码核对失败')
        self.assertEqual(records[-1]['detail'], str(timeout))
        self.assertFalse((self.workspace / '.feature-progress-tracker' / 'source-reviews').exists())

    def test_write_action_failures_have_chinese_titles_and_unchanged_reasons(self):
        cases = [
            ('save_plan', {'content': PLAN, 'revision': 'stale'}, '保存规划失败'),
            ('edit_features', {'revision': 'stale'}, '编辑功能表失败'),
            ('search_references', {'query': ''}, '搜索 GitHub 参考失败'),
            ('select_references', {'revision': 'stale'}, '保存参考选择失败'),
            ('submit_source_review', {'review_id': '../invalid'}, '提交源码核对失败'),
            ('save_ledger', {'content': ''}, '保存功能台账失败'),
            ('record_suggestions', {'revision': 'stale'}, '记录功能建议失败'),
            ('preview_suggestions', {'revision': 'stale'}, '预览采纳建议失败'),
            ('update_feature_progress', {'revision': 'stale'}, '更新功能进度失败'),
            ('export_project', {'format': 'invalid'}, '导出规划书失败'),
            ('generate_ledger', {}, '生成功能台账失败'),
        ]
        self.refs(['fixture/books'], selected=False, confirmed=False)
        for action, payload, title in cases:
            with self.subTest(action=action):
                previous = planning_activity.read(self.project)
                before_plan = Path(self.project['plan_path']).read_bytes()
                with self.assertRaises((ValueError, RequestError, OSError)) as error:
                    self.call(action, **payload)
                records = planning_activity.read(self.project)
                self.assertEqual(records[:-1], previous)
                self.assertEqual(records[-1]['title'], title)
                self.assertEqual(records[-1]['state'], 'failed')
                self.assertEqual(records[-1]['detail'], str(error.exception))
                self.assertEqual(Path(self.project['plan_path']).read_bytes(), before_plan)

    def test_failed_activity_write_keeps_symlink_target_and_plan_unchanged(self):
        log = self.root / '规划操作记录.md'
        log.unlink()
        target = Path(self.temp.name) / 'protected.md'
        target.write_text('原始内容', encoding='utf-8')
        log.symlink_to(target)
        before_plan = Path(self.project['plan_path']).read_bytes()
        with self.assertRaises(RequestError) as error:
            self.call('save_plan', content=PLAN, revision='stale')
        self.assertEqual(error.exception.code, 409)
        self.assertIn('文件已变化或缺少版本', str(error.exception))
        self.assertIn('操作记录未保存', str(error.exception))
        self.assertTrue(log.is_symlink())
        self.assertEqual(target.read_text(encoding='utf-8'), '原始内容')
        self.assertEqual(Path(self.project['plan_path']).read_bytes(), before_plan)


if __name__ == '__main__':
    unittest.main()
