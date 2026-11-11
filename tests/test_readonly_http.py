"""Current public HTTP interface is read-only, including stale browser requests."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import urllib.error
import zipfile
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from project_service import ProjectService
from test_project_service import PLAN


class ReadonlyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name)/'manager'
        self.service=ProjectService(str(self.workspace))
        self.project=self.service.call('create_project',{'name':'浏览验证'})['project']
        self.pid=self.project['id']
        self.proc=subprocess.Popen([sys.executable,str(ROOT/'scripts/serve_dashboard.py'),'--workspace',str(self.workspace),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(self.stop)
        self.url=self.proc.stdout.readline().strip().split('：')[1].rstrip('/')

    def stop(self):
        self.proc.terminate(); self.proc.wait(timeout=5)
        self.proc.stdout.close();self.proc.stderr.close()

    def request(self, route, body=None, headers=None):
        req=urllib.request.Request(self.url+route,data=None if body is None else json.dumps(body).encode(),headers=headers or {})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers

    def test_all_old_write_and_ai_routes_are_gone_even_without_token(self):
        before={p:p.read_bytes() for p in self.workspace.rglob('*.md')}
        for path in ('/api/projects','/api/planning','/api/plan/save','/api/plan/merge','/api/plan/features',
                     '/api/plan/suggestions','/api/research/source-check','/api/research','/api/ledger/save'):
            status,body,_=self.request(path+'?project='+self.pid,{'content':'malicious old draft'})
            self.assertEqual(status,410,(path,body))
            self.assertEqual(json.loads(body)['code'],'host_conversation_required')
        self.assertEqual(before,{p:p.read_bytes() for p in self.workspace.rglob('*.md')})
        self.assertEqual(self.request('/api/projects',{}, {'Origin':'https://example.net'})[0],403)
        for path in ('/assets/planning-assistant.js','/assets/planning-suggestions.js','/assets/planning-workflow.js'):
            self.assertEqual(self.request(path)[0],404)

    def test_current_and_historical_table_export_and_board_follow_chat_writes(self):
        args={'project_id':self.pid}
        old=self.service.call('read_project',args)
        first=self.service.call('save_plan',{**args,'content':PLAN,'revision':old['plan']['revision']})
        self.service.call('save_plan',{**args,'content':PLAN.replace('登记图书','添加图书'),'revision':first['revision']})
        status,body,_=self.request('/api/plan/table?project='+self.pid)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['revision'],self.service.call('read_project',args)['plan']['revision'])
        for version in ('',first['history_version']['id']):
            status,data,headers=self.request('/api/plan/export?project='+self.pid+('&version='+version if version else ''))
            self.assertEqual(status,200)
            self.assertIn('spreadsheetml',headers['Content-Type'])
            with zipfile.ZipFile(BytesIO(data)) as z:self.assertIsNone(z.testzip())
        candidate=self.service.call('generate_ledger',args)
        self.service.call('save_ledger',{**args,'content':candidate['content'],'revision':candidate['ledger_revision'],
            'plan_revision':candidate['plan_revision'],'source_revision':candidate['source_revision']})
        status,body,_=self.request('/api/ledger?project='+self.pid)
        self.assertEqual(status,200)
        self.assertIn('添加图书',body.decode())
        for path in ('/projects','/planning?project='+self.pid,'/?project='+self.pid):
            status,body,_=self.request(path)
            self.assertEqual(status,200)
            self.assertNotIn('__PLANNING_TOKEN__',body.decode())

    def test_idle_socket_does_not_prevent_shutdown(self):
        port=int(self.url.rsplit(':',1)[1])
        with socket.create_connection(('127.0.0.1',port)):
            self.proc.terminate()
            self.proc.wait(timeout=5)


if __name__=='__main__':unittest.main()
