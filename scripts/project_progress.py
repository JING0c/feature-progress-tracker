"""Deterministic, evidence-gated ledger updates for host conversations.

This module performs no file, network, clock or model operations.  The caller
must validate the ledger revision, serialize writes and record the result.
Review identities and evidence are explicit attestations, not authenticated
proof that another agent ran a test; the host must supply real review results.
"""
import copy
import json
import re

from serve_dashboard import parse, flatten, normalize_progress_summary, item_flags
from planning_operations import (history_text, replace_item_records, reopened_fields,
                                 TRACKING_FIELD, INACTIVE_TRACKING, HISTORY_FIELDS)


STATUSES = {'未开始', '进行中', '待审核', '受阻', '已取消', '已完成'}
FIELDS = {'状态', '执行 Agent', '实现证据', '问题', '争议'}
HISTORY = '进度更新历史'
EMPTY = {'', '无', '暂无', '未知', '待分配', '待审核', '待确认', '未提供', '不适用', '-', '—',
         'unknown', 'pending', 'none', 'n/a', 'tbd'}


def _text(value, label, required=False):
    if not isinstance(value, str) or len(value) > 10000:
        raise ValueError(label + '必须是长度不超过10000的文字。')
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or len(value.splitlines()) > 1 or any(char in value for char in '|｜;；'):
        raise ValueError(label + '请使用单行文字，不要包含竖线、分号或控制字符。')
    value = value.strip()
    if required and value.lower() in EMPTY:
        raise ValueError(label + '需要具体身份或可核查的证据，不能使用占位内容。')
    return value


def _accepted(item):
    return bool(item['checked'] and item['fields'].get('状态') == '已完成')


def _present(value, label):
    # Existing fields were already parsed from the ledger. Do not reject or
    # rewrite their ordinary punctuation while checking whether they exist.
    if not isinstance(value, str) or value.strip().lower() in EMPTY:
        raise ValueError(label + '需要具体可核查的内容，不能使用占位文字。')


def _accepted_tree(item):
    children = [child for child in item.get('children', []) if child['fields'].get('状态') != '已取消']
    return _accepted(item) and all(_accepted_tree(child) for child in children)


def _history(item):
    try:
        records = json.loads(item['fields'].get(HISTORY, '[]'))
    except (ValueError, TypeError) as exc:
        raise ValueError('已有进度更新历史损坏，请先核对：' + item['id']) from exc
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise ValueError('已有进度更新历史损坏，请先核对：' + item['id'])
    return records


def _archive(old, new, actor, reason):
    # Store only this record's business state. Both histories stay on the live
    # record; copying either one here recursively nests the planning archive.
    before = {key: copy.deepcopy(old[key]) for key in ('id', 'name', 'checked', 'notes')}
    before['fields'] = {key: copy.deepcopy(value) for key, value in old['fields'].items()
                        if key not in HISTORY_FIELDS}
    entry = {'actor': actor, 'reason': reason, 'before': before}
    new['fields'][HISTORY] = history_text(_history(old) + [entry])


def _review(review, executors):
    required = {'reviewer', 'score', 'conclusion', 'evidence', 'reason'}
    if not isinstance(review, dict) or set(review) != required:
        raise ValueError('完成需要独立审核资料：reviewer、score、conclusion、evidence、reason。')
    reviewer = _text(review['reviewer'], '审核 Agent', required=True)
    if reviewer.casefold() in {executor.strip().casefold() for executor in executors}:
        raise ValueError('审核 Agent 必须与实际执行 Agent 不同。')
    score = review['score']
    if type(score) is not int or not 80 <= score <= 100:
        raise ValueError('通过审核的评分必须是80至100之间的整数。')
    if review['conclusion'] != '通过':
        raise ValueError('只有独立审核结论为通过时才能完成。')
    return {'审核 Agent': reviewer, '评分': str(score), '审核结论': '通过',
            '审核证据': _text(review['evidence'], '审核证据', required=True),
            '评分理由': _text(review['reason'], '评分理由', required=True)}


def update_progress(content, feature_id, changes, actor, review=None):
    """Update one feature and invalidate affected parent approval if necessary.

    ``changes`` accepts 状态/执行 Agent/实现证据/问题/争议 only. Completion
    additionally needs a concrete executor, implementation evidence and a
    separate reviewer with a passing score, reason and review evidence.
    Completion of a parent never marks its children complete; all non-cancelled
    children must already be independently accepted. Cancelled parents hide
    their subtree from totals while retaining every original child record.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError('请先生成并保存功能台账。')
    if not isinstance(feature_id, str) or not re.fullmatch(r'F\d+(?:-\d+)*', feature_id):
        raise ValueError('功能编号格式无效。')
    if not isinstance(changes, dict) or not changes or set(changes) - FIELDS:
        raise ValueError('只允许更新状态、执行 Agent、实现证据、问题和争议。')
    actor = _text(actor, '操作 Agent', required=True)
    values = {key: _text(value, key) for key, value in changes.items()}
    if '状态' in values and values['状态'] not in STATUSES:
        raise ValueError('功能状态无效。')
    groups = parse(content)
    original = [item for group in groups for item in flatten(group['items'])]
    by_id = {item['id']: item for item in original}
    if len(original) != len(by_id):
        raise ValueError('台账存在重复功能编号，请先核对。')
    if feature_id not in by_id:
        raise ValueError('未找到功能编号：' + feature_id)
    parents = {}
    for item in original:
        for child in item.get('children', []):
            parents[child['id']] = item['id']
    ancestors, identity = [], feature_id
    while identity in parents:
        identity = parents[identity]
        ancestors.append(by_id[identity])
    old = by_id[feature_id]
    inactive = old['fields'].get(TRACKING_FIELD) in INACTIVE_TRACKING
    if inactive and values.get('状态', old['fields'].get('状态')) != '已取消':
        raise ValueError('该功能未在当前规划中采用；请先修改规划采用选择，再生成并保存台账，不能直接激活。')
    recording_cancelled = inactive and old['fields'].get('状态') == '已取消' and review is None
    if not recording_cancelled and any(item['fields'].get('状态') == '已取消' for item in ancestors):
        raise ValueError('上级功能已取消，请先恢复上级功能后再更新子功能。')
    _history(old)
    current = copy.deepcopy(old)
    current['fields'].update(values)
    # Repeat calls with exactly the same state/evidence do not manufacture
    # new historical operations or revoke an already accepted feature.
    own_change = current['fields'] != old['fields']
    if not own_change and review is None:
        _, summary, _ = normalize_progress_summary(content, groups)
        return {'content': content, 'summary': summary, 'adjustments': [], 'changed_ids': []}
    status = current['fields'].get('状态', '未开始')
    explicit_complete = values.get('状态') == '已完成'
    if review is not None and not explicit_complete:
        raise ValueError('审核资料仅用于明确标记已完成的操作。')
    if explicit_complete:
        executor = _text(current['fields'].get('执行 Agent', ''), '执行 Agent', required=True)
        _present(current['fields'].get('实现证据', ''), '实现证据')
        _present(current['fields'].get('验收', ''), '验收标准')
        if any(item_flags(current).values()):
            raise ValueError('仍有问题或争议，不能标记为已完成。')
        children = [item for item in current.get('children', []) if item['fields'].get('状态') != '已取消']
        if not all(_accepted_tree(item) for item in children):
            raise ValueError('上级功能只有在所有有效子功能均已验收后才能完成。')
        current['fields'].update(_review(review, (executor, old['fields'].get('执行 Agent', ''))))
        current['checked'] = True
    else:
        current['checked'] = False
        if _accepted(old) or old['fields'].get('状态') == '已完成':
            current['fields'] = reopened_fields(current['fields'])
            current['fields']['审核证据'] = '待审核'
    changed = {}
    if current['fields'] != old['fields'] or current['checked'] != old['checked']:
        _archive(old, current, actor, '更新功能进度')
        changed[feature_id] = current
        for parent in ancestors:
            if not parent['checked'] and parent['fields'].get('状态') not in ('已完成', '待审核'):
                continue
            reopened = copy.deepcopy(parent)
            reopened['checked'] = False
            reopened['fields'] = reopened_fields(parent['fields'])
            reopened['fields']['审核证据'] = '待审核'
            _archive(parent, reopened, actor, '子功能 ' + feature_id + ' 已变化，需重新审核')
            changed[parent['id']] = reopened
    result = replace_item_records(content, changed)
    result, summary, adjustments = normalize_progress_summary(result, parse(result))
    return {'content': result, 'summary': summary, 'adjustments': adjustments,
            'changed_ids': [item['id'] for item in original if item['id'] in changed]}
