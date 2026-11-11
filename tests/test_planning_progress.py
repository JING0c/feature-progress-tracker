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

# 旧网页编排集成类已归档到 legacy_web/test_planning_progress.py。
