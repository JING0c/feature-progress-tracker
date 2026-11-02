import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dashboard', ROOT / 'scripts/serve_dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)
PLAN = '''# 测试台账
## 大功能 F01：图书
- [ ] F01-01 添加图书｜状态：未开始｜优先级：高｜依赖：无
  - **验收**：可以添加图书。
  - **执行 Agent**：待分配；**实现证据**：无
  - **审核 Agent**：待审核；**评分**：待审核；**问题**：编号规则待确认
  - [ ] F01-01-01 录入编号｜状态：未开始｜优先级：高｜依赖：无
    - **验收**：编号唯一。
    - **执行 Agent**：待分配；**实现证据**：无
    - **审核 Agent**：待审核；**评分**：待审核；**问题**：无
'''

class LedgerTest(unittest.TestCase):
    def test_bold_fields_and_nested_items(self):
        item = dashboard.parse(PLAN)[0]['items'][0]
        self.assertEqual(item['fields']['验收'], '可以添加图书。')
        self.assertEqual(item['fields']['问题'], '编号规则待确认')
        self.assertEqual(item['fields']['执行 Agent'], '待分配')
        self.assertEqual(item['children'][0]['fields']['验收'], '编号唯一。')

class SaveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.temp.name) / 'ledger.md'
        self.original = '# 原有内容\n'
        self.ledger.write_text(self.original, encoding='utf-8')
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/serve_dashboard.py'), str(self.ledger), '--port', '0'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.url = self.proc.stdout.readline().strip().split('：', 1)[1].rstrip('/')
        page = urllib.request.urlopen(self.url + '/planning').read().decode()
        self.token = re.search(r"const TOKEN='([^']+)'", page).group(1)

    def tearDown(self):
        self.proc.terminate(); self.proc.wait(timeout=5); self.proc.stdout.close(); self.temp.cleanup()

    def get(self, path):
        return json.load(urllib.request.urlopen(self.url + path))

    def post(self, data):
        req = urllib.request.Request(self.url + '/api/ledger/save', data=json.dumps(data).encode(), headers={'Content-Type':'application/json','X-Planning-Token':self.token}, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_save_and_view_with_backup(self):
        meta = self.get('/api/ledger/info')
        code, data = self.post({'content':PLAN, 'revision':meta['revision']})
        self.assertEqual(code, 200, data)
        self.assertEqual(self.ledger.read_text(encoding='utf-8'), PLAN)
        self.assertEqual(Path(data['backup']).read_text(encoding='utf-8'), self.original)
        item = self.get('/api/ledger')['groups'][0]['items'][0]
        self.assertEqual(item['fields']['问题'], '编号规则待确认')
        self.assertEqual(item['children'][0]['id'], 'F01-01-01')

    def test_conflict_and_invalid_do_not_change_ledger(self):
        rev = self.get('/api/ledger/info')['revision']
        self.ledger.write_text('external change', encoding='utf-8')
        self.assertEqual(self.post({'content':PLAN, 'revision':rev})[0], 409)
        current = self.get('/api/ledger/info')['revision']
        self.assertEqual(self.post({'content':'普通对话', 'revision':current})[0], 400)
        self.assertEqual(self.ledger.read_text(encoding='utf-8'), 'external change')

if __name__ == '__main__': unittest.main()
