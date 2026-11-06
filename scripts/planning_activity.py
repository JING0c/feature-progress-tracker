"""Project-scoped, readable Markdown record of actual planning request outcomes."""
import json
import os
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone
import difflib

LABELS={'/api/ledger/generate':'按规划转换台账','/api/plan/merge':'合并已确认的功能','/api/plan/save':'保存功能表','/api/plan/suggestions':'生成智能体建议',
        '/api/plan/suggestions/preview':'生成采纳建议预览','/api/research':'搜索 GitHub 参考',
        '/api/research/selection':'保存参考选择','/api/research/source-check':'源码核对',
        '/api/planning':'规划生成与对话','/api/ledger/save':'保存台账到看板'}
MARKER='<!-- planning-activity-v1 -->\n'

def path_for(project):
    root=Path(project['directory']).resolve();path=root/'规划操作记录.md'
    if path.is_symlink() or path in (Path(project['plan_path']).resolve(),Path(project['ledger_path']).resolve()):
        raise ValueError('操作记录路径与项目资料冲突。')
    return path

def read(project):
    path=path_for(project)
    if not path.exists():return []
    content=path.read_text(encoding='utf-8')
    if not content.startswith(MARKER):raise ValueError('操作记录格式无效，原文件已保留。')
    line=content.splitlines()[1] if len(content.splitlines())>1 else ''
    if not line.startswith('<!-- records ') or not line.endswith(' -->'):
        raise ValueError('操作记录元数据无效，原文件已保留。')
    records=json.loads(line[len('<!-- records '):-len(' -->')])
    if not isinstance(records,list) or any(not isinstance(r,dict) or any(not isinstance(r.get(k),str) for k in ('id','time','title','detail','state')) for r in records):
        raise ValueError('操作记录内容损坏，原文件已保留。')
    return records

def append(project,record):
    records=read(project)+[record];path=path_for(project)
    raw=json.dumps(records,ensure_ascii=False).replace('--','\\u002d\\u002d')
    text=MARKER+'<!-- records '+raw+' -->\n# 规划操作记录\n\n记录实际请求结果；预览不代表已保存或已实现。\n'
    for item in records:
        text+='\n## '+item['time']+' · '+item['title']+'\n\n'+item['detail']+'\n'
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
            temporary=f.name;f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)

def changes(before,after):
    if before==after:return '内容没有变化。'
    try:
        from planning_editor import editable_table
        old={r['编号']:r for r in editable_table(before)['rows']}
        new={r['编号']:r for r in editable_table(after)['rows']}
        lines=[]
        for identity,row in new.items():
            if identity not in old:lines.append('新增 '+identity+' '+row.get('功能名称','')+'\n'+'\n'.join(key+'：'+value for key,value in row.items()));continue
            for key,value in row.items():
                if value!=old[identity].get(key,''):
                    lines.append(identity+' · '+key+'\n修改前：'+old[identity].get(key,'')+'\n修改后：'+value)
        for identity in old.keys()-new.keys():lines.append('移除 '+identity+' '+old[identity].get('功能名称',''))
        if lines:return '\n\n'.join(lines)
    except (ValueError,KeyError):pass
    return '\n'.join(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile='修改前',tofile='修改后',lineterm='')) or '内容没有变化。'

def event(route,payload,data,status,before=''):
    if route not in LABELS:return None
    title=LABELS[route];detail='';state='success'
    if status>=400:
        title+='失败';state='failed';detail=str(data.get('error','请求失败'))
    elif route in ('/api/ledger/generate','/api/plan/merge'):
        title+='（尚未保存）';detail='由代码执行，未调用模型。\n新增条目：'+('、'.join(data.get('added',[])) or '无')+'\n'+data.get('note','')
    elif route=='/api/plan/save':
        title='功能表已保存';detail=changes(before,payload.get('content',data.get('content','')))
        version=data.get('history_version',{}).get('id','')
        if version:detail='历史版本：'+version+'\n'+detail
        if payload.get('note'):detail+='\n保存备注：'+payload['note']
    elif route=='/api/plan/suggestions':
        title+=' · '+str(len(data.get('suggestions',[])))+' 条（未采纳）'
        detail='\n\n'.join(s['id']+' '+s['title']+'\n'+s['reason'] for s in data.get('suggestions',[])) or '本轮没有建议。'
    elif route.endswith('/suggestions/preview'):
        title+='（尚未保存）';detail='所选建议：'+', '.join(payload.get('selected',[]))+'\n'+data.get('diff','')
    elif route=='/api/research':
        detail='搜索：'+str(data.get('query',payload.get('query','')))+'\n'+'\n'.join(r['name'] for r in data.get('repositories',[]))
    elif route=='/api/research/selection':
        detail='选作参考：'+('、'.join(r['name'] for r in data.get('repositories',[]) if r.get('selected')) or '明确不选')
    elif route=='/api/planning':
        title={'chat':'补充需求对话完成','plan':'规划书已生成（待保存）','ledger':'台账已生成（待保存）','decompose':'新功能拆分已生成（待确认）'}.get(payload.get('intent'),'规划回复已生成')
        detail=data.get('reply','')
    elif route=='/api/research/source-check':
        detail=data.get('report','核对完成。')
    else:detail='台账文件已保存。'
    return {'id':uuid.uuid4().hex,'time':datetime.now(timezone.utc).isoformat(),'title':title,'detail':detail,'state':state,
            'history_version':data.get('history_version',{}).get('id','')}

def listing(project, warnings=None):
    from planning_history import list_versions,read_version
    try:records=read(project)
    except (OSError,ValueError) as error:
        if warnings is None:raise
        warnings.append('操作记录暂时无法读取，仍可查看保留的功能表：'+str(error))
        records=[]
    versions=list_versions(project,warnings=warnings)
    readable=[];contents={}
    for version in versions:
        try:
            contents[version['id']]=read_version(project,version['id'])['content']
            readable.append(version)
        except (OSError,ValueError) as error:
            if warnings is None:raise
            warnings.append('有一份已保存功能表的内容无法读取，操作记录仍保留：'+str(error))
    versions=readable
    snapshots={v['id']:{key:v[key] for key in ('id','saved_at','source','note')} for v in versions}
    known=set()
    for record in records:
        # These are derived read-only fields, never trusted from the stored log.
        record.pop('snapshot',None);record.pop('snapshot_missing',None)
        identity=record.get('history_version')
        saved=record['state']=='success' and record['title'] in ('功能表已保存','规划书已保存')
        if not saved or not identity:continue
        snapshot=snapshots.get(identity) if isinstance(identity,str) else None
        if snapshot:
            record['snapshot']=snapshot
            known.add(identity)
        else:record['snapshot_missing']=True
    for i,version in enumerate(versions):
        if version['id'] in known:continue
        after=contents[version['id']]
        before=contents[versions[i+1]['id']] if i+1<len(versions) else None
        backup=version['source']=='保存前文件版本'
        detail='来源：已有保存历史（不是补记操作）。\n保存方式：'+version['source']+'\n'
        if backup:detail+='保存前留存的功能表；显示时间为归档时间，原修改时间未知。\n'
        else:detail+='保留了当时的功能表，未记录完整操作过程。\n'
        if version['note']:detail+='保存备注：'+version['note']+'\n'
        detail+=('与上一份可读取功能表比较：\n'+changes(before,after) if before is not None else
                 '这是目前最早可读取的功能表，没有更早可读取内容可比较。')
        records.append({'id':version['id'],'time':version['saved_at'],
                        'title':'保存前的功能表备份' if backup else '早期保存的功能表',
                        'history_version':version['id'],'snapshot':snapshots[version['id']],
                        'state':'history','detail':detail})
    return sorted(records,key=lambda r:(r['time'],r['id']),reverse=True)
