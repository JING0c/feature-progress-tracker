"""Round-trip a canonical feature table without replacing surrounding prose."""
import re
from planning_sheet import _table_row, _table_start

COLUMNS = ['采用','编号','上级编号','功能名称','说明','验收标准','优先级','依赖','所需技术','前期准备','备注']

def editable_table(content):
    lines = content.splitlines(keepends=True)
    fence = None
    tables = []
    for index,line in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})',line)
        if marker:
            if fence == marker[1][0]: fence = None
            elif fence is None: fence = marker[1][0]
            continue
        if fence: continue
        header = _table_start(lines,index)
        if header is None or not {'编号','上级编号','功能名称','说明','验收标准'}.issubset(set(header)):
            continue
        if len(set(header)) != len(header):
            raise ValueError('功能表有重复列，请先通过对话重新整理。')
        end=index+2; rows=[]
        while end < len(lines) and lines[end].strip() and _table_row(lines[end])[1]:
            cells = _table_row(lines[end])[0]
            if len(cells) != len(header): raise ValueError('功能表列数不一致，请先整理原文。')
            rows.append({k: re.sub(r'\\([\\|])',r'\1',v).replace('<br>','\n') for k,v in zip(header,cells)});end+=1
        tables.append({'start':index,'end':end,'columns':header,'rows':rows})
    if len(tables) != 1:
        raise ValueError('请先生成一份包含编号、上级编号和验收标准的单一功能表，再直接编辑。旧规划仍可阅读。')
    table=tables[0]
    for row in table['rows']: row['采用']=row.get('采用','').strip() or '是'
    table['columns'] = COLUMNS + [c for c in table['columns'] if c not in COLUMNS]
    return table

def replace_features(content, rows):
    table=editable_table(content)
    if not isinstance(rows,list) or not 1 <= len(rows) <= 500:
        raise ValueError('功能表需包含1至500行。')
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or any(not isinstance(v,str) or len(v)>10000 for v in row.values()):
            raise ValueError('功能单元格内容无效或过长。')
        identity=row.get('编号','').strip()
        if not re.fullmatch(r'F\d+(?:-\d+)*',identity) or identity in ids or not row.get('功能名称','').strip():
            raise ValueError('功能编号必须唯一（如F01-01），名称不能为空。')
        if row.get('采用','是') not in ('是','否'): raise ValueError('采用列只能为是或否。')
        ids.add(identity)
    parents={r['编号'].strip():r.get('上级编号','').strip() for r in rows}
    choices={r['编号'].strip():r.get('采用','是') for r in rows}
    for identity,parent in parents.items():
        expected=identity.rsplit('-',1)[0] if '-' in identity else ''
        actual='' if parent in ('','无','—','-') else parent
        if actual!=expected: raise ValueError('上级编号需与功能编号前缀一致，例如F01-01的上级为F01；调整层级时请同步编号与依赖。')
        if parent in choices and choices[identity]=='是' and choices[parent]=='否':
            raise ValueError('采用子功能时也需采用上级功能；取消父功能会连同子项取消。')
        seen={identity}
        while parent and parent not in ('无','—','-'):
            if parent not in parents or parent in seen: raise ValueError('上级编号不存在或形成循环，请调整层级。')
            seen.add(parent);parent=parents[parent]
    columns=table['columns']
    def cell(value):
        # Escaped delimiters remain in a single cell; line breaks use safe HTML
        # notation that is displayed as text by the document renderer.
        return value.replace('\\','\\\\').replace('|','\\|').replace('\r\n','\n').replace('\r','\n').replace('\n','<br>')
    def line(values):return '| '+' | '.join(cell(v) for v in values)+' |\n'
    block=line(columns)+line(['---']*len(columns))+''.join(line([r.get(c,'') for c in columns]) for r in rows)
    lines=content.splitlines(keepends=True)
    return ''.join(lines[:table['start']])+block+''.join(lines[table['end']:])


def select_feature(content, identity, selected):
    table=editable_table(content); rows=table['rows']; by_id={r['编号']:r for r in rows}
    if identity not in by_id or not isinstance(selected,bool): raise ValueError('采用选择无效。')
    pending=[identity]; seen=set()
    while pending:
        key=pending.pop()
        if key in seen: continue
        seen.add(key); by_id[key]['采用']='是' if selected else '否'
        pending.extend(r['编号'] for r in rows if r.get('上级编号')==key)
    if selected:
        parent=by_id[identity].get('上级编号')
        while parent in by_id and parent not in seen:
            seen.add(parent);by_id[parent]['采用']='是';parent=by_id[parent].get('上级编号')
    # A parent whose children are all declined is also declined.
    for _ in range(len(rows)):
        changed=False
        for row in rows:
            children=[r for r in rows if r.get('上级编号')==row['编号']]
            if children and all(r.get('采用')=='否' for r in children) and row.get('采用')!='否':
                row['采用']='否';changed=True
        if not changed: break
    return replace_features(content,rows)
