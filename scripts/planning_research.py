"""Public GitHub reference research; repository content is data, never commands."""
import base64
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def github_json(path):
    request = Request('https://api.github.com/' + path, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'LocalFeaturePlanner/1.0'})
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(500001)
        if len(raw) > 500000:
            raise ValueError('GitHub 返回内容过大，请缩小关键词。')
        return json.loads(raw)
    except HTTPError as error:
        raise ValueError('GitHub 检索失败（HTTP %s），可能已达到公开接口限额，请稍后重试。' % error.code) from error
    except (URLError, TimeoutError) as error:
        raise ValueError('无法连接 GitHub，请检查网络后重试。') from error

def search_repositories(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 160 or any(c in query for c in '\n\r\0'):
        raise ValueError('请填写不超过160字的 GitHub 搜索关键词。')
    query = query.strip()
    data = github_json('search/repositories?' + urlencode({'q':query, 'per_page':5}))
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):
        raise ValueError('GitHub 返回格式异常，请稍后重试。')
    repositories = []
    for item in data.get('items', [])[:5]:
        name = item.get('full_name', '')
        if len(name)>200 or not re.fullmatch(r'[\w.-]+/[\w.-]+', name, re.ASCII):
            continue
        license_data = item.get('license') or {}
        repo = {'name':name, 'url':'https://github.com/' + name,
                'description':str(item.get('description') or '')[:2000],
                'language':str(item.get('language') or '未标注')[:100],
                'license':str(license_data.get('spdx_id') or '未标注')[:100],
                'stars':item.get('stargazers_count',0), 'updated_at':str(item.get('updated_at') or '')[:100],
                'readme':'', 'readme_note':'未读取', 'selected':False}
        if len(repositories) < 3:
            try:
                readme = github_json('repos/' + name + '/readme')
                if readme.get('encoding') == 'base64':
                    repo['readme'] = base64.b64decode(readme.get('content','')).decode('utf-8',errors='replace')[:8000]
                    repo['readme_note'] = 'README节选，未验证代码实现'
            except (ValueError, TypeError):
                repo['readme_note'] = 'README无法读取，仅有仓库元数据'
        repositories.append(repo)
    return {'version':1, 'completed':True, 'selection_confirmed':not repositories, 'query':query,
            'searched_at':datetime.now(timezone.utc).isoformat(), 'repositories':repositories}

def research_markdown(result):
    # JSON strings escape embedded newlines, so a README cannot close the fence.
    return ('# GitHub 参考项目\n\n勾选表示将仓库纳入功能参考，不代表采用其代码。'
            '星数不代表适用性，README声明不等于实现已验证，采用前需核对许可证及实际行为。\n\n'
            '```json\n' + json.dumps(result,ensure_ascii=False,indent=2) + '\n```\n')

def read_research(content):
    match = re.search(r'^```json\n(.*?)\n```',content,re.M|re.S)
    if not match:
        raise ValueError('调研文件格式无效，请重新搜索。')
    data = json.loads(match[1])
    if not isinstance(data,dict): raise ValueError('调研记录格式无效，请重新搜索。')
    if data.get('version') != 1 or data.get('completed') is not True or not isinstance(data.get('repositories'),list):
        raise ValueError('调研记录无效，请重新搜索。')
    feature_idea = data.get('feature_idea', '')
    if not isinstance(feature_idea, str) or len(feature_idea) > 6000:
        raise ValueError('新增功能调研记录无效，请重新搜索。')
    if len(data['repositories'])>20:raise ValueError('调研项目过多，请重新搜索。')
    for repo in data['repositories']:
        if not isinstance(repo,dict) or len(str(repo.get('name','')))>200 or not re.fullmatch(r'[\w.-]+/[\w.-]+',str(repo.get('name','')),re.ASCII):
            raise ValueError('调研仓库记录无效，请重新搜索。')
        repo['url'] = 'https://github.com/' + repo['name']
        repo['selected'] = repo.get('selected') is True
    data['selection_confirmed'] = data.get('selection_confirmed') is True or not data['repositories']
    return data


def select_repositories(data, names):
    if not isinstance(names,list) or any(not isinstance(name,str) for name in names) or len(names)!=len(set(names)):
        raise ValueError('参考项目选择无效。')
    known={repo['name'] for repo in data['repositories']}
    if set(names)-known:raise ValueError('所选项目不在当前候选列表中，请重新读取调研结果。')
    result=json.loads(json.dumps(data))
    result.pop('revision',None)
    for repo in result['repositories']:repo['selected']=repo['name'] in names
    result['selection_confirmed']=True
    result['selected_at']=datetime.now(timezone.utc).isoformat()
    return result
