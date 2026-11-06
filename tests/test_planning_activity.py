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

    def test_saved_record_links_exact_snapshot_without_duplicate_or_writing(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            version=history.commit(history.stage(p,PLAN,'功能表编辑','补充预约',[]))
            event=activity.event('/api/plan/save',{}, {'content':PLAN,'history_version':version},200,'')
            activity.append(p,event)
            before={f.relative_to(d):f.read_bytes() for f in Path(d).rglob('*') if f.is_file()}
            records=activity.listing(p)
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['id'],event['id'])
            self.assertEqual(records[0].get('snapshot'),{k:version[k] for k in ('id','saved_at','source','note')})
            self.assertEqual(before,{f.relative_to(d):f.read_bytes() for f in Path(d).rglob('*') if f.is_file()})
            self.assertNotIn('snapshot',activity.read(p)[0],'read-only projection must not rewrite existing logs')

    def test_legacy_snapshots_keep_identity_and_explain_archive_time(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            early=history.commit(history.stage(p,PLAN,'用户保存','早期保存',[]))
            backup=history.commit(history.stage(p,PLAN+'\n旧文件补充','保存前文件版本','已有文件归档',[]))
            records={r.get('history_version'):r for r in activity.listing(p)}
            self.assertEqual(set(records),{early['id'],backup['id']})
            self.assertEqual(records[early['id']]['title'],'早期保存的功能表')
            self.assertEqual(records[backup['id']]['title'],'保存前的功能表备份')
            self.assertIn('原修改时间未知',records[backup['id']]['detail'])
            for version in (early,backup):
                record=records[version['id']]
                self.assertEqual(record['state'],'history')
                self.assertEqual(record['snapshot']['id'],version['id'])
                self.assertIn('不是补记操作',record['detail'])
            self.assertFalse(Path(d,'规划操作记录.md').exists())

    def test_preview_and_failure_do_not_link_or_hide_saved_snapshot(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            version=history.commit(history.stage(p,PLAN,'用户保存','',[]))
            preview=activity.event('/api/plan/suggestions/preview',{}, {'diff':'new','history_version':version},200,'')
            failed=activity.event('/api/plan/save',{}, {'error':'冲突','history_version':version},409,'')
            activity.append(p,preview);activity.append(p,failed)
            records=activity.listing(p)
            self.assertEqual(len(records),3)
            for record in records:
                if record['id'] in (preview['id'],failed['id']):self.assertNotIn('snapshot',record)
                else:self.assertEqual(record['snapshot']['id'],version['id'])

    def test_missing_snapshot_keeps_log_and_marks_missing_reference(self):
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            event=activity.event('/api/plan/save',{}, {'content':PLAN,'history_version':{'id':'v-'+'a'*32}},200,'')
            activity.append(p,event)
            records=activity.listing(p)
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['detail'],event['detail'])
            self.assertTrue(records[0].get('snapshot_missing'))
            self.assertNotIn('snapshot',records[0])

    def test_same_content_in_different_saves_is_not_deduplicated(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            versions=[history.commit(history.stage(p,PLAN,'用户保存',note,[])) for note in ('第一次','第二次')]
            for version in versions:
                activity.append(p,activity.event('/api/plan/save',{}, {'content':PLAN,'history_version':version},200,PLAN))
            records=activity.listing(p)
            self.assertEqual(len(records),2)
            self.assertEqual({r.get('snapshot',{}).get('id') for r in records},{v['id'] for v in versions})

    def test_tolerant_listing_keeps_snapshots_when_log_is_corrupt(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            version=history.commit(history.stage(p,PLAN,'用户保存','仍可追溯',[]))
            Path(d,'规划操作记录.md').write_text('broken log')
            before={f.relative_to(d):f.read_bytes() for f in Path(d).rglob('*') if f.is_file()}
            warnings=[]
            records=activity.listing(p,warnings=warnings)
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['snapshot']['id'],version['id'])
            self.assertTrue(any('操作记录' in message for message in warnings))
            self.assertEqual(before,{f.relative_to(d):f.read_bytes() for f in Path(d).rglob('*') if f.is_file()})
            with self.assertRaises(ValueError):activity.listing(p)

    def test_tolerant_listing_keeps_readable_records_when_snapshots_are_corrupt(self):
        import planning_history as history
        with tempfile.TemporaryDirectory() as d:
            p={'directory':d,'plan_path':d+'/plan.md','ledger_path':d+'/ledger.md'}
            good=history.commit(history.stage(p,PLAN,'用户保存','有效保存',[]))
            bad_meta=history.commit(history.stage(p,PLAN,'用户保存','坏元数据',[]))
            bad_body=history.commit(history.stage(p,PLAN,'用户保存','坏正文',[]))
            for version in (good,bad_meta,bad_body):
                activity.append(p,activity.event('/api/plan/save',{}, {'content':PLAN,'history_version':version},200,''))
            Path(d,'规划历史',bad_meta['id']+'.md').write_text('broken metadata')
            body_path=Path(d,'规划历史',bad_body['id']+'.md')
            body_path.write_text(body_path.read_text()+'\nchanged body')
            before={f.relative_to(d):f.read_bytes() for f in Path(d).rglob('*') if f.is_file()}
            warnings=[]
            records=activity.listing(p,warnings=warnings)
            self.assertEqual(len(records),3,'corrupt snapshots must not erase their real save events')
            linked={r['history_version']:r for r in records}
            self.assertEqual(linked[good['id']]['snapshot']['id'],good['id'])
            for version in (bad_meta,bad_body):
                self.assertNotIn('snapshot',linked[version['id']])
                self.assertTrue(linked[version['id']]['snapshot_missing'])
            self.assertEqual(len(warnings),2)
            self.assertEqual(before,{f.relative_to(d):f.read_bytes() for f in Path(d).rglob('*') if f.is_file()})
            with self.assertRaises(ValueError):history.list_versions(p)
