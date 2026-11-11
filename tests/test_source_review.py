import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_research_editor as existing

class SourceReviewTests(unittest.TestCase):
    def test_git_source_preserves_leading_lines(self):
        source=existing.dashboard.planning_module('planning_source')
        from types import SimpleNamespace
        with patch.object(source.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='\n\ndef source():\n    pass\n')):
            self.assertTrue(source.git(['show','HEAD:src/app.py']).startswith('\n\n'))

    def test_evidence_must_be_present_in_supplied_source(self):
        source=existing.dashboard.planning_module('planning_source')
        snippets=[{'repository':'org/repo','commit':'abc','path':'src/app.py','start':1,'end':3,'text':'1: def search():\n2:     return []\n3:'}]
        rows=[{'编号':'F01','功能名称':'搜索','采用':'是'}]
        report={'features':[{'id':'F01','status':'有源码依据','finding':'实现搜索','evidence':[{'repository':'org/repo','path':'src/app.py','line':1}]}]}
        self.assertEqual(source.validate_report(report,rows,snippets)['features'][0]['status'],'有源码依据')
        report['features'][0]['evidence'][0]['path']='invented.py'
        with self.assertRaises(ValueError): source.validate_report(report,rows,snippets)
        report['features']=[]
        with self.assertRaises(ValueError): source.validate_report(report,rows,snippets)

    def test_clone_is_reused_and_code_is_read_from_git_objects(self):
        source=existing.dashboard.planning_module('planning_source')
        calls=[]
        def git(args,cwd=None,timeout=60):
            calls.append(args)
            if 'clone' in args: Path(args[-1]).mkdir(); return ''
            if 'rev-parse' in args:return 'a'*40
            if 'config' in args:return 'https://github.com/org/repo.git'
            if 'ls-tree' in args:return 'src/app.py\0README.md\0'
            if 'show' in args:return 'def search():\n    return []\n'
            return ''
        with tempfile.TemporaryDirectory() as tmp, patch.object(source,'git',side_effect=git):
            repo={'name':'org/repo'}
            a=source.collect_sources(Path(tmp),[repo],'search',lambda **kw:None)
            b=source.collect_sources(Path(tmp),[repo],'search',lambda **kw:None)
            self.assertEqual(sum('clone' in c for c in calls),1)
            self.assertEqual(a['snippets'],b['snippets'])
            self.assertEqual(b['repositories'][0]['state'],'已克隆，使用本地提交')
            self.assertTrue(a['snippets'])
            with self.assertRaises(ValueError):source.collect_sources(Path(tmp),[{'name':'../repo'}],'',lambda **kw:None)

import test_references_history as history_tests
# 旧网页编排集成类已归档到 legacy_web/test_source_review.py。
