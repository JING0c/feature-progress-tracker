"""Current host-tool equivalents of retired browser-write safety checks.

All files and Git repositories are isolated temporary fixtures. Source review
uses actual local Git objects; no model, remote search or network is invoked.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_service import ProjectService
from serve_dashboard import RequestError, parse, flatten
import planning_research
import project_service
from test_project_service import PLAN


class ChatSafetyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / '管理资料'
        self.service = ProjectService(str(self.workspace), actor='codex')
        self.project = self.service.call('create_project', {'name':'项目一','mode':'create'})['project']
        self.other = self.service.call('create_project', {'name':'项目二','mode':'create'})['project']

    def call(self, action, project=None, **payload):
        return self.service.call(action, {'project_id':(project or self.project)['id'], **payload})

    def save_plan(self, text=PLAN, project=None):
        read = self.call('read_project', project)
        return self.call('save_plan', project, content=text, revision=read['plan']['revision'])

    def save_candidate(self, candidate, project=None):
        return self.call('save_ledger', project, content=candidate['content'], revision=candidate['ledger_revision'],
                         plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])

    def project_files(self, project=None):
        root = Path((project or self.project)['directory'])
        return {file.relative_to(root):file.read_bytes() for file in root.rglob('*') if file.is_file()}

    def refs(self):
        data = {'version':1,'completed':True,'selection_confirmed':False,'query':'library search',
                'repositories':[{'name':'fixture/library','url':'https://github.com/fixture/library','readme':'Library example','selected':False}]}
        Path(self.project['directory'], 'GitHub参考项目.md').write_text(planning_research.research_markdown(data))
        refs = self.call('read_project')['references']
        return self.call('select_references', revision=refs['revision'], selected=['fixture/library'])

    def source_cache(self):
        repo = Path(self.project['directory'], '.reference-code', 'fixture--library')
        repo.mkdir(parents=True)
        self.git(repo, 'init', '-q')
        self.git(repo, 'remote', 'add', 'origin', 'https://github.com/fixture/library.git')
        (repo/'library.py').write_text('def search_books(name):\n    return [name]\n')
        self.git(repo, 'add', 'library.py'); self.git(repo, 'commit', '-qm', 'fixture library')
        return repo

    def git(self, repo, *args):
        result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Fixture',
                                 '-c', 'user.email=fixture@example.invalid', *args],
                                cwd=repo, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def prepare_review(self):
        prepared = self.call('prepare_source_review')
        report = {'features':[{'id':row['编号'],'status':'有源码依据','finding':'存在可参考的查询函数，未运行项目',
                              'evidence':[{'repository':'fixture/library','path':'library.py','line':1}]}
                             for row in prepared['features']]}
        return prepared, report

    def test_project_writes_do_not_cross_scope_and_unknown_identity_fails(self):
        other_before = self.project_files(self.other)
        self.save_plan(); candidate=self.call('generate_ledger'); self.save_candidate(candidate)
        self.assertEqual(other_before, self.project_files(self.other))
        read = self.call('read_project')
        with self.assertRaises(RequestError):
            self.call('save_plan', self.other, content=PLAN, revision=read['plan']['revision'])
        with self.assertRaises(RequestError):
            self.service.call('read_project', {'project_id':'not-registered'})
        self.assertEqual(Path(self.other['plan_path']).read_bytes(), other_before[Path('项目规划书.md')])

    def test_stale_save_cannot_overwrite_external_edit_or_create_history(self):
        self.save_plan(); prior=self.call('read_project'); history=self.call('history')['versions']
        external=PLAN+'\n## 外部说明\n文件由另一个宿主更新。\n'
        Path(self.project['plan_path']).write_text(external)
        with self.assertRaises(RequestError):
            self.call('save_plan', content=PLAN+'\n旧页面修改', revision=prior['plan']['revision'])
        self.assertEqual(Path(self.project['plan_path']).read_text(), external)
        self.assertEqual(self.call('history')['versions'], history)

    def test_missing_or_deleted_plan_relocks_ledger_operations(self):
        with self.assertRaises(RequestError): self.call('generate_ledger')
        self.save_plan(); candidate=self.call('generate_ledger')
        Path(self.project['plan_path']).unlink()
        with self.assertRaises(RequestError): self.save_candidate(candidate)
        self.assertFalse(self.call('read_project')['project']['planning']['ready'])
        self.assertNotIn('F01-01', Path(self.project['ledger_path']).read_text())

    def test_import_preserves_existing_documents_and_requires_host_plan_save(self):
        folder=Path(self.temp.name)/'已有项目'; folder.mkdir()
        (folder/'项目规划书.md').write_text(PLAN)
        (folder/'功能执行情况.md').write_text('# 功能执行情况\n\n原有资料\n')
        original={p.name:p.read_bytes() for p in folder.iterdir()}
        imported=self.service.call('create_project', {'name':'导入项目','mode':'import','directory':str(folder)})['project']
        self.assertEqual((folder/'项目规划书.md').read_bytes(), original['项目规划书.md'])
        self.assertEqual((folder/'功能执行情况.md').read_bytes(), original['功能执行情况.md'])
        self.assertFalse(imported['planning']['ready'])
        with self.assertRaises(RequestError): self.call('generate_ledger', imported)
        saved=self.save_plan(project=imported)
        self.assertTrue(saved['planning']['ready'])
        self.assertEqual(Path(saved['backup']).read_bytes(), original['项目规划书.md'])

    def test_plan_ledger_path_collisions_cannot_replace_existing_files(self):
        before=self.project_files()
        for payload in [{'name':'重复','mode':'import','directory':self.project['directory']},
                        {'name':'碰撞','mode':'import','directory':self.project['directory'],'ledger_path':'项目规划书.md'}]:
            with self.assertRaises(RequestError): self.service.call('create_project', payload)
        self.assertEqual(before,self.project_files())

    def test_accepted_history_cannot_be_forged_by_ordinary_ledger_save(self):
        self.save_plan(); self.save_candidate(self.call('generate_ledger'))
        ledger=self.call('read_project')['ledger']
        review={'reviewer':'independent-reviewer','score':96,'conclusion':'通过','reason':'独立覆盖正常与边界流程',
                'evidence':'验收报告reports/acceptance.md'}
        self.call('update_feature_progress', feature_id='F01-01', revision=ledger['revision'],
                  changes={'状态':'已完成','执行 Agent':'developer','实现证据':'提交abc与测试记录'}, review=review)
        before=self.call('read_project')['ledger']
        candidate=self.call('generate_ledger')
        forged=copy.deepcopy(candidate)
        forged['content']=forged['content'].replace('评分：96', '评分：100')
        with self.assertRaises((ValueError,RequestError)): self.save_candidate(forged)
        self.assertEqual(self.call('read_project')['ledger'],before)
        forged=copy.deepcopy(candidate); forged['content']=forged['content'].replace('- [ ] F02', '- [x] F02').replace('状态：未开始','状态：已完成')
        with self.assertRaises((ValueError,RequestError)): self.save_candidate(forged)
        self.assertEqual(self.call('read_project')['ledger'],before)
        # A legitimate requirements change reopens acceptance while keeping evidence.
        self.save_plan(PLAN.replace('保存后列表可见图书','保存后可按标题检索到图书'))
        updated=self.call('generate_ledger'); self.save_candidate(updated)
        item=next(i for g in parse(self.call('read_project')['ledger']['content']) for i in flatten(g['items']) if i['id']=='F01-01')
        self.assertFalse(item['checked']); self.assertEqual(item['fields']['审核 Agent'],'待审核')
        self.assertEqual(item['fields']['实现证据'],'提交abc与测试记录')
        self.assertTrue(json.loads(item['fields']['规划同步历史'])[-1]['checked'])

    def test_reference_selection_changes_reject_old_no_reference_candidate(self):
        self.save_plan(); candidate=self.call('generate_ledger'); before=Path(self.project['ledger_path']).read_bytes()
        self.refs()
        with self.assertRaises(RequestError): self.save_candidate(candidate)
        refs=self.call('read_project')['references']
        self.call('select_references', revision=refs['revision'],selected=[])
        with self.assertRaises(RequestError): self.save_candidate(candidate)
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(),before)
        self.save_candidate(self.call('generate_ledger'))

    def test_source_review_is_bound_to_project_and_committed_code(self):
        self.save_plan(); self.refs(); repo=self.source_cache()
        prepared,report=self.prepare_review()
        self.save_plan(project=self.other)
        with self.assertRaises(RequestError):
            self.call('submit_source_review', self.other, review_id=prepared['review_id'],report=report)
        self.call('submit_source_review', review_id=prepared['review_id'],report=report)
        candidate=self.call('generate_ledger'); before=Path(self.project['ledger_path']).read_bytes()
        # A working-tree edit is not source evidence: the reader uses Git blobs.
        (repo/'library.py').write_text('def search_books(name):\n    return []\n')
        self.assertEqual(self.call('generate_ledger')['source_revision'], candidate['source_revision'])
        self.git(repo,'add','library.py');self.git(repo,'commit','-qm','changed source')
        with self.assertRaises(RequestError): self.save_candidate(candidate)
        with self.assertRaises(RequestError):
            self.call('submit_source_review',review_id=prepared['review_id'],report=report)
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(),before)

    def test_source_report_removal_invalidates_candidate_without_touching_ledger(self):
        self.save_plan();self.refs();self.source_cache();prepared,report=self.prepare_review()
        self.call('submit_source_review',review_id=prepared['review_id'],report=report)
        candidate=self.call('generate_ledger');before=Path(self.project['ledger_path']).read_bytes()
        Path(self.project['directory'],'规划源码核对.md').unlink()
        with self.assertRaises(RequestError):self.save_candidate(candidate)
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(),before)

    def test_external_edit_during_source_validation_cannot_commit_old_candidate(self):
        for filename in ('项目规划书.md','GitHub参考项目.md','规划源码核对.md'):
            with self.subTest(filename=filename):
                self.project=self.service.call('create_project', {'name':filename,'mode':'create'})['project']
                self.save_plan();self.refs();self.source_cache();prepared,report=self.prepare_review()
                self.call('submit_source_review',review_id=prepared['review_id'],report=report)
                candidate=self.call('generate_ledger');before=Path(self.project['ledger_path']).read_bytes()
                target=Path(self.project['directory'],filename); original=target.read_text()
                changed=original+'\n外部同时更新内容。\n'
                if filename=='GitHub参考项目.md':
                    record=planning_research.read_research(original);record['repositories'][0]['selected']=False
                    changed=planning_research.research_markdown(record)
                old_git=project_service.source.git; entered=[]
                def concurrent_edit(args, cwd=None, timeout=60):
                    if 'config' in args and not entered:
                        entered.append(True);target.write_text(changed)
                    return old_git(args,cwd=cwd,timeout=timeout)
                with patch.object(project_service.source,'git',side_effect=concurrent_edit):
                    with self.assertRaises(RequestError):self.save_candidate(candidate)
                self.assertTrue(entered)
                self.assertEqual(target.read_text(),changed)
                self.assertEqual(Path(self.project['ledger_path']).read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
