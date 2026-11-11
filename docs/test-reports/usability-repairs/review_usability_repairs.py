from pathlib import Path
import sys, unittest
from unittest.mock import patch
sys.path[:0] = ['/Users/olcgb/code/protuct_plan/scripts', '/Users/olcgb/code/protuct_plan/tests']
from test_source_activity_truth import SourceActivityTruthTests
import planning_activity

class IndependentReview(SourceActivityTruthTests):
    def assert_failed_truth(self, perform, expected):
        before = planning_activity.read(self.project)
        raw = (self.root/'规划操作记录.md').read_bytes()
        plan = Path(self.project['plan_path']).read_bytes()
        with self.assertRaises(expected) as raised: perform()
        after = planning_activity.read(self.project)
        self.assertEqual(after[:-1], before)
        self.assertEqual(after[-1]['state'], 'failed')
        self.assertEqual(after[-1]['title'], '准备源码核对失败')
        self.assertEqual(after[-1]['detail'], str(raised.exception))
        self.assertEqual(Path(self.project['plan_path']).read_bytes(), plan)
        self.assertFalse((self.root/'规划源码核对.md').exists())
        self.assertFalse((self.workspace/'.feature-progress-tracker'/'source-reviews').exists())

    def test_independent_unborn_git_repository_fails_without_success_record(self):
        self.refs(['review/empty'])
        cache = self.root/'.reference-code'/'review--empty'
        cache.mkdir(parents=True)
        self.git(cache, 'init', '-q')
        self.git(cache, 'remote', 'add', 'origin', 'https://github.com/review/empty.git')
        self.assert_failed_truth(lambda: self.call('prepare_source_review'), ValueError)

    def test_independent_supported_files_all_empty_oversized_or_binary(self):
        self.refs(['review/no-evidence'])
        cache=self.source_cache('review/no-evidence', {'empty.py':'', 'oversized.js':'x'*120001, 'binary.ts':'hello\0world'})
        result=self.call('prepare_source_review')
        self.assertEqual(result['sources']['repositories'][0]['files_read'], 0)
        self.assertEqual(result['sources']['snippets'], [])
        record=planning_activity.read(self.project)[-1]
        self.assertIn('无可用源码片段', record['detail'])
        self.assertNotIn('已读取', record['detail'])
        self.assertEqual(record['state'], 'success')

    def test_independent_invalid_utf8_records_failure(self):
        self.refs(['review/encoding'])
        cache=self.source_cache('review/encoding', {'source.py':'pass\n'})
        (cache/'source.py').write_bytes(b'\xff\xfe\xff')
        self.git(cache, 'add', '.')
        self.git(cache, 'commit', '-qm', 'bad utf8 fixture')
        self.assert_failed_truth(lambda: self.call('prepare_source_review'), UnicodeDecodeError)

    def test_independent_ticket_write_failure_not_success(self):
        with patch.object(self.service, '_review_path', side_effect=OSError('isolated write failure')):
            self.assert_failed_truth(lambda:self.call('prepare_source_review'), OSError)

    def test_independent_reads_do_not_rewrite_legacy_failure(self):
        planning_activity.append(self.project, {'id':'legacy-id','time':'2020-01-01T00:00:00Z', 'title':'save_plan 失败','detail':'old detail','state':'failed'})
        before=(self.root/'规划操作记录.md').read_bytes()
        self.call('read_project'); self.call('history')
        self.assertEqual(before,(self.root/'规划操作记录.md').read_bytes())
        self.assertEqual(planning_activity.read(self.project)[-1]['title'],'save_plan 失败')

if __name__ == '__main__':
    suite=unittest.TestSuite(IndependentReview(name) for name in unittest.defaultTestLoader.getTestCaseNames(IndependentReview) if name.startswith('test_independent'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
