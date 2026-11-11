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

    def test_new_suggestions_cannot_reuse_reserved_group_or_feature_ids(self):
        for identity,parent in (('F02','无'),('F01-02','F01')):
            with self.subTest(identity=identity):
                raw={'suggestions':[{'title':'新增历史同名功能','reason':'验收已变更',
                    'changes':[{'action':'add','id':identity,'fields':{
                        '上级编号':parent,'功能名称':'历史功能','说明':'新需求',
                        '验收标准':'只有新验收通过后才可完成。'}}]}]}
                record=self.module.validate(raw,self.plan)
                with self.assertRaisesRegex(ValueError,identity):
                    self.module.apply(self.plan,record['suggestions'],['S01'],reserved_ids={identity})
                with self.assertRaisesRegex(ValueError,identity):
                    self.module.validate(raw,self.plan,reserved_ids={identity})

    def test_reserved_existing_update_and_unused_new_id_remain_allowed(self):
        raw={'suggestions':[{'title':'修改当前功能并新增','reason':'补充边界',
            'changes':[
                {'action':'update','id':self.id,'fields':{'验收标准':'新的边界条件可验收。'}},
                {'action':'add','id':'F03','fields':{'上级编号':'无',
                    '功能名称':'全新功能','说明':'新功能说明','验收标准':'可独立验收。'}}]}]}
        reserved={'F01',self.id,'F02'}
        record=self.module.validate(raw,self.plan,reserved_ids=reserved)
        result=self.module.apply(self.plan,record['suggestions'],['S01'],reserved_ids=reserved)
        rows={row['编号']:row for row in existing.editor.editable_table(result)['rows']}
        self.assertEqual(rows[self.id]['验收标准'],'新的边界条件可验收。')
        self.assertEqual(rows[self.id]['采用'],'是')
        self.assertEqual(rows['F03']['功能名称'],'全新功能')
        self.assertEqual(rows['F03']['采用'],'是')

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

# 旧网页编排集成类已归档到 legacy_web/test_planning_suggestions.py。
