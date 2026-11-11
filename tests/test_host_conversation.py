"""Exercise shipped stdio tools, not internal functions, for both host labels."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
from test_project_service import PLAN


class HostConversationTests(unittest.TestCase):
    entrypoints = {}
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='host chat ')
        self.addCleanup(self.tmp.cleanup)
        self.workspace = str(Path(self.tmp.name) / 'manager')
        self.empty_bin = Path(self.tmp.name) / 'empty-bin'; self.empty_bin.mkdir()

    def call(self, tool_name, host='codex', expect_error=False, **args):
        requests = [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{
                'name':tool_name,'arguments':{'workspace':self.workspace,**args},'_meta':{'progressToken':'test-step'}}}]
        # No model CLI or Git on PATH: editing/saving must use only code.
        result = subprocess.run([sys.executable, str(self.entrypoints.get(host, ROOT/'scripts/plugin_mcp.py')), '--agent',host],
            input='\n'.join(json.dumps(r) for r in requests)+'\n',text=True,capture_output=True,
            env={**os.environ,'PATH':str(self.empty_bin)},timeout=15,cwd=self.tmp.name)
        self.assertEqual(result.returncode,0,result.stderr)
        frames=[json.loads(line) for line in result.stdout.splitlines()]
        response=next(r['result'] for r in frames if r.get('id')==2)
        self.assertEqual(bool(response.get('isError')),expect_error,response)
        progress=[r['params']['progress'] for r in frames if r.get('method')=='notifications/progress']
        self.assertEqual(progress,sorted(progress))
        self.assertEqual(progress[-1]==100,not expect_error)
        return response['structuredContent']

    def test_two_hosts_create_edit_adopt_save_progress_history_export(self):
        a=self.call('create_project',name='图书角',host='codex')['project']['id']
        b=self.call('create_project',name='第二项目',host='claude')['project']['id']
        initial=self.call('read_project',project_id=a,host='claude')
        self.call('save_plan',project_id=a,content=PLAN,revision=initial['plan']['revision'])
        before=self.call('read_project',project_id=a)
        preview=self.call('edit_features',project_id=a,revision=before['plan']['revision'],host='claude',additions=[
            {'key':'N1','parent':'F01','功能名称':'修改图书','说明':'修改图书名称','验收标准':'保存后显示新名称'},
            {'key':'N2','parent':'N1','功能名称':'名称校验','说明':'拒绝空白名称','验收标准':'空名称提示错误且保留输入'}])
        self.assertFalse(preview['saved']); self.assertIn('F01-02-01',preview['content'])
        self.assertEqual(self.call('read_project',project_id=a)['plan']['revision'],before['plan']['revision'])
        self.call('save_plan',project_id=a,content=preview['content'],revision=preview['revision'],host='claude')
        current=self.call('read_project',project_id=a)
        suggestions=self.call('record_suggestions',project_id=a,revision=current['plan']['revision'],analyst='审阅子Agent A',suggestions=[{
            'title':'补充重名处理','reason':'当前只校验空白名称','changes':[{
            'action':'update','id':'F01-02-01','fields':{'验收标准':'空名称及重复名称都提示错误且保留输入'}}]}])
        adopted=self.call('preview_suggestions',project_id=a,revision=current['plan']['revision'],selected=[suggestions['suggestions'][0]['id']],suggestion_id=suggestions['id'],host='claude')
        self.assertIn('重复名称',adopted['diff'])
        self.call('save_plan',project_id=a,revision=adopted['revision'],content=adopted['content'])
        candidate=self.call('generate_ledger',project_id=a,host='claude')
        saved=self.call('save_ledger',project_id=a,content=candidate['content'],revision=candidate['ledger_revision'],
                       plan_revision=candidate['plan_revision'],source_revision=candidate['source_revision'])
        working=self.call('update_feature_progress',project_id=a,feature_id='F01-01',revision=saved['revision'],
                          changes={'状态':'待审核','执行 Agent':'developer-A','实现证据':'测试记录 test-create 通过'})
        self.call('update_feature_progress',project_id=a,feature_id='F01-01',revision=working['revision'],expect_error=True,
                  changes={'状态':'已完成'})
        done=self.call('update_feature_progress',project_id=a,feature_id='F01-01',revision=working['revision'],host='claude',
             changes={'状态':'已完成'},review={'reviewer':'reviewer-B','score':92,'conclusion':'通过','evidence':'独立复测创建与列表读取通过','reason':'基本与异常通过，未做长期压力'})
        self.assertGreater(done['summary']['done'],0)
        records=self.call('history',project_id=a)
        self.assertGreaterEqual(len(records['versions']),3)
        export=self.call('export_project',project_id=a,format='xlsx',host='claude')
        with zipfile.ZipFile(export['path']) as book:
            self.assertIsNone(book.testzip())
            self.assertIn('规划原文',book.read('xl/workbook.xml').decode())
        other=self.call('read_project',project_id=b)
        self.assertFalse(other['project']['planning']['ready'])
        self.assertNotIn('F01-02',other['plan']['content'])

    def test_nested_schema_rejects_unknown_or_unsafe_fields_before_writes(self):
        self.call('create_project',name='结构校验',unexpected=True,expect_error=True)
        self.assertFalse(Path(self.workspace).exists())
        self.call('open_dashboard',port=True,expect_error=True)
        self.assertFalse(Path(self.workspace).exists())


if __name__=='__main__': unittest.main()
