import concurrent.futures
import time
import unittest
import test_research_editor as existing
import test_projects

module=existing.dashboard.planning_module('planning_progress')

class ProgressTests(unittest.TestCase):
    def test_monotonic_failure_scope_and_context(self):
        store=module.Progress();token=store.start('a','operation-one')
        try:
            module.step(50,'Codex','等待输出');module.step(20,'检查下一项')
            self.assertEqual(store.read('a','operation-one')['percent'],50)
            self.assertEqual(store.read('b','operation-one')['status'],'pending')
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(module.step,90,'其他线程').result()
            self.assertEqual(store.read('a','operation-one')['percent'],50)
            store.finish(('a','operation-one'),'失败');module.step(90,'不能覆盖失败')
            self.assertEqual(store.read('a','operation-one')['status'],'failed')
            self.assertEqual(store.read('a','operation-one')['percent'],50)
        finally:module.CURRENT.reset(token)
        with self.assertRaises(ValueError):store.start('a','operation-one')
        with self.assertRaises(ValueError):store.start('a','../bad')

    def test_completed_history_reclaimed_without_expiring_running_task(self):
        store=module.Progress();token=store.start('a','long-running')
        store.records[('a','long-running')]['started']-=3600
        module.CURRENT.reset(token)
        for i in range(520):
            identity='finished-%04d'%i;token=store.start('a',identity)
            store.finish(('a',identity));module.CURRENT.reset(token)
        self.assertEqual(len(store.records),512)
        self.assertEqual(store.read('a','long-running')['status'],'running')
        store.step(('a','long-running'),50,'仍在处理');store.finish(('a','long-running'))
        self.assertEqual(store.read('a','long-running')['percent'],100)

class ProgressHttpTests(test_projects.ManagerTest):
    test_project_isolation_external_edits_and_restart=None
    test_unknown_scope_and_conflict_fail_closed=None
    test_existing_acceptance_survives_and_fabrication_is_rejected=None
    test_registry_and_cross_document_collisions_are_rejected=None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved=None

    def test_running_codex_then_complete_and_failure(self):
        project=self.request('/api/projects',{'name':'progress','directory':'progress','mode':'new'})[1]['project']
        other=self.request('/api/projects',{'name':'other','directory':'other','mode':'new'})[1]['project']
        suffix='?project='+project['id']; op='operation-http-test'
        path='/api/operation-progress'+suffix+'&operation='+op
        release=self.fake_bin/'release'
        fake=self.fake_bin/'codex'
        fake.write_text(fake.read_text().replace('reply = ', 'import time\nwhile not pathlib.Path('+repr(str(release))+').exists(): time.sleep(.02)\nreply = '))
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending=pool.submit(self.request,'/api/planning'+suffix,{'intent':'chat','messages':[{'role':'user','content':'检查需求'}]},{'X-Operation-ID':op})
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    state=self.request(path)[1]
                    if state['percent']==50:break
                    time.sleep(.02)
                self.assertEqual(state['status'],'running');self.assertEqual(state['percent'],50)
                self.assertIn('Codex',state['stage'])
                self.assertEqual(self.request('/api/operation-progress?project='+other['id']+'&operation='+op)[1]['status'],'pending')
            finally:release.touch()
            self.assertEqual(pending.result()[0],200)
        completed=self.request(path)[1];self.assertEqual(completed['percent'],100);self.assertEqual(completed['status'],'completed')
        status,_=self.request('/api/plan/table'+suffix,{'content':''},{'X-Operation-ID':'operation-failure'})
        self.assertEqual(status,400)
        failed=self.request('/api/operation-progress'+suffix+'&operation=operation-failure')[1]
        self.assertEqual(failed['status'],'failed');self.assertLess(failed['percent'],100)
        self.assertEqual(self.request('/api/planning'+suffix,{}, {'X-Operation-ID':op})[0],400)
        self.assertEqual(self.request(path)[1]['status'],'completed','duplicate id cannot overwrite completed operation')
