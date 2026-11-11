import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import test_projects as project_tests
import test_research_editor as workflow_tests

dashboard=workflow_tests.dashboard
research=dashboard.planning_module('planning_research')
history=dashboard.planning_module('planning_history')
PLAN=workflow_tests.PLAN

# 旧网页编排集成类已归档到 legacy_web/test_references_history.py。

class HistoryFailureTest(unittest.TestCase):
    def test_archive_failure_restores_file_keeps_pending_and_can_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            store=dashboard.ProjectStore(workspace=Path(temp));p=store.register({'name':'pending','directory':'pending','mode':'new'})
            path=Path(p['plan_path']);before=path.read_bytes();revision=dashboard.digest(before)
            store.generated_plans[p['ledger_path']]=(dashboard.digest(PLAN.encode()),revision)
            with patch.object(history,'commit',side_effect=OSError('archive unavailable')):
                with self.assertRaises(OSError):store.save_plan(p,PLAN,revision)
            self.assertEqual(path.read_bytes(),before);self.assertFalse(store.planning_state(store.project(p['id']))['ready']);self.assertEqual(history.list_versions(p),[])
            self.assertEqual(list(history.history_directory(p).glob('.pending-*')),[])
            self.assertTrue(store.save_plan(p,PLAN,revision)['planning']['ready']);self.assertEqual(len(history.list_versions(p)),1)

    def test_archive_failure_on_ready_project_preserves_previous_document_and_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            store=dashboard.ProjectStore(workspace=Path(temp));p=store.register({'name':'ready','directory':'ready','mode':'new'});revision=dashboard.read_document(Path(p['plan_path']))['revision'];store.generated_plans[p['ledger_path']]=(dashboard.digest(PLAN.encode()),revision)
            saved=store.save_plan(p,PLAN,revision);p=store.project(p['id']);versions=history.list_versions(p)
            with patch.object(history,'commit',side_effect=OSError('archive unavailable')):
                with self.assertRaises(OSError):store.save_plan(p,PLAN+'\n改动',saved['revision'])
            self.assertEqual(Path(p['plan_path']).read_text(),PLAN);self.assertEqual(history.list_versions(p),versions)

    def test_crlf_and_tamper_detection_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p={'directory':str(root),'plan_path':str(root/'plan.md'),'ledger_path':str(root/'ledger.md')}
            content=PLAN.replace('\n','\r\n');staged=history.stage(p,content,'用户保存','说明',[]);version=history.commit(staged)
            self.assertEqual(history.read_version(p,version['id'])['content'],content)
            (history.history_directory(p)/'v-自己的笔记.md').write_text('其他文档');self.assertEqual(len(history.list_versions(p)),1)
            with staged['target'].open('a') as file:file.write('改动')
            with self.assertRaisesRegex(ValueError,'改动'):history.read_version(p,version['id'])
