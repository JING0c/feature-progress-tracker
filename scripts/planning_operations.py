"""Deterministic document operations. This module never calls an agent."""
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


def ledger_from_plan(content, existing, parse):
    rows = editable_table(content)['rows']
    replace_features(content, rows)
    adopted = [r for r in rows if r.get('采用') != '否']
    if not adopted:
        raise ValueError('请先勾选要采用的功能，再生成台账。')
    groups = parse(existing)
    old = {i['id']: i for g in groups for i in walk(g['items'])}
    if len(old) != sum(1 for g in groups for i in walk(g['items'])):
        raise ValueError('已有台账编号重复，请先整理原记录。')
    children = {r['上级编号'] for r in adopted}
    roots = [r for r in adopted if '-' not in r['编号']]
    output = existing.rstrip() + '\n' if existing.strip() else '# 功能执行情况\n进度：已验收 0/0（0%）\n'
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
            values = {'验收': row.get('验收标准', ''), '说明': row.get('说明', ''),
                      '优先级': row.get('优先级') or '待确认', '依赖': row.get('依赖') or '无',
                      '所需技术': row.get('所需技术') or '待确认', '前期准备': row.get('前期准备') or '待确认',
                      '执行 Agent': '待分配', '实现证据': '无', '审核 Agent': '待审核', '评分': '待审核', '问题': '无'}
            if not values['验收'].strip():
                raise ValueError('功能缺少验收标准：' + identity)
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
    return {'content': output, 'added': added, 'preserved': preserved,
            'note': '按已采用功能转换；已有条目原文与实施审核历史保留，不自动改写。' if preserved else '按已采用功能转换；新条目均为未开始、待审核。'}


def walk(items):
    for item in items:
        yield item
        yield from walk(item.get('children', []))
