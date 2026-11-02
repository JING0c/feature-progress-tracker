#!/usr/bin/env python3
"""Serve a local feature ledger dashboard and planning assistant."""
import argparse
import errno
import hashlib
import json
import os
import tempfile
import re
import secrets
import shutil
import subprocess
import threading
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GROUP = re.compile(r'^##\s+大功能\s+([^：:\s]+)\s*[：:]\s*(.+?)\s*$')
ITEM = re.compile(r'^\s*-\s*\[([ xX])\]\s+(\S+-\d+)\s+(.+?)\s*$')
FIELD = re.compile(r'(?:^|[｜|])\s*([^：:｜|]+)\s*[：:]\s*([^｜|]*)')

def parse(text):
    groups, group, item = [], None, None
    items_by_id = {}
    for line in text.splitlines():
        m = GROUP.match(line)
        if m:
            group = {'id': m[1], 'name': m[2], 'items': []}
            groups.append(group)
            items_by_id = {}
            item = None
            continue
        if line.startswith('## '):
            group = item = None
            continue
        m = ITEM.match(line)
        if m and group is not None:
            pieces = re.split(r'[｜|]', m[3])
            item = {'id': m[2], 'name': pieces[0].strip(), 'checked': m[1].lower() == 'x', 'fields': {}, 'notes': [], 'children': []}
            item['fields'].update({k.strip().strip('*_`').strip(): v.strip() for k, v in FIELD.findall('｜'.join(pieces[1:]))})
            parent = items_by_id.get(item['id'].rsplit('-', 1)[0])
            (parent['children'] if parent else group['items']).append(item)
            items_by_id[item['id']] = item
            continue
        if item is not None and re.match(r'^\s{2,}-\s+', line):
            content = re.sub(r'^\s*-\s*', '', line)
            # A semicolon separates fields only when followed by another label;
            # ordinary punctuation inside acceptance criteria must be preserved.
            content = re.sub(r'[；;](?=\s*[^；;：:｜|]{1,30}[：:])', '｜', content)
            fields = FIELD.findall(content)
            if fields:
                item['fields'].update({k.strip().strip('*_`').strip(): v.strip() for k, v in fields})
            else:
                item['notes'].append(content)
    return groups

PAGE = (Path(__file__).resolve().parent / 'dashboard.html').read_text(encoding='utf-8')
PLANNING_PAGE = (Path(__file__).resolve().parent / 'planning.html').read_text(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description='Serve a read-only local feature dashboard')
    parser.add_argument('ledger', type=Path)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    ledger = args.ledger.resolve()
    if not ledger.is_file():
        parser.error(f'台账不存在: {ledger}')
    token = secrets.token_urlsafe(32)
    planning_lock = threading.Lock()
    ledger_lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def local_request(self):
            host = self.headers.get('Host', '')
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            origin = self.headers.get('Origin')
            return host in expected and (not origin or origin in {f'http://{h}' for h in expected})

        def do_POST(self):
            if not self.local_request() or self.headers.get('X-Planning-Token') != token:
                self.send_error(403)
                return
            if self.path == '/api/ledger/save':
                self.save_ledger()
                return
            if self.path != '/api/planning':
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 100000:
                    raise ValueError('对话内容过长或为空')
                payload = json.loads(self.rfile.read(length))
                messages = payload.get('messages')
                if not isinstance(messages, list) or not messages or len(messages) > 60:
                    raise ValueError('对话格式无效或轮次过多')
                for m in messages:
                    if not isinstance(m, dict) or m.get('role') not in ('user', 'assistant') or not isinstance(m.get('content'), str) or not m['content'].strip():
                        raise ValueError('对话格式无效')
                if messages[-1]['role'] != 'user':
                    raise ValueError('最后一条消息必须来自用户')
                codex = shutil.which('codex')
                if not codex:
                    raise RuntimeError('未找到 Codex 命令行，请检查安装与登录状态。')
                if not planning_lock.acquire(blocking=False):
                    raise RuntimeError('已有规划对话正在处理，请稍后再试。')
                try:
                    prompt = ("你是项目规划助手，参考 project-mngt 的项目经理方法，与用户多轮对话逐步完成规划。"
                              "先了解目标、使用者、场景、范围及约束；按已有信息有针对性地追问，每轮不要堆砌问题。"
                              "梳理需求及来源，标记假设、争议和待确认事项；按用户流程和功能内聚性拆成可独立验证的功能组，"
                              "分析业务、技术、数据和集成依赖及阻塞关系，结合用户价值、风险、依赖确定先后顺序。"
                              "必要时提出验证核心假设的 MVP、上线必需项和后续迭代，并说明取舍；小项目不强加阶段。"
                              "仅在有团队、资源、范围和约束依据时估算工期，标明假设和不确定性，不编造数字。"
                              "用户要求整理规划时，概述目标与范围、分层功能、可检验验收标准、优先级、依赖、风险、"
                              "未决问题；按需求适当加入阶段、里程碑和退出标准。现有项目需求变更时保留历史和审核证据，"
                              "说明对已完成、进行中及未开始工作的影响；已完成项发生实质变化或回归时重新审核。"
                              "不要把规划假称已实现，不修改文件或执行命令。用户要求功能台账时，输出可解析的 Markdown："
                              "大功能标题使用‘## 大功能 F01：名称’，小功能使用‘- [ ] F01-01 名称｜状态：未开始’，"
                              "更细功能按 F01-01-01 编号并缩进；列出验收、优先级、依赖、执行 Agent、实现证据、"
                              "审核 Agent、评分和问题。身份未知写待分配，未审核项不勾选。"
                              "以下是完整对话，继续回复最后一条：\n\n" +
                              '\n\n'.join(('用户' if m['role'] == 'user' else '助手') + '：' + m['content'] for m in messages))
                    result = subprocess.run([codex, 'exec', '--sandbox', 'read-only', '--skip-git-repo-check', '--ephemeral', '--json', '-'],
                                            input=prompt, text=True, capture_output=True, cwd=str(ledger.parent), timeout=180)
                    if result.returncode:
                        raise RuntimeError('Codex 未能完成回复，请检查 Codex 登录状态及网络连接。')
                    replies = []
                    for line in result.stdout.splitlines():
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        item = event.get('item', {})
                        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                            replies.append(item.get('text', ''))
                    if not replies:
                        raise RuntimeError('Codex 没有返回可显示的回复。')
                    response = {'reply': replies[-1]}
                finally:
                    planning_lock.release()
                code = 200
            except (ValueError, json.JSONDecodeError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                response = {'error': '智能体回复超时，请重试。' if isinstance(exc, subprocess.TimeoutExpired) else str(exc)}
                code = 400
            data = json.dumps(response, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def save_ledger(self):
            code = 400
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 1000000:
                    raise ValueError('台账内容为空或超过大小限制。')
                payload = json.loads(self.rfile.read(length))
                content = payload.get('content')
                revision = payload.get('revision')
                if not isinstance(content, str) or not isinstance(revision, str):
                    raise ValueError('台账或版本信息无效。')
                groups = parse(content)
                all_items = []
                def collect(items):
                    for item in items:
                        all_items.append(item)
                        collect(item['children'])
                for group in groups:
                    collect(group['items'])
                if not all_items:
                    raise ValueError('未找到可识别的功能台账；请先生成含大功能和功能点的台账。')
                if any(i['checked'] or i['fields'].get('状态') == '已完成' for i in all_items):
                    raise ValueError('规划草稿包含已完成项；请先移除未经独立审核的完成标记。')
                required = ('状态', '验收', '优先级', '依赖', '执行 Agent', '实现证据', '审核 Agent', '评分', '问题')
                incomplete = [i['id'] for i in all_items if any(not i['fields'].get(k, '').strip() for k in required)]
                if incomplete:
                    raise ValueError('以下功能点缺少状态、验收、优先级、依赖、执行、证据、审核、评分或问题：' + '、'.join(incomplete[:8]))
                with ledger_lock:
                    old = ledger.read_bytes()
                    if hashlib.sha256(old).hexdigest() != revision:
                        code = 409
                        raise ValueError('台账已在别处发生变化，请重新检查后再保存。')
                    with tempfile.NamedTemporaryFile(prefix=ledger.name + '.backup-', suffix='.md', dir=ledger.parent, delete=False) as backup:
                        backup.write(old)
                        backup.flush()
                        os.fsync(backup.fileno())
                        backup_path = backup.name
                    tmp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(prefix='.ledger-', dir=ledger.parent, delete=False) as tmp:
                            tmp_path = tmp.name
                            tmp.write(content.encode('utf-8'))
                            tmp.flush()
                            os.fsync(tmp.fileno())
                        os.chmod(tmp_path, ledger.stat().st_mode & 0o777)
                        if hashlib.sha256(ledger.read_bytes()).hexdigest() != revision:
                            code = 409
                            raise ValueError('台账已在别处发生变化，请重新检查后再保存。')
                        os.replace(tmp_path, ledger)
                        tmp_path = None
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                response = {'backup': backup_path, 'count': len(all_items)}
                code = 200
            except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
                response = {'error': str(exc)}
            data = json.dumps(response, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.local_request():
                self.send_error(403)
                return
            if self.path == '/planning':
                data, status, kind = PLANNING_PAGE.replace('__PLANNING_TOKEN__', token).replace('__PLANNING_KEY__', hashlib.sha256(str(ledger).encode()).hexdigest()).encode(), 200, 'text/html; charset=utf-8'
            elif self.path == '/':
                data, status, kind = PAGE.encode(), 200, 'text/html; charset=utf-8'
            elif self.path == '/api/ledger/info':
                try:
                    data = json.dumps({'revision': hashlib.sha256(ledger.read_bytes()).hexdigest(), 'path': str(ledger)}, ensure_ascii=False).encode()
                    status = 200
                except OSError as exc:
                    data, status = json.dumps({'error': str(exc)}, ensure_ascii=False).encode(), 500
                kind = 'application/json; charset=utf-8'
            elif self.path == '/api/ledger':
                try:
                    data = json.dumps({'groups': parse(ledger.read_text(encoding='utf-8'))}, ensure_ascii=False).encode()
                    status = 200
                except (OSError, UnicodeError) as exc:
                    data, status = json.dumps({'error': str(exc)}, ensure_ascii=False).encode(), 500
                kind = 'application/json; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE or args.port == 0:
            raise
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        print(f'端口 {args.port} 已被占用，已切换到空闲端口 {server.server_port}。', flush=True)
    print(f'功能看板：http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
