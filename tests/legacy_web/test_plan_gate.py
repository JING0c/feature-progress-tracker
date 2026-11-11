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


class PlanGateTest(project_tests.ManagerTest):
    test_project_isolation_external_edits_and_restart = None
    test_unknown_scope_and_conflict_fail_closed = None
    test_existing_acceptance_survives_and_fabrication_is_rejected = None
    test_registry_and_cross_document_collisions_are_rejected = None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved = None

    def pending(self, name, **options):
        code, data = self.request('/api/projects', {'name':name, 'directory':name, **options})
        self.assertEqual(code, 200, data)
        return data['project']

    def save_plan(self, p, text=VALID_PLAN, revision=None, generate=True):
        suffix = '?project=' + p['id']
        if generate:
            self.generate_plan(p, text)
        if revision is None:
            revision = self.request('/api/plan'+suffix)[1]['revision']
        return self.request('/api/plan/save'+suffix, {'content':text,'revision':revision})

    def assert_locked(self, p):
        suffix = '?project=' + p['id']
        content = project_tests.ledger('测试')
        revision = self.request('/api/ledger/info'+suffix)[1]['revision']
        for endpoint, payload in [('/api/ledger',None),('/api/ledger/preview',{'content':content}),('/api/ledger/save',{'content':content,'revision':revision}),('/api/planning',{'intent':'ledger','messages':[{'role':'user','content':'生成功能台账'}]})]:
            code, data = self.request(endpoint+suffix, payload)
            self.assertEqual(code,409,(endpoint,data))
            self.assertEqual(data['code'],'planning_required')
            self.assertEqual(data['planning_url'],'/planning'+suffix)

    def test_new_project_has_no_board_or_ledger_until_valid_plan_saved(self):
        p = self.pending('new', mode='new')
        self.assertFalse(p['planning']['ready'])
        self.assertEqual(p['source'],'new')
        self.assert_locked(p)
        self.assertEqual(self.save_plan(p, VALID_PLAN, generate=False)[0],409)
        with urllib.request.urlopen(self.url+'/?project='+p['id']) as response:
            self.assertEqual(response.url,self.url+'/planning?project='+p['id'])
        row = self.request('/api/projects')[1]['projects'][0]
        self.assertIsNone(row['summary'])
        self.assertNotIn('error',row)
        for invalid in ('# 项目规划书\n', '# 项目规划书\n尚未生成规划书，请在规划页面梳理需求。', '# 项目规划书\n## 目标\n待补充\n## 范围\nTODO\n## 功能与验收\n待规划'):
            self.assertEqual(self.save_plan(p,invalid)[0],400)
            self.assert_locked(p)
        code, saved = self.save_plan(p)
        self.assertEqual(code,200,saved)
        self.assertTrue(saved['planning']['ready'])
        self.assertEqual(self.request('/api/ledger?project='+p['id'])[0],200)
        self.assertIn('规划状态：已生成',(self.workspace/'项目列表.md').read_text())

    def test_import_preserves_existing_documents_but_requires_new_saved_plan(self):
        directory = self.workspace/'imported'
        directory.mkdir()
        plan = directory/'项目规划书.md'; plan.write_text(VALID_PLAN)
        ledger = directory/'功能执行情况.md'; ledger.write_text(project_tests.ledger('已验收','已完成',True))
        before = ledger.read_bytes()
        p = self.pending('imported',mode='import')
        self.assertEqual(p['source'],'import')
        self.assertFalse(p['planning']['ready'])
        self.assertEqual(plan.read_text(),VALID_PLAN)
        self.assertEqual(ledger.read_bytes(),before)
        self.assert_locked(p)
        self.assertEqual(self.save_plan(p,VALID_PLAN,generate=False)[1]['code'],'plan_generation_required')
        code, result = self.save_plan(p,VALID_PLAN.replace('管理员','社区管理员'))
        self.assertEqual(code,200,result)
        self.assertTrue(result['planning']['ready'])
        self.assertEqual(Path(result['backup']).read_text(),VALID_PLAN)
        self.assertEqual(ledger.read_bytes(),before)

    def test_state_survives_restart_deleted_or_placeholder_plan_relocks(self):
        p = self.pending('persistent')
        self.assertEqual(self.save_plan(p)[0],200)
        self.stop(); self.start()
        self.assertTrue(self.request('/api/project?project='+p['id'])[1]['planning']['ready'])
        Path(p['plan_path']).unlink()
        self.assert_locked(p)
        self.assertFalse(self.request('/api/plan?project='+p['id'])[1]['planning']['ready'])
        self.assertEqual(self.save_plan(p)[0],200)
        Path(p['plan_path']).write_text('# 项目规划书\n待规划')
        self.assert_locked(p)

    def test_conflict_does_not_unlock_other_project_remains_locked(self):
        a,b = self.pending('a'),self.pending('b')
        old = self.request('/api/plan?project='+a['id'])[1]['revision']
        Path(a['plan_path']).write_text('# 外部草稿\n尚未完成')
        self.assertEqual(self.save_plan(a,revision=old)[0],409)
        self.assert_locked(a)
        self.assertEqual(self.save_plan(a)[0],200)
        self.assert_locked(b)

    def test_old_registry_uses_valid_plan_but_never_placeholder(self):
        p = self.pending('legacy')
        registry = self.workspace/'项目列表.md'
        text = '\n'.join(line for line in registry.read_text().splitlines() if not line.startswith(('项目来源：','规划状态：')))+'\n'
        registry.write_text(text)
        self.assert_locked(p)
        Path(p['plan_path']).write_text(VALID_PLAN)
        self.assertTrue(self.request('/api/project?project='+p['id'])[1]['planning']['ready'])
        self.assertEqual(self.request('/api/ledger?project='+p['id'])[0],200)

    def test_import_requires_directory_and_metadata_is_explicit(self):
        self.assertEqual(self.request('/api/projects',{'name':'bad','directory':'missing','mode':'import'})[0],400)
        self.assertEqual(self.request('/api/projects',{'name':'bad','directory':'missing','mode':'other'})[0],400)
        directory = self.workspace/'existing'; directory.mkdir()
        (directory/'README.md').write_text('# 已有项目\n这是现有资料。')
        p = self.pending('existing')
        self.assertEqual(p['source'],'import')
        self.assertFalse(p['planning']['ready'])
        code, data = self.request('/api/planning?project='+p['id'],{'intent':'invalid','messages':[{'role':'user','content':'test'}]})
        self.assertEqual(code,400,data)

    def test_generated_plan_binding_requires_same_project_revision_and_content(self):
        a,b = self.pending('bound-a'),self.pending('bound-b')
        self.generate_plan(a,VALID_PLAN)
        self.assertEqual(self.save_plan(b,generate=False)[1]['code'],'plan_generation_required')
        self.assertEqual(self.save_plan(a,VALID_PLAN.replace('管理员','读者'),generate=False)[1]['code'],'plan_generation_required')
        Path(a['plan_path']).write_text('# 外部编辑后的草稿')
        self.assertEqual(self.save_plan(a,generate=False)[1]['code'],'plan_generation_required')
        self.generate_plan(a,VALID_PLAN)
        self.stop(); self.start()
        self.assertEqual(self.save_plan(a,generate=False)[1]['code'],'plan_generation_required')
        self.assert_locked(a)
        self.assertEqual(self.save_plan(a)[0],200)

    def test_chat_is_not_plan_generation_and_import_context_is_confined(self):
        directory = self.workspace/'context'; directory.mkdir()
        outside = Path(self.temp.name)/'secret.md'; outside.write_text('OUTSIDE_SECRET')
        (directory/'README.md').symlink_to(outside)
        (directory/'功能执行情况.md').write_text(project_tests.ledger('既有资料'))
        p = self.pending('context',mode='import')
        self.fake_reply.write_text(VALID_PLAN)
        self.assertEqual(self.request('/api/planning?project='+p['id'], {'intent':'chat','messages':[{'role':'user','content':'生成规划'}]})[0],200)
        self.assertEqual(self.save_plan(p,generate=False)[1]['code'],'plan_generation_required')
        self.generate_plan(p,VALID_PLAN)
        prompt = self.fake_prompt.read_text()
        self.assertIn('既有资料',prompt)
        self.assertNotIn('OUTSIDE_SECRET',prompt)
        self.assertIn('尚未完成规划',prompt)
        (directory/'README.md').unlink(); (directory/'README.md').write_text('正常项目README参考资料')
        self.generate_plan(p,VALID_PLAN)
        self.assertIn('正常项目README参考资料',self.fake_prompt.read_text())

    def test_invalid_registry_metadata_does_not_fall_back_to_legacy_ready(self):
        p = self.pending('invalid-meta')
        Path(p['plan_path']).write_text(VALID_PLAN)
        registry = self.workspace/'项目列表.md'
        registry.write_text(registry.read_text().replace('项目来源：本机新建','项目来源：错误来源'))
        self.assertEqual(self.request('/api/project?project='+p['id'])[0],400)

    def test_damaged_encoding_locks_but_can_be_regenerated_with_backup(self):
        p = self.pending('broken-encoding')
        self.assertEqual(self.save_plan(p)[0],200)
        Path(p['plan_path']).write_bytes(b'\xff\xfeinvalid encoding')
        self.assert_locked(p)
        code, doc = self.request('/api/plan?project='+p['id'])
        self.assertEqual(code,200,doc)
        self.assertFalse(doc['planning']['ready'])
        code, saved = self.save_plan(p)
        self.assertEqual(code,200,saved)
        self.assertEqual(Path(saved['backup']).read_bytes(), b'\xff\xfeinvalid encoding')

    def test_imported_ledger_encoding_does_not_block_planning_metadata(self):
        directory = self.workspace/'legacy-encoding'; directory.mkdir()
        ledger = directory/'功能执行情况.md'; ledger.write_bytes(b'\xff\xfeledger')
        p = self.pending('legacy-encoding',mode='import')
        code, meta = self.request('/api/ledger/info?project='+p['id'])
        self.assertEqual(code,200,meta)
        self.assertEqual(meta['revision'],dashboard.digest(b'\xff\xfeledger'))
        self.generate_plan(p)
        self.assertEqual(ledger.read_bytes(),b'\xff\xfeledger')


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
