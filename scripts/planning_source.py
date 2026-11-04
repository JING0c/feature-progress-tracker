"""Read pinned public GitHub source without executing repository code."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def git(args, cwd=None, timeout=60):
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never'] + args,
                            cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('仓库读取失败，请检查网络或本地缓存后重试。')
    return result.stdout if args and args[0] == 'show' else result.stdout.strip()


def collect_sources(root, repositories, need, progress, focus=""):
    cache = root / '.reference-code'
    if cache.is_symlink(): raise ValueError('源码缓存路径不能是符号链接。')
    cache.mkdir(exist_ok=True)
    result = {'repositories': [], 'snippets': [], 'scope': '静态源码节选核对，未运行项目；未看到的实现保持待确认。'}
    extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.vue', '.svelte', '.cs', '.rb', '.php'}
    tokens = set(re.findall(r'[a-zA-Z]{3,}', focus.lower() or need.lower()))
    for index, repo in enumerate(repositories):
        name = repo['name']
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*', name):
            raise ValueError('仓库名称无效。')
        path = cache / name.replace('/', '--')
        if path.is_symlink(): raise ValueError('仓库缓存不能是符号链接。')
        url = 'https://github.com/' + name + '.git'
        progress(stage='检查仓库', message=name, completed=index, total=len(repositories))
        reused = path.exists()
        if not reused:
            progress(stage='克隆仓库', message=name + '（网络传输中，耗时取决于仓库大小）', completed=index, total=len(repositories))
            temporary = Path(tempfile.mkdtemp(prefix='.clone-', dir=cache))
            try:
                git(['clone', '--depth=1', '--no-checkout', '--', url, str(temporary / 'repo')], timeout=180)
                (temporary / 'repo').rename(path)
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
        if git(['config', '--get', 'remote.origin.url'], path) != url:
            raise ValueError('缓存仓库来源不匹配，未使用此缓存。')
        commit = git(['rev-parse', '--verify', 'HEAD'], path)
        if not re.fullmatch(r'[0-9a-f]{40,64}', commit): raise ValueError('仓库提交无效。')
        progress(stage='读取源码', message=name + ' @ ' + commit[:10], completed=index, total=len(repositories))
        paths = git(['ls-tree', '-r', '--name-only', '-z', commit], path).split('\0')
        candidates = [p for p in paths if Path(p).suffix in extensions and not any(part in ('node_modules', 'vendor', 'dist', 'build', 'docs', '.github', 'tests', 'test') for part in Path(p).parts)]
        candidates.sort(key=lambda p: (-sum(t in p.lower() for t in tokens), p.count('/'), p))
        excerpts = []
        for filename in candidates[:32]:
            # Read Git blobs, never checkout symlinks or execute repository scripts.
            size = git(['cat-file', '-s', commit + ':' + filename], path)
            if size and (not size.isdigit() or int(size) > 120000): continue
            raw = git(['show', commit + ':' + filename], path)
            if '\0' in raw: continue
            lines = raw.splitlines()
            if not lines: continue
            # Select a bounded window near relevant code, including deep functions.
            windows=[]
            for start in range(0,len(lines),40):
                chunk='\n'.join(lines[start:start+140]).lower()
                score=sum(min(chunk.count(token),12)*len(token) for token in tokens)
                windows.append((score,start))
            score,start=max(windows,key=lambda item:(item[0],-item[1]))
            selected=lines[start:start+140]
            while len('\n'.join(selected))>10000: selected.pop()
            if not selected: continue
            excerpt={'repository':name, 'commit':commit, 'path':filename, 'start':start+1, 'end':start+len(selected),
                     'text':'\n'.join(str(start+i+1)+': '+line for i,line in enumerate(selected))}
            excerpts.append((score,filename,excerpt))
        excerpts.sort(key=lambda item:(-item[0],item[1]))
        result['snippets'].extend(item[2] for item in excerpts[:6])
        count=min(len(excerpts),6)
        result['repositories'].append({'name':name, 'commit':commit, 'path':str(path), 'files_read':count,
                                       'state':'已克隆，使用本地提交' if reused else '已克隆新缓存'})
    return result


def validate_report(report, rows, snippets):
    expected = {r['编号'] for r in rows if r.get('采用') != '否'}
    features = report.get('features') if isinstance(report, dict) else None
    if not isinstance(features, list) or len(features) != len(expected) or {r.get('id') for r in features if isinstance(r,dict)} != expected:
        raise ValueError('源码核对未覆盖所有采用的功能，请重试。')
    for item in features:
        if item.get('status') not in ('有源码依据', '部分依据', '未找到依据') or not isinstance(item.get('finding'), str) or not item['finding'].strip():
            raise ValueError('源码核对结果格式无效。')
        evidence = item.get('evidence')
        if not isinstance(evidence,list) or (item['status'] != '未找到依据' and not evidence):
            raise ValueError('源码核对缺少证据。')
        for entry in evidence:
            if not isinstance(entry,dict) or not any(entry.get('repository') == s['repository'] and entry.get('path') == s['path']
                    and isinstance(entry.get('line'),int) and s['start'] <= entry['line'] <= s['end'] for s in snippets):
                raise ValueError('源码核对引用了未读取的文件或行号。')
    return {'features':features}


def report_markdown(report):
    lines=['# 规划源码核对', '', '本报告为静态源码参考，不代表本项目已经实现或验收。', '',
           '## 仓库版本', '']
    for repo in report['sources']['repositories']:
        lines.append('- '+repo['name']+' @ '+repo['commit']+'；'+repo['state']+'；读取 '+str(repo['files_read'])+' 个文件')
    lines += ['', '## 功能核对', '']
    for item in report['features']:
        lines += ['- '+item['id']+'：'+item['status']+' — '+item['finding']]
        for e in item['evidence']: lines.append('  - '+e['repository']+' / '+e['path']+':'+str(e['line']))
    lines += ['', '## 版本绑定数据', '', '```json', json.dumps(report,ensure_ascii=False,indent=2), '```', '']
    return '\n'.join(lines)
