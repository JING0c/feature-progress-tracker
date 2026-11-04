import unittest
import tempfile
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import planning_activity as activity
from test_research_editor import PLAN

class ActivityTests(unittest.TestCase):
    def test_changes_and_roundtrip(self):
        updated=PLAN.replace('预约','预约管理')
        event=activity.event('/api/plan/save',{}, {'content':updated},200,PLAN)
        self.assertIn('已保存',event['title'])
        self.assertIn('预约管理',event['detail'])
        with tempfile.TemporaryDirectory() as d:
            project={'directory':d,'plan_path':d+'/项目规划书.md','ledger_path':d+'/功能执行情况.md'}
            event['detail']+='\n<!-- records [] -->\n<!-- event fake -->'
            activity.append(project,event)
            self.assertEqual(activity.read(project)[0]['detail'],event['detail'])
            self.assertIn('预约管理',Path(d,'规划操作记录.md').read_text())
    def test_preview_failure_and_polling(self):
        event=activity.event('/api/plan/suggestions/preview',{}, {'diff':'-old\n+new'},200,'')
        self.assertIn('尚未保存',event['title'])
        failed=activity.event('/api/plan/save',{}, {'error':'版本冲突'},409,'')
        self.assertEqual(failed['state'],'failed');self.assertIn('版本冲突',failed['detail'])
        self.assertIsNone(activity.event('/api/plan/table',{}, {},200,''))
    def test_conflicting_path_and_corrupt_record(self):
        with tempfile.TemporaryDirectory() as d:
            project={'directory':d,'plan_path':d+'/规划操作记录.md','ledger_path':d+'/ledger.md'}
            with self.assertRaises(ValueError): activity.read(project)
            project['plan_path']=d+'/plan.md'
            Path(d,'规划操作记录.md').write_text('bad')
            with self.assertRaises(ValueError): activity.append(project,{'title':'test'})

    def test_existing_history_is_shown_without_writing_activity(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            history.commit(history.stage(p,PLAN,'用户保存','旧保存',[]))
            records=activity.listing(p)
            self.assertEqual(records[0]['state'],'history')
            self.assertIn('旧保存',records[0]['detail'])
            self.assertFalse(Path(d,'规划操作记录.md').exists())
