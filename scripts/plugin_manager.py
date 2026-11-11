#!/usr/bin/env python3
"""Start or locate a plugin's loopback dashboard without using the plugin cache for data."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

STATE_DIR = '.feature-progress-tracker'
AGENTS = ('codex', 'claude')
_PROCESSES = []  # Keep handles so a long-lived MCP process can reap exited servers.


def workspace_path(value):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '\x00\r\n'):
        raise ValueError('请明确指定保存项目列表的管理目录。')
    path = Path(value).expanduser().resolve()
    if path.exists() and not path.is_dir():
        raise ValueError('管理目录必须是文件夹。')
    # Installed code may be refreshed or removed by the host at any time.
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / 'plugin.json').is_file() or (ancestor / '.claude-plugin/plugin.json').is_file():
            if path == ancestor or ancestor in path.parents:
                raise ValueError('请把项目数据放在插件目录之外，以免插件更新时丢失。')
            break
    return path


def validate_options(workspace, agent, port=8765):
    path = workspace_path(workspace)
    if agent not in AGENTS:
        raise ValueError('智能体只能选择 codex 或 claude。')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('端口必须是 0 到 65535 的整数。')
    return path


def http_json(url):
    # A machine-wide proxy must never receive local project metadata.
    with build_opener(ProxyHandler({})).open(url, timeout=1) as response:
        return json.loads(response.read(65536))


def runtime_signature():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for file in sorted(root.iterdir()):
        if file.is_file() and file.suffix in ('.py', '.js', '.css', '.html'):
            digest.update(file.name.encode()); digest.update(file.read_bytes())
    return str(root), digest.hexdigest()


def _status(path, agent):
    empty = {'running': False, 'workspace': str(path), 'agent': agent}
    try:
        record = json.loads((path / STATE_DIR / 'dashboard.json').read_text(encoding='utf-8'))
        port = record['port']
        if type(port) is not int or not 1 <= port <= 65535:
            return empty
        # Construct our own loopback URL; never follow a URL from a state file.
        base = 'http://127.0.0.1:' + str(port)
        runtime = http_json(base + '/api/runtime')
        expected = {key: record[key] for key in ('instance_id', 'pid')}
        expected.update(workspace=str(path), agent=record['agent'])
        if record['agent'] not in AGENTS or not record['instance_id'] or runtime != expected:
            return empty
        runtime_path, signature = runtime_signature()
        return {**empty, 'running': True, 'agent': record['agent'], 'url': base + '/projects',
                'runtime_current': record.get('runtime_path') == runtime_path and record.get('runtime_signature') == signature,
                'pid': record['pid'], 'log_path': record.get('log_path', '')}
    except (OSError, URLError, ValueError, KeyError, TypeError):
        return empty


def status(workspace, agent='codex'):
    return _status(validate_options(workspace, agent), agent)


@contextmanager
def file_lock(path, timeout=15):
    """OS locks release on process exit, including a crashed MCP client."""
    with path.open('a+b') as file:
        if os.name == 'nt':
            import msvcrt
            if file.tell() == 0:
                file.write(b'0'); file.flush()
            def acquire():
                file.seek(0); msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                file.seek(0); msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire(); break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('这个管理目录已有服务或操作正在运行，请先关闭原服务再重试。')
                time.sleep(.1)
        try:
            yield
        finally:
            release()


def service_lease(workspace):
    """The running server holds this lease even if metadata is damaged or lost."""
    state = Path(workspace).resolve() / STATE_DIR
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    return file_lock(state / 'service.lock', timeout=0)


def start(workspace, agent='codex', port=8765):
    _PROCESSES[:] = [child for child in _PROCESSES if child.poll() is None]
    path = validate_options(workspace, agent, port)
    state = path / STATE_DIR
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with file_lock(state / 'dashboard.lock'):
        current = _status(path, agent)
        if current['running']:
            if current['agent'] != agent:
                raise RuntimeError('这个管理目录正由 ' + current['agent'] + ' 提供分析。请先停止原服务，再使用 ' + agent + ' 打开；项目文件会保留。原网页：' + current['url'])
            if not current['runtime_current']:
                raise RuntimeError('项目管理器代码已更新，请先停止旧服务再重新打开。项目文件会保留。')
            return {**current, 'reused': True}
        instance_id = secrets.token_hex(16)
        log_path = state / (agent + '-' + instance_id + '.log')
        command = [sys.executable, str(Path(__file__).with_name('serve_dashboard.py')),
                   '--workspace', str(path), '--agent', agent,
                   '--port', str(port), '--instance-id', instance_id]
        with log_path.open('wb') as log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, cwd=path, start_new_session=True)
        try:
            deadline = time.monotonic() + 12
            actual_port = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('项目管理器启动失败，请查看日志：' + str(log_path))
                with log_path.open('rb') as log:
                    output = log.read(65536).decode('utf-8', errors='replace')
                match = re.search(r'功能看板：http://127\.0\.0\.1:(\d+)/', output)
                if match:
                    actual_port = int(match[1])
                    try:
                        runtime = http_json(f'http://127.0.0.1:{actual_port}/api/runtime')
                        if runtime == {'instance_id': instance_id, 'pid': process.pid,
                                       'workspace': str(path), 'agent': agent}:
                            break
                    except (OSError, URLError, ValueError):
                        pass
                time.sleep(.1)
            else:
                raise RuntimeError('项目管理器启动超时，请查看日志：' + str(log_path))
            runtime_path, signature = runtime_signature()
            record = {'instance_id': instance_id, 'pid': process.pid, 'port': actual_port,
                      'runtime_path': runtime_path, 'runtime_signature': signature,
                      'workspace': str(path), 'agent': agent, 'log_path': str(log_path)}
            fd, temporary = tempfile.mkstemp(prefix=agent + '-', suffix='.tmp', dir=state)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as file:
                    json.dump(record, file, ensure_ascii=False)
                os.replace(temporary, state / 'dashboard.json')
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            _PROCESSES.append(process)
            return {'running': True, 'workspace': str(path), 'agent': agent,
                    'url': f'http://127.0.0.1:{actual_port}/projects', 'pid': process.pid,
                    'log_path': str(log_path), 'reused': False}
        except BaseException:
            # Only this process handle is ours; never terminate a listener occupying a port.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            raise


def stop(workspace, agent='codex'):
    path = validate_options(workspace, agent)
    state = path / STATE_DIR
    if not state.is_dir():
        return {'stopped': False, 'workspace': str(path), 'agent': agent, 'reason': '未找到本插件启动的服务。'}
    with file_lock(state / 'dashboard.lock'):
        current = _status(path, agent)
        if not current['running']:
            return {**current, 'stopped': False, 'reason': '没有可核验的插件服务，未停止任何进程。'}
        if current['agent'] != agent:
            raise RuntimeError('当前服务使用 ' + current['agent'] + '，请明确指定 --agent ' + current['agent'] + ' 再停止。')
        try:
            os.kill(current['pid'], signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            # A failed HTTP request alone does not establish process exit; acquire its lease.
            try:
                with service_lease(path):
                    break
            except RuntimeError:
                time.sleep(.1)
        else:
            raise RuntimeError('停止服务尚未完成，请稍后查看状态；未强制终止进程。')
        (state / 'dashboard.json').unlink(missing_ok=True)
        for child in _PROCESSES:
            child.poll()
        return {'stopped': True, 'workspace': str(path), 'agent': agent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'status', 'stop'))
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--agent', choices=AGENTS, default='codex')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.action == 'start':
            result = start(args.workspace, args.agent, args.port)
        else:
            result = (stop if args.action == 'stop' else status)(args.workspace, args.agent)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
