"""A new completion must use the current adopted requirements, via public MCP."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from plugin_mcp import call_tool
from planning_editor import editable_table, replace_features
from serve_dashboard import RequestError

PLAN = '''# 订单项目规划书
## 项目目标
帮助用户保存并查看本地订单。
## 范围边界
仅管理本地订单，不进行在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 | 备注 |
|---|---|---|---|---|---|---|
| F01 | 无 | 订单管理 | 管理本地订单 | 订单可保存和查看 | 是 | |
| F01-01 | F01 | 保存订单 | 保存输入的信息 | 保存后能读取订单 | 是 | |
| F02 | 无 | 导出订单 | 导出订单文件 | 文件可以打开 | 是 | |
'''
REVIEW = {'reviewer': 'independent-B', 'score': 95, 'conclusion': '通过',
          'evidence': 'tests/订单验收.md', 'reason': '独立核对实现及当前验收'}


class CompletionPlanBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.workspace = str(Path(tmp.name) / 'workspace')
        self.project = call_tool('create_project', {'workspace': self.workspace, 'name': '订单'}, 'codex')['project']
        self.save_plan(PLAN); self.sync()
        self.update({'执行 Agent': 'developer-A', '实现证据': '提交abc：保存读取测试通过'})

    def call(self, name, **args):
        return call_tool(name, {'workspace': self.workspace, 'project_id': self.project['id'], **args}, 'codex')

    def save_plan(self, content):
        return self.call('save_plan', content=content, revision=self.call('read_project')['plan']['revision'])

    def sync(self):
        candidate = self.call('generate_ledger')
        return self.call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                         plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])

    def update(self, changes, identity='F01-01', review=None):
        args = dict(feature_id=identity, changes=changes, revision=self.call('read_project')['ledger']['revision'])
        if review is not None: args['review'] = review
        return self.call('update_feature_progress', **args)

    def change(self, identity='F01-01', **fields):
        text = self.call('read_project')['plan']['content']
        rows = editable_table(text)['rows']
        next(row for row in rows if row['编号'] == identity).update(fields)
        self.save_plan(replace_features(text, rows))

    def assert_completion_rejected(self, identity='F01-01'):
        before = Path(self.project['ledger_path']).read_bytes()
        with self.assertRaisesRegex(RequestError, '同步.*台账') as caught:
            self.update({'状态': '已完成'}, identity, REVIEW)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(), before)

    def test_changed_acceptance_cannot_complete_until_synced(self):
        self.change(验收标准='保存的订单必须加密')
        self.assert_completion_rejected()
        self.sync()
        result = self.update({'状态': '已完成'}, review=REVIEW)
        self.assertEqual(result['summary']['done'], 1)
        self.assertIn('保存的订单必须加密', result['content'])

    def test_declined_or_removed_function_cannot_newly_complete(self):
        self.change(采用='否')
        self.assert_completion_rejected()
        self.save_plan(PLAN.replace('| F01-01 | F01 | 保存订单 | 保存输入的信息 | 保存后能读取订单 | 是 | |\n', ''))
        self.assert_completion_rejected()

    def test_non_requirement_changes_do_not_block_completion(self):
        self.change(备注='增加保存说明', 优先级='高')
        self.change('F02', 验收标准='导出需包含日期')
        self.assertEqual(self.update({'状态': '已完成'}, review=REVIEW)['summary']['done'], 1)

    def test_descendant_change_or_addition_blocks_parent_completion(self):
        text = PLAN + '| F01-01-01 | F01-01 | 校验输入 | 校验必填信息 | 缺少名称时提示 | 是 | |\n'
        self.save_plan(text); self.sync()
        self.update({'状态': '已取消'}, 'F01-01-01')
        self.change('F01-01-01', 验收标准='缺少名称或数量时提示')
        self.assert_completion_rejected()
        self.sync()
        self.save_plan(self.call('read_project')['plan']['content'] + '\n')
        self.assertEqual(self.update({'状态': '已完成'}, review=REVIEW)['summary']['done'], 1)
        text = self.call('read_project')['plan']['content']
        rows = editable_table(text)['rows']
        rows.append({'编号':'F01-01-02','上级编号':'F01-01','功能名称':'检查库存','说明':'核对库存数量','验收标准':'不足时明确提示','采用':'是'})
        self.save_plan(replace_features(text, rows))
        self.assert_completion_rejected()

    def test_external_plan_change_during_completion_rejected_without_ledger_write(self):
        import project_progress
        original = project_progress.update_progress
        before = Path(self.project['ledger_path']).read_bytes()
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            path = Path(self.project['plan_path'])
            path.write_text(path.read_text().replace('保存后能读取订单', '保存后能读取加密订单'))
            return result
        with patch('project_progress.update_progress', side_effect=changed):
            with self.assertRaises(RequestError): self.update({'状态':'已完成'}, review=REVIEW)
        self.assertEqual(Path(self.project['ledger_path']).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
