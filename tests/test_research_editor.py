import json
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from ledger_context_fixture import legacy_no_reference_context
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

# 旧网页编排集成类已归档到 legacy_web/test_research_editor.py。
