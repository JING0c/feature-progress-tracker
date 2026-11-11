"""Deterministic document operations. This module never calls an agent."""
import copy
import json
import re
from planning_editor import editable_table, replace_features

FIELDS = ('功能名称', '说明', '验收标准', '优先级', '依赖', '所需技术', '前期准备', '备注')


def proposal_rows(text):
    matches = re.findall(r'^```json\s*\n(.*?)\n```\s*$', text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError('拆分提案缺少结构化功能数据，请重新拆分或在功能表中手动添加；不会自动猜测合并。')
    try:
        rows = json.loads(matches[0]).get('features')
    except (ValueError, AttributeError) as exc:
        raise ValueError('拆分提案的数据格式无效，请重新整理。') from exc
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('拆分提案必须包含1至100个功能。')
    keys = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - set(FIELDS) - {'key', 'parent'}:
            raise ValueError('提案包含不支持的字段。')
        if any(not isinstance(v, str) or len(v) > 10000 for v in row.values()):
            raise ValueError('提案字段无效或过长。')
        key = row.get('key', '')
        if not re.fullmatch(r'N\d+', key) or key in keys:
            raise ValueError('提案临时编号必须是唯一的N数字。')
        keys.add(key)
        if any(not row.get(k, '').strip() for k in ('parent', '功能名称', '说明', '验收标准')):
            raise ValueError('提案缺少上级、名称、说明或验收。')
    return rows


def merge_proposal(content, proposal, reserved=()):
    existing = editable_table(content)['rows']
    replace_features(content, existing)  # Validate the base graph first.
    pending = list(proposal_rows(proposal))
    rows = [dict(r) for r in existing]
    by_id = {r['编号']: r for r in rows}
    used = set(by_id) | set(reserved)
    mapping, added = {}, []
    while pending:
        advanced = False
        for item in pending[:]:
            parent = item['parent'].strip()
            if parent.startswith('N'):
                if parent not in mapping:
                    continue
                parent = mapping[parent]
            parent = '' if parent in ('无', '-', '—', '') else parent
            if parent and parent not in by_id:
                raise ValueError('提案的上级功能不存在：' + parent)
            duplicate = next((r for r in rows if (r.get('上级编号') if '-' in r['编号'] else '') == parent
                              and r['功能名称'].strip() == item['功能名称'].strip()), None)
            if duplicate:
                mapping[item['key']] = duplicate['编号']
            else:
                prefix = parent + '-' if parent else 'F'
                siblings = [int(i[len(prefix):]) for i in used if i.startswith(prefix) and i[len(prefix):].isdigit()]
                identity = prefix + str(max(siblings, default=0) + 1).zfill(2)
                row = {k: item.get(k, '') for k in FIELDS}
                row.update({'编号': identity, '上级编号': parent or '无',
                            '采用': by_id[parent].get('采用', '是') if parent else '是'})
                rows.append(row); by_id[identity] = row; used.add(identity)
                mapping[item['key']] = identity; added.append(identity)
            pending.remove(item); advanced = True
        if not advanced:
            raise ValueError('提案上级存在循环或缺少对应功能。')
    for row in rows[len(existing):]:
        row['依赖'] = re.sub(r'\bN\d+\b', lambda m: mapping.get(m[0], m[0]), row.get('依赖', ''))
        if re.search(r'\bN\d+\b', row['依赖']):
            raise ValueError('提案依赖引用了不存在的临时编号。')
    if not added:
        raise ValueError('提案中的同父同名功能已在清单中，无需重复添加。')
    return {'content': replace_features(content, rows), 'added': added, 'mapping': mapping}


def safe_field(value):
    # Ledger syntax uses these separators for metadata. Prevent user text from
    # injecting status/acceptance fields or new Markdown nodes.
    return re.sub(r'\s+', ' ', value or '').replace('|', '／').replace('｜', '／').replace(';', '，').replace('；', '，').strip()


PLAN_FIELDS = {'验收', '说明', '优先级', '依赖', '所需技术', '前期准备', '备注'}
REQUIREMENT_FIELDS = {'验收', '说明', '依赖', '所需技术', '前期准备'}
HISTORY_FIELD = '规划同步历史'
HISTORY_FIELDS = {HISTORY_FIELD, '进度更新历史'}
TRACKING_FIELD = '规划跟踪'
INACTIVE_TRACKING = {'未采用', '已从规划移除'}
REVIEW_RESET = {'审核 Agent': '待审核', '评分': '待审核',
                '评分理由': '需求已变化，待重新审核', '审核结论': '需求已变化，待重新审核'}


def plan_fields(row):
    values = {'验收': row.get('验收标准', ''), '说明': row.get('说明', ''),
              '优先级': row.get('优先级') or '待确认', '依赖': row.get('依赖') or '无',
              '所需技术': row.get('所需技术') or '待确认', '前期准备': row.get('前期准备') or '待确认',
              '备注': row.get('备注', '')}
    if not values['验收'].strip():
        raise ValueError('功能缺少验收标准：' + row['编号'])
    return {key: safe_field(value) for key, value in values.items()}


def history_records(item):
    try:
        records = json.loads(item['fields'].get(HISTORY_FIELD, '[]'))
    except (TypeError, ValueError) as exc:
        raise ValueError('已有规划同步历史格式无效，请先核对：' + item['id']) from exc
    if not isinstance(records, list):
        raise ValueError('已有规划同步历史格式无效，请先核对：' + item['id'])
    return records


def history_snapshot(item):
    # Both archives remain on the live record, including legacy nested entries.
    # A new snapshot retains the business state and subtree, never another
    # archive; otherwise alternating planning/progress edits grow exponentially.
    snapshot = {key: copy.deepcopy(value) for key, value in item.items()
                if key not in ('fields', 'children')}
    snapshot['fields'] = {key: copy.deepcopy(value) for key, value in item['fields'].items()
                          if key not in HISTORY_FIELDS}
    snapshot['children'] = [history_snapshot(child) for child in item.get('children', [])]
    return snapshot


def history_text(records):
    text = json.dumps(records, ensure_ascii=False, separators=(',', ':'))
    # These separators have meaning to the Markdown ledger field parser. JSON
    # unicode escapes keep the exact old values recoverable without new fields.
    for char in (';', '；', '|', '｜'):
        text = text.replace(char, '\\u%04x' % ord(char))
    return text


def requirements_changed(old, new):
    return ((old['fields'].get(TRACKING_FIELD) in INACTIVE_TRACKING) !=
            (new['fields'].get(TRACKING_FIELD) in INACTIVE_TRACKING)
            or any(safe_field(old['fields'].get(key)) != safe_field(new['fields'].get(key))
                for key in REQUIREMENT_FIELDS)
            or any(requirements_changed(before, after)
                   for before, after in zip(old.get('children', []), new.get('children', []))))


def reopened_fields(fields):
    result = dict(fields)
    if result.get('状态') in ('已完成', '待审核'):
        result['状态'] = '进行中'
    for key, value in REVIEW_RESET.items():
        if key in result or key in ('审核 Agent', '评分'):
            result[key] = value
    return result


def sync_tracking_status(old, current):
    """Archive scope withdrawals; re-adoption cannot resurrect old acceptance."""
    fields = current['fields']
    if fields.get(TRACKING_FIELD) in INACTIVE_TRACKING:
        current['checked'] = False
        fields['状态'] = '已取消'
        return
    if old['fields'].get(TRACKING_FIELD) in INACTIVE_TRACKING:
        # Find the latest state before this scope withdrawal, including a manual
        # cancellation. Repeated unadopt/remove edits must not lose that state.
        previous = next((record for record in reversed(history_records(old))
                         if isinstance(record, dict) and isinstance(record.get('fields'), dict)
                         and record['fields'].get(TRACKING_FIELD) not in INACTIVE_TRACKING), None)
        if previous is None:
            raise ValueError('取消跟踪前的历史记录缺失，请先核对：' + old['id'])
        fields['状态'] = previous['fields'].get('状态', '未开始')
        current['checked'] = False
        if fields['状态'] in ('已完成', '待审核') or previous.get('checked'):
            current['fields'] = reopened_fields(fields)
            current['fields']['评分理由'] = '功能重新采用，待重新审核'
            current['fields']['审核结论'] = '功能重新采用，待重新审核'
        return
    if requirements_changed(old, current):
        current['checked'] = False
        current['fields'] = reopened_fields(fields)


def valid_ledger_transition(old, new):
    """Allow requirements/scope sync with exact old history, never new approval.

    Used by the server's final ledger validation, not as a client assertion.
    Names, topology, notes and implementation evidence cannot be changed here.
    """
    if any(old.get(key) != new.get(key) for key in ('id', 'name', 'notes')):
        return False
    before_children, after_children = old.get('children', []), new.get('children', [])
    if len(before_children) != len(after_children):
        return False
    if any(before != after and not valid_ledger_transition(before, after)
           for before, after in zip(before_children, after_children)):
        return False
    old_fields = {k: v for k, v in old['fields'].items() if k != HISTORY_FIELD}
    new_fields = {k: v for k, v in new['fields'].items() if k != HISTORY_FIELD}
    expected = dict(old_fields)
    for key in PLAN_FIELDS:
        if key in new_fields:
            expected[key] = new_fields[key]
        elif key in old_fields:
            return False
    if new_fields.get(TRACKING_FIELD) != old_fields.get(TRACKING_FIELD):
        tracking = new_fields.get(TRACKING_FIELD)
        if tracking not in INACTIVE_TRACKING and not (
                tracking == '已采用' and old_fields.get(TRACKING_FIELD) in INACTIVE_TRACKING):
            return False
        expected[TRACKING_FIELD] = tracking
    try:
        transition = {'fields': expected, 'checked': old['checked'], 'children': after_children}
        sync_tracking_status(old, transition)
        if transition['fields'] != new_fields or transition['checked'] != new['checked']:
            return False
        old_history, new_history = history_records(old), history_records(new)
    except ValueError:
        return False
    own_change = old_fields != new_fields or old['checked'] != new['checked']
    return new_history == old_history + ([history_snapshot(old)] if own_change else [])


def sync_existing_items(groups, rows):
    by_id = {row['编号']: row for row in rows}
    changed = {}
    def sync(old):
        current = copy.deepcopy(old)
        current['children'] = [sync(child) for child in old.get('children', [])]
        row = by_id.get(old['id'])
        if row and row.get('采用') != '否':
            if old['name'] != safe_field(row['功能名称']):
                raise ValueError('编号 '+old['id']+' 与已有台账名称不同，请核对编号或为新功能使用新编号；已有实施记录未修改。')
            for key, value in plan_fields(row).items():
                if safe_field(old['fields'].get(key)) != value:
                    current['fields'][key] = value
            if old['fields'].get(TRACKING_FIELD) in INACTIVE_TRACKING:
                current['fields'][TRACKING_FIELD] = '已采用'
        else:
            current['fields'][TRACKING_FIELD] = '未采用' if row else '已从规划移除'
        sync_tracking_status(old, current)
        if current['fields'] != old['fields'] or current['checked'] != old['checked']:
            current['fields'][HISTORY_FIELD] = history_text(history_records(old) + [history_snapshot(old)])
            changed[old['id']] = current
        return current
    for group in groups:
        for item in group['items']:
            sync(item)
    return changed


def replace_item_records(text, changed):
    """Replace changed records only; retain surrounding prose and fenced examples."""
    result, current, group, fence = [], None, False, None
    item_pattern = re.compile(r'^(\s*)-\s*\[([ xX])\]\s+(\S+-\d+|F\d+(?!\s+总状态\s*[：:]))\s+(.+?)\s*$')
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line.rstrip())
        if fence:
            result.append(line)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]; result.append(line); continue
        if line.startswith('## '):
            group = bool(re.match(r'^##\s+大功能\s+([^：:\s]+)\s*[：:]\s*(.+?)\s*$', line)); current = None
        match = item_pattern.match(line)
        if match and group:
            current = match[3] if match[3] in changed else None
            if current:
                item = changed[current]; pad = match[1]
                result.append(pad + '- [' + ('x' if item['checked'] else ' ') + '] ' + current + ' ' + item['name'] + '｜状态：' + item['fields'].get('状态', '未开始') + '\n')
                result.extend(pad + '  - ' + key + '：' + value + '\n' for key, value in item['fields'].items() if key != '状态')
                result.extend(pad + '  - ' + note + '\n' for note in item.get('notes', []))
                continue
        if current and re.match(r'^\s{2,}-\s+', line):
            continue
        result.append(line)
    return ''.join(result)


def ledger_from_plan(content, existing, parse):
    rows = editable_table(content)['rows']
    replace_features(content, rows)
    adopted = [r for r in rows if r.get('采用') != '否']
    groups = parse(existing)
    old = {i['id']: i for g in groups for i in walk(g['items'])}
    if not adopted and not old:
        raise ValueError('请先勾选要采用的功能，再生成台账。')
    if len(old) != sum(1 for g in groups for i in walk(g['items'])):
        raise ValueError('已有台账编号重复，请先整理原记录。')
    children = {r['上级编号'] for r in adopted}
    roots = [r for r in adopted if '-' not in r['编号']]
    updated = sync_existing_items(groups, rows)
    synced = replace_item_records(existing, updated)
    output = synced.rstrip() + '\n' if synced.strip() else '# 功能执行情况\n进度：已验收 0/0（0%）\n'
    added, preserved = [], []
    for root in roots:
        root_id = root['编号']
        branch = [r for r in adopted if r['编号'].startswith(root_id + '-') or r['编号'] == root_id and root_id not in children]
        branch.sort(key=lambda r: tuple(int(n) for n in r['编号'][1:].split('-')))
        block = ''
        for row in branch:
            identity = row['编号']
            if identity in old:
                if old[identity]['name']!=safe_field(row['功能名称']):
                    raise ValueError('编号 '+identity+' 与已有台账名称不同，请核对编号或为新功能使用新编号；已有实施记录未修改。')
                preserved.append(identity)
                continue
            depth = max(identity.count('-') - 1, 0); pad = '  ' * depth
            block += '\n' + pad + '- [ ] ' + identity + ' ' + safe_field(row['功能名称']) + '｜状态：未开始\n'
            values = {key: value for key, value in plan_fields(row).items() if value}
            values.update({'执行 Agent': '待分配', '实现证据': '无', '审核 Agent': '待审核', '评分': '待审核', '问题': '无'})
            for key, value in values.items():
                block += pad + '  - ' + key + '：' + safe_field(value) + '\n'
            added.append(identity)
        if not block:
            continue
        # Locate real Markdown sections; headings inside fenced examples are data.
        positions=[];offset=0;fence=None
        for line in output.splitlines(keepends=True):
            marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line.rstrip())
            if fence:
                if marker and marker[1][0]==fence[0] and len(marker[1])>=len(fence) and not marker[2].strip():fence=None
            elif marker:fence=marker[1]
            elif line.startswith('## '):positions.append((offset,line))
            offset+=len(line)
        section=next((n for n,(_,line) in enumerate(positions) if re.match(r'^##\s+大功能\s+'+re.escape(root_id)+r'\s*[：:]',line)),None)
        if section is not None:
            at=positions[section+1][0] if section+1<len(positions) else len(output)
            output=output[:at].rstrip()+'\n'+block+'\n'+output[at:]
        else:
            output += '\n## 大功能 ' + root_id + '：' + safe_field(root['功能名称']) + '\n' + block
    return {'content': output, 'added': added, 'preserved': preserved, 'updated': list(updated),
            'note': '按当前采用范围同步规划；未采用或移除的旧功能取消跟踪，实施及审核历史保留；重新采用的已验收项需重新审核。' if updated else ('按已采用功能转换；未变化条目与实施审核历史保留。' if preserved else '按已采用功能转换；新条目均为未开始、待审核。')}


def walk(items):
    for item in items:
        yield item
        yield from walk(item.get('children', []))
