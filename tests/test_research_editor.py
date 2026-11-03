import json
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import test_projects as project_tests
import test_planning_export as export_tests

dashboard=export_tests.dashboard
editor=dashboard.planning_module('planning_editor')
research=dashboard.planning_module('planning_research')
PLAN=export_tests.PLAN.replace('| 依赖 | 备注 |','| 依赖 | 所需技术 | 前期准备 | 采用 | 备注 |').replace('|---|---|---|---|---|---|---|---|','|---|---|---|---|---|---|---|---|---|---|---|').replace('| 未开始 |','| Python（建议） | 准备器材清单 | 是 | 未开始 |').replace('| 未审核 |','| SQLite（建议） | 确认时间规则 | 是 | 未审核 |').replace('| 待分配 |','| 待确认 | 准备边界样例 | 是 | 待分配 |')

class ResearchAndEditorTest(unittest.TestCase):
    def test_roundtrip_preserves_surroundings_unknown_columns_and_pipes(self):
        plan=PLAN+'\n## 历史\n2026-01-01：保留原决定。\n'
        table=editor.editable_table(plan)
        table['rows'][1]['说明']='A|B\\C\n两行'
        updated=editor.replace_features(plan,table['rows'])
        self.assertEqual(editor.editable_table(updated)['rows'][1]['说明'],'A|B\\C\n两行')
        self.assertEqual(updated.split('## 功能规划')[0],plan.split('## 功能规划')[0])
        self.assertTrue(updated.endswith('## 历史\n2026-01-01：保留原决定。\n'))

    def test_parent_selection_cascades_and_child_selection_restores_ancestors(self):
        result=editor.select_feature(PLAN,'F01',False)
        self.assertTrue(all(r['采用']=='否' for r in editor.editable_table(result)['rows']))
        result=editor.select_feature(result,'F01-01-01',True)
        self.assertTrue(all(r['采用']=='是' for r in editor.editable_table(result)['rows']))

    def test_invalid_or_inconsistent_graph_rejected(self):
        for change in ('duplicate','cycle','missing','adoption','prefix'):
            rows=editor.editable_table(PLAN)['rows']
            if change=='duplicate': rows[1]['编号']='F01'
            if change=='cycle': rows[0]['上级编号']='F01-01'
            if change=='missing': rows[1]['上级编号']='F99'
            if change=='adoption': rows[0]['采用']='否'
            if change=='prefix': rows[2]['上级编号']='F01'
            with self.assertRaises(ValueError): editor.replace_features(PLAN,rows)

    def test_blank_adoption_defaults_to_selected_and_can_save(self):
        plan=PLAN.replace('| 是 |','|  |')
        rows=editor.editable_table(plan)['rows']
        self.assertTrue(all(r['采用']=='是' for r in rows))
        self.assertIn('| 是 |',editor.replace_features(plan,rows))

    def test_legacy_or_multiple_tables_do_not_get_silently_replaced(self):
        with self.assertRaises(ValueError): editor.editable_table('# 旧规划\n### 功能\n- 手动描述')
        with self.assertRaises(ValueError): editor.editable_table(PLAN+'\n'+PLAN)

    def test_research_is_bounded_real_data_and_does_not_trust_urls(self):
        data={'items':[{'full_name':'org/project','html_url':'javascript:bad','description':'Example','license':{'spdx_id':'MIT'}}]}
        with patch.object(research,'github_json',side_effect=[data,{'encoding':'base64','content':'IyBSZWFkIHNvdXJjZQ=='}]):
            result=research.search_repositories('ticket management')
        self.assertTrue(result['completed']);self.assertEqual(result['repositories'][0]['url'],'https://github.com/org/project')
        self.assertIn('Read source',result['repositories'][0]['readme'])
        saved=research.research_markdown(result)
        self.assertEqual(research.read_research(saved),result)
        with patch.object(research,'github_json',return_value={'items':[]}): self.assertEqual(research.search_repositories('nothing')['repositories'],[])
        with patch.object(research,'github_json',side_effect=ValueError('rate limit')):
            with self.assertRaisesRegex(ValueError,'rate limit'):research.search_repositories('ticket')

    def test_malformed_research_does_not_look_successful(self):
        with self.assertRaises(ValueError):research.read_research('```json\n[]\n```')
        with patch.object(research,'github_json',return_value=[]):
            with self.assertRaises(ValueError):research.search_repositories('ticket')

class WorkflowHttpTest(project_tests.ManagerTest):
    test_project_isolation_external_edits_and_restart=None
    test_unknown_scope_and_conflict_fail_closed=None
    test_existing_acceptance_survives_and_fabrication_is_rejected=None
    test_registry_and_cross_document_collisions_are_rejected=None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved=None

    def ready(self):
        p=self.request('/api/projects',{'name':'编辑测试','directory':'editor','mode':'new'})[1]['project'];suffix='?project='+p['id']
        self.generate_plan(p,PLAN);revision=self.request('/api/plan'+suffix)[1]['revision']
        self.assertEqual(self.request('/api/plan/save'+suffix,{'content':PLAN,'revision':revision})[0],200)
        return p,suffix

    def test_editor_conversion_is_read_only_and_save_conflict_keeps_disk(self):
        p,suffix=self.ready();before=Path(p['plan_path']).read_text();meta=self.request('/api/plan'+suffix)[1]
        rows=self.request('/api/plan/features'+suffix,{'content':before})[1]['rows'];rows[1]['所需技术']='用户指定 Python'
        code,data=self.request('/api/plan/features'+suffix,{'content':before,'rows':rows});self.assertEqual(code,200,data)
        self.assertEqual(Path(p['plan_path']).read_text(),before)
        Path(p['plan_path']).write_text(before+'\n外部修改')
        self.assertEqual(self.request('/api/plan/save'+suffix,{'content':data['content'],'revision':meta['revision']})[0],409)
        self.assertTrue(Path(p['plan_path']).read_text().endswith('外部修改'))

    def test_adoption_tech_prepare_export_and_declined_dependency_cannot_bypass(self):
        p,suffix=self.ready();revision=self.request('/api/plan'+suffix)[1]['revision']
        data=self.request('/api/plan/features'+suffix,{'content':PLAN,'selection':{'id':'F01-01-01','selected':False}})[1]
        self.assertEqual(self.request('/api/plan/save'+suffix,{'content':data['content'],'revision':revision})[0],200)
        model=self.request('/api/plan/table'+suffix,{'content':data['content']})[1]
        listing=model['sheets'][0];self.assertEqual(listing['columns'][0],'采用');self.assertIn('所需技术',listing['columns']);self.assertIn('前期准备',listing['columns'])
        self.assertTrue(any(r['cells'][0]=='否' for r in listing['rows']))
        # Mention in a dependency is not an existing historical feature node.
        Path(p['ledger_path']).write_text(project_tests.ledger('旧项')+'\n备注：依赖 F01-01-01\n')
        declined=project_tests.ledger('不采用项').replace('F01-01','F01-01-01')
        code,reply=self.request('/api/ledger/preview'+suffix,{'content':declined});self.assertEqual(code,400,reply);self.assertIn('未采用',reply['error'])
        all_declined=editor.select_feature(data['content'],'F01',False)
        revision=self.request('/api/plan'+suffix)[1]['revision']
        self.assertEqual(self.request('/api/plan/save'+suffix,{'content':all_declined,'revision':revision})[0],200)
        prompt_before=self.fake_prompt.read_bytes()
        code,reply=self.request('/api/planning'+suffix,{'intent':'ledger','messages':[{'role':'user','content':'生成台账'}]})
        self.assertEqual(code,400,reply);self.assertIn('勾选',reply['error']);self.assertEqual(self.fake_prompt.read_bytes(),prompt_before)

    def test_research_is_project_scoped_persistent_and_required_by_new_client(self):
        p,suffix=self.ready()
        code,data=self.request('/api/planning'+suffix,{'intent':'chat','research_first':True,'messages':[{'role':'user','content':'需求'}]})
        self.assertEqual(code,409,data)
        record={'version':1,'completed':True,'query':'ticket','repositories':[]}
        Path(p['directory'],'GitHub参考项目.md').write_text(research.research_markdown(record))
        self.stop();self.start()
        self.assertTrue(self.request('/api/research'+suffix)[1]['completed'])
        self.assertEqual(self.request('/api/research?project=missing')[0],404)
        code,data=self.request('/api/planning'+suffix,{'intent':'decompose','research_first':True,'messages':[{'role':'user','content':'增加统计功能，先讨论拆分'}]})
        self.assertEqual(code,200,data);self.assertIn('最多两个关键问题',self.fake_prompt.read_text());self.assertIn('GitHub调研资料',self.fake_prompt.read_text())
        self.assertEqual(Path(p['plan_path']).read_text(),PLAN)

    def test_new_feature_research_uses_its_description_and_keeps_selected_sources(self):
        project, suffix = self.ready()
        idea = '增加按仓库盘点和库存流水'
        self.fake_reply.write_text('{"query": ""}')
        code, _ = self.request('/api/research' + suffix, {'feature_idea': idea})
        self.assertEqual(code, 400)
        self.assertIn(idea, self.fake_prompt.read_text())
        self.assertIn('优先按这次新增功能提取关键词', self.fake_prompt.read_text())

        record = {'version': 1, 'completed': True, 'query': 'inventory', 'feature_idea': idea,
                  'repositories': [{'name': 'test/inventory', 'readme': 'inventory movements evidence'},
                                   {'name': 'test/other', 'readme': 'unselected repo evidence'}]}
        Path(project['directory'], 'GitHub参考项目.md').write_text(research.research_markdown(record))
        data = self.request('/api/research' + suffix)[1]
        self.assertEqual(data['feature_idea'], idea)
        code, selected = self.request('/api/research/selection' + suffix,
                                      {'revision': data['revision'], 'selected': ['test/inventory']})
        self.assertEqual(code, 200, selected)
        self.assertEqual(selected['feature_idea'], idea)
        code, reply = self.request('/api/planning' + suffix, {'intent': 'decompose', 'research_first': True,
                                   'messages': [{'role': 'user', 'content': idea}]})
        self.assertEqual(code, 200, reply)
        prompt = self.fake_prompt.read_text()
        self.assertIn('inventory movements evidence', prompt)
        self.assertNotIn('unselected repo evidence', prompt)
        self.assertIn('附仓库链接', prompt)
        self.assertEqual(Path(project['plan_path']).read_text(), PLAN)

    def test_confirmed_feature_merge_preserves_existing_rows_and_saves_new_rows(self):
        project, suffix = self.ready()
        previous = editor.editable_table(PLAN)['rows']
        changed = [dict(row) for row in previous]
        changed[0]['功能名称'] = '模型改写的旧名称'
        new = dict(previous[-1], 编号='F02', 上级编号='无', 功能名称='参考图片')
        duplicate = dict(previous[0], 编号='F03')
        self.fake_reply.write_text(editor.replace_features(PLAN, changed + [new, duplicate]))
        proposal_text = '新增参考图片，能保存并打开原图。\n<!-- feature-proposal -->'
        code, proposal = self.request('/api/planning' + suffix, {'intent': 'plan', 'merge_feature': True,
                                      'feature_proposal': proposal_text,
                                      'messages': [{'role': 'assistant', 'content': proposal_text},
                                                   {'role': 'user', 'content': '确认追加参考图片'}]})
        self.assertEqual(code, 200, proposal)
        merged = editor.editable_table(proposal['reply'])['rows']
        self.assertEqual(merged, previous + [new])
        self.assertEqual(Path(project['plan_path']).read_text(), PLAN)
        version = self.request('/api/plan' + suffix)[1]['revision']
        code, saved = self.request('/api/plan/save' + suffix,
                                   {'revision': version, 'content': proposal['reply']})
        self.assertEqual(code, 200, saved)
        self.assertIn('history_version', saved)

    def test_empty_technical_columns_and_multiline_content_remain_in_projection(self):
        _,suffix=self.ready()
        rows=editor.editable_table(PLAN)['rows']
        for row in rows:row['所需技术']='';row['前期准备']=''
        content=editor.replace_features(PLAN,rows)
        model=self.request('/api/plan/table'+suffix,{'content':content})[1]
        self.assertIn('所需技术',model['sheets'][0]['columns']);self.assertIn('前期准备',model['sheets'][0]['columns'])
        rows[1]['前期准备']='第一项\n第二项'
        content=editor.replace_features(PLAN,rows)
        model=self.request('/api/plan/table'+suffix,{'content':content})[1]
        self.assertNotIn('<br>',json.dumps(model,ensure_ascii=False));self.assertIn('第一项\\n第二项',json.dumps(model,ensure_ascii=False))
        listing=model['sheets'][0];row=next(r for r in listing['rows'] if r['feature_id']=='F01-01')
        self.assertEqual(row['cells'][listing['columns'].index('前期准备')],'第一项\n第二项')

    def test_maximum_chinese_research_is_readable_after_save(self):
        p,suffix=self.ready()
        record={'version':1,'completed':True,'query':'中文','repositories':[{'name':'org/repo'+str(i),'description':'文'*2000,'readme':'文'*8000 if i<3 else ''} for i in range(5)]}
        document=research.research_markdown(record)
        self.assertGreater(len(document.encode()),100000)
        Path(p['directory'],'GitHub参考项目.md').write_text(document)
        code,data=self.request('/api/research'+suffix);self.assertEqual(code,200,data);self.assertTrue(data['completed'])
