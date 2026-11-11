"""Host-chat orchestration uses deterministic, revision-bound operations."""
import json
import concurrent.futures
import subprocess
import time
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_service import ProjectService
from serve_dashboard import RequestError

PLAN = '''# 图书角项目规划书
## 项目目标与场景
帮助管理员登记借阅，读者查看可借图书。
## 范围与边界
本期仅管理本地图书借阅，不实现在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 | 依赖 |
|---|---|---|---|---|---|---|
| F01 | 无 | 图书管理 | 维护图书目录 | 可登记并找到图书 | 是 | 无 |
| F01-01 | F01 | 登记图书 | 输入名称保存图书 | 保存后列表可见图书 | 是 | 无 |
| F02 | 无 | 导出图书 | 下载图书清单 | 文件能打开并包含图书 | 是 | F01-01 |
'''

class ProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name) / '管理目录'
        self.service = ProjectService(str(self.workspace), actor='codex')
        self.project = self.service.call('create_project', {'name':'图书角','mode':'create'})['project']
        self.pid = self.project['id']

    def call(self, action, **payload):
        return self.service.call(action, {'project_id':self.pid, **payload})

    def plan(self):
        read = self.call('read_project')
        return self.call('save_plan', content=PLAN, revision=read['plan']['revision'])

    def test_initial_plan_required_then_history_and_ledger_roundtrip(self):
        with self.assertRaises(RequestError): self.call('generate_ledger')
        result = self.plan()
        self.assertTrue(result['planning']['ready'])
        candidate = self.call('generate_ledger')
        saved = self.call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                          plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])
        self.assertEqual(saved['summary']['total'], 2)
        self.assertEqual(saved['summary']['done'], 0)
        self.assertTrue(self.call('history')['records'])

    def test_edit_preview_does_not_save_and_duplicate_revision_is_rejected(self):
        self.plan(); before = self.call('read_project')
        preview = self.call('edit_features', revision=before['plan']['revision'],
                            updates=[{'id':'F01-01','fields':{'验收标准':'保存后按名称搜索可见图书'}}],
                            additions=[{'key':'N1','parent':'F01','功能名称':'修改图书','说明':'修改名称','验收标准':'改后名称立即可见'}])
        self.assertIn('F01-02', preview['added'])
        self.assertEqual(self.call('read_project')['plan']['revision'], before['plan']['revision'])
        self.call('save_plan', content=preview['content'], revision=preview['revision'])
        with self.assertRaises(RequestError): self.call('save_plan', content=PLAN, revision=before['plan']['revision'])

    def test_removal_cannot_leave_dependency_or_erase_every_row(self):
        self.plan(); revision=self.call('read_project')['plan']['revision']
        with self.assertRaises(ValueError): self.call('edit_features', revision=revision, remove_ids=['F01'])
        with self.assertRaises(ValueError): self.call('edit_features', revision=revision, remove_ids=['F01','F02'])

    def test_direct_save_validates_numbered_dependencies_but_allows_preparation_text(self):
        revision=self.call('read_project')['plan']['revision']
        with self.assertRaises(ValueError):
            self.call('save_plan',content=PLAN.replace('| 是 | F01-01 |','| 是 | F99-99 |'),revision=revision)
        self.assertEqual(self.call('read_project')['plan']['revision'],revision)
        saved=self.call('save_plan',content=PLAN.replace('| 是 | F01-01 |','| 是 | 模板素材准备；F01-01 |'),revision=revision)
        self.assertTrue(saved['saved'])

    def test_ledger_candidate_is_bound_to_source_report_and_project(self):
        self.plan()
        baseline=self.call('generate_ledger')
        prepared=self.call('prepare_source_review')
        report={'features':[{'id':i,'status':'未找到依据','finding':'未选择参考仓库','evidence':[]} for i in ('F01','F01-01','F02')]}
        self.call('submit_source_review',review_id=prepared['review_id'],report=report)
        old=self.call('generate_ledger')
        report['features'][0]['finding']='未选择参考仓库，暂按当前规划实现'
        self.call('submit_source_review',review_id=prepared['review_id'],report=report)
        current=self.call('generate_ledger')
        self.assertNotEqual(old['source_revision'],current['source_revision'])
        with self.assertRaises(RequestError):
            self.call('save_ledger',content=old['content'],revision=old['ledger_revision'],plan_revision=old['plan_revision'],source_revision=old['source_revision'])
        other=self.service.call('create_project',{'name':'另一个图书角'})['project']['id']
        before=self.service.call('read_project',{'project_id':other})
        self.service.call('save_plan',{'project_id':other,'revision':before['plan']['revision'],'content':PLAN})
        second=self.service.call('generate_ledger',{'project_id':other})
        self.assertNotEqual(baseline['source_revision'],second['source_revision'])

    def test_declined_children_cannot_be_silently_reintroduced(self):
        self.plan(); revision=self.call('read_project')['plan']['revision']
        preview=self.call('edit_features', revision=revision, selections=[{'id':'F01','selected':False}])
        self.call('save_plan', content=preview['content'], revision=revision)
        candidate=self.call('generate_ledger')
        self.assertNotIn('- [ ] F01-01',candidate['content'])

    def test_old_plan_or_reference_binding_cannot_save_ledger(self):
        self.plan(); candidate=self.call('generate_ledger')
        self.call('save_plan', content=PLAN+'\n## 风险\n需定期备份。\n', revision=candidate['plan_revision'])
        with self.assertRaises(RequestError): self.call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                          plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])

    def test_malformed_or_cross_project_payloads_are_rejected(self):
        with self.assertRaises((ValueError, RequestError)): self.call('read_project', project_id='../outside')
        with self.assertRaises((ValueError, RequestError)): self.call('save_plan', content='# 未完成', revision='x')
        with self.assertRaises((ValueError, RequestError)): self.call('create_project', name='bad', mode='unknown')

    def test_export_history_uses_unique_project_paths(self):
        self.plan(); first=self.call('export_project', format='xlsx'); second=self.call('export_project', format='xlsx')
        self.assertNotEqual(first['path'],second['path'])
        self.assertTrue(Path(first['path']).is_relative_to(Path(self.project['directory'])/'exports'))
        versions=self.call('history')['versions']
        old=self.call('export_project', format='markdown', version_id=versions[0]['id'])
        self.assertEqual(Path(old['path']).read_text(),PLAN)

    def test_source_review_ticket_and_reference_revisions(self):
        self.plan()
        result={'version':1,'completed':True,'selection_confirmed':False,'query':'library','repositories':[{'name':'org/books','selected':False}]}
        with patch('project_service.research.search_repositories', return_value=result):
            refs=self.call('search_references', query='library')
        self.call('select_references', revision=refs['revision'], selected=['org/books'])
        sources={'repositories':[{'name':'org/books','commit':'a'*40,'files_read':1,'state':'已克隆','path':'unused'}],
                 'snippets':[{'repository':'org/books','path':'src/app.py','start':1,'end':2,'text':'1: x=1','commit':'a'*40}], 'scope':'静态节选'}
        with patch('project_service.source.collect_sources', return_value=sources):
            prepared=self.call('prepare_source_review')
            report={'features':[{'id':i,'status':'部分依据','finding':'有入口，异常需确认','evidence':[{'repository':'org/books','path':'src/app.py','line':1}]} for i in ('F01','F01-01','F02')]}
            other=self.service.call('create_project',{'name':'另一个','mode':'create'})['project']['id']
            with self.assertRaises((ValueError,RequestError)):
                self.service.call('submit_source_review',{'project_id':other,'review_id':prepared['review_id'],'report':report})
            completed=self.call('submit_source_review', review_id=prepared['review_id'], report=report)
            self.assertTrue(Path(completed['path']).is_file())
            candidate=self.call('generate_ledger')
            self.assertTrue(candidate['source_revision'])
            refs=self.call('read_project')['references']
            self.call('select_references',revision=refs['revision'],selected=[])
            with self.assertRaises(RequestError): self.call('save_ledger',content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])

    def test_suggestions_record_preview_then_save_and_stale_rejection(self):
        self.plan(); before=self.call('read_project')
        suggestion=[{'title':'补充重复处理','reason':'登记图书需要处理重复', 'changes':[{'action':'update','id':'F01-01','fields':{'验收标准':'重复ISBN明确提示，不重复登记'}}]}]
        recorded=self.call('record_suggestions',revision=before['plan']['revision'],suggestions=suggestion,analyst='独立审核助手A')
        self.assertFalse(recorded['adopted'])
        self.assertIn('独立审核助手A',Path(recorded['path']).read_text())
        self.assertEqual(self.call('read_project')['plan']['revision'],before['plan']['revision'])
        preview=self.call('preview_suggestions',revision=before['plan']['revision'],suggestion_id=recorded['id'],selected=['S01'])
        self.assertIn('重复ISBN',preview['content']); self.assertFalse(preview['saved'])
        saved=self.call('save_plan',content=preview['content'],revision=preview['revision'])
        self.assertTrue(self.call('read_project')['suggestions']['stale'])
        with self.assertRaises(RequestError): self.call('preview_suggestions',revision=saved['revision'],suggestion_id=recorded['id'],selected=['S01'])

    def test_replaced_suggestions_on_same_plan_reject_old_selection(self):
        self.plan(); revision=self.call('read_project')['plan']['revision']
        item={'title':'补充重复处理','reason':'登记图书需要处理重复','changes':[{'action':'update','id':'F01-01','fields':{'验收标准':'重复ISBN明确提示'}}]}
        old=self.call('record_suggestions',revision=revision,suggestions=[item],analyst='助手A')
        item['changes'][0]['fields']['验收标准']='ISBN空白拒绝提交'
        new=self.call('record_suggestions',revision=revision,suggestions=[item],analyst='助手B')
        self.assertNotEqual(old['id'],new['id'])
        with self.assertRaises(RequestError): self.call('preview_suggestions',revision=revision,suggestion_id=old['id'],selected=['S01'])

    def test_read_existing_workspace_does_not_create_state_files(self):
        import shutil
        shutil.rmtree(self.workspace/'.feature-progress-tracker')
        before=sorted(str(p.relative_to(self.workspace)) for p in self.workspace.rglob('*'))
        self.call('read_project'); self.call('history')
        self.assertEqual(before, sorted(str(p.relative_to(self.workspace)) for p in self.workspace.rglob('*')))

    def test_two_services_cannot_both_save_same_revision(self):
        self.plan(); revision=self.call('read_project')['plan']['revision']
        def write(index):
            other=ProjectService(str(self.workspace),actor='claude')
            try:
                other.call('save_plan', {'project_id':self.pid,'revision':revision,'content':PLAN+'\n## 风险\n备份方案'+str(index)+'。\n'})
                return 'saved'
            except RequestError:
                return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write, [1,2]))
        self.assertCountEqual(results,['saved','conflict'])

    def test_forged_ledger_completion_and_extra_rows_are_rejected(self):
        self.plan(); candidate=self.call('generate_ledger')
        for content in [candidate['content'].replace('- [ ]','- [x]').replace('状态：未开始','状态：已完成'),
                        candidate['content']+'\n- [ ] F02-01 伪造功能｜状态：未开始\n']:
            with self.assertRaises((RequestError,ValueError)):
                self.call('save_ledger',content=content,revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])

    def test_export_symlink_and_invalid_review_identity_are_rejected(self):
        self.plan(); target=Path(self.project['directory'])/'exports'
        target.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(ValueError): self.call('export_project',format='markdown')
        with self.assertRaises(ValueError): self.call('submit_source_review',review_id='../wrong',report={})

    def test_progress_changes_use_current_ledger_revision(self):
        self.plan(); candidate=self.call('generate_ledger')
        saved=self.call('save_ledger',content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
        changed=self.call('update_feature_progress',revision=saved['revision'],feature_id='F01-01',changes={'状态':'进行中','执行 Agent':'codex','实现证据':'提交 abc123，测试已启动'})
        self.assertIn('状态：进行中',changed['content'])
        with self.assertRaises(RequestError): self.call('update_feature_progress',revision=saved['revision'],feature_id='F01-01',changes={'状态':'待审核'})

    def test_imported_initial_plan_cannot_relabel_existing_ledger_ids(self):
        self.plan(); candidate=self.call('generate_ledger')
        self.call('save_ledger',content=candidate['content'],revision=candidate['ledger_revision'],plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
        Path(self.project['plan_path']).write_text('# 原始资料\n')
        revision=self.call('read_project')['plan']['revision']
        with self.assertRaises(RequestError): self.call('save_plan',content=PLAN.replace('登记图书','完全不同功能'),revision=revision)

    def test_source_review_rejects_plan_changes(self):
        self.plan(); prepared=self.call('prepare_source_review')
        report={'features':[{'id':i,'status':'未找到依据','finding':'未选择参考','evidence':[]} for i in ('F01','F01-01','F02')]}
        self.call('save_plan',content=PLAN+'\n## 风险\n需要备份。\n',revision=prepared['binding']['plan_revision'])
        with self.assertRaises(RequestError): self.call('submit_source_review',review_id=prepared['review_id'],report=report)

    def test_invalid_source_evidence_cannot_be_persisted(self):
        self.plan(); prepared=self.call('prepare_source_review')
        report={'features':[{'id':i,'status':'有源码依据','finding':'伪造引用','evidence':[{'repository':'fake/repo','path':'not-read.py','line':1}]} for i in ('F01','F01-01','F02')]}
        with self.assertRaises(ValueError): self.call('submit_source_review',review_id=prepared['review_id'],report=report)
        self.assertFalse((Path(self.project['directory'])/'规划源码核对.md').exists())

    def test_cross_process_writes_hold_lock_before_atomic_replace(self):
        self.plan(); revision=self.call('read_project')['plan']['revision']
        signals=Path(self.tmp.name)/'signals'; signals.mkdir()
        script = '''import json,sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from project_service import ProjectService
from serve_dashboard import RequestError
import serve_dashboard as d
workspace,pid,revision,content,signals,index=sys.argv[2:]
signals=Path(signals); original=d.atomic_write
def gate(path,*args,**kwargs):
    if path.name=='项目规划书.md':
        (signals/('entered'+index)).touch()
        until=time.monotonic()+8
        while not (signals/'release').exists():
            if time.monotonic()>until: raise RuntimeError('test barrier timeout')
            time.sleep(.01)
    return original(path,*args,**kwargs)
(signals/('ready'+index)).touch()
try:
    with patch('serve_dashboard.atomic_write',side_effect=gate):
        ProjectService(workspace).call('save_plan',{'project_id':pid,'revision':revision,'content':content+'\\n## 风险\\n进程'+index+'备份。\\n'})
    print('saved')
except RequestError: print('conflict')
'''
        commands = [[sys.executable,'-c',script,str(Path(__file__).resolve().parents[1]/'scripts'),str(self.workspace),self.pid,revision,PLAN,str(signals),str(i)] for i in (1,2)]
        children = [subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for cmd in commands]
        try:
            deadline=time.monotonic()+5
            while not (all((signals/('ready'+str(i))).exists() for i in (1,2)) and list(signals.glob('entered*'))):
                if time.monotonic()>deadline: self.fail('children did not reach lock test')
                time.sleep(.01)
            time.sleep(.15)
            self.assertEqual(len(list(signals.glob('entered*'))),1)
        finally:
            (signals/'release').touch()
            outputs=[child.communicate(timeout=10) for child in children]
        self.assertCountEqual([out.strip() for out,err in outputs],['saved','conflict'],outputs)
        self.assertTrue(all(child.returncode==0 for child in children),outputs)

    def test_imported_project_shared_by_two_workspaces_preserves_revision(self):
        self.plan()
        other=ProjectService(str(Path(self.tmp.name)/'第二个管理目录'),actor='claude')
        imported=other.call('create_project',{'name':'共享图书角','mode':'import','directory':self.project['directory']})['project']
        doc=other.call('read_project',{'project_id':imported['id']})['plan']
        other.call('save_plan',{'project_id':imported['id'],'revision':doc['revision'],'content':PLAN})
        def write(pair):
            svc,pid,n=pair
            try:
                svc.call('save_plan',{'project_id':pid,'revision':doc['revision'],'content':PLAN+'\n## 风险\n方案'+n+'。\n'})
                return 'saved'
            except RequestError: return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,[(self.service,self.pid,'A'),(other,imported['id'],'B')]))
        self.assertCountEqual(results,['saved','conflict'])

if __name__ == '__main__': unittest.main()
