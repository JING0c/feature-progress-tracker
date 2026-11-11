"""New and imported projects must save a real project plan before continuing."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

import test_projects as project_tests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate_dashboard', ROOT / 'scripts/serve_dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)

VALID_PLAN = '''# 项目规划书
## 目标
帮助管理员在本机管理图书借阅，避免重复借出。
## 范围
包括图书登记、借还记录和逾期名单；不做支付。
## 功能与验收
图书登记后按编号可查到；借出的图书不能重复借出。
'''


# 旧网页编排集成类已归档到 legacy_web/test_plan_gate.py。


class PlanContentTest(unittest.TestCase):
    def test_required_categories_need_body_not_just_headers(self):
        self.assertTrue(dashboard.inspect_plan(VALID_PLAN)['valid'])
        empty = '# 项目规划书\n## 目标\n## 范围\n## 功能与验收\n'
        self.assertFalse(dashboard.inspect_plan(empty)['valid'])
        self.assertFalse(dashboard.inspect_plan(VALID_PLAN.replace('图书登记后按编号可查到；借出的图书不能重复借出。','待补充'))['valid'])
        for placeholder in ('待补充项目目标', 'TODO: Add project goals here', 'TBD: to be decided later', '**待完善功能需求**', '请填写验收标准'):
            with self.subTest(placeholder=placeholder):
                template = '# 项目规划书\n' + '\n'.join('## '+title+'\n'+placeholder for title in ('目标','范围','功能','验收'))
                self.assertFalse(dashboard.inspect_plan(template)['valid'])
        self.assertTrue(dashboard.inspect_plan(VALID_PLAN.replace('不做支付。','不做支付。具体编号格式待确认。'))['valid'])

    def test_real_project_plans_are_accepted(self):
        plan = (ROOT/'项目规划书.md').read_text()
        self.assertTrue(dashboard.inspect_plan(plan)['valid'])

    def test_failed_registry_save_keeps_pending_even_if_document_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            store = dashboard.ProjectStore(workspace=Path(temp))
            p = store.register({'name':'失败','directory':'failed','mode':'new'})
            revision = dashboard.read_document(Path(p['plan_path']))['revision']
            store.generated_plans[p['ledger_path']] = (dashboard.digest(VALID_PLAN.encode()),revision)
            original = dashboard.atomic_write
            def fail_registry(path, *args, **kwargs):
                if path == store.registry:
                    raise OSError('simulated registry write failure')
                return original(path,*args,**kwargs)
            with patch.object(dashboard,'atomic_write',side_effect=fail_registry):
                with self.assertRaises(OSError):
                    store.save_plan(p,VALID_PLAN,revision)
            self.assertFalse(store.planning_state(store.project(p['id']))['ready'])
            self.assertFalse(dashboard.ProjectStore(workspace=Path(temp)).planning_state(store.project(p['id']))['ready'])

    def test_single_project_requires_plan_and_saved_generation_unlocks(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'ledger.md'; path.write_text(project_tests.ledger('single'))
            store = dashboard.ProjectStore(ledger=path)
            p = store.single()
            self.assertFalse(store.planning_state(p)['ready'])
            with self.assertRaises(dashboard.RequestError):
                store.require_planning(p)
            with self.assertRaises(dashboard.RequestError):
                store.save_plan(p,VALID_PLAN,dashboard.EMPTY_HASH)
            store.generated_plans[p['ledger_path']] = (dashboard.digest(VALID_PLAN.encode()),dashboard.EMPTY_HASH)
            self.assertTrue(store.save_plan(p,VALID_PLAN,dashboard.EMPTY_HASH)['planning']['ready'])
            Path(p['plan_path']).unlink()
            self.assertFalse(store.planning_state(p)['ready'])


if __name__ == '__main__': unittest.main()
