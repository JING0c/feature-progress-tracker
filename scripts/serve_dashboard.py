#!/usr/bin/env python3
"""Read-only local views of projects managed from Codex or Claude Code conversations."""
import sys
import argparse
import atexit
from contextlib import nullcontext
import difflib
import errno
import hashlib
import importlib.util
import json
import os
import tempfile
import re
import secrets
import signal
import subprocess
import threading
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlparse, parse_qs, quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GROUP = re.compile(r'^##\s+大功能\s+([^：:\s]+)\s*[：:]\s*(.+?)\s*$')
ITEM = re.compile(r'^\s*-\s*\[([ xX])\]\s+(\S+-\d+|F\d+(?!\s+总状态\s*[：:]))\s+(.+?)\s*$')
FIELD = re.compile(r'(?:^|[｜|])\s*([^：:｜|]+)\s*[：:]\s*([^｜|]*)')

def parse(text):
    groups, group, item = [], None, None
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        m = GROUP.match(line)
        if m:
            group = {'id': m[1], 'name': m[2], 'items': []}
            groups.append(group)
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
            group['items'].append(item)
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
    # Saved history may precede a newly added parent. Collect complete records
    # first, then link only within each section without changing sibling order.
    for group in groups:
        records = group['items']
        items_by_id = {record['id']: record for record in records}
        group['items'] = []
        for record in records:
            parent_id, separator, _ = record['id'].rpartition('-')
            parent = items_by_id.get(parent_id) if separator else None
            (parent['children'] if parent else group['items']).append(record)
    return groups

BASE = Path(__file__).resolve().parent
VALID_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
EMPTY_HASH = hashlib.sha256(b'').hexdigest()


@lru_cache(maxsize=None)
def planning_module(name):
    if name == 'planning_editor': planning_module('planning_sheet')
    if name in ('planning_suggestions','planning_activity','planning_operations'): planning_module('planning_editor')
    if name == 'planning_activity': planning_module('planning_history')
    # Resolve these local helpers independently of the caller's working directory
    # (the dashboard can also be imported by an integration test).
    spec = importlib.util.spec_from_file_location(name, BASE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def operation_step(percent, stage, detail=''):
    planning_module('planning_progress').step(percent, stage, detail)

def planning_converters():
    return planning_module('planning_sheet').parse_plan_sheet, planning_module('planning_xlsx').export_plan_xlsx


class RequestError(Exception):
    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.code = status
        self.details = details








def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_document(path, optional=False, recover=False):
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        if not optional:
            raise
        raw = b''
    return {'content': raw.decode('utf-8', errors='replace' if recover else 'strict'), 'revision': digest(raw), 'path': str(path)}


def atomic_write(path, content, revision, backup=True):
    """Validate the observed version, retain the previous file, then replace atomically."""
    existed = path.exists()
    old = path.read_bytes() if existed else b''
    if digest(old) != revision:
        raise RequestError('文件已在别处发生变化，请重新读取后再保存。', 409)
    backup_path = None
    if backup and existed:
        with tempfile.NamedTemporaryFile(prefix=path.name + '.backup-', suffix='.md', dir=path.parent, delete=False) as previous:
            previous.write(old)
            previous.flush()
            os.fsync(previous.fileno())
            backup_path = previous.name
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.project-manager-', dir=path.parent, delete=False) as temp:
            temp_path = temp.name
            temp.write(content.encode('utf-8'))
            temp.flush()
            os.fsync(temp.fileno())
        if existed:
            os.chmod(temp_path, path.stat().st_mode & 0o777)
        current = path.read_bytes() if path.exists() else b''
        if path.exists() != existed or digest(current) != revision:
            raise RequestError('文件已在别处发生变化，请重新读取后再保存。', 409)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    return {'revision': digest(content.encode('utf-8')), 'path': str(path), 'backup': backup_path}


def flatten(items):
    for item in items:
        yield item
        yield from flatten(item.get('children', []))


def leaves(items):
    for item in items:
        # A cancelled parent cancels its subtree for aggregate counting.
        if item['fields'].get('状态') == '已取消':
            continue
        # Cancelled children remain as audit records. If none are active, the
        # retained parent is the current leaf and must still be tracked once.
        children = [child for child in item.get('children', []) if child['fields'].get('状态') != '已取消']
        if children:
            yield from leaves(children)
        else:
            yield item


def has_issue(value):
    value = re.sub(r'\s+', '', (value or '').strip()).rstrip('。.!！')
    # Match the whole negative statement, never a prefix: "无权限" and
    # "暂无问题，但需确认备份" still describe actionable information.
    negative = (r'(?:(?:目前|当前|暂时))?'
                r'(?:(?:无|暂无|没有)(?:已知|新增|额外|其他)*(?:问题|争议|待确认事项)?'
                r'|(?:尚未|未)(?:发现|记录)(?:已知|新增|额外|其他)*(?:问题|争议)?'
                r'|不适用|待确认|—|-)')
    return bool(value) and re.fullmatch(negative, value) is None


def item_flags(item):
    fields = item['fields']
    return {
        'issue': fields.get('状态') == '受阻' or any(has_issue(fields.get(key)) for key in ('问题', '待解决问题')),
        'dispute': any(has_issue(fields.get(key)) for key in ('争议', '争议事项', '争议问题')),
    }


def summarize(groups):
    items = [item for group in groups for item in leaves(group['items'])]
    status = lambda item: item['fields'].get('状态', '未开始')
    return {
        'total': len(items),
        'done': sum(item['checked'] and status(item) == '已完成' for item in items),
        'working': sum(status(item) == '进行中' for item in items),
        'review': sum(status(item) == '待审核' or (status(item) == '已完成' and not item['checked']) for item in items),
        'blocked': sum(status(item) == '受阻' for item in items),
        'issues': sum(item_flags(item)['issue'] for item in items),
        'disputes': sum(item_flags(item)['dispute'] for item in items),
    }


def parse_document(content):
    groups = parse(content)
    if not groups and content.strip():
        has_items = any(ITEM.match(line) for line in content.splitlines())
        empty_template = content.lstrip().startswith('# 功能执行情况') and not has_items
        if not empty_template:
            raise RequestError('台账格式无法识别，请使用大功能标题与功能点列表。')
    for group in groups:
        for item in flatten(group['items']):
            item.update(item_flags(item))
    return groups


def normalize_progress_summary(content, groups):
    """Correct explicit document-header progress only, leaving source prose alone."""
    summary = summarize(groups)
    adjustments, output = [], []
    header, fence = True, None
    progress = re.compile(r'^ {0,3}(?:\*\*)?进度(?:\*\*)?\s*[：:]\s*(?:\*\*)?\s*')
    fraction = re.compile(r'(?P<prefix>(?:已验收|已完成)\s*)\d+(?P<slash>\s*/\s*)\d+'
                          r'(?P<unit>\s*(?:个(?:最细)?功能点)?\s*)'
                          r'(?P<percentage>[（(]\s*(?:\d+(?:\.\d+)?\s*%|不适用)\s*[）)])?'
                          r'(?P<suffix>\s*[。.!！]?\s*)')
    status_field = re.compile(r'(?P<prefix>\s*(?P<label>待审核|受阻|进行中|未开始|已完成)\s*)\d+(?P<suffix>\s*(?:个(?:最细)?功能点)?\s*[。.!！]?\s*)')
    counts = {'待审核': summary['review'], '受阻': summary['blocked'], '进行中': summary['working'], '已完成': summary['done'],
              '未开始': sum(item['fields'].get('状态', '未开始') == '未开始' for group in groups for item in leaves(group['items']))}
    for line in content.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line.rstrip('\r\n'))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            output.append(line)
            continue
        if marker:
            fence = marker[1]
            output.append(line)
            continue
        if re.match(r'^ {0,3}#{2,6}\s', line) or ITEM.match(line):
            header = False
        prefix = progress.match(line)
        if not header or not prefix:
            output.append(line)
            continue
        # Parse independent summary fields, not arbitrary prose containing numbers.
        # Stop at the first unknown field so inline history stays untouched too.
        parts = re.split(r'([；;｜|])', line[prefix.end():])
        completion = fraction.fullmatch(parts[0])
        if not completion:
            output.append(line)
            continue
        percent = str(round(summary['done'] / summary['total'] * 100)) + '%' if summary['total'] else '不适用'
        def update_fraction(match):
            percentage = match['percentage'] or ''
            if percentage:
                percentage = percentage[0] + percent + percentage[-1]
            return f"{match['prefix']}{summary['done']}{match['slash']}{summary['total']}{match['unit']}{percentage}{match['suffix']}"
        parts[0] = update_fraction(completion)
        for index in range(2, len(parts), 2):
            match = status_field.fullmatch(parts[index])
            if not match:
                break
            parts[index] = match['prefix'] + str(counts[match['label']]) + match['suffix']
        revised = line[:prefix.end()] + ''.join(parts)
        if revised != line:
            adjustments.append('台账进度已按实际最细功能点校正：' + line.strip() + ' → ' + revised.strip())
        output.append(revised)
    return ''.join(output), summary, adjustments


def prepare_ledger(content, existing):
    items = validate_ledger(content, existing)
    normalized, summary, adjustments = normalize_progress_summary(content, parse_document(content))
    return {'content': normalized, 'summary': summary, 'adjustments': adjustments, 'count': len(items)}


def preserve_generated_source(target, content):
    with tempfile.NamedTemporaryFile(prefix=target.name + '.generated-source-', suffix='.md', dir=target.parent, delete=False) as source:
        source.write(content.encode('utf-8'))
        source.flush()
        os.fsync(source.fileno())
        return source.name


def inspect_plan(content):
    """Require actual prose under goal, scope, feature and acceptance labels."""
    categories = {'目标': r'目标|背景|概述|goal|objective', '范围': r'范围|边界|约束|scope',
                  '功能': r'功能|需求|feature|requirement', '验收': r'验收|acceptance'}
    placeholder = re.compile(r'^(?:待(?:补充|完善|规划|填写|编写|定义|确定|确认|定)|'
                             r'(?:请|在此)?(?:填写|补充|描述)(?:项目)?(?:目标|范围|功能|需求|验收)|'
                             r'尚未生成|未生成|todo\b|tbd\b|'
                             r'(?:add|insert|write|enter|describe)\b.*\bhere\b|'
                             r'to be (?:decided|defined|determined)\b)', re.I)
    def substantive(text):
        if placeholder.search(text.strip('*_`[<>] ')):
            return False
        plain = re.sub(r'[*_`#\[\]（）()。.!！：:;；、，,\s-]', '', text)
        return (len(plain) >= 6 and
                not re.fullmatch(r'(?i)(?:todo|tbd|待补充|待规划|待确认|尚未生成|未生成|暂无|无|待定)+', plain) and
                '尚未生成规划书' not in plain and '请在规划页面梳理需求' not in plain)

    syntax = planning_module('planning_sheet')

    def cells(line):
        return syntax._table_row(line)[0]

    def category_keys(label):
        return {key for key, pattern in categories.items() if re.search(pattern, label, re.I)}

    found, section, fence, table_headers = set(), set(), None, None
    lines = content.splitlines()
    for number, line in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence == marker[1][0]:
                fence = None
            elif not fence:
                fence = marker[1][0]
            continue
        if fence or line.lstrip().startswith('>'):
            continue
        heading = re.match(r'^\s*#{1,6}\s+(.+)', line)
        if heading:
            section = category_keys(heading[1])
            table_headers = None
            continue
        # A table's header/separator is structure, never evidence of a real plan.
        table_start = syntax._table_start(lines, number)
        if table_start:
            table_headers = table_start
            continue
        if '|' in line and all(re.fullmatch(r':?-{3,}:?', c) for c in cells(line)):
            continue
        if table_headers and '|' in line:
            values = cells(line)
            if len(values) != len(table_headers):
                # An unescaped pipe can shift fields; ambiguous columns must not
                # turn a description into evidence for missing acceptance text.
                continue
            typed = set().union(*(category_keys(h) for h in table_headers))
            row_keys = category_keys(values[0]) if values and not typed else set()
            for column, value in enumerate(values):
                header = table_headers[column] if column < len(table_headers) else ''
                keys = category_keys(header) or (section - typed)
                if re.search(r'说明|描述|内容|description', header, re.I) and '功能' in section:
                    keys.add('功能')
                if column > 0:
                    keys |= row_keys
                if substantive(value):
                    found.update(keys)
            continue
        table_headers = None
        if line.lstrip().startswith('|'):
            continue
        text = re.sub(r'^[\s*+\-\d.)]+', '', line).strip()
        if placeholder.search(text.strip('*_`[<>] ')):
            continue
        fields = re.match(r'^([^：:]{1,40})[：:]\s*(.*)$', text)
        keys = set(section)
        if fields:
            keys.update(key for key, pattern in categories.items() if re.search(pattern, fields[1], re.I))
            text = fields[2]
        if substantive(text):
            found.update(keys)
    missing = [key for key in categories if key not in found]
    return {'valid': not missing, 'missing': missing}


class ProjectStore:
    def __init__(self, workspace=None, ledger=None, initialize=True):
        self.workspace = workspace.resolve() if workspace else None
        self.single_ledger = ledger.resolve() if ledger else None
        self.registry_lock = threading.Lock()
        self.locks_lock = threading.Lock()
        self.locks = {}
        self.generated_plans = {}
        self.source_progress = {}
        self.operation_progress = planning_module('planning_progress').Progress()
        if self.workspace:
            self.registry = self.workspace / '项目列表.md'
            if initialize:
                self.workspace.mkdir(parents=True, exist_ok=True)
            if initialize and not self.registry.exists():
                try:
                    with self.registry.open('x', encoding='utf-8') as file:
                        file.write('# 项目列表\n\n每个项目使用独立目录，规划书与功能台账都是 Markdown。\n')
                except FileExistsError:
                    pass

    def lock_for(self, kind, path):
        key = (kind, str(path))
        with self.locks_lock:
            return self.locks.setdefault(key, threading.Lock())

    def single(self):
        return {'id': 'single', 'name': self.single_ledger.parent.name,
                'directory': str(self.single_ledger.parent), 'ledger_path': str(self.single_ledger),
                'plan_path': str(self.single_ledger.parent / '项目规划书.md'), 'source': 'existing'}

    def planning_state(self, project):
        url = '/planning' + ('?project=' + project['id'] if self.workspace else '')
        try:
            inspected = inspect_plan(read_document(Path(project['plan_path']), optional=True)['content'])
        except (OSError, UnicodeError):
            return {'ready': False, 'reason': '规划书无法读取，请重新生成并保存。', 'missing': [], 'planning_url': url}
        missing = inspected['missing']
        if missing:
            reason = '请先生成并保存项目规划书，补齐' + '、'.join(missing) + '。'
        elif project.get('planning_status') == 'pending':
            reason = '请参考已有资料，与智能体生成并保存本项目规划书后继续。'
        else:
            reason = '项目规划书已保存，可以继续管理功能。'
        return {'ready': inspected['valid'] and project.get('planning_status') != 'pending',
                'reason': reason, 'missing': missing, 'planning_url': url}

    def describe(self, project):
        return {**project, 'planning': self.planning_state(project)}

    def require_planning(self, project):
        state = self.planning_state(project)
        if not state['ready']:
            raise RequestError(state['reason'], 409, code='planning_required', planning_url=state['planning_url'], planning=state)
        return state

    def save_plan(self, project, content, revision, source="规划保存", note="", references=None):
        inspected = inspect_plan(content)
        if not inspected['valid']:
            raise RequestError('规划书缺少实质内容：' + '、'.join(inspected['missing']) + '。请继续规划后重新生成。')
        state = self.planning_state(project)
        if not state['ready'] and self.generated_plans.get(project['ledger_path']) != (digest(content.encode()), revision):
            raise RequestError('请先使用智能体生成项目规划书；重启服务后尚未保存的草稿需要重新生成。', 409,
                               code='plan_generation_required', planning_url=state['planning_url'], planning=state)
        path = Path(project['plan_path'])
        history=planning_module('planning_history')
        versions=history.list_versions(project)
        before=read_document(path,optional=True,recover=True)
        staged=[];committed=[];response=None
        existed=path.exists()
        # Serialize registry changes and their rollback with other in-process saves.
        with self.registry_lock if self.workspace else nullcontext():
            try:
                if inspect_plan(before['content'])['valid'] and (not versions or versions[0]['revision']!=before['revision']):
                    staged.append(history.stage(project,before['content'],'保存前文件版本','已有文件归档；参考选择为归档时状态。',references or []))
                staged.append(history.stage(project,content,source,note,references or []))
                if self.workspace:
                    latest=self.project(project['id'])
                    if not state['ready'] and latest.get('planning_status')!='pending':
                        self.set_planning_status(latest,'pending')
                response=atomic_write(path,content,revision)
                for version in staged:committed.append(history.commit(version))
                # Unlock only after both the document and its archive exist.
                if self.workspace:self.set_planning_status(latest,'ready')
                response['history_version']=committed[-1]
            except Exception as error:
                recovery=[]
                if response is not None:
                    try:
                        now=read_document(path,optional=True,recover=True)
                        if now['revision']!=response['revision']:raise ValueError('文件又被外部修改，已保留外部内容')
                        if existed:atomic_write(path,before['content'],response['revision'],backup=False)
                        else:path.unlink(missing_ok=True)
                    except Exception as failure:recovery.append(str(failure))
                    if self.workspace and not state['ready']:
                        try:
                            latest=self.project(project['id'])
                            if latest.get('planning_status')!='pending':self.set_planning_status(latest,'pending')
                        except Exception as failure:recovery.append(str(failure))
                for version in staged:
                    try:
                        history.discard(version)
                        if version['target'].exists():
                            if recovery:version['target'].rename(version['target'].with_name('.recovery-'+version['target'].name))
                            else:version['target'].unlink()
                    except Exception as failure:recovery.append(str(failure))
                if recovery:raise RequestError('保存未完成，请核对项目文件与隐藏的恢复记录：'+'；'.join(recovery)) from error
                raise
        self.generated_plans.pop(project['ledger_path'], None)
        response.update({'planning': self.planning_state(self.project(project['id'])), 'source': project['source']})
        return response

    def set_planning_status(self, project, status):
        before = self.registry.read_bytes()
        pattern = re.compile(r'(^## ' + re.escape(project['id']) + r'\s*\n)(.*?)(?=^## |\Z)', re.M | re.S)
        def update(match):
            body = re.sub(r'^规划状态[：:].*\n?', '', match[2], flags=re.M).rstrip()
            return match[1] + body + '\n规划状态：' + ('已生成' if status == 'ready' else '待生成') + '\n\n'
        content, count = pattern.subn(update, before.decode('utf-8'))
        if count != 1:
            raise RequestError('项目登记已变化，请刷新后重试。', 409)
        atomic_write(self.registry, content, digest(before), backup=False)

    @staticmethod
    def resolve_path(value, directory):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = directory / path
        path = path.resolve()
        if not path.is_relative_to(directory) or path.suffix.lower() not in ('.md', '.markdown'):
            raise RequestError('项目文件必须是项目目录内的 Markdown 文件。')
        return path

    def projects(self):
        if not self.workspace:
            return [self.single()]
        text = self.registry.read_text(encoding='utf-8')
        entries, current = [], None
        labels = {'名称': 'name', '目录': 'directory', '台账': 'ledger_path', '规划书': 'plan_path', '项目来源': 'source', '规划状态': 'planning_status'}
        for line in text.splitlines():
            if line.startswith('## '):
                identity = line[3:].strip()
                if not VALID_ID.fullmatch(identity):
                    raise RequestError('项目列表中的项目编号无效。')
                current = {'id': identity}
                entries.append(current)
            elif current:
                pair = re.match(r'^(名称|目录|台账|规划书|项目来源|规划状态)[：:]\s*(.*?)\s*$', line)
                if pair:
                    key = labels[pair[1]]
                    if key in current:
                        raise RequestError('项目列表中同一字段重复：' + pair[1])
                    current[key] = pair[2]
        ids, directories, documents = set(), set(), {str(self.registry.resolve())}
        for entry in entries:
            sources = {'本机新建': 'new', '导入项目': 'import'}
            statuses = {'待生成': 'pending', '已生成': 'ready'}
            if ('source' in entry and entry['source'] not in sources) or ('planning_status' in entry and entry['planning_status'] not in statuses):
                raise RequestError('项目来源或规划状态无效，请检查项目列表。')
            entry['source'] = sources.get(entry.get('source'), 'existing')
            if 'planning_status' in entry:
                entry['planning_status'] = statuses[entry['planning_status']]
            if not all(entry.get(k) for k in ('name', 'directory', 'ledger_path', 'plan_path')):
                raise RequestError('项目列表缺少名称、目录、台账或规划书字段。')
            directory = Path(entry['directory']).expanduser()
            if not directory.is_absolute():
                directory = self.workspace / directory
            directory = directory.resolve()
            entry['directory'] = str(directory)
            entry['ledger_path'] = str(self.resolve_path(entry['ledger_path'], directory))
            entry['plan_path'] = str(self.resolve_path(entry['plan_path'], directory))
            if entry['ledger_path'] == entry['plan_path']:
                raise RequestError('规划书与功能台账不能使用同一个文件。')
            if entry['id'] in ids or entry['directory'] in directories or documents.intersection((entry['ledger_path'], entry['plan_path'])):
                raise RequestError('项目编号、目录或文档重复，或项目文档指向项目列表。')
            ids.add(entry['id']); directories.add(entry['directory']); documents.update((entry['ledger_path'], entry['plan_path']))
        return entries

    def project(self, identity):
        if not self.workspace and identity in (None, '', 'single'):
            return self.single()
        if not identity:
            raise RequestError('请先选择项目。')
        if not VALID_ID.fullmatch(identity):
            raise RequestError('无效的项目编号。', 404)
        for project in self.projects():
            if project['id'] == identity:
                return project
        raise RequestError('项目不存在或已从项目列表移除。', 404)

    def register(self, payload):
        if not self.workspace:
            raise RequestError('请使用 --workspace 指定管理目录后启动多项目模式。')
        name, folder = payload.get('name'), payload.get('directory')
        if not isinstance(name, str) or not name.strip() or len(name) > 150 or any(c in name for c in '\r\n\0'):
            raise RequestError('请输入有效的项目名称。')
        if payload.get('mode') == 'new' and (folder is None or isinstance(folder, str) and not folder.strip()):
            label=re.sub(r'[^\w\-\u3400-\u9fff]+','-',name.strip()).strip('-')[:60] or '新项目'
            folder=str(self.workspace / '项目' / (label+'-'+secrets.token_hex(4)))
        if not isinstance(folder, str) or not folder.strip() or any(c in folder for c in '\r\n\0'):
            raise RequestError('请输入项目目录。')
        directory = Path(folder).expanduser()
        if not directory.is_absolute():
            directory = self.workspace / directory
        directory = directory.resolve()
        mode = payload.get('mode')
        if mode is not None and mode not in ('new', 'import'):
            raise RequestError('项目来源必须为 new 或 import。')
        if mode == 'import' and not directory.is_dir():
            raise RequestError('导入项目目录不存在，请选择已有目录。')
        if mode is None:
            mode = 'import' if directory.is_dir() and any(directory.iterdir()) else 'new'
        requested_ledger = payload.get('ledger_path') or '功能执行情况.md'
        if not isinstance(requested_ledger, str) or any(c in requested_ledger for c in '\r\n\0'):
            raise RequestError('台账路径无效。')
        ledger = self.resolve_path(requested_ledger, directory)
        plan = self.resolve_path('项目规划书.md', directory)
        if ledger == plan:
            raise RequestError('规划书与功能台账不能使用同一个文件。')
        with self.registry_lock:
            before = self.registry.read_bytes()
            entries = self.projects()
            registered_docs = {str(self.registry.resolve())}
            for entry in entries:
                registered_docs.update((entry['ledger_path'], entry['plan_path']))
            if any(entry['directory'] == str(directory) for entry in entries) or registered_docs.intersection((str(ledger), str(plan))):
                raise RequestError('项目目录或文档已经登记，或文档指向项目列表。', 409)
            if directory.exists() and not directory.is_dir():
                raise RequestError('项目目录不是文件夹。')
            if directory.exists() and not ledger.exists() and requested_ledger != '功能执行情况.md':
                raise RequestError('指定的现有台账不存在，请检查路径。')
            directory.mkdir(parents=True, exist_ok=True)
            if not ledger.parent.is_dir():
                raise RequestError('台账所在目录不存在。')
            for path, content in ((ledger, '# 功能执行情况\n\n目标：待规划\n'),
                                  (plan, '# 项目规划书\n\n尚未生成规划书，请在规划页面梳理需求。\n')):
                if not path.exists():
                    try:
                        with path.open('x', encoding='utf-8') as file:
                            file.write(content)
                    except FileExistsError:
                        pass
                if not path.is_file():
                    raise RequestError('项目文档路径不是文件。')
            project = {'id': 'p-' + secrets.token_hex(6), 'name': name.strip(), 'directory': str(directory), 'ledger_path': str(ledger), 'plan_path': str(plan), 'source': mode, 'planning_status': 'pending'}
            block = '\n\n## {id}\n名称：{name}\n目录：{directory}\n台账：{ledger_path}\n规划书：{plan_path}\n'.format(**project)
            block += '项目来源：' + ('本机新建' if mode == 'new' else '导入项目') + '\n规划状态：待生成\n'
            atomic_write(self.registry, before.decode('utf-8').rstrip() + block, digest(before), backup=False)
            self.generated_plans.pop(str(ledger), None)
            return self.describe(project)

    def overview(self):
        output = []
        for project in self.projects():
            entry = self.describe(project)
            try:
                ledger, plan = Path(project['ledger_path']), Path(project['plan_path'])
                entry['summary'] = summarize(parse_document(ledger.read_text(encoding='utf-8'))) if entry['planning']['ready'] else None
                timestamps = [path.stat().st_mtime for path in (ledger, plan) if path.exists()]
                entry['updated_at'] = datetime.fromtimestamp(max(timestamps), timezone.utc).isoformat() if timestamps else None
            except (OSError, UnicodeError, RequestError) as exc:
                entry['error'] = str(exc)
                entry['summary'] = None
                entry['updated_at'] = None
            output.append(entry)
        return {'projects': output, 'workspace': str(self.workspace) if self.workspace else None}


def validate_ledger(content, existing=""):
    groups = parse(content)
    items = [item for group in groups for item in flatten(group['items'])]
    if not items:
        raise RequestError('未找到可识别的功能台账；请先生成含大功能和功能点的台账。')
    old_items = [item for group in parse(existing) for item in flatten(group['items'])]
    accepted = {item['id']: item for item in old_items if item['checked'] and item['fields'].get('状态') == '已完成'}
    by_id = {item['id']: item for item in items}
    if len(by_id) != len(items):
        raise RequestError('台账包含重复功能编号。')
    protected = {item['id']: item for item in old_items if item['id'] in accepted or '规划同步历史' in item['fields']}
    for identity, old in protected.items():
        new = by_id.get(identity)
        if new != old and (new is None or not planning_module('planning_operations').valid_ledger_transition(old, new)):
            raise RequestError('已验收功能必须保留实施及审核历史：' + identity + '。请按当前规划重新转换，需求变化后重新审核。')
    for item in items:
        old = accepted.get(item['id'])
        if (item['checked'] or item['fields'].get('状态') == '已完成') and old != item and (old is None or not planning_module('planning_operations').valid_ledger_transition(old, item)):
            raise RequestError('规划草稿不能新增或改写完成标记：' + item['id'] + '。新功能需要独立审核。')
    required = ('状态', '验收', '优先级', '依赖', '执行 Agent', '实现证据', '审核 Agent', '评分', '问题')
    incomplete = [item['id'] for item in items if any(not item['fields'].get(key, '').strip() for key in required)]
    if incomplete:
        raise RequestError('以下功能点缺少状态、验收、优先级、依赖、执行、证据、审核、评分或问题：' + '、'.join(incomplete[:8]))
    return items


def main():
    cli = argparse.ArgumentParser(description='Local Markdown project manager and feature dashboard')
    cli.add_argument('ledger', type=Path, nargs='?')
    cli.add_argument('--workspace', type=Path, help='Directory containing 项目列表.md')
    cli.add_argument('--port', type=int, default=8765)
    cli.add_argument('--agent', choices=('codex', 'claude'), default='codex', help='Host label for this read-only viewer')
    cli.add_argument('--instance-id', default='', help=argparse.SUPPRESS)
    args = cli.parse_args()
    if bool(args.ledger) == bool(args.workspace):
        cli.error('请提供单个台账路径，或使用 --workspace 指定管理目录。')
    if args.ledger and not args.ledger.is_file():
        cli.error(f'台账不存在: {args.ledger}')
    if args.workspace and args.instance_id:
        lease = planning_module('plugin_manager').service_lease(args.workspace)
        lease.__enter__()
        atexit.register(lease.__exit__, None, None, None)
    store = ProjectStore(args.workspace, args.ledger)
    agent_label = {'codex': 'Codex', 'claude': 'Claude Code'}[args.agent]

    class Handler(BaseHTTPRequestHandler):
        # Bound idle loopback clients so graceful shutdown cannot wait forever.
        # Bound idle socket I/O so viewer shutdown cannot wait forever.
        timeout = 2


        def local_request(self):
            host = self.headers.get('Host', '')
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            origin = self.headers.get('Origin')
            return host in expected and (not origin or origin in {f'http://{h}' for h in expected})

        def project(self):
            query = parse_qs(urlparse(self.path).query)
            ids = query.get('project', [])
            if len(ids) > 1:
                raise RequestError('只能选择一个项目。')
            return store.project(ids[0] if ids else None)


        def respond(self, data, status=200, kind='application/json; charset=utf-8', headers=None):
            activity = getattr(self, 'activity_context', None)
            self.activity_context = None
            if activity and isinstance(data, dict):
                project, route, payload = activity
                try:
                    module=planning_module('planning_activity')
                    record=module.event(route,payload,data,status,getattr(self,'activity_before',''))
                    if record:
                        with store.lock_for('activity',project['plan_path']):module.append(project,record)
                except (ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:
                    data['activity_warning']='操作结果已返回，但记录未保存：'+str(exc)
            operation = getattr(self, 'operation_key', None)
            if operation:
                if status >= 400: store.operation_progress.finish(operation, data.get('error', '请求失败') if isinstance(data, dict) else '请求失败')
                else: operation_step(95, '返回结果', '服务端处理完成，正在返回页面')
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
            if operation and status < 400: store.operation_progress.finish(operation)

        def error(self, exc):
            message = '智能体回复超时，请重试。' if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
            self.respond({'error': message, **getattr(exc, 'details', {})}, getattr(exc, 'code', 400))

        def html(self, filename, project=None):
            page = (BASE / filename).read_text(encoding='utf-8')
            identity = project['id'] if project and store.workspace else ''
            page = page.replace('__PROJECT_ID__', identity).replace('__PLANNING_AGENT__', agent_label)
            if project:
                page = page.replace('__PLANNING_KEY__', digest(project['ledger_path'].encode()))
            self.respond(page.encode(), kind='text/html; charset=utf-8')

        def do_POST(self):
            # Old cached clients must not retain a second write/analysis workflow.
            if not self.local_request():
                self.respond({'error': '请求来源无效。'}, 403)
                return
            self.respond({'error': '网页现在只用于查看。请在 Codex 或 Claude Code 对话中操作项目。',
                          'code': 'host_conversation_required'}, 410)
            return


        def planning_model(self, content):
            operation_step(65, '整理层级表格', '解析功能编号、父子关系与说明')
            model=planning_module('planning_sheet').parse_plan_sheet(content)
            try: table=planning_module('planning_editor').editable_table(content)
            except ValueError: return model
            choices={r['编号']:r.get('采用','是')!='否' for r in table['rows']}
            technical={r['编号']:[r.get('所需技术'),r.get('前期准备')] for r in table['rows']}
            for sheet in model['sheets']:
                if '所需技术' not in sheet['columns'] and ('功能名称' in sheet['columns'] or sheet.get('kind')=='feature-list'):
                    sheet['columns']+=['所需技术','前期准备']
                    for row in sheet['rows']: row['cells']+=[value or '' for value in technical.get(row.get('feature_id',row['cells'][0]),['',''])]
                if '所需技术' in sheet['columns']:
                    for row in sheet['rows']:
                        values=technical.get(row.get('feature_id',row['cells'][0]))
                        if values is not None:
                            for field,value in zip(('所需技术','前期准备'),values):
                                if value is not None: row['cells'][sheet['columns'].index(field)]=value
                if sheet.get('kind')!='feature-list': continue
                has_adoption='采用' in sheet['columns']
                if not has_adoption: sheet['columns'].insert(0,'采用')
                adoption_column=sheet['columns'].index('采用')
                for row in sheet['rows']:
                    value='是' if choices.get(row.get('feature_id'),True) else '否'
                    if has_adoption: row['cells'][adoption_column]=value
                    else: row['cells'].insert(adoption_column,value)
                if not has_adoption:
                    for merge in sheet['merges']: merge['column']+=1
            return model

        def research_path(self, project):
            path=(Path(project['directory'])/'GitHub参考项目.md').resolve()
            if not path.is_relative_to(Path(project['directory'])) or str(path) in (project['plan_path'],project['ledger_path'],str(store.registry) if store.workspace else ''):
                raise RequestError('调研文件路径与项目资料冲突。')
            return path

        def research_data(self, project):
            path=self.research_path(project)
            if not path.exists(): return {'completed':False,'repositories':[]}
            if path.stat().st_size>256000: raise RequestError('调研资料过大，请重新搜索。')
            doc=read_document(path)
            data=planning_module('planning_research').read_research(doc['content'])
            data['revision']=doc['revision']
            return data


        def suggestion_path(self, project):
            path=Path(project['directory'])/'功能建议.md'
            if path.is_symlink() or str(path) in (project['plan_path'],project['ledger_path']):
                raise RequestError('功能建议文件路径冲突。')
            return path



        def plan_history(self, project):
            module=planning_module('planning_history')
            query=parse_qs(urlparse(self.path).query)
            identity=query.get('version',[])
            if len(identity)>1:raise RequestError('只能读取一个历史版本。')
            if not identity:return {'versions':module.list_versions(project)}
            try:version=module.read_version(project,identity[0])
            except FileNotFoundError:raise RequestError('历史版本不存在。',404)
            version['model']=self.planning_model(version['content'])
            warnings=[]
            versions=module.list_versions(project,warnings=warnings)
            version['warnings']=warnings
            if warnings:
                version['diff']='部分保存记录无法读取，无法可靠确定上次保存的功能表；这份功能表仍可查看和下载。'
                return version
            index=next(i for i,item in enumerate(versions) if item['id']==version['id'])
            previous=versions[index+1] if index+1<len(versions) else None
            if previous:
                try:prior=module.read_version(project,previous['id'])
                except (OSError,ValueError):
                    warnings.append('上次保存的功能表无法读取，暂时不能比较改动。')
                    version['diff']='无法与上次保存比较；这份功能表仍可查看和下载。'
                    return version
                version['previous']=previous['id']
                version['diff']=''.join(difflib.unified_diff(prior['content'].splitlines(keepends=True),version['content'].splitlines(keepends=True),fromfile='上次保存的功能表',tofile='这次保存的功能表'))
            else:version['diff']='这是最早归档版本，没有上一版可比较。'
            return version









        def do_GET(self):
            self.operation_key = None
            self.activity_context = None
            self.activity_before = ''
            if not self.local_request():
                self.respond({'error': '请求来源无效。'}, 403)
                return
            route = urlparse(self.path).path
            try:
                assets = {
                    '/assets/planning-markdown.js': ('planning-markdown.js', 'text/javascript; charset=utf-8'),
                    '/assets/planning-markdown.css': ('planning-markdown.css', 'text/css; charset=utf-8'),
                    '/assets/planning-sheet-view.js': ('planning-sheet-view.js', 'text/javascript; charset=utf-8'),
                    '/assets/planning-sheet.css': ('planning-sheet.css', 'text/css; charset=utf-8'),
                    '/assets/planning-activity.js': ('planning-activity.js', 'text/javascript; charset=utf-8'),
                    '/assets/planning-history-view.js': ('planning-history-view.js', 'text/javascript; charset=utf-8'),
                }
                if route in assets:
                    filename, kind = assets[route]
                    self.respond((BASE / filename).read_bytes(), kind=kind)
                    return
                if route == '/api/runtime':
                    self.respond({'instance_id': args.instance_id, 'agent': args.agent,
                                  'workspace': str(store.workspace) if store.workspace else None,
                                  'pid': os.getpid()})
                    return
                if route == '/api/projects':
                    self.respond(store.overview())
                    return
                if route == '/projects' or (route == '/' and store.workspace and not urlparse(self.path).query):
                    self.html('projects.html')
                    return
                if route not in ('/', '/planning', '/api/project', '/api/plan', '/api/plan/table', '/api/plan/export', '/api/ledger/info', '/api/ledger', '/api/research', '/api/plan/history', '/api/research/source-progress', '/api/plan/suggestions', '/api/operation-progress', '/api/plan/activity'):
                    raise RequestError('页面不存在。', 404)
                project = self.project()
                if route == '/':
                    state = store.planning_state(project)
                    if not state['ready']:
                        self.send_response(303)
                        self.send_header('Location', state['planning_url'])
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                    else:
                        self.html('dashboard.html', project)
                elif route == '/planning':
                    self.html('planning.html', project)
                elif route in ('/api/plan/table', '/api/plan/export'):
                    versions = parse_qs(urlparse(self.path).query).get('version', [])
                    if len(versions) > 1:
                        raise RequestError('只能读取一个历史版本。')
                    if versions:
                        document = planning_module('planning_history').read_version(project, versions[0])
                    else:
                        document = read_document(Path(project['plan_path']), optional=True, recover=True)
                    model = self.planning_model(document['content'])
                    if route.endswith('/table'):
                        self.respond({**model, 'revision': document['revision']})
                    else:
                        if not document['content'].strip():
                            raise RequestError('尚无已保存的规划书，请先在宿主对话中保存。')
                        filename = quote(project['name'] + '-项目规划书.xlsx', safe='')
                        self.respond(planning_module('planning_xlsx').export_plan_xlsx(model, document['content']),
                                     kind='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                     headers={'Content-Disposition': 'attachment; filename="project-plan.xlsx"; filename*=UTF-8\'\'' + filename})
                elif route == '/api/operation-progress':
                    identities=parse_qs(urlparse(self.path).query).get('operation',[])
                    if len(identities)!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',identities[0]):raise RequestError('进度任务编号无效。')
                    self.respond(store.operation_progress.read(project['id'],identities[0]))
                elif route == '/api/plan/activity':
                    planning_module('planning_history')
                    with store.lock_for('workflow',project['plan_path']), store.lock_for('activity',project['plan_path']):
                        warnings=[]
                        records=planning_module('planning_activity').listing(project,warnings=warnings)
                        self.respond({'records':records,'warnings':warnings})
                elif route == '/api/plan/suggestions':
                    path=self.suggestion_path(project)
                    data=planning_module('planning_suggestions').read(read_document(path)['content']) if path.exists() else {'suggestions':[]}
                    data['stale']=data.get('plan_revision')!=read_document(Path(project['plan_path']),optional=True)['revision']
                    self.respond(data)
                elif route == '/api/research/source-progress':
                    self.respond(store.source_progress.get(project['id'],{'running':False,'stage':'尚未核对','message':'初稿使用 README，最终确认前检查源码'}))
                elif route == '/api/research':
                    self.respond(self.research_data(project))
                elif route == '/api/plan/history':
                    with store.lock_for('workflow', project['plan_path']):
                        result = self.plan_history(project)
                    self.respond(result)
                elif route == '/api/project':
                    self.respond(store.describe(project))
                elif route == '/api/plan':
                    self.respond({**read_document(Path(project['plan_path']), optional=True, recover=True), 'planning': store.planning_state(project), 'source': project['source']})
                elif route == '/api/ledger/info':
                    doc = read_document(Path(project['ledger_path']), optional=True, recover=True)
                    self.respond({'path': doc['path'], 'revision': doc['revision']})
                else:
                    store.require_planning(project)
                    self.respond({'groups': parse_document(Path(project['ledger_path']).read_text(encoding='utf-8'))})
            except (RequestError, OSError, UnicodeError, ValueError) as exc:
                self.error(exc)

    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE or args.port == 0:
            raise
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        print(f'端口 {args.port} 已被占用，已切换到空闲端口 {server.server_port}。', flush=True)
    # ThreadingHTTPServer normally abandons daemon request threads at exit.
    # Wait for in-flight read responses to finish within the socket timeout.
    server.daemon_threads = False
    shutdown_requested = threading.Event()

    def stop_server(_signal, _frame):
        if shutdown_requested.is_set():
            return
        shutdown_requested.set()

        def shutdown():
            # shutdown() must run outside the serve_forever thread.
            server.shutdown()

        threading.Thread(target=shutdown, name='dashboard-shutdown', daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    print(f'功能看板：http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
