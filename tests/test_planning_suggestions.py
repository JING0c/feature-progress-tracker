import unittest
import copy
import test_research_editor as existing

class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.module=existing.dashboard.planning_module('planning_suggestions')
        self.plan=existing.PLAN
        self.id=existing.editor.editable_table(self.plan)['rows'][1]['编号']
    def test_selected_patch_preserves_other_rows_and_prose(self):
        raw={'suggestions':[{'title':'完善验收','reason':'边界未说明','changes':[{'action':'update','id':self.id,'fields':{'验收标准':'输入无效时提示原因，并允许重试。'}}]}]}
        record=self.module.validate(raw,self.plan)
        updated=self.module.apply(self.plan,record['suggestions'],['S01'])
        before=existing.editor.editable_table(self.plan)['rows'];after=existing.editor.editable_table(updated)['rows']
        self.assertEqual(before[0],after[0]);self.assertEqual(before[1]['采用'],after[1]['采用'])
        self.assertEqual(after[1]['验收标准'],'输入无效时提示原因，并允许重试。')
        self.assertEqual(updated.split('## 功能规划')[0],self.plan.split('## 功能规划')[0])
    def test_cannot_remove_renumber_or_silently_adopt_existing_rows(self):
        for change in ({'action':'delete','id':self.id,'fields':{}},{'action':'update','id':self.id,'fields':{'编号':'F99'}},{'action':'update','id':self.id,'fields':{'采用':'否'}},{'action':'add','id':self.id,'fields':{'功能名称':'重复'}}):
            with self.assertRaises(ValueError):self.module.validate({'suggestions':[{'title':'变更','reason':'原因','changes':[change]}]},self.plan)
    def test_empty_unknown_and_conflicting_choices_rejected(self):
        suggestions=self.module.validate({'suggestions':[{'title':str(i),'reason':'建议','changes':[{'action':'update','id':self.id,'fields':{'说明':str(i)}}]} for i in (1,2)]},self.plan)['suggestions']
        for selected in ([],['UNKNOWN'],['S01','S02'],['S01','S01']):
            with self.assertRaises(ValueError): self.module.apply(self.plan,suggestions,selected)

    def test_saved_record_fences_and_reordered_ids(self):
        raw={'suggestions':[{'title':str(i),'reason':'说明\n```json\n{"plan_revision":"evil"}\n```','changes':[{'action':'update','id':self.id,'fields':{'说明':str(i)}}]} for i in (1,2)]}
        record=self.module.validate(raw,self.plan)
        record['plan_revision']='real'
        self.assertEqual(self.module.read(self.module.markdown(record)),record)
        legacy='# 功能建议\n'+raw['suggestions'][0]['reason']+'\n```json\n'+json.dumps(record,ensure_ascii=False)+'\n```\n'
        self.assertEqual(self.module.read(legacy),record)
        record['suggestions'].reverse()
        checked=self.module.validate(record,self.plan,preserve_ids=True)
        result=self.module.apply(self.plan,checked['suggestions'],['S02'])
        self.assertEqual(existing.editor.editable_table(result)['rows'][1]['说明'],'2')
        record['suggestions'][1]['id']='S02'
        with self.assertRaises(ValueError):self.module.validate(record,self.plan,preserve_ids=True)

import json
from pathlib import Path
import test_projects

class SuggestionHttpTests(test_projects.ManagerTest):
    test_project_isolation_external_edits_and_restart=None
    test_unknown_scope_and_conflict_fail_closed=None
    test_existing_acceptance_survives_and_fabrication_is_rejected=None
    test_registry_and_cross_document_collisions_are_rejected=None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved=None

    def setup_plan(self,name):
        p=self.request('/api/projects',{'name':name,'directory':name,'mode':'new'})[1]['project']
        self.generate_plan(p,existing.PLAN)
        suffix='?project='+p['id'];revision=self.request('/api/plan'+suffix)[1]['revision']
        code,data=self.request('/api/plan/save'+suffix,{'content':existing.PLAN,'revision':revision})
        self.assertEqual(code,200,data)
        return p,suffix,data['revision']

    def test_generate_preview_edit_save_and_reload_isolated(self):
        p,suffix,rev=self.setup_plan('advice-a');q,other,_=self.setup_plan('advice-b')
        fid=existing.editor.editable_table(existing.PLAN)['rows'][1]['编号']
        self.fake_reply.write_text(json.dumps({'suggestions':[{'title':'增加校验','reason':'当前流程缺少输入异常说明','changes':[{'action':'update','id':fid,'fields':{'验收标准':'输入异常可重试，不丢失已填字段。'}}]}]},ensure_ascii=False))
        code,data=self.request('/api/plan/suggestions'+suffix,{'revision':rev,'focus':'异常输入'})
        self.assertEqual(code,200,data);self.assertEqual(Path(p['plan_path']).read_text(),existing.PLAN)
        self.assertIn('独立的功能建议子智能体',self.fake_prompt.read_text())
        self.assertEqual(self.request('/api/plan/suggestions'+other)[1]['suggestions'],[])
        self.stop();self.start()
        stored=self.request('/api/plan/suggestions'+suffix)[1];self.assertEqual(stored['id'],data['id'])
        code,preview=self.request('/api/plan/suggestions/preview'+suffix,{'revision':rev,'suggestion_id':data['id'],'selected':['S01']})
        self.assertEqual(code,200,preview);self.assertIn('输入异常可重试',preview['diff'])
        self.assertEqual(Path(p['plan_path']).read_text(),existing.PLAN)
        code,saved=self.request('/api/plan/save'+suffix,{'revision':rev,'content':preview['content'].replace('输入异常可重试','用户调整后可重试'),'source':'功能表编辑','note':'采纳建议后调整'})
        self.assertEqual(code,200,saved);self.assertIn('用户调整后可重试',Path(p['plan_path']).read_text())
        self.assertEqual(self.request('/api/plan/suggestions/preview'+suffix,{'revision':saved['revision'],'suggestion_id':data['id'],'selected':['S01']})[0],409)
        self.assertEqual(Path(q['plan_path']).read_text(),existing.PLAN)
        history=self.request('/api/plan/history'+suffix)[1]['versions'];self.assertEqual(history[0]['note'],'采纳建议后调整')
        activities=self.request('/api/plan/activity'+suffix)[1]['records']
        self.assertTrue(any('未采纳' in r['title'] for r in activities))
        self.assertTrue(any('尚未保存' in r['title'] and '输入异常可重试' in r['detail'] for r in activities))
        self.assertTrue(any(r['title']=='功能表已保存' and '修改前：' in r['detail'] and '用户调整后可重试' in r['detail'] for r in activities))
        self.assertTrue(any(r['state']=='failed' for r in activities))
        self.assertFalse(any('用户调整后可重试' in r['detail'] for r in self.request('/api/plan/activity'+other)[1]['records']))
        self.assertTrue(Path(p['directory'],'规划操作记录.md').exists())
        self.stop();self.start()
        self.assertEqual(self.request('/api/plan/activity'+suffix)[1]['records'],activities)


    def test_bad_model_reply_and_unselected_invalid_patch_do_not_write_plan(self):
        p,suffix,rev=self.setup_plan('bad-advice')
        for reply in ('invalid','{"suggestions":[{"title":"bad","reason":"bad","changes":[{"action":"delete","id":"F01","fields":{}}]}]}'):
            self.fake_reply.write_text(reply)
            self.assertEqual(self.request('/api/plan/suggestions'+suffix,{'revision':rev})[0],400)
            self.assertEqual(Path(p['plan_path']).read_text(),existing.PLAN)
            self.assertFalse(Path(p['directory'],'功能建议.md').exists())
