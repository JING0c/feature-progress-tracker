"""Validated, opt-in feature suggestions from an isolated Codex process."""
import copy
import json
import re
from planning_editor import editable_table, replace_features

EDITABLE={'功能名称','说明','验收标准','优先级','依赖','所需技术','前期准备','备注'}

def apply(content,suggestions,selected,reserved_ids=()):
    if not isinstance(selected,list) or not selected or any(not isinstance(s,str) for s in selected) or len(set(selected))!=len(selected):
        raise ValueError('请勾选至少一条建议，不能重复选择。')
    by_id={s['id']:s for s in suggestions}
    if set(selected)-set(by_id):raise ValueError('建议已变化，请重新读取。')
    rows=copy.deepcopy(editable_table(content)['rows']);existing={r['编号']:r for r in rows}; touched={}
    reserved=set(reserved_ids)
    for sid in selected:
        for change in by_id[sid]['changes']:
            action,identity,fields=change.get('action'),change.get('id'),change.get('fields')
            if action not in ('add','update') or not isinstance(identity,str) or not re.fullmatch(r'F\d+(?:-\d+)*',identity):raise ValueError('建议操作或功能编号无效。')
            allowed=EDITABLE|({'上级编号'} if action=='add' else set())
            if not isinstance(fields,dict) or not fields or set(fields)-allowed or any(not isinstance(v,str) or len(v)>10000 for v in fields.values()):raise ValueError('建议只可修改功能描述字段，不能删除、改编号或改变原采用决定。')
            if action=='add':
                if identity in reserved:
                    raise ValueError('功能编号 '+identity+' 已保留在现有台账中，不能作为新功能复用；请重新生成建议或使用新的编号。')
                if identity in existing or any(not fields.get(k,'').strip() for k in ('功能名称','说明','验收标准','上级编号')):raise ValueError('新增功能编号重复或缺少名称、上级、说明、验收。')
                row={'编号':identity,'采用':'是',**fields};rows.append(row);existing[identity]=row
            else:
                if identity not in existing:raise ValueError('建议修改的功能不存在。')
                for key,value in fields.items():
                    cell=(identity,key)
                    if cell in touched and touched[cell]!=value:raise ValueError('所选建议对同一字段有不同修改，请分别预览。')
                    touched[cell]=value
                existing[identity].update(fields)
    result=replace_features(content,rows)
    if editable_table(result)['rows']==editable_table(content)['rows']:raise ValueError('所选建议未产生功能表变化。')
    return result


def validate(raw,content,preserve_ids=False,reserved_ids=()):
    suggestions=raw.get('suggestions') if isinstance(raw,dict) else None
    if not isinstance(suggestions,list) or not 0<=len(suggestions)<=8:raise ValueError('子智能体应返回最多8条结构化建议。')
    clean=[]
    for index,item in enumerate(suggestions):
        if not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not item[k].strip() or len(item[k])>4000 for k in ('title','reason')):raise ValueError('建议缺少标题或理由。')
        changes=item.get('changes')
        if not isinstance(changes,list) or not 1<=len(changes)<=20 or any(not isinstance(c,dict) for c in changes):raise ValueError('建议缺少具体变更。')
        identity=item.get('id') if preserve_ids else 'S%02d'%(index+1)
        if not isinstance(identity,str) or not re.fullmatch(r'S\d+',identity) or any(s['id']==identity for s in clean):raise ValueError('建议编号无效或重复，请重新生成。')
        proposal={'id':identity,'title':item['title'],'reason':item['reason'],'changes':changes}
        apply(content,[proposal],[proposal['id']],reserved_ids=reserved_ids)
        clean.append(proposal)
    return {'suggestions':clean}


def markdown(record):
    lines=['来源：独立 Codex 子进程；建议不代表已采纳、已实现或已验收。','基于规划版本：'+record['plan_revision'],'']
    for s in record['suggestions']:lines+=['## '+s['id']+' '+s['title'],s['reason'],'']
    return '# 功能建议\n\n```json\n'+json.dumps(record,ensure_ascii=False,indent=2)+'\n```\n\n'+'\n'.join(lines)+'\n'


def read(content):
    # New records put machine data first. Legacy records put it last. JSON
    # strings escape newlines, so embedded Markdown cannot create a fence here.
    match=re.match(r'\A# 功能建议\n\n```json\n(.*?)\n```',content,re.S)
    if not match:
        tail=content.rsplit('\n```json\n',1)
        match=re.fullmatch(r'(.*?)\n```\s*',tail[-1],re.S) if len(tail)==2 else None
    if not match:raise ValueError('建议文件格式无效，请重新生成。')
    result=json.loads(match[1])
    if not isinstance(result,dict) or not isinstance(result.get('suggestions'),list) or not isinstance(result.get('plan_revision'),str):raise ValueError('建议记录无效。')
    return result
