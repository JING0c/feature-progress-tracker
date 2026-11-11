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

class ReferencesHistoryHttpTest(project_tests.ManagerTest):
    test_project_isolation_external_edits_and_restart=None
    test_unknown_scope_and_conflict_fail_closed=None
    test_existing_acceptance_survives_and_fabrication_is_rejected=None
    test_registry_and_cross_document_collisions_are_rejected=None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved=None

    def project(self,name='versions'):
        return self.request('/api/projects',{'name':name,'directory':name,'mode':'new'})[1]['project']

    def refs(self,p):
        data={'version':1,'completed':True,'selection_confirmed':False,'query':'example',
              'repositories':[{'name':'org/one','url':'javascript:bad','readme':'FIRST_UNCHOSEN'},
                              {'name':'org/two','url':'https://github.com/org/two','readme':'SECOND_SELECTED'}]}
        Path(p['directory'],'GitHub参考项目.md').write_text(research.research_markdown(data))
        return self.request('/api/research?project='+p['id'])[1]

    def select(self,p,names):
        suffix='?project='+p['id'];data=self.request('/api/research'+suffix)[1]
        return self.request('/api/research/selection'+suffix,{'revision':data['revision'],'selected':names})

    def save(self,p,content=PLAN,note='',source='用户保存',generate=False):
        suffix='?project='+p['id']
        if generate:self.generate_plan(p,content)
        revision=self.request('/api/plan'+suffix)[1]['revision']
        return self.request('/api/plan/save'+suffix,{'content':content,'revision':revision,'source':source,'note':note})

    def versions(self,p):return self.request('/api/plan/history?project='+p['id'])[1]['versions']

    def test_multiple_selection_persists_and_only_selected_sources_enter_prompt(self):
        p=self.project();suffix='?project='+p['id'];self.refs(p)
        code,data=self.request('/api/planning'+suffix,{'intent':'chat','research_first':True,'messages':[{'role':'user','content':'需求'}]})
        self.assertEqual(code,409,data)
        code,data=self.select(p,['org/one','org/two']);self.assertEqual(code,200,data)
        self.assertTrue(all(r['selected'] for r in data['repositories']))
        self.select(p,['org/two']);self.stop();self.start()
        data=self.request('/api/research'+suffix)[1]
        self.assertEqual([r['selected'] for r in data['repositories']],[False,True]);self.assertTrue(data['selection_confirmed'])
        self.request('/api/planning'+suffix,{'intent':'chat','research_first':True,'messages':[{'role':'user','content':'需求'}]})
        prompt=self.fake_prompt.read_text();self.assertIn('SECOND_SELECTED',prompt);self.assertNotIn('FIRST_UNCHOSEN',prompt);self.assertNotIn('org/one',prompt)

    def test_explicit_empty_selection_is_supported_without_changing_feature_adoption(self):
        p=self.project();self.refs(p);code,data=self.select(p,[])
        self.assertEqual(code,200,data);self.assertTrue(data['selection_confirmed']);self.assertFalse(any(r['selected'] for r in data['repositories']))
        self.assertEqual(self.save(p,generate=True)[0],200)
        content=Path(p['plan_path']).read_text();self.assertEqual(content,PLAN)
        self.assertEqual(self.versions(p)[0]['references'],[])

    def test_selection_conflict_unknown_candidates_and_project_isolation(self):
        p=self.project();other=self.project('other');data=self.refs(p);suffix='?project='+p['id']
        self.select(p,['org/two'])
        code,_=self.request('/api/research/selection'+suffix,{'revision':data['revision'],'selected':['org/one']});self.assertEqual(code,409)
        for names in (['org/unknown'],['org/one','org/one'],[1]):self.assertEqual(self.select(p,names)[0],400)
        code,_=self.request('/api/research/selection?project='+other['id'],{'revision':data['revision'],'selected':['org/one']});self.assertEqual(code,400)
        self.assertFalse(self.request('/api/research?project='+other['id'])[1]['completed'])

    def test_each_successful_save_is_immutable_and_retains_its_reference_context(self):
        p=self.project();suffix='?project='+p['id'];self.refs(p);self.select(p,['org/one'])
        code,first=self.save(p,note='初稿',generate=True);self.assertEqual(code,200,first)
        first_id=first['history_version']['id'];self.select(p,['org/two'])
        changed=PLAN.replace('器材登记','器材维护')
        self.assertEqual(self.save(p,changed,note='调整范围')[0],200)
        self.assertEqual(self.save(p,changed,note='确认同版')[0],200)
        versions=self.versions(p);self.assertEqual(len(versions),3);self.assertEqual(len({v['id'] for v in versions}),3)
        old=self.request('/api/plan/history'+suffix+'&version='+first_id)[1]
        self.assertEqual(old['content'],PLAN);self.assertEqual(old['references'][0]['name'],'org/one');self.assertEqual(old['note'],'初稿')
        latest=self.request('/api/plan/history'+suffix+'&version='+versions[0]['id'])[1]
        self.assertEqual(latest['references'][0]['name'],'org/two');self.assertEqual(latest['content'],changed)
        previous=self.request('/api/plan/history'+suffix+'&version='+versions[1]['id'])[1]
        self.assertIn('-首期只做器材登记',previous['diff']);self.assertIn('+首期只做器材维护',previous['diff'])
        self.assertEqual(Path(p['plan_path']).read_text(),changed)

    def test_history_survives_restart_is_scoped_and_exports_old_content(self):
        p=self.project();other=self.project('other');first=self.save(p,generate=True)[1]['history_version']['id'];self.save(p,PLAN+'\n新修改')
        self.stop();self.start();self.assertEqual(len(self.versions(p)),2)
        self.assertEqual(self.request('/api/plan/history?project='+other['id']+'&version='+first)[0],404)
        self.assertEqual(self.request('/api/plan/history?project='+p['id']+'&version=../../outside')[0],400)
        version=self.request('/api/plan/history?project='+p['id']+'&version='+first)[1]
        import urllib.request
        request=urllib.request.Request(self.url+'/api/plan/export?project='+p['id'],data=json.dumps({'content':version['content']}).encode(),headers={'Content-Type':'application/json','X-Planning-Token':self.token})
        with urllib.request.urlopen(request) as response:raw=response.read()
        with ZipFile(BytesIO(raw)) as z:
            ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};wb=ET.fromstring(z.read('xl/workbook.xml'));count=len(wb.findall('s:sheets/s:sheet',ns));sheet=ET.fromstring(z.read('xl/worksheets/sheet'+str(count)+'.xml'))
            text=''.join(c.find('s:is/s:t',ns).text or '' for c in sheet.findall('s:sheetData/s:row/s:c',ns) if c.attrib['r'].startswith('B') and c.attrib['r']!='B1')
            self.assertEqual(text,PLAN)
        self.assertTrue(Path(p['plan_path']).read_text().endswith('新修改'))

    def test_invalid_conflicting_saves_do_not_create_versions(self):
        p=self.project();suffix='?project='+p['id'];self.save(p,generate=True);before=self.versions(p)
        self.assertEqual(self.save(p,'# 只有标题')[0],400)
        self.assertEqual(self.request('/api/plan/save'+suffix,{'content':PLAN,'revision':'stale'})[0],409)
        self.assertEqual(self.versions(p),before);self.assertEqual(list(history.history_directory(p).glob('.pending-*')),[])

    def test_external_file_change_is_captured_before_next_webpage_save(self):
        p=self.project();self.save(p,generate=True);external=PLAN+'\n外部AI修改\n';Path(p['plan_path']).write_text(external)
        self.save(p,PLAN+'\n网页再次修改\n');versions=self.versions(p)
        self.assertEqual(len(versions),3);prior=next(v for v in versions if v['source']=='保存前文件版本')
        self.assertEqual(self.request('/api/plan/history?project='+p['id']+'&version='+prior['id'])[1]['content'],external)

    def test_readable_snapshot_survives_unrelated_corrupt_metadata(self):
        p=self.project();self.save(p,generate=True)
        changed=PLAN+'\n第二次保存\n';latest=self.save(p,changed)[1]['history_version']
        versions=self.versions(p);older=versions[1]
        Path(p['directory'],'规划历史',older['id']+'.md').write_text('broken metadata')
        before={f.relative_to(p['directory']):f.read_bytes() for f in Path(p['directory']).rglob('*') if f.is_file()}
        code,listing=self.request('/api/plan/activity?project='+p['id'])
        self.assertEqual(code,200,listing)
        self.assertIn(latest['id'],[r.get('snapshot',{}).get('id') for r in listing['records']])
        code,data=self.request('/api/plan/history?project='+p['id']+'&version='+latest['id'])
        self.assertEqual(code,200,{'message':'a listed readable snapshot must remain openable','response':data})
        self.assertEqual(data['content'],changed)
        self.assertTrue(data.get('warnings'),'unreadable metadata must be disclosed')
        self.assertIn('无法',data['diff'],'unknown chronological metadata cannot imply this is the earliest save')
        self.assertEqual(before,{f.relative_to(p['directory']):f.read_bytes() for f in Path(p['directory']).rglob('*') if f.is_file()})
        code,_=self.save(p,changed+'\n新写入\n')
        self.assertGreaterEqual(code,400,'read tolerance must not relax strict save validation')
        self.assertEqual(Path(p['plan_path']).read_text(),changed)

    def test_readable_snapshot_survives_corrupt_previous_body(self):
        p=self.project();first=self.save(p,generate=True)[1]['history_version']
        changed=PLAN+'\n第二次保存\n';latest=self.save(p,changed)[1]['history_version']
        prior=Path(p['directory'],'规划历史',first['id']+'.md')
        prior.write_text(prior.read_text()+'\ncorrupted body')
        before={f.relative_to(p['directory']):f.read_bytes() for f in Path(p['directory']).rglob('*') if f.is_file()}
        code,data=self.request('/api/plan/history?project='+p['id']+'&version='+latest['id'])
        self.assertEqual(code,200,data)
        self.assertEqual(data['content'],changed)
        self.assertTrue(data.get('warnings'),'a missing comparison must be visible')
        self.assertIn('无法',data['diff'])
        self.assertEqual(before,{f.relative_to(p['directory']):f.read_bytes() for f in Path(p['directory']).rglob('*') if f.is_file()})

    def test_selected_corrupt_snapshot_is_still_rejected(self):
        p=self.project();version=self.save(p,generate=True)[1]['history_version']
        target=Path(p['directory'],'规划历史',version['id']+'.md')
        target.write_text(target.read_text()+'\ncorrupted body')
        code,data=self.request('/api/plan/history?project='+p['id']+'&version='+version['id'])
        self.assertGreaterEqual(code,400,data)
        self.assertNotIn('content',data)

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
