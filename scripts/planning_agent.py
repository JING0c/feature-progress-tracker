"""Read-only local analysis adapters; project mutations stay in application code.

Claude flags follow https://code.claude.com/docs/en/cli-reference.
Safe mode retains subscription authentication while disabling plugin/skill/MCP
discovery. Do not use bare mode here: it does not use subscription credentials.
"""
import json
import os
import shutil
import signal
import subprocess
import threading
import time

LABELS = {'codex': 'Codex', 'claude': 'Claude Code'}
TIMEOUT_SECONDS = 180
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_RUNS = {}
_SHUTTING_DOWN = False


class AgentError(ValueError):
    pass


def cancel_active():
    """Stop admitting analyses and cancel every child, including headerless calls."""
    global _SHUTTING_DOWN
    with _ACTIVE_LOCK:
        _SHUTTING_DOWN = True
        events = list(_ACTIVE_RUNS.values())
    for event in events:
        event.set()


def executable(provider):
    if provider not in LABELS:
        raise AgentError('未知分析智能体，请选择 codex 或 claude。')
    path = shutil.which(provider)
    if not path:
        raise AgentError(f'未找到 {LABELS[provider]} 命令行（{provider}），请安装并登录后重试；不会自动切换到其他智能体。')
    return path


def codex_options(mcp_names=()):
    options = ['-c', 'features.plugins=false', '-c', 'features.apps=false', '-c', 'features.hooks=false']
    if mcp_names:
        # CLI dotted paths do not parse quoted components. A TOML table value
        # correctly handles names containing dots and preserves transport config.
        entries = [json.dumps(name, ensure_ascii=False) + '={enabled=false}' for name in mcp_names]
        options += ['-c', 'mcp_servers={' + ','.join(entries) + '}']
    return options


def command(provider, path=None, mcp_names=()):
    path = path or executable(provider)
    if provider == 'codex':
        return [path, 'exec', '--sandbox', 'read-only', '--skip-git-repo-check',
                '--ephemeral', '--json', *codex_options(mcp_names), '-']
    return [path, '--print', '--output-format', 'json', '--safe-mode',
            '--tools', '', '--disallowedTools', 'mcp__*', '--strict-mcp-config',
            '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence',
            '--disable-slash-commands', '--no-chrome']


def parse_reply(provider, output, returncode=0, errors=''):
    label = LABELS[provider]
    if provider == 'claude':
        if returncode and 'cannot be launched inside another Claude Code session' in errors:
            raise AgentError('Claude Code 阻止了嵌套会话。请从独立终端启动项目管理器后重试；当前会话和规划文件未改变。')
        if returncode and ('unknown option' in errors.lower() or 'unknown argument' in errors.lower()):
            raise AgentError('当前 Claude Code 版本不支持安全分析参数，请更新 Claude Code 后重试；未更新功能表。')
        try:
            result = json.loads(output)
        except (TypeError, json.JSONDecodeError):
            raise AgentError(f'{label} 未返回有效 JSON；请检查 CLI 版本、登录状态及网络连接。') from None
        if not isinstance(result, dict) or result.get('type') != 'result':
            raise AgentError(f'{label} 返回格式无效，未更新功能表。')
        # Even some CLI wrappers return exit 0 for a failed result. Fail closed.
        if returncode or result.get('is_error') is not False or result.get('subtype') != 'success':
            raise AgentError(f'{label} 未能完成回复，请检查登录状态、网络连接及 CLI 版本；未更新功能表。')
        reply = result.get('result')
    else:
        if returncode:
            raise AgentError('Codex 未能完成回复，请检查 Codex 登录状态及网络连接。')
        reply = None
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get('type') in ('error', 'turn.failed'):
                raise AgentError('Codex 分析失败，未更新功能表；请检查登录状态及网络连接。')
            item = event.get('item', {})
            if event.get('type') == 'item.completed' and isinstance(item, dict) and item.get('type') == 'agent_message':
                reply = item.get('text')
    if not isinstance(reply, str) or not reply.strip():
        raise AgentError(f'{label} 没有返回可显示的回复。')
    return reply


def capture(args, project, prompt, cancelled, deadline, timeout, env=None):
    """Capture one cancellable child without exposing its stderr or configuration."""
    if cancelled.is_set():
        raise AgentError('操作已取消，原规划文件未改变；可以修改需求后重试。')
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding='utf-8',
                          cwd=project['directory'], env=env, start_new_session=True) as process:
        first = True

        def stop():
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()

        try:
            while True:
                if cancelled.is_set():
                    stop()
                    raise AgentError('操作已取消，原规划文件未改变；可以修改需求后重试。')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stop()
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    output, errors = process.communicate(input=prompt if first else None,
                                                         timeout=min(.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    first = False
        except BaseException:
            if process.poll() is None:
                stop()
            raise
        if cancelled.is_set():
            raise AgentError('操作已取消，原规划文件未改变；可以修改需求后重试。')
        return subprocess.CompletedProcess(args, process.returncode, output, errors)


def mcp_inventory(result, require_disabled=False):
    message = '无法确认 Codex 的 MCP 工具已禁用，已停止分析；请检查 Codex CLI 配置后重试。'
    try:
        servers = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise AgentError(message) from None
    if result.returncode or not isinstance(servers, list):
        raise AgentError(message)
    names = []
    for server in servers:
        name = server.get('name') if isinstance(server, dict) else None
        if not isinstance(name, str) or not name or len(name) > 256 or not name.isprintable():
            raise AgentError(message)
        if require_disabled and server.get('enabled') is not False:
            raise AgentError(message)
        names.append(name)
    return names


def run(provider, project, prompt, *, cancelled=None, timeout=TIMEOUT_SECONDS, on_start=None, on_finish=None):
    """Run one analysis in a fresh process group, without changing saved documents.

    stdin carries the complete project-scoped prompt. No conversation/session is
    resumed across requests or projects. Cancellation and the 180-second deadline
    cover both the safety preflight and the model request.
    """
    cancelled = cancelled if cancelled is not None else threading.Event()
    registration = object()
    with _ACTIVE_LOCK:
        if _SHUTTING_DOWN:
            raise AgentError('项目管理器正在停止，未启动新的分析；请重新打开后重试。')
        _ACTIVE_RUNS[registration] = cancelled
    deadline = time.monotonic() + timeout
    try:
        path = executable(provider)
        if on_start:
            on_start(cancelled.set)
        names = []
        env = None
        if provider == 'codex':
            inventory = capture([path, *codex_options(), 'mcp', 'list', '--json'], project, '',
                                cancelled, deadline, timeout)
            names = mcp_inventory(inventory)
            checked = capture([path, *codex_options(names), 'mcp', 'list', '--json'], project, '',
                              cancelled, deadline, timeout)
            mcp_inventory(checked, require_disabled=True)
        else:
            # Match the official Agent SDK subprocess isolation (anthropics/
            # claude-agent-sdk-python, transport/subprocess_cli.py, issue #573).
            # CLAUDECODE marks the host session; authentication, permissions and
            # managed policy remain untouched. No resume/session ID is passed.
            env = {key: value for key, value in os.environ.items() if key != 'CLAUDECODE'}
        args = command(provider, path, names)
        result = capture(args, project, prompt, cancelled, deadline, timeout, env)
        return parse_reply(provider, result.stdout, result.returncode, result.stderr)
    finally:
        try:
            if on_finish:
                on_finish()
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_RUNS.pop(registration, None)
