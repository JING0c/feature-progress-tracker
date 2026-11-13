#!/usr/bin/env python3
"""Independently audit release ZIPs, then exercise their actual MCP entrypoints."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path('/Users/olcgb/code/protuct_plan')
OUT = Path(Path('/tmp/fpt-release-package-review-current').read_text())
RAW = OUT / 'stdio-raw.jsonl'
EVIDENCE = {'reviewer': '/root/release_package_review', 'archives': {}, 'calls': [], 'result': 'RUNNING'}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def package_members(z, prefix=''):
    return {n[len(prefix):]: z.read(n) for n in z.namelist() if n.startswith(prefix)}

def check_package(data, host):
    inventory = json.loads(data['package-inventory.json'])
    assert inventory['version'] == '0.2.0' and inventory['host'] == host
    assert inventory['files_sha256'] == {n: sha(raw) for n, raw in data.items() if n != 'package-inventory.json'}
    for n, raw in data.items():
        if n.startswith('runtime/scripts/'):
            assert raw == (ROOT / 'scripts' / n[len('runtime/scripts/'):]).read_bytes(), n
    for n in ('SKILL.md', 'docs/plugins.md', 'docs/项目文件说明.md'):
        assert data['runtime/' + n] == (ROOT / n).read_bytes(), n
    assert data['skills/project-manager/references/workflow.md'] == (ROOT / 'plugins/common/workflow.md').read_bytes()
    return {'files': len(data), 'version': inventory['version'], 'inventory_source_match': True}

def call(package, host, workspace, tool, **args):
    spec = json.loads((package / '.mcp.json').read_text())['mcpServers']['feature-progress-tracker']
    executable = shutil.which(spec['command'])
    assert executable
    argv = [executable] + [v.replace('${PLUGIN_ROOT}', str(package)).replace('${CLAUDE_PLUGIN_ROOT}', str(package)) for v in spec['args']]
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': tool, 'arguments': {'workspace': str(workspace), **args}, '_meta': {'progressToken': 'review'}}},
    ]
    empty_bin = OUT / 'empty-bin'; empty_bin.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PATH=str(empty_bin), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    result = subprocess.run(argv, input='\n'.join(json.dumps(r, ensure_ascii=False) for r in requests) + '\n',
                            text=True, capture_output=True, timeout=30, cwd=OUT, env=env)
    assert result.returncode == 0 and result.stderr == '', result.stderr
    frames = [json.loads(row) for row in result.stdout.splitlines()]
    with RAW.open('a') as stream:
        stream.write(json.dumps({'host': host, 'requests': requests, 'frames': frames}, ensure_ascii=False) + '\n')
    by_id = {r['id']: r for r in frames if 'id' in r}
    assert by_id[1]['result']['serverInfo']['version'] == '0.2.0'
    assert len(by_id[2]['result']['tools']) == 18
    payload = by_id[3]['result']; assert not payload.get('isError'), payload
    progress = [r['params']['progress'] for r in frames if r.get('method') == 'notifications/progress']
    assert progress == sorted(progress) and progress[-1] == 100
    EVIDENCE['calls'].append({'host': host, 'tool': tool, 'progress': progress, 'exit_code': 0, 'error': False})
    return payload['structuredContent']

PLAN = '''# 发布包隔离测试规划书
## 项目目标与场景
在本机记录书籍并按标题检索。
## 范围与边界
仅测试发布包，不调用模型、不联网。
## 功能规划与验收
| 采用 | 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 所需技术 | 前期准备 | 备注 | 责任组 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 是 | F01 | 无 | 书籍管理 | 管理书籍 | 能保存记录 | 高 | 无 | Python | 准备本地目录 | 根备注 | 测试组 |
| 是 | F01-01 | F01 | 保存书籍 | 保存书籍标题 | 重启后可读取保存的标题 | 高 | 无 | SQLite | 两本测试书 | 用户备注保留 | 测试组 |
'''

def main():
    initial_sources = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (ROOT / 'scripts').glob('*') if p.is_file()}
    unpacked = {}
    for host in ('codex', 'claude', 'marketplace'):
        archive = ROOT / 'dist' / ('feature-progress-tracker-' + host + '.zip')
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            names = z.namelist(); assert len(names) == len(set(names))
            assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
            assert not any(stat.S_ISLNK(i.external_attr >> 16) for i in z.infolist())
            forbidden = [n for n in names if any(x in Path(n).parts for x in ('项目', '规划历史', 'exports', 'tests', '__pycache__', '.git')) or Path(n).name in ('.env', '功能执行情况.md', '项目规划书.md', '项目列表.md') or n.endswith(('.key', '.pem', '.pyc'))]
            assert not forbidden, forbidden
            details = {'sha256': sha(archive.read_bytes()), 'files': len(names), 'forbidden_files': []}
            if host != 'marketplace':
                unpacked[host] = package_members(z)
                details.update(check_package(unpacked[host], host))
                package = OUT / ('final-extracted-' + host)
                z.extractall(package)
            else:
                for nested in ('codex', 'claude'):
                    nested_data = package_members(z, 'plugins/' + nested + '/')
                    assert nested_data == unpacked[nested], nested
                    check_package(nested_data, nested)
                details['nested_plugins_equal_single_zips'] = True
                for config, host_ in (('.agents/plugins/marketplace.json', 'codex'), ('.claude-plugin/marketplace.json', 'claude')):
                    market = json.loads(z.read(config)); source = market['plugins'][0]['source']
                    assert (source['path'] if isinstance(source, dict) else source) == './plugins/' + host_
            EVIDENCE['archives'][host] = details
    for host in ('codex', 'claude'):
        package = OUT / ('final-extracted-' + host)
        workspace = OUT / ('isolated-' + host)
        def run(tool, **kwargs):
            return call(package, host, workspace, tool, **kwargs)
        pid = run('create_project', name='发布包隔离测试')['project']['id']
        before = run('read_project', project_id=pid)
        run('save_plan', project_id=pid, content=PLAN, revision=before['plan']['revision'])
        candidate = run('generate_ledger', project_id=pid)
        assert '目标：在本机记录书籍并按标题检索。' in candidate['content']
        assert run('read_project', project_id=pid)['ledger']['content'] == before['ledger']['content']
        run('save_ledger', project_id=pid, content=candidate['content'], revision=candidate['ledger_revision'], plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])
        saved = run('read_project', project_id=pid)
        assert '目标：在本机记录书籍并按标题检索。' in saved['ledger']['content']
        exported = run('export_project', project_id=pid, format='xlsx')
        with zipfile.ZipFile(exported['path']) as book:
            assert book.testzip() is None
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            sheet = ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
            rows = [{''.join(c for c in cell.attrib['r'] if c.isalpha()): ''.join(cell.itertext()) for cell in row} for row in sheet.findall('s:sheetData/s:row', ns)]
            header = next(row for row in rows if '功能介绍' in row.values() and '所需技术' in row.values())
            columns = {value: key for key, value in header.items()}
            detail = next(row for row in rows if any('F01-01' in value for value in row.values()))
            assert detail[columns['所需技术']] == 'SQLite'
            assert detail[columns['前期准备']] == '两本测试书'
            assert '所需技术：' not in detail[columns['功能介绍']] and '前期准备：' not in detail[columns['功能介绍']]
            assert '用户备注保留' in detail[columns['功能介绍']] and '测试组' in detail[columns['功能介绍']]
        EVIDENCE.setdefault('hosts', {})[host] = {'goal_sync': True, 'preview_not_saved': True, 'details_export_separate': True, 'no_model_or_git_on_path': True}
    assert initial_sources == {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (ROOT / 'scripts').glob('*') if p.is_file()}
    EVIDENCE['source_sha256'] = initial_sources
    EVIDENCE['result'] = 'PASS'

try:
    main()
except Exception as exc:
    EVIDENCE['result'] = 'FAIL'; EVIDENCE['error'] = repr(exc)
    raise
finally:
    (OUT / 'final-audit.json').write_text(json.dumps(EVIDENCE, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'result': EVIDENCE['result'], 'calls': len(EVIDENCE['calls']), 'archives': EVIDENCE['archives']}, ensure_ascii=False, indent=2))
