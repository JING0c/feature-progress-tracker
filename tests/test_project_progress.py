import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import serve_dashboard as d

MODULE = ROOT / 'scripts' / 'project_progress.py'
if MODULE.exists():
    spec = importlib.util.spec_from_file_location('project_progress', MODULE)
    progress = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(progress)
else:
    progress = None


def record(identity, name, status='未开始', checked=False, pad=''):
    return (f'{pad}- [{"x" if checked else " "}] {identity} {name}｜状态：{status}\n'
            f'{pad}  - 验收：能明确得到结果\n'
            f'{pad}  - 优先级：高\n'
            f'{pad}  - 依赖：无\n'
            f'{pad}  - 执行 Agent：implementer-A\n'
            f'{pad}  - 实现证据：提交abc，正常与异常流程测试通过\n'
            f'{pad}  - 审核 Agent：{"reviewer-B" if checked else "待审核"}\n'
            f'{pad}  - 评分：{"95" if checked else "待审核"}\n'
            f'{pad}  - 问题：无\n'
            f'{pad}  - 自定义：原资料不能丢失\n')


BASE = ('# 功能执行情况\n进度：已验收 0/2（0%）；待审核 0；受阻 0\n\n'
        '## 大功能 F01：订单\n' + record('F01-01', '订单流程')
        + record('F01-01-01', '提交', pad='  ')
        + record('F01-01-02', '查询', pad='  ')
        + '\n## 补充\n保留这段文字。\n```markdown\n- [x] F99-01 示例｜状态：已完成\n```\n')
REVIEW = {'reviewer': 'reviewer-C', 'score': 94, 'conclusion': '通过',
          'evidence': '独立复测正常与失败流程，结果见report.md', 'reason': '功能40，边界28，证据18，维护8'}


def items(content):
    return {item['id']: item for group in d.parse(content) for item in d.flatten(group['items'])}


class ProgressTest(unittest.TestCase):
    def update(self, text=BASE, identity='F01-01-01', changes=None, review=None):
        self.assertIsNotNone(progress, 'project_progress implementation is missing')
        return progress.update_progress(text, identity, changes or {'状态': '进行中'}, 'codex', review)

    def test_state_change_preserves_other_records_and_records_exact_old_fields(self):
        result = self.update()
        before, after = items(BASE), items(result['content'])
        self.assertEqual(after['F01-01-02'], before['F01-01-02'])
        self.assertEqual(after['F01-01-01']['fields']['验收'], before['F01-01-01']['fields']['验收'])
        self.assertEqual(after['F01-01-01']['fields']['自定义'], '原资料不能丢失')
        self.assertEqual(after['F01-01-01']['fields']['状态'], '进行中')
        history = json.loads(after['F01-01-01']['fields']['进度更新历史'])
        self.assertEqual(history[-1]['before']['fields'], before['F01-01-01']['fields'])
        self.assertEqual(history[-1]['actor'], 'codex')
        self.assertIn('## 补充\n保留这段文字。\n```markdown\n- [x] F99-01 示例｜状态：已完成\n```', result['content'])
        self.assertEqual(result['summary']['working'], 1)

    def test_completion_requires_independent_review_and_implementation_evidence(self):
        for review in [None, {**REVIEW, 'reviewer': 'implementer-A'}, {**REVIEW, 'reviewer': '待审核'},
                       {**REVIEW, 'conclusion': '待审核'}, {**REVIEW, 'score': 79},
                       {**REVIEW, 'score': True}, {**REVIEW, 'score': 101},
                       {**REVIEW, 'evidence': ''}, {**REVIEW, 'reason': '无'}]:
            with self.subTest(review=review):
                with self.assertRaises(ValueError): self.update(changes={'状态': '已完成'}, review=review)
        for key in ['实现证据', '执行 Agent']:
            with self.assertRaises(ValueError):
                self.update(changes={'状态': '已完成', key: '未知'}, review=REVIEW)

    def test_completion_sets_review_fields_and_counts_leaves_only(self):
        result = self.update(changes={'状态': '已完成'}, review=REVIEW)
        item = items(result['content'])['F01-01-01']
        self.assertTrue(item['checked'])
        self.assertEqual(item['fields']['审核 Agent'], 'reviewer-C')
        self.assertEqual(item['fields']['审核证据'], REVIEW['evidence'])
        self.assertEqual(item['fields']['评分理由'], REVIEW['reason'])
        self.assertEqual(result['summary']['done'], 1)
        self.assertEqual(result['summary']['total'], 2)
        self.assertIn('进度：已验收 1/2（50%）', result['content'])

    def test_parent_cannot_be_completed_before_children_and_never_auto_accepts(self):
        with self.assertRaises(ValueError):
            self.update(identity='F01-01', changes={'状态': '已完成'}, review=REVIEW)
        first = self.update(changes={'状态': '已完成'}, review=REVIEW)['content']
        second = self.update(first, 'F01-01-02', {'状态': '已完成'}, REVIEW)['content']
        self.assertFalse(items(second)['F01-01']['checked'])
        accepted = self.update(second, 'F01-01', {'状态': '已完成'}, REVIEW)
        self.assertTrue(items(accepted['content'])['F01-01']['checked'])
        self.assertEqual(accepted['summary']['total'], 2)

    def test_reopening_child_revokes_parent_and_preserves_review_history(self):
        accepted = BASE.replace('状态：未开始', '状态：已完成').replace('- [ ]', '- [x]').replace('审核 Agent：待审核', '审核 Agent：old-reviewer').replace('评分：待审核', '评分：95')
        result = self.update(accepted, changes={'状态': '受阻', '问题': '无法加载数据'})
        before, after = items(accepted), items(result['content'])
        self.assertFalse(after['F01-01']['checked'])
        self.assertEqual(after['F01-01']['fields']['状态'], '进行中')
        self.assertEqual(after['F01-01-01']['fields']['审核 Agent'], '待审核')
        self.assertEqual(after['F01-01-01']['fields']['评分'], '待审核')
        self.assertFalse(after['F01-01-01']['checked'])
        for identity in ['F01-01', 'F01-01-01']:
            self.assertEqual(json.loads(after[identity]['fields']['进度更新历史'])[-1]['before']['fields'], before[identity]['fields'])
        self.assertEqual(after['F01-01-02'], before['F01-01-02'])

    def test_changing_completed_evidence_reopens_without_silent_review_reuse(self):
        accepted = self.update(changes={'状态': '已完成'}, review=REVIEW)['content']
        result = self.update(accepted, changes={'实现证据': '新提交def，尚未复验'})
        item = items(result['content'])['F01-01-01']
        self.assertEqual(item['fields']['状态'], '进行中')
        self.assertFalse(item['checked'])
        self.assertEqual(item['fields']['审核 Agent'], '待审核')

    def test_invalid_input_and_injection_are_rejected(self):
        cases = [{'验收': '篡改'}, {'状态': '完工'}, {'实现证据': '成功｜状态：已完成'},
                 {'实现证据': '成功；评分：100'}, {'问题': '无\n- [x] F09-01 注入'},
                 {'问题': '\x00'}, {'问题': '无\u2028- [x] F09-01 注入'}, {'实现证据': 123}]
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): self.update(changes=changes)
        with self.assertRaises(ValueError): self.update(identity='F99-01')
        with self.assertRaises(ValueError): self.update(changes={'状态': '进行中'}, review=REVIEW)

    def test_cancellation_excludes_subtree_without_deleting_children(self):
        result = self.update(identity='F01-01', changes={'状态': '已取消'})
        self.assertEqual(result['summary']['total'], 0)
        self.assertEqual(items(result['content'])['F01-01-01'], items(BASE)['F01-01-01'])
        with self.assertRaises(ValueError):
            self.update(result['content'], 'F01-01-01', {'状态': '已完成'}, REVIEW)

    def test_plan_excluded_feature_cannot_be_activated_through_progress_updates(self):
        for tracking in ('未采用', '已从规划移除'):
            text = '# 功能执行情况\n## 大功能 F02：导出\n' + record('F02', '导出', '已取消')
            text += '  - 规划跟踪：' + tracking + '\n'
            for status in ('未开始', '进行中', '受阻', '待审核', '已完成'):
                with self.subTest(tracking=tracking, status=status):
                    with self.assertRaisesRegex(ValueError, '规划.*采用'):
                        self.update(text, 'F02', {'状态':status}, REVIEW if status == '已完成' else None)

    def test_plan_excluded_child_can_record_evidence_without_becoming_active(self):
        text = ('# 功能执行情况\n## 大功能 F01：订单\n'
                + record('F01-01', '订单流程', '已取消') + '  - 规划跟踪：未采用\n'
                + record('F01-01-01', '提交', '已取消', pad='  ') + '    - 规划跟踪：未采用\n')
        result = self.update(text, changes={'实现证据':'归档的提交abc', '问题':'暂不实施，待确认需求'})
        after = items(result['content'])['F01-01-01']
        self.assertEqual(after['fields']['状态'], '已取消')
        self.assertFalse(after['checked'])
        self.assertEqual(after['fields']['实现证据'], '归档的提交abc')
        self.assertEqual(after['fields']['问题'], '暂不实施，待确认需求')
        self.assertEqual(result['summary']['total'], 0)
        self.assertEqual(items(result['content'])['F01-01']['fields'], items(text)['F01-01']['fields'])
        self.assertFalse(items(result['content'])['F01-01']['checked'])

    def test_noop_is_idempotent_and_history_does_not_grow(self):
        first = self.update()
        second = self.update(first['content'])
        self.assertEqual(first['content'], second['content'])
        self.assertEqual(second['changed_ids'], [])

    def test_duplicate_ids_or_corrupt_history_fail_closed(self):
        with self.assertRaises(ValueError): self.update(BASE.replace('F01-01-02', 'F01-01-01'))
        damaged = BASE.replace('  - 问题：无', '  - 问题：无\n  - 进度更新历史：broken', 1)
        with self.assertRaises(ValueError): self.update(damaged, 'F01-01')

    def test_changing_executor_cannot_turn_original_executor_into_independent_reviewer(self):
        with self.assertRaises(ValueError):
            self.update(changes={'状态': '已完成', '执行 Agent': 'new-executor'},
                        review={**REVIEW, 'reviewer': 'implementer-A'})

    def test_unfinished_grandchild_prevents_accepting_higher_parent(self):
        malformed = BASE.replace('状态：未开始', '状态：已完成').replace('- [ ]', '- [x]')
        malformed = malformed.replace('## 补充', record('F01-01-01-01', '未完成孙项', pad='    ') + '\n## 补充')
        with self.assertRaises(ValueError):
            self.update(malformed, 'F01-01', {'状态': '已完成'}, REVIEW)

    def test_completion_requires_known_acceptance_and_no_unresolved_issue(self):
        without_acceptance = BASE.replace('验收：能明确得到结果', '验收：待确认')
        with self.assertRaises(ValueError): self.update(without_acceptance, changes={'状态': '已完成'}, review=REVIEW)
        for key in ['问题', '争议']:
            with self.assertRaises(ValueError):
                self.update(changes={'状态': '已完成', key: '验收还有争议'}, review=REVIEW)

    def test_existing_acceptance_punctuation_remains_usable(self):
        content = BASE.replace('验收：能明确得到结果', '验收：能明确得到结果；异常时可以重试')
        content = content.replace('实现证据：提交abc，正常与异常流程测试通过', '实现证据：提交abc；正常与异常流程测试通过')
        result = self.update(content, changes={'状态': '已完成'}, review=REVIEW)
        self.assertEqual(items(result['content'])['F01-01-01']['fields']['验收'], '能明确得到结果；异常时可以重试')


if __name__ == '__main__':
    unittest.main()
