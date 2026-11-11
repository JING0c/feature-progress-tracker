"""Exercise both CLI wire formats with real child processes, no model charges."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load('planning_agent')
dashboard = load('serve_dashboard')
SUCCESS = {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': '请确认图书借还流程。'}
FIXTURE = '''import json, os, pathlib, sys, time
if 'mcp' in sys.argv and 'list' in sys.argv:
    servers = json.loads(os.environ.get('TEST_AGENT_MCPS', '[]'))
    if any(value.startswith('mcp_servers=') for value in sys.argv) and not os.environ.get('TEST_AGENT_MCP_FAILURE'):
        servers = [{**row, 'enabled': False} for row in servers]
    print(json.dumps(servers))
    sys.exit()
prompt = sys.stdin.read()
pathlib.Path(os.environ['TEST_AGENT_TRACE']).write_text(json.dumps({
    'args': sys.argv[1:], 'prompt': prompt, 'cwd': os.getcwd(), 'pid': os.getpid(),
    'claudecode': os.environ.get('CLAUDECODE'), 'auth_preserved': 'ANTHROPIC_API_KEY' in os.environ
}))
if pathlib.Path(os.environ['TEST_AGENT_WAIT']).exists():
    time.sleep(30)
print(pathlib.Path(os.environ['TEST_AGENT_REPLY']).read_text())
print(os.environ.get('TEST_AGENT_STDERR', ''), file=sys.stderr)
sys.exit(int(os.environ.get('TEST_AGENT_EXIT', '0')))
'''


class AgentFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.reply = self.root / 'reply.json'
        self.reply.write_text(json.dumps(SUCCESS))
        self.trace = self.root / 'trace.json'
        self.wait = self.root / 'wait'
        self.env = {'PATH': str(self.bin), 'TEST_AGENT_REPLY': str(self.reply),
                    'TEST_AGENT_TRACE': str(self.trace), 'TEST_AGENT_WAIT': str(self.wait)}
        context = patch.dict(os.environ, self.env)
        context.start()
        self.addCleanup(context.stop)
        for name in ('claude', 'codex'):
            executable = self.bin / name
            executable.write_text('#!' + sys.executable + '\n' + FIXTURE)
            executable.chmod(0o755)

    def run_agent(self, provider='claude', **kwargs):
        return agent.run(provider, {'directory': str(self.project)}, '项目 A：保留现有功能，只分析。', **kwargs)


class PlanningAgentTests(AgentFixture):
    def test_claude_print_success_disables_tools_and_customizations(self):
        self.assertEqual(self.run_agent(), SUCCESS['result'])
        trace = json.loads(self.trace.read_text())
        args = trace['args']
        self.assertIn('--print', args)
        self.assertEqual(args[args.index('--output-format') + 1], 'json')
        self.assertEqual(args[args.index('--tools') + 1], '')
        self.assertEqual(args[args.index('--disallowedTools') + 1], 'mcp__*')
        self.assertEqual(json.loads(args[args.index('--mcp-config') + 1]), {'mcpServers': {}})
        for flag in ('--safe-mode', '--strict-mcp-config', '--no-session-persistence', '--disable-slash-commands'):
            self.assertIn(flag, args)
        self.assertNotIn('--dangerously-skip-permissions', args)
        self.assertNotIn('--bare', args, 'subscription authentication must remain available')
        self.assertEqual(trace['cwd'], str(self.project))
        self.assertIn('项目 A', trace['prompt'])
        self.assertEqual(list(self.project.iterdir()), [])

    def test_codex_jsonl_keeps_last_agent_message_and_readonly_sandbox(self):
        self.reply.write_text('\n'.join(json.dumps(event) for event in [
            {'type': 'thread.started'},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '初步分析'}},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '最终分析'}}]))
        self.assertEqual(self.run_agent('codex'), '最终分析')
        args = json.loads(self.trace.read_text())['args']
        self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
        for setting in ('features.plugins=false', 'features.apps=false', 'features.hooks=false'):
            self.assertIn(setting, args)

    def test_claude_error_result_exit_zero_is_not_a_success(self):
        self.reply.write_text(json.dumps({**SUCCESS, 'is_error': True, 'result': 'Login required'}))
        with self.assertRaisesRegex(agent.AgentError, 'Claude Code 未能完成'):
            self.run_agent()

    def test_claude_error_subtype_and_nonzero_exit_are_not_success(self):
        self.reply.write_text(json.dumps({**SUCCESS, 'subtype': 'error_max_turns'}))
        with self.assertRaises(agent.AgentError):
            self.run_agent()
        self.reply.write_text(json.dumps(SUCCESS))
        with patch.dict(os.environ, {'TEST_AGENT_EXIT': '1'}), self.assertRaises(agent.AgentError):
            self.run_agent()

    def test_cli_guard_and_unsupported_flags_give_actionable_errors(self):
        for error, hint in (("Claude Code cannot be launched inside another Claude Code session", '独立终端'),
                            ("error: unknown option '--safe-mode'", '更新 Claude Code')):
            with self.subTest(error=error), patch.dict(os.environ, {'TEST_AGENT_EXIT': '1', 'TEST_AGENT_STDERR': error}):
                with self.assertRaisesRegex(agent.AgentError, hint):
                    self.run_agent()

    def test_invalid_or_empty_claude_output_is_not_accepted(self):
        for value in ('not json', '[]', '{}', json.dumps({**SUCCESS, 'result': ''}),
                      json.dumps({**SUCCESS, 'is_error': 'false'})):
            with self.subTest(value=value):
                self.reply.write_text(value)
                with self.assertRaises(agent.AgentError):
                    self.run_agent()

    def test_codex_failure_after_partial_message_is_not_accepted(self):
        self.reply.write_text(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'partial'}})
                              + '\n' + json.dumps({'type': 'turn.failed'}))
        with self.assertRaises(agent.AgentError):
            self.run_agent('codex')

    def test_codex_disables_independent_mcp_names_and_verifies_result(self):
        self.reply.write_text(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'analysis'}}))
        servers = [{'name': 'writer.server', 'enabled': True}, {'name': 'previously-disabled', 'enabled': False}]
        with patch.dict(os.environ, {'TEST_AGENT_MCPS': json.dumps(servers)}):
            self.assertEqual(self.run_agent('codex'), 'analysis')
            settings = json.loads(self.trace.read_text())['args']
            self.assertIn('mcp_servers={"writer.server"={enabled=false},"previously-disabled"={enabled=false}}', settings)
            self.trace.unlink()
            with patch.dict(os.environ, {'TEST_AGENT_MCP_FAILURE': '1'}), self.assertRaisesRegex(agent.AgentError, 'MCP 工具已禁用'):
                self.run_agent('codex')
            self.assertFalse(self.trace.exists(), 'never start analysis while a writer MCP remains enabled')

    def test_claude_child_does_not_inherit_host_session_marker(self):
        with patch.dict(os.environ, {'CLAUDECODE': '1', 'ANTHROPIC_API_KEY': 'fixture-only'}):
            self.assertEqual(self.run_agent(), SUCCESS['result'])
            trace = json.loads(self.trace.read_text())
            self.assertIsNone(trace['claudecode'])
            self.assertTrue(trace['auth_preserved'])
            self.assertEqual(os.environ['CLAUDECODE'], '1', 'host environment is never modified')

    def test_missing_claude_never_falls_back_to_installed_codex(self):
        (self.bin / 'claude').unlink()
        with self.assertRaisesRegex(agent.AgentError, '未找到 Claude Code.*不会自动切换'):
            self.run_agent()
        self.assertFalse(self.trace.exists())

    def test_timeout_kills_child_and_disables_cancel_handler(self):
        self.wait.touch()
        callbacks = []
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_agent(timeout=1, on_start=lambda cancel: callbacks.append('start'),
                           on_finish=lambda: callbacks.append('finish'))
        self.assertEqual(callbacks, ['start', 'finish'])
        pid = json.loads(self.trace.read_text())['pid']
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_cancel_kills_child_and_leaves_project_unchanged(self):
        self.wait.touch()
        cancel = threading.Event()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(self.run_agent, cancelled=cancel)
            deadline = time.monotonic() + 3
            while not self.trace.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(self.trace.exists())
            cancel.set()
            with self.assertRaisesRegex(agent.AgentError, '已取消'):
                pending.result(timeout=3)
        self.assertEqual(list(self.project.iterdir()), [])
        with self.assertRaises(ProcessLookupError):
            os.kill(json.loads(self.trace.read_text())['pid'], 0)

    def test_readonly_store_does_not_initialize_workspace(self):
        missing = self.root / 'not-created'
        store = dashboard.ProjectStore(workspace=missing, initialize=False)
        self.assertEqual(store.registry, missing / '项目列表.md')
        self.assertFalse(missing.exists())

    def test_codex_reply_entrypoint_remains_patchable(self):
        with patch.object(dashboard, 'agent_reply', return_value='compatible') as mocked:
            self.assertEqual(dashboard.codex_reply({'directory': 'unused'}, 'prompt'), 'compatible')
        mocked.assert_called_once_with({'directory': 'unused'}, 'prompt', 'codex')

    def test_shutdown_rejects_new_analysis_without_starting_a_child(self):
        isolated = load('planning_agent')
        isolated.cancel_active()
        with self.assertRaisesRegex(isolated.AgentError, '正在停止'):
            isolated.run('claude', {'directory': str(self.project)}, 'new request')
        self.assertFalse(self.trace.exists())


class ClaudeDashboardTests(AgentFixture):
    def setUp(self):
        super().setUp()
        self.workspace = self.root / 'manager'
        self.proc = subprocess.Popen([
            sys.executable, str(ROOT / 'scripts' / 'serve_dashboard.py'), '--workspace', str(self.workspace),
            '--port', '0', '--agent', 'claude', '--instance-id', 'fixture-instance'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop)
        self.url = self.proc.stdout.readline().strip().split('：', 1)[1].rstrip('/')
        page = urllib.request.urlopen(self.url + '/projects').read().decode()
        self.token = re.search(r"const TOKEN=['\"]([^'\"]+)", page).group(1)

    def stop(self):
        self.proc.terminate()
        self.proc.communicate(timeout=5)

    def request(self, path, payload=None, headers=None):
        request = urllib.request.Request(self.url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json', 'X-Planning-Token': self.token, **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def project_row(self, name):
        code, result = self.request('/api/projects', {'name': name, 'directory': name, 'mode': 'new'})
        self.assertEqual(code, 200, result)
        return result['project']

    def test_runtime_and_html_identify_actual_provider(self):
        code, runtime = self.request('/api/runtime')
        self.assertEqual(code, 200)
        self.assertEqual(runtime, {'instance_id': 'fixture-instance', 'agent': 'claude',
                                  'workspace': str(self.workspace), 'pid': self.proc.pid})
        self.assertEqual(self.request('/api/runtime', headers={'Host': 'evil.example'})[0], 403)
        project = self.project_row('first')
        page = urllib.request.urlopen(self.url + '/planning?project=' + project['id']).read().decode()
        self.assertIn('由本机 Claude Code 提供回复', page)
        self.assertNotIn('__PLANNING_AGENT__', page)

    def test_claude_multi_project_context_and_progress(self):
        (self.bin / 'codex').unlink()
        a, b = self.project_row('project-a'), self.project_row('project-b')
        for project, marker, other in ((a, 'ALPHA-CONTEXT', 'BETA-CONTEXT'), (b, 'BETA-CONTEXT', 'ALPHA-CONTEXT')):
            Path(project['plan_path']).write_text('# ' + marker)
            operation = 'analysis-' + project['id']
            code, result = self.request('/api/planning?project=' + project['id'],
                {'intent': 'chat', 'messages': [{'role': 'user', 'content': '请讨论现有需求'}]},
                {'X-Operation-ID': operation})
            self.assertEqual(code, 200, result)
            self.assertEqual(result['reply'], SUCCESS['result'])
            trace = json.loads(self.trace.read_text())
            self.assertIn(marker, trace['prompt'])
            self.assertNotIn(other, trace['prompt'])
            self.assertEqual(trace['cwd'], project['directory'])
            progress = self.request('/api/operation-progress?project=' + project['id'] + '&operation=' + operation)[1]
            self.assertEqual(progress['status'], 'completed')
            self.assertEqual(progress['percent'], 100)

    def test_missing_claude_error_does_not_use_available_codex(self):
        project = self.project_row('missing-cli')
        (self.bin / 'claude').unlink()
        code, result = self.request('/api/planning?project=' + project['id'],
            {'intent': 'chat', 'messages': [{'role': 'user', 'content': '请规划'}]})
        self.assertEqual(code, 400)
        self.assertIn('未找到 Claude Code', result['error'])
        self.assertFalse(self.trace.exists())

    def test_failed_claude_result_does_not_change_plan(self):
        project = self.project_row('failed-result')
        before = Path(project['plan_path']).read_bytes()
        self.reply.write_text(json.dumps({**SUCCESS, 'is_error': True}))
        code, result = self.request('/api/planning?project=' + project['id'],
            {'intent': 'plan', 'messages': [{'role': 'user', 'content': '生成项目规划'}]})
        self.assertEqual(code, 400)
        self.assertIn('Claude Code 未能完成', result['error'])
        self.assertEqual(Path(project['plan_path']).read_bytes(), before)

    def test_claude_generated_plan_can_be_saved_using_existing_validation(self):
        from test_projects import project_plan
        project = self.project_row('claude-plan')
        document = project_plan('Claude 规划')
        self.reply.write_text(json.dumps({**SUCCESS, 'result': document}))
        suffix = '?project=' + project['id']
        code, generated = self.request('/api/planning' + suffix,
            {'intent': 'plan', 'messages': [{'role': 'user', 'content': '生成图书借还规划'}]})
        self.assertEqual(code, 200, generated)
        code, saved = self.request('/api/plan/save' + suffix,
            {'content': generated['reply'], 'revision': generated['plan_revision']})
        self.assertEqual(code, 200, saved)
        self.assertEqual(Path(project['plan_path']).read_text(), document)
        self.assertTrue(self.request('/api/project' + suffix)[1]['planning']['ready'])

    def test_claude_cancel_reports_provider_progress_and_preserves_documents(self):
        project = self.project_row('claude-cancel')
        before = Path(project['plan_path']).read_bytes()
        self.wait.touch()
        suffix = '?project=' + project['id']
        operation = 'claude-cancel-operation'
        path = '/api/operation-progress' + suffix + '&operation=' + operation
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(self.request, '/api/planning' + suffix,
                {'intent': 'plan', 'messages': [{'role': 'user', 'content': '规划后取消'}]},
                {'X-Operation-ID': operation})
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                state = self.request(path)[1]
                if state.get('cancellable'):
                    break
                time.sleep(.02)
            self.assertTrue(state.get('cancellable'), state)
            self.assertIn('Claude Code', state['stage'])
            self.assertEqual(self.request('/api/operation-cancel' + suffix, {'operation': operation})[0], 200)
            code, result = pending.result(timeout=3)
            self.assertEqual(code, 400)
            self.assertIn('已取消', result['error'])
        self.assertEqual(Path(project['plan_path']).read_bytes(), before)
        self.assertEqual(self.request(path)[1]['status'], 'cancelled')


class PluginAnalysisShutdownTests(AgentFixture):
    request = ClaudeDashboardTests.request
    project_row = ClaudeDashboardTests.project_row

    def setUp(self):
        super().setUp()
        self.manager = load('plugin_manager')
        self.workspace = self.root / 'plugin-workspace'
        started = self.manager.start(str(self.workspace), 'claude', 0)
        self.proc = self.manager._PROCESSES[-1]
        self.addCleanup(self.stop_server)
        self.addCleanup(self.cleanup_child)
        self.url = started['url'].removesuffix('/projects')
        page = urllib.request.urlopen(self.url + '/projects').read().decode()
        self.token = re.search(r"const TOKEN=['\"]([^'\"]+)", page).group(1)

    def stop_server(self):
        if self.proc.poll() is None:
            self.manager.stop(str(self.workspace), 'claude')
        self.proc.wait(timeout=5)

    def cleanup_child(self):
        if self.trace.exists():
            try:
                os.killpg(json.loads(self.trace.read_text())['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass

    def check_stop_during_headerless_analysis(self, sigint=False):
        project = self.project_row('stop-during-analysis')
        paths = [Path(project[key]) for key in ('plan_path', 'ledger_path')]
        before = [path.read_bytes() for path in paths]
        self.wait.touch()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(self.request, '/api/planning?project=' + project['id'],
                {'intent': 'plan', 'messages': [{'role': 'user', 'content': '开始规划，测试停止服务'}]})
            try:
                deadline = time.monotonic() + 3
                while not self.trace.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(self.trace.exists(), 'the real CLI child must be running before stop')
                pid = json.loads(self.trace.read_text())['pid']
                if sigint:
                    self.proc.send_signal(signal.SIGINT)
                    self.proc.wait(timeout=5)
                else:
                    stopped = self.manager.stop(str(self.workspace), 'claude')
                    self.assertTrue(stopped['stopped'])
                    self.proc.wait(timeout=5)
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
                code, result = pending.result(timeout=3)
                self.assertEqual(code, 400)
                self.assertIn('已取消', result['error'])
                self.assertEqual([path.read_bytes() for path in paths], before)
            finally:
                # Clean up even if this regression reappears, avoiding orphan fixtures.
                self.cleanup_child()

    def test_plugin_stop_reaps_headerless_analysis_and_preserves_documents(self):
        self.check_stop_during_headerless_analysis()

    def test_sigint_reaps_headerless_analysis_and_preserves_documents(self):
        self.check_stop_during_headerless_analysis(sigint=True)

    def test_incomplete_browser_request_cannot_hold_shutdown_open(self):
        with socket.create_connection(('127.0.0.1', urlsplit(self.url).port), timeout=3) as idle:
            idle.sendall(b'GET /projects HTTP/1.1\r\n')
            time.sleep(.05)
            stopped = self.manager.stop(str(self.workspace), 'claude')
            self.assertTrue(stopped['stopped'])
            self.proc.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
