"""Immutable Markdown snapshots of successful webpage plan saves."""
import os
import hashlib
import json
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

MARKER='\n<!-- planning-version-content -->\n'

def history_directory(project):
    root=Path(project['directory']).resolve()
    directory=(root/'规划历史').resolve()
    if not directory.is_relative_to(root) or str(directory) in (project['plan_path'],project['ledger_path']):
        raise ValueError('规划历史目录与项目文件冲突。')
    return directory

def read_version(project, identity, content=True):
    if not isinstance(identity,str) or not re.fullmatch(r'v-[0-9a-f]{32}',identity):
        raise ValueError('历史版本编号无效。')
    directory=history_directory(project);path=(directory/(identity+'.md')).resolve()
    if not path.is_relative_to(directory):raise ValueError('历史版本路径无效。')
    with path.open(encoding='utf-8',newline='') as file:
        header=[]
        for _ in range(1000):
            line=file.readline()
            if not line or sum(map(len,header))>30000:raise ValueError('历史版本记录损坏。')
            header.append(line)
            if line=='<!-- planning-version-content -->\n':break
        else:raise ValueError('历史版本记录损坏。')
        match=re.search(r'^```json\n(.*?)\n```',''.join(header),re.M|re.S)
        if not match:raise ValueError('历史版本元数据无效。')
        metadata=json.loads(match[1])
        if (not isinstance(metadata,dict) or metadata.get('id')!=identity or
                any(not isinstance(metadata.get(k),str) for k in ('saved_at','revision','source','note')) or
                not re.fullmatch(r'[a-f0-9]{64}',metadata['revision']) or not isinstance(metadata.get('references'),list)):
            raise ValueError('历史版本元数据无效。')
        for reference in metadata['references']:
            if not isinstance(reference,dict) or not re.fullmatch(r'[\w.-]+/[\w.-]+',str(reference.get('name','')),re.ASCII):
                raise ValueError('历史参考项目记录无效。')
            reference['url']='https://github.com/'+reference['name']
        if content:
            body=file.read(1000001)
            if len(body)>1000000 or hashlib.sha256(body.encode()).hexdigest()!=metadata.get('revision'):
                raise ValueError('历史内容已被改动，无法作为原保存版本读取。')
            metadata['content']=body
    return metadata

def list_versions(project, warnings=None):
    directory=history_directory(project)
    versions=[]
    if directory.exists():
        for path in directory.glob('v-*.md'):
            if not re.fullmatch(r'v-[0-9a-f]{32}',path.stem):continue
            try:
                versions.append(read_version(project,path.stem,content=False))
            except (OSError,ValueError) as error:
                if warnings is None:raise
                warnings.append('有一份已保存功能表的记录无法读取，其他记录仍可查看：'+str(error))
    return sorted(versions,key=lambda version:(version['saved_at'],version['id']),reverse=True)

def stage(project, body, source, note, references):
    if len(body)>1000000:raise ValueError('规划内容过大，无法建立可追溯版本，请先整理文档。')
    directory=history_directory(project);directory.mkdir(parents=True,exist_ok=True)
    identity='v-'+uuid.uuid4().hex
    metadata={'id':identity,'saved_at':datetime.now(timezone.utc).isoformat(),
              'revision':hashlib.sha256(body.encode()).hexdigest(),'source':source,'note':note,
              'references':[{'name':r['name'],'url':'https://github.com/'+r['name']} for r in references]}
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='',dir=directory,prefix='.pending-',suffix='.md',delete=False) as file:
        file.write('# 项目规划历史版本\n\n```json\n'+json.dumps(metadata,ensure_ascii=False,indent=2)+'\n```\n'+MARKER+body)
        file.flush();os.fsync(file.fileno())
        name=file.name
    return {'temporary':Path(name),'target':directory/(identity+'.md'),'metadata':metadata}

def commit(staged):
    staged['temporary'].rename(staged['target'])
    return staged['metadata']

def discard(staged):
    staged['temporary'].unlink(missing_ok=True)
