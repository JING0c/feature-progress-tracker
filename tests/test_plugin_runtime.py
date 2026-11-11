import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import plugin_manager as manager
import plugin_mcp as mcp


class PluginRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plugin workspace ')
        self.root = Path(self.temp.name).resolve()
        self.pids = []

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
                os.waitpid(pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        self.temp.cleanup()

    def registered_project(self):
        project = self.root / '项目' / '测试项目'
        project.mkdir(parents=True)
        plan = '# 项目规划书\n\n## 目标\n管理日常任务。\n\n## 范围\n个人本地使用。\n\n## 功能与验收\n新增任务后可在列表查看。\n'
        (project / '项目规划书.md').write_text(plan, encoding='utf-8')
        ledger = '# 功能执行情况\n\n## 大功能 F01：任务\n- [ ] F01-01 新建任务｜状态：未开始\n  - 验收：新建后在列表可见。\n'
        (project / '功能执行情况.md').write_text(ledger, encoding='utf-8')
        (self.root / '项目列表.md').write_text('# 项目列表\n\n## p-test\n名称：测试项目\n目录：项目/测试项目\n规划书：项目规划书.md\n台账：功能执行情况.md\n', encoding='utf-8')
        return plan, ledger

    def test_read_tools_never_create_missing_workspace_or_registry(self):
        missing = self.root / '不存在'
        for path in (missing, self.root):
            with self.assertRaises(ValueError):
                mcp.call_tool('list_projects', {'workspace': str(path)}, 'codex')
        self.assertFalse(missing.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse(manager.status(str(missing))['running'])
        self.assertFalse(missing.exists())

    def test_registered_markdown_and_revisions_are_read_without_changes(self):
        plan, ledger = self.registered_project()
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = mcp.call_tool('list_projects', {'workspace': str(self.root)}, 'codex')
        self.assertEqual([p['id'] for p in result['projects']], ['p-test'])
        read = mcp.call_tool('read_project', {'workspace': str(self.root), 'project_id': 'p-test'}, 'claude')
        self.assertEqual(read['plan']['content'], plan)
        self.assertEqual(read['ledger']['content'], ledger)
        self.assertEqual(len(read['plan']['revision']), 64)
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(Exception):
            mcp.call_tool('read_project', {'workspace': str(self.root), 'project_id': '../../other'}, 'codex')
        self.assertFalse((self.root / manager.STATE_DIR).exists())

    def test_missing_document_is_explicit_and_not_created(self):
        self.registered_project()
        ledger = self.root / '项目/测试项目/功能执行情况.md'
        ledger.unlink()
        result = mcp.call_tool('read_project', {'workspace': str(self.root), 'project_id': 'p-test'}, 'codex')
        self.assertEqual(result['ledger']['content'], '')
        self.assertFalse(result['ledger']['exists'])
        self.assertFalse(ledger.exists())

    def test_stdio_initialization_errors_notifications_and_reads(self):
        plan, _ = self.registered_project()
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'read_project', 'arguments': {'workspace': str(self.root), 'project_id': 'p-test'}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'open_dashboard', 'arguments': {'workspace': str(self.root), 'port': True}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'unknown'},
            {'jsonrpc': '2.0', 'id': 6, 'method': 'ping'},
        ]
        payload = 'not json\n' + '\n'.join(json.dumps(r) for r in requests) + '\n'
        process = subprocess.run([sys.executable, str(SCRIPTS / 'plugin_mcp.py'), '--agent', 'claude'], input=payload, capture_output=True, text=True, timeout=10, cwd=self.root)
        self.assertEqual(process.returncode, 0, process.stderr)
        output = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(output), 7)
        self.assertEqual(output[0]['error']['code'], -32700)
        by_id = {r['id']: r for r in output}
        self.assertEqual(by_id[1]['result']['protocolVersion'], '2025-06-18')
        self.assertTrue({'open_dashboard','list_projects','read_project','create_project','save_plan','edit_features','record_suggestions','preview_suggestions','prepare_source_review','submit_source_review','generate_ledger','save_ledger','update_feature_progress','history','export_project','stop_dashboard'} <= {t['name'] for t in by_id[2]['result']['tools']})
        self.assertEqual(by_id[3]['result']['structuredContent']['plan']['content'], plan)
        self.assertTrue(by_id[4]['result']['isError'])
        self.assertEqual(by_id[5]['error']['code'], -32601)
        self.assertEqual(by_id[6]['result'], {})
        self.assertEqual(process.stderr, '')

    def test_real_dashboard_reuses_instance_and_does_not_take_occupied_port(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            port = occupied.getsockname()[1]
            first = manager.start(str(self.root), 'codex', port)
            self.pids.append(first['pid'])
            self.assertFalse(first['reused'])
            self.assertNotIn(f':{port}/', first['url'])
            second = manager.start(str(self.root), 'codex', port)
            self.assertTrue(second['reused'])
            self.assertEqual(first['pid'], second['pid'])
            self.assertEqual(manager.status(str(self.root))['url'], first['url'])
            self.assertEqual(occupied.getsockname()[1], port)
        overview = manager.http_json(first['url'].replace('/projects', '/api/projects'))
        self.assertEqual(overview['workspace'], str(self.root))
        self.assertEqual(overview['projects'], [])
        # Both hosts may share the same read-only viewer; writes use MCP locks.
        shared = manager.start(str(self.root), 'claude', 0)
        self.assertTrue(shared['reused'])
        self.assertEqual(shared['pid'], first['pid'])
        with self.assertRaisesRegex(RuntimeError, '--agent codex'):
            manager.stop(str(self.root), 'claude')
        self.assertTrue(manager.stop(str(self.root), 'codex')['stopped'])
        claude = manager.start(str(self.root), 'claude', 0)
        self.pids.append(claude['pid'])
        self.assertNotEqual(claude['pid'], first['pid'])
        self.assertNotEqual(claude['url'], first['url'])
        self.assertEqual(manager.status(str(self.root), 'claude')['agent'], 'claude')

    def test_wrong_instance_id_is_not_reused(self):
        current = manager.start(str(self.root), 'codex', 0)
        self.pids.append(current['pid'])
        state = self.root / manager.STATE_DIR / 'dashboard.json'
        record = json.loads(state.read_text())
        record['instance_id'] = 'different-process'
        state.write_text(json.dumps(record))
        self.assertFalse(manager.status(str(self.root))['running'])
        # The original listener was not stopped or otherwise changed.
        runtime = manager.http_json(current['url'].replace('/projects', '/api/runtime'))
        self.assertEqual(runtime['pid'], current['pid'])
        with self.assertRaisesRegex(RuntimeError, '启动失败'):
            manager.start(str(self.root), 'claude', 0)
        self.assertEqual(manager.http_json(current['url'].replace('/projects', '/api/runtime'))['pid'], current['pid'])

    def test_runtime_update_requires_explicit_restart(self):
        current = manager.start(str(self.root), 'codex', 0)
        self.pids.append(current['pid'])
        with mock.patch.object(manager, 'runtime_signature', return_value=('new-install', 'new-content')):
            with self.assertRaisesRegex(RuntimeError, '代码已更新'):
                manager.start(str(self.root), 'codex', 0)
            self.assertTrue(manager.stop(str(self.root), 'codex')['stopped'])

    def test_installed_plugin_cache_cannot_be_used_as_workspace(self):
        plugin = self.root / 'plugin'
        scripts = plugin / 'runtime/scripts'
        scripts.mkdir(parents=True)
        (plugin / 'plugin.json').write_text('{}')
        with mock.patch.object(manager, '__file__', str(scripts / 'plugin_manager.py')):
            with self.assertRaises(ValueError):
                manager.workspace_path(str(plugin / 'projects'))
            self.assertEqual(manager.workspace_path(str(self.root / 'data')), self.root / 'data')


if __name__ == '__main__':
    unittest.main()
