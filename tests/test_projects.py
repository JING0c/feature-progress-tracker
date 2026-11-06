"""Integration checks for independent, disk-backed project state."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from ledger_context_fixture import legacy_no_reference_context

ROOT = Path(__file__).resolve().parents[1]


def project_plan(name='测试'):
    return f'''# {name} 项目规划书
## 目标
帮助管理员在本机管理图书借阅，避免重复借出。
## 范围
包括图书登记、借还记录和逾期名单；不做支付。
## 功能与验收
图书登记后按编号可查到；借出的图书不能重复借出。
'''


def ledger(name, state='进行中', checked=False):
    return f'''# 功能执行情况
## 大功能 F01：{name}
- [{'x' if checked else ' '}] F01-01 任务｜状态：{state}｜优先级：高｜依赖：无
  - 验收：可验证结果。
  - 执行 Agent：开发者；实现证据：记录
  - 审核 Agent：待审核；评分：待审核；问题：无新增待确认事项。
'''


class ManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / 'manager'
        self.fake_bin = Path(self.temp.name) / 'bin'; self.fake_bin.mkdir()
        self.fake_reply = Path(self.temp.name) / 'reply.txt'
        self.fake_prompt = Path(self.temp.name) / 'prompt.txt'
        self.fake_reply.write_text(project_plan())
        fake = self.fake_bin / 'codex'
        fake.write_text('#!' + sys.executable + '\nimport json, os, pathlib, sys\n'
                        'pathlib.Path(os.environ["FAKE_CODEX_PROMPT"]).write_text(sys.stdin.read())\n'
                        'reply = pathlib.Path(os.environ["FAKE_CODEX_REPLY"]).read_text()\n'
                        'print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":reply}}))\n')
        fake.chmod(0o755)
        self.start()

    def start(self):
        env = {**os.environ, 'PATH': str(self.fake_bin) + os.pathsep + os.environ.get('PATH',''),
               'FAKE_CODEX_REPLY':str(self.fake_reply), 'FAKE_CODEX_PROMPT':str(self.fake_prompt)}
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/serve_dashboard.py'), '--workspace', str(self.workspace), '--port', '0'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        self.url = self.proc.stdout.readline().strip().split('：', 1)[1].rstrip('/')
        # The HTML asset can be supplied independently of backend integration tests.
        # Registration still requires the same token as the page.
        page = urllib.request.urlopen(self.url + '/projects').read().decode()
        self.token = re.search(r"(?:const TOKEN=|name=\"planning-token\" content=)[\"']([^\"']+)", page).group(1)

    def stop(self):
        self.proc.terminate(); self.proc.wait(timeout=5); self.proc.stdout.close()

    def tearDown(self):
        self.stop(); self.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        hdr = {'X-Planning-Token': self.token, 'Content-Type': 'application/json'}
        hdr.update(headers or {})
        req = urllib.request.Request(self.url + path, headers=hdr, data=None if payload is None else json.dumps(payload).encode())
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def register(self, name):
        status, data = self.request('/api/projects', {'name':name, 'directory':name})
        self.assertEqual(status, 200, data)
        p = data['project']
        self.generate_plan(p, project_plan(name))
        doc = self.request('/api/plan?project='+p['id'])[1]
        code, result = self.request('/api/plan/save?project='+p['id'], {'content':project_plan(name),'revision':doc['revision']})
        self.assertEqual(code, 200, result)
        return self.request('/api/project?project='+p['id'])[1]

    def generate_plan(self, project, text=None):
        self.fake_reply.write_text(text or project_plan())
        code, result = self.request('/api/planning?project='+project['id'], {'intent':'plan','messages':[{'role':'user','content':'请生成项目规划书'}]})
        self.assertEqual(code, 200, result)
        return result['reply']

    def test_new_project_can_use_safe_default_folder(self):
        code, data = self.request('/api/projects', {'name':'../自动/记账', 'directory':'', 'mode':'new'})
        self.assertEqual(code, 200, data)
        folder = Path(data['project']['directory'])
        self.assertEqual(folder.parent, (self.workspace / '项目').resolve())
        self.assertTrue(folder.is_dir())
        second = self.request('/api/projects', {'name':'../自动/记账', 'directory':'', 'mode':'new'})[1]['project']
        self.assertNotEqual(second['directory'], str(folder))
        self.assertEqual(self.request('/api/projects', {'name':'导入', 'directory':'', 'mode':'import'})[0], 400)

    def test_project_isolation_external_edits_and_restart(self):
        a, b = self.register('项目 A'), self.register('项目 B')
        Path(a['ledger_path']).write_text(ledger('A'), encoding='utf-8')
        Path(b['ledger_path']).write_text(ledger('B', '已完成', True), encoding='utf-8')
        status, data = self.request('/api/projects')
        by_id = {p['id']: p for p in data['projects']}
        self.assertEqual(by_id[a['id']]['summary']['working'], 1)
        self.assertEqual(by_id[b['id']]['summary']['done'], 1)
        self.assertEqual(by_id[a['id']]['summary']['issues'], 0)
        self.assertEqual(self.request('/api/ledger?project='+a['id'])[1]['groups'][0]['name'], 'A')
        Path(a['ledger_path']).write_text(ledger('A', '受阻'), encoding='utf-8')
        by_id = {p['id']:p for p in self.request('/api/projects')[1]['projects']}
        self.assertEqual(by_id[a['id']]['summary']['blocked'], 1)
        doc = self.request('/api/plan?project='+a['id'])[1]
        status, saved = self.request('/api/plan/save?project='+a['id'], {'content':project_plan('A 的规划'), 'revision':doc['revision']})
        self.assertEqual(status, 200, saved)
        self.assertTrue(Path(saved['backup']).is_file())
        self.assertNotIn('A 的规划', Path(b['plan_path']).read_text())
        self.stop(); self.start()
        self.assertEqual(self.request('/api/plan?project='+a['id'])[1]['content'], project_plan('A 的规划'))
        self.assertEqual(len(self.request('/api/projects')[1]['projects']), 2)
        registry = (self.workspace/'项目列表.md').read_text()
        self.assertIn('名称：项目 A', registry)
        self.assertIn(a['ledger_path'], registry)

    def test_unknown_scope_and_conflict_fail_closed(self):
        p = self.register('test')
        for path in ('/api/ledger', '/api/plan', '/api/ledger/info', '/planning'):
            self.assertEqual(self.request(path)[0], 400)
            self.assertEqual(self.request(path+'?project=missing')[0], 404)
        original = self.request('/api/plan?project='+p['id'])[1]
        Path(p['plan_path']).write_text('# 外部更改\n')
        status, _ = self.request('/api/plan/save?project='+p['id'], {'content':'# 错误覆盖', 'revision':original['revision']})
        self.assertEqual(status, 409)
        self.assertEqual(Path(p['plan_path']).read_text(), '# 外部更改\n')
        self.assertEqual(self.request('/api/projects', {'name':'duplicate','directory':p['directory']})[0], 409)
        self.assertEqual(self.request('/api/projects', {'name':'bad','directory':'bad','ledger_path':'../outside.md'})[0], 400)
        self.assertEqual(self.request('/api/plan/save?project='+p['id'], {'content':'# bad','revision':original['revision']}, {'Origin':'https://evil.example'})[0], 403)

    def test_existing_acceptance_survives_and_fabrication_is_rejected(self):
        p = self.register('accepted')
        original = ledger('已验收项目', '已完成', True)
        path = Path(p['ledger_path'])
        path.write_text(original, encoding='utf-8')
        revision = self.request('/api/ledger/info?project='+p['id'])[1]['revision']
        context = legacy_no_reference_context(self.request('/api/plan?project='+p['id'])[1]['revision'])
        endpoint = '/api/ledger/save?project='+p['id']
        status, _ = self.request(endpoint, {'content':original, 'revision':revision, **context})
        self.assertEqual(status, 200)
        for invalid in (original.replace('可验证结果。','changed'), ledger('已验收项目'), original + ledger('new', '已完成', True).replace('F01','F02')):
            self.assertEqual(self.request(endpoint, {'content':invalid, 'revision':revision, **context})[0], 400)
        self.assertEqual(path.read_text(), original)

    def test_registry_and_cross_document_collisions_are_rejected(self):
        status, _ = self.request('/api/projects', {'name':'registry','directory':str(self.workspace),'ledger_path':'项目列表.md'})
        self.assertEqual(status, 409)
        child = self.register('child')
        status, _ = self.request('/api/projects', {'name':'parent','directory':str(self.workspace),'ledger_path':'child/项目规划书.md'})
        self.assertEqual(status, 409)
        registry = self.workspace/'项目列表.md'
        registry.write_text(registry.read_text() + '\n## bad\n名称：bad\n目录：' + str(self.workspace) + '\n台账：项目列表.md\n规划书：another.md\n')
        self.assertEqual(self.request('/api/projects')[0], 400)

    def test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved(self):
        p = self.register('test')
        Path(p['ledger_path']).unlink()
        row = self.request('/api/projects')[1]['projects'][0]
        self.assertIn('error', row)
        self.assertIsNone(row['summary'])
        Path(p['ledger_path']).write_text('# 不支持的格式\n这是一个普通文档。')
        self.assertIn('error', self.request('/api/projects')[1]['projects'][0])
        Path(p['plan_path']).unlink()
        empty = self.request('/api/plan?project='+p['id'])[1]
        self.assertEqual(empty['content'], '')
        self.generate_plan(p)
        status, _ = self.request('/api/plan/save?project='+p['id'], {'content':project_plan(), 'revision':empty['revision']})
        self.assertEqual(status, 200)


if __name__ == '__main__': unittest.main()
