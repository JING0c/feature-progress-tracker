#!/usr/bin/env python3
"""Stdio MCP adapter for deterministic project operations in host conversations."""
import argparse
import json
from pathlib import Path
import sys

from plugin_manager import start, stop, status, workspace_path
from serve_dashboard import ProjectStore, RequestError, planning_module
from project_tools import TOOLS, validate

VERSION = '0.2.0'
PROTOCOLS = ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')
def call_tool(name, args, agent):
    schema = next((tool['inputSchema'] for tool in TOOLS if tool['name'] == name), None)
    if schema is None:
        raise ValueError('未知工具：' + str(name))
    validate(args, schema)
    path = workspace_path(args['workspace'])
    if name == 'open_dashboard':
        return start(str(path), agent, args.get('port', 8765))
    if name == 'stop_dashboard':
        current = status(str(path), agent)
        return stop(str(path), current['agent'] if current['running'] else agent)
    if name != 'create_project' and (not path.is_dir() or not (path / '项目列表.md').is_file()):
        raise ValueError('未找到项目列表.md。请在当前对话中调用create_project新建或导入项目。')
    if name == 'list_projects':
        return ProjectStore(workspace=path, initialize=False).overview()
    from project_service import ProjectService
    return ProjectService(str(path), actor=agent).call(name, {k:v for k,v in args.items() if k != 'workspace'})


def respond(identity, result=None, error=None):
    response = {'jsonrpc': '2.0', 'id': identity}
    response['error' if error else 'result'] = error if error else result
    print(json.dumps(response, ensure_ascii=False, separators=(',', ':')), flush=True)


class ConversationProgress:
    def __init__(self, token):
        self.token = token
        self.percent = 0

    def step(self, _key, percent, stage, detail=''):
        self.percent = max(self.percent, min(100, int(percent)))
        print(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {
            'progressToken': self.token, 'progress': self.percent, 'total': 100,
            'message': stage + ('：' + detail if detail else '')}}, ensure_ascii=False), flush=True)


def serve(agent):
    initialized = False
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except (ValueError, UnicodeError):
            respond(None, error={'code': -32700, 'message': 'Invalid JSON'})
            continue
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            respond(None, error={'code': -32600, 'message': 'Invalid JSON-RPC request'})
            continue
        identity = request.get('id')
        if 'id' not in request:
            # Notifications never produce a response, including initialization acknowledgement.
            continue
        if identity is None or type(identity) not in (int, str):
            respond(None, error={'code': -32600, 'message': 'Invalid request ID'})
            continue
        method, params = request['method'], request.get('params', {})
        if not isinstance(params, dict):
            respond(identity, error={'code': -32602, 'message': 'Parameters must be an object'})
            continue
        if method == 'initialize':
            version = params.get('protocolVersion')
            if not isinstance(version, str):
                respond(identity, error={'code': -32602, 'message': 'protocolVersion is required'})
                continue
            initialized = True
            respond(identity, {'protocolVersion': version if version in PROTOCOLS else '2025-06-18',
                               'capabilities': {'tools': {}},
                               'serverInfo': {'name': 'feature-progress-tracker', 'version': VERSION},
                               'instructions': '只访问用户明确指定的管理目录。所有分析在当前宿主会话完成，操作通过工具执行，不启动另一个模型。先读当前版本再预览修改，按用户授权保存；网页只读。不能把建议或源码核对当独立实现验收。'})
        elif method == 'ping':
            respond(identity, {})
        elif not initialized:
            respond(identity, error={'code': -32002, 'message': 'Initialize first'})
        elif method == 'tools/list':
            respond(identity, {'tools': TOOLS})
        elif method == 'tools/call':
            progress = None
            context = None
            try:
                meta = params.get('_meta', {})
                if isinstance(meta, dict) and type(meta.get('progressToken')) in (str, int):
                    progress = ConversationProgress(meta['progressToken'])
                    module = planning_module('planning_progress')
                    context = module.CURRENT.set((progress, None))
                    progress.step(None, 5, '检查工具参数')
                result = call_tool(params.get('name'), params.get('arguments', {}), agent)
                if progress: progress.step(None, 100, '操作完成')
                respond(identity, {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'structuredContent': result})
            except (RequestError, OSError, ValueError, TypeError, RuntimeError) as exc:
                if progress: progress.step(None, progress.percent, '操作失败', str(exc))
                respond(identity, {'content': [{'type': 'text', 'text': str(exc)}],
                                   'structuredContent': {'error': str(exc), 'code': getattr(exc, 'code', 400), **getattr(exc, 'details', {})}, 'isError': True})
            except Exception as exc:
                # Keep the protocol alive without leaking a traceback or project content to stdout.
                print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr, flush=True)
                respond(identity, {'content': [{'type': 'text', 'text': '操作失败，请检查目录、版本和 Markdown 文件格式；不要假定已经保存。'}], 'isError': True})
            finally:
                if context is not None: module.CURRENT.reset(context)
        else:
            respond(identity, error={'code': -32601, 'message': 'Method not found'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=('codex', 'claude'), default='codex')
    serve(parser.parse_args().agent)
