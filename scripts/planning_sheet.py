"""A loss-conscious, dependency-free worksheet view of a Markdown project plan.

This is a presentation projection, never a new source of project facts. Explicit
table columns and document headings determine hierarchy; unstructured prose is
kept alongside them rather than interpreted as implementation status.
"""
import re


FEATURE_COLUMNS = ['编号', '功能名称', '说明与验收', '优先级', '依赖', '备注']
_HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$')
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
_LIST = re.compile(r'^(\s*)(?:[-+*]|\d+[.)])[ \t]+(.+)$')
_NO_PARENT = {'', '-', '—', '无', '无上级', '根', '根级', 'null', 'none', 'n/a'}


def _text(value):
    """Remove common inline decoration, retaining links/HTML as inert text."""
    value = re.sub(r'<br\s*/?>', '\n', str(value), flags=re.I).strip()
    value = re.sub(r'\*\*(.+?)\*\*|__(.+?)__', lambda m: m[1] or m[2], value)
    value = re.sub(r'(`+)(.+?)\1', lambda m: m[2], value)
    return re.sub(r'\\([\\`*_{}\[\]()#+.!|>-])', r'\1', value)


def _table_row(line):
    cells, cell, code = [], '', ''
    text, index, delimited = line.strip(), 0, False
    while index < len(text):
        char = text[index]
        if char == '\\' and index + 1 < len(text):
            cell += text[index:index + 2]
            index += 2
            continue
        if char == '`':
            ticks = re.match(r'`+', text[index:])[0]
            if not code and text.find(ticks, index + len(ticks)) >= 0:
                code = ticks
            elif code == ticks:
                code = ''
            cell += ticks
            index += len(ticks)
            continue
        if char == '|' and not code:
            cells.append(cell.strip())
            cell, delimited = '', True
        else:
            cell += char
        index += 1
    cells.append(cell.strip())
    if text.startswith('|'):
        cells.pop(0)
    # Count backslashes: an odd number escapes the final pipe.
    escaped = re.search(r'(\\+)\|$', text)
    if text.endswith('|') and not (escaped and len(escaped[1]) % 2):
        cells.pop()
    return cells, delimited


def _table_start(lines, index):
    if index + 1 >= len(lines):
        return None
    header, delimited = _table_row(lines[index])
    separators, _ = _table_row(lines[index + 1])
    if not delimited or not header or not separators or not all(
        re.fullmatch(r':?-{3,}:?', cell) for cell in separators
    ):
        return None
    if len(header) == len(separators):
        return header

    # Some generated plans miscount divider cells while the data is aligned.
    required = {'编号', '上级编号', '功能名称', '说明', '验收标准'}
    if not required.issubset(header) or len(set(header)) != len(header):
        return None
    first_row = index + 2
    row_index = first_row
    while row_index < len(lines) and lines[row_index].strip():
        cells, has_pipes = _table_row(lines[row_index])
        if not has_pipes:
            break
        if len(cells) != len(header):
            return None
        row_index += 1
    return header if row_index > first_row else None


def _feature_title(text):
    plain = _text(text)
    match = re.match(r'^(?:大功能\s*)?(F\d+(?:[-.]\d+)*)\s*[：:.、-]?\s*(.+)$', plain, re.I)
    if not match:
        match = re.match(r'^(\d+(?:\.\d+)*)(?:[.、：:]\s*|\s+)(.+)$', plain)
    return (match[1], match[2].strip()) if match else ('', plain)


def _bold_feature(line):
    match = re.fullmatch(r'\s*\*\*(.+)\*\*\s*', line)
    if match and re.match(r'^(?:大功能\s*)?F\d+(?:[-.]\d+)*[\s：:、]', _text(match[1]), re.I):
        return _feature_title(match[1])
    return None


def _blocks(lines):
    """Tokenize the supported Markdown without consuming unknown content."""
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        fence = _FENCE.match(line)
        if fence:
            code, marker = [line], fence[1]
            closing = re.compile(r'^ {0,3}' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*$')
            index += 1
            while index < len(lines):
                code.append(lines[index])
                done = closing.match(lines[index])
                index += 1
                if done:
                    break
            yield {'type': 'code', 'text': '\n'.join(code)}
            continue
        title = _HEADING.match(line)
        if title:
            yield {'type': 'heading', 'level': len(title[1]), 'text': _text(title[2])}
            index += 1
            continue
        bold = _bold_feature(line)
        if bold:
            yield {'type': 'feature', 'identity': bold[0], 'text': bold[1]}
            index += 1
            continue
        header = _table_start(lines, index)
        if header is not None:
            data = []
            index += 2
            while index < len(lines) and lines[index].strip():
                row, delimited = _table_row(lines[index])
                if not delimited:
                    break
                data.append(row)
                index += 1
            width = max([len(header)] + [len(row) for row in data])
            header = header + ['补充列 ' + str(i + 1) for i in range(width - len(header))]
            yield {'type': 'table', 'columns': [_text(c) for c in header],
                   'rows': [[_text(c) for c in row] + [''] * (width - len(row)) for row in data]}
            continue
        item = _LIST.match(line)
        if item:
            yield {'type': 'list', 'indent': len(item[1].expandtabs(4)), 'text': _text(item[2])}
            index += 1
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip():
            following = lines[index]
            if (_HEADING.match(following) or _FENCE.match(following) or _bold_feature(following)
                    or _LIST.match(following) or _table_start(lines, index) is not None):
                break
            paragraph.append(following)
            index += 1
        yield {'type': 'paragraph', 'text': _text('\n'.join(paragraph))}


def _append_text(row, value, column=2):
    if value:
        row['cells'][column] += ('\n' if row['cells'][column] else '') + value


def _field_kind(name):
    name = re.sub(r'\s+', '', name).lower()
    if name in ('编号', '功能编号', 'id', '功能id'):
        return 'id'
    if name in ('上级编号', '父级编号', '父编号', '父功能编号', 'parent', 'parentid'):
        return 'parent'
    if name in ('功能名称', '功能', '子功能', '大功能', '功能点', '功能项', '名称'):
        return 'name'
    if name in ('优先级', '优先顺序', 'priority'):
        return 'priority'
    if name in ('依赖', '主要依赖', '前置依赖', '依赖项', '依赖编号'):
        return 'dependency'
    if name in ('备注', '待确认事项', '风险与待确认', '风险', '说明事项'):
        return 'notes'
    if re.search(r'验收|说明|描述|目标|结果', name):
        return 'description'
    return 'extra'


class _Rows:
    def __init__(self, sheet_id, width):
        self.prefix = sheet_id
        self.width = width
        self.rows = []

    def add(self, cells, parent=None, kind='item'):
        row = {'key': self.prefix + '-row-' + str(len(self.rows) + 1), 'parent': parent,
               'depth': 0, 'cells': cells + [''] * (self.width - len(cells)), 'kind': kind}
        self.rows.append(row)
        return row

    def finish(self):
        by_key = {row['key']: row for row in self.rows}
        # Remove invalid/cyclic links before computing depths. No row is discarded.
        for row in self.rows:
            current, seen = row, {row['key']}
            while current['parent'] in by_key:
                parent = current['parent']
                if parent in seen:
                    row['parent'] = None
                    if self.width == len(FEATURE_COLUMNS):
                        _append_text(row, '上级关系形成循环，已作为独立项展示。', 5)
                    break
                seen.add(parent)
                current = by_key[parent]
        children = {None: []}
        for row in self.rows:
            if row['parent'] not in by_key:
                row['parent'] = None
            children.setdefault(row['parent'], []).append(row)
        result, pending = [], [(row, 0) for row in reversed(children[None])]
        while pending:
            row, depth = pending.pop()
            row['depth'] = depth
            result.append(row)
            if row['key'] in children:
                row['kind'] = 'section'
            pending.extend((child, depth + 1) for child in reversed(children.get(row['key'], [])))
        return result


def _feature_rows(blocks, sheet_id, feature_keys=None):
    rows = _Rows(sheet_id, len(FEATURE_COLUMNS))
    heading_stack, current_feature = [], None
    id_refs, parent_refs = {}, {}

    def feature(row):
        # Keep presentation scaffolding distinguishable from actual features,
        # without exposing temporary parser metadata in the source worksheets.
        if feature_keys is not None and (row['cells'][0] or row['cells'][1] not in
                                         ('', '补充说明', '代码示例', '补充表格', '表格行')):
            feature_keys.add(row['key'])
        return row

    def register(row, identity, explicit=None):
        if identity:
            id_refs.setdefault(identity, []).append(row['key'])
        if explicit is not None:
            parent_refs[row['key']] = explicit

    def heading_parent():
        return heading_stack[-1][1] if heading_stack else None

    for block in blocks:
        kind = block['type']
        if kind == 'heading':
            level = block['level']
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            identity, name = _feature_title(block['text'])
            current_feature = feature(rows.add([identity, name], heading_parent(), 'section'))
            register(current_feature, identity)
            heading_stack.append((level, current_feature['key']))
        elif kind == 'feature':
            current_feature = feature(rows.add([block['identity'], block['text']], heading_parent()))
            register(current_feature, block['identity'])
        elif kind == 'table':
            fields = [_field_kind(name) for name in block['columns']]
            if 'name' not in fields:
                parent = rows.add(['', '补充表格', '；'.join(block['columns'])], heading_parent(), 'section')
                for data in block['rows']:
                    detail = '\n'.join(name + '：' + value for name, value in zip(block['columns'], data))
                    rows.add(['', data[0] or '表格行', detail], parent['key'])
                continue
            for data in block['rows']:
                cells, identity, explicit = [''] * 6, '', None
                for column, value, field in zip(block['columns'], data, fields):
                    if field == 'id':
                        if identity:
                            cells[5] += ('\n' if cells[5] else '') + column + '（重复列）：' + value
                        else:
                            identity = value
                            cells[0] = value
                    elif field == 'name':
                        cells[1] += (' / ' if cells[1] else '') + value
                    elif field == 'parent':
                        if explicit is not None:
                            cells[5] += ('\n' if cells[5] else '') + column + '（重复列）：' + value
                        else:
                            explicit = value
                    else:
                        target = {'priority': 3, 'dependency': 4, 'notes': 5}.get(field, 2 if field == 'description' else 5)
                        label = column + '：' if field in ('description', 'extra') and value else ''
                        cells[target] += ('\n' if cells[target] and value else '') + label + value
                row = feature(rows.add(cells, heading_parent()))
                register(row, identity, explicit)
            # A following paragraph retains the section context, not the last table row.
        elif kind == 'list' and current_feature is not None:
            _append_text(current_feature, '• ' + block['text'])
        elif (kind == 'paragraph' and current_feature is not None
              and (current_feature['key'] == heading_parent()
                   or not re.match(r'^(?:主要|前置)?依赖[：:]', block['text']))):
            _append_text(current_feature, block['text'])
        else:
            rows.add(['', '代码示例' if kind == 'code' else '补充说明', block['text']], heading_parent())

    by_key = {row['key']: row for row in rows.rows}
    for row in rows.rows:
        explicit = parent_refs.get(row['key'])
        identity = row['cells'][0]
        if explicit is not None:
            if explicit.lower() in _NO_PARENT:
                row['parent'] = None
            elif len(id_refs.get(explicit, [])) == 1:
                row['parent'] = id_refs[explicit][0]
            else:
                row['parent'] = None
                _append_text(row, '上级编号：' + explicit + '（未找到唯一父项，作为独立项展示）', 5)
        elif identity:
            # Only complete segment prefixes count. F010 is never a parent of F01.
            parent_id = re.sub(r'[-.]\d+$', '', identity)
            if parent_id != identity and len(id_refs.get(parent_id, [])) == 1:
                row['parent'] = id_refs[parent_id][0]
        if identity and len(id_refs[identity]) > 1:
            _append_text(row, '编号重复：' + identity + '；保留本行原内容。', 5)
    # Find all members of a cycle before mutating links, including self-parenting.
    cyclic = set()
    for row in rows.rows:
        path, positions, key = [], {}, row['key']
        while key in by_key:
            if key in positions:
                cyclic.update(path[positions[key]:])
                break
            positions[key] = len(path)
            path.append(key)
            key = by_key[key]['parent']
    for key in cyclic:
        row = by_key[key]
        original = parent_refs.get(key) or by_key[row['parent']]['cells'][0]
        row['parent'] = None
        _append_text(row, '上级编号：' + original + '（关系循环，作为独立项展示）', 5)
    return rows.finish()


def _general_sheet(blocks, sheet_id):
    if len(blocks) == 1 and blocks[0]['type'] == 'table':
        table = blocks[0]
        rows = _Rows(sheet_id, len(table['columns']))
        for cells in table['rows']:
            rows.add(cells)
        return table['columns'], rows.finish()
    rows, stack, list_stack = _Rows(sheet_id, 2), [], []
    for block in blocks:
        parent = stack[-1][1] if stack else None
        kind = block['type']
        if kind in ('heading', 'feature'):
            level = block.get('level', (stack[-1][0] + 1) if stack else 3)
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else None
            label = (block.get('identity', '') + ' ' + block['text']).strip()
            row = rows.add([label, ''], parent, 'section')
            stack.append((level, row['key']))
            list_stack = []
        elif kind == 'table':
            table = rows.add(['表格', '；'.join(block['columns'])], parent, 'section')
            for data in block['rows']:
                detail = '\n'.join(name + '：' + value for name, value in zip(block['columns'], data))
                rows.add([data[0] or '表格行', detail], table['key'])
            list_stack = []
        elif kind == 'list':
            while list_stack and list_stack[-1][0] >= block['indent']:
                list_stack.pop()
            if list_stack:
                parent = list_stack[-1][1]
            row = rows.add(['事项', block['text']], parent)
            list_stack.append((block['indent'], row['key']))
        else:
            rows.add(['代码示例' if kind == 'code' else '说明', block['text']], parent)
            list_stack = []
    return ['规划事项', '内容'], rows.finish()


def _feature_list(title, sheets, feature_keys):
    """Project recorded feature paths into a reference-style horizontal list.

    The detailed worksheets stay intact. Group merges refer to row identities,
    never just their names, so unrelated same-name modules cannot coalesce.
    """
    entries = []
    money_label = re.compile(r'^(大概金额|预算(?:金额)?|预估金额|估算金额|预计金额|报价|成本)[：:]\s*(.*)$')
    unknown_money = re.compile(r'^(?:待确认|待补充|待定|未知|未提供|暂无报价|无报价|不估价|不适用|'
                               r'n/?a\b|tbd\b|无[。.!！]?\s*$)', re.I)
    for source in sheets:
        if source['columns'] != FEATURE_COLUMNS:
            continue
        rows = source['rows']
        by_key = {row['key']: row for row in rows}
        candidates = {row['key']: row for row in rows if row['key'] in feature_keys}
        paths, children = {}, set()
        for row in candidates.values():
            chain, seen, current = [], set(), row
            while current and current['key'] not in seen:
                seen.add(current['key'])
                if current['key'] in candidates:
                    chain.append(current)
                current = by_key.get(current['parent'])
            chain.reverse()
            paths[row['key']] = chain
            if len(chain) > 1:
                children.add(chain[-2]['key'])
        for row in rows:
            if row['key'] not in candidates:
                continue
            values = row['cells']
            details = [values[2]] if values[2] else []
            for label, value in zip(('优先级', '依赖', '备注'), values[3:6]):
                if value:
                    details.append(label + '：' + value)
            # A parent with its own information receives its own row; child
            # descriptions are never substituted for that parent's evidence.
            if row['key'] in children and not details:
                continue
            recorded_money = []
            for line in values[5].splitlines():
                match = money_label.match(line.strip())
                if match and match[2].strip() and not unknown_money.search(match[2].strip()):
                    recorded_money.append((match[1], match[2].strip()))
            amount = (recorded_money[0][1] if len(recorded_money) == 1 else
                      '\n'.join(label + '：' + value for label, value in recorded_money))
            entries.append({'key': 'feature-list-' + row['key'], 'path': paths[row['key']],
                            'description': '\n'.join(details), 'money': amount, 'feature_id':values[0]})
    if not entries:
        return None
    depth = max(3, max(len(entry['path']) for entry in entries))
    columns = ['大功能', '小功能', '细分功能'] + ['第' + str(level) + '级功能' for level in range(4, depth + 1)]
    columns.append('功能介绍')
    has_money = any(entry['money'] for entry in entries)
    if has_money:
        columns.append('大概金额')
    rows = []
    for entry in entries:
        labels = [(' '.join(value for value in ancestor['cells'][:2] if value)).strip()
                  for ancestor in entry['path']]
        cells = labels + [''] * (depth - len(labels)) + [entry['description']]
        if has_money:
            cells.append(entry['money'])
        rows.append({'key': entry['key'], 'parent': None, 'depth': 0, 'kind': 'item', 'cells': cells, 'feature_id':entry['feature_id']})
    merges = []
    for column in range(depth):
        start = 0
        while start < len(entries):
            path = entries[start]['path']
            if column >= len(path):
                start += 1
                continue
            identity = tuple(row['key'] for row in path[:column + 1])
            end = start + 1
            while end < len(entries):
                following = entries[end]['path']
                if column >= len(following) or tuple(row['key'] for row in following[:column + 1]) != identity:
                    break
                end += 1
            if end - start > 1:
                merges.append({'row': start, 'column': column, 'rowSpan': end - start})
            start = end
    return {'id': 'feature-list', 'name': '功能清单', 'kind': 'feature-list', 'title': title,
            'hierarchyColumns': depth, 'columns': columns, 'rows': rows, 'merges': merges}


def parse_plan_sheet(content):
    """Return JSON-serializable worksheets, with every row reachable from a root."""
    title, sections, current, fence = '项目规划书', [], None, None
    first_title = True
    for line in str(content or '').splitlines():
        marker = _FENCE.match(line)
        in_code = fence is not None
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        heading = None if in_code or marker else _HEADING.match(line)
        if heading and len(heading[1]) == 1 and first_title:
            title = _text(heading[2])
            first_title = False
            continue
        if heading and len(heading[1]) == 2:
            current = {'name': _text(heading[2]), 'lines': []}
            sections.append(current)
        else:
            if current is None:
                if not line.strip():
                    continue
                current = {'name': '规划概览', 'lines': []}
                sections.append(current)
            current['lines'].append(line)
    sheets, feature_keys = [], set()
    for index, section in enumerate(sections, 1):
        identity = 'sheet-' + str(index)
        blocks = list(_blocks(section['lines']))
        if '功能' in section['name'] and not re.search(r'优先|依赖|风险|阶段', section['name']):
            columns, rows = list(FEATURE_COLUMNS), _feature_rows(blocks, identity, feature_keys)
        else:
            columns, rows = _general_sheet(blocks, identity)
        sheets.append({'id': identity, 'name': section['name'], 'columns': columns, 'rows': rows})
    feature_list = _feature_list(title, sheets, feature_keys)
    if feature_list:
        sheets.insert(0, feature_list)
    technology = {}
    for sheet in sheets:
        if sheet['columns'] != FEATURE_COLUMNS: continue
        for row in sheet['rows']:
            fields = {}
            for line in row['cells'][5].splitlines():
                match = re.match(r'^(所需技术|技术方案|前期准备|准备条件)[：:]\s*(.*)',line)
                if match: fields[match[1]]=match[2]
            technology[row['key']] = [fields.get('所需技术',fields.get('技术方案','')),fields.get('前期准备',fields.get('准备条件',''))]
    if any(any(values) for values in technology.values()):
        for sheet in sheets:
            if sheet['columns'] == FEATURE_COLUMNS:
                sheet['columns'] = list(FEATURE_COLUMNS) + ['所需技术','前期准备']
                for row in sheet['rows']: row['cells'] += technology.get(row['key'],['',''])
            elif sheet.get('kind') == 'feature-list':
                sheet['columns'] += ['所需技术','前期准备']
                for row in sheet['rows']: row['cells'] += technology.get(row['key'].removeprefix('feature-list-'),['',''])
    return {'title': title, 'sheets': sheets}
