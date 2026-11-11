"""Mixed edits resolve dependencies after code allocates stable feature IDs."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from plugin_mcp import call_tool
from planning_editor import editable_table, replace_features
from serve_dashboard import parse, flatten

PLAN = '''# 图书项目规划书
## 项目目标
帮助管理员登记并导出本地图书目录。
## 范围边界
本期仅管理本机图书，不提供在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 依赖 | 采用 |
|---|---|---|---|---|---|---|
| F01 | 无 | 图书管理 | 维护本地图书目录 | 可登记并找到图书 | 无 | 是 |
| F01-01 | F01 | 登记图书 | 输入名称保存图书 | 保存后列表可见图书 | 无 | 是 |
| F02 | 无 | 导出图书 | 下载图书清单 | 文件能打开并包含图书 | F01-01 | 是 |
'''
ADDITION = {'key':'N1', 'parent':'F01', '功能名称':'备份图书', '说明':'生成图书备份', '验收标准':'备份可完整还原所有图书'}


class FeatureDependencyMergeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.workspace = str(Path(tmp.name) / 'workspace')
        self.project = call_tool('create_project', {'workspace':self.workspace,'name':'图书'}, 'codex')['project']
        self.call('save_plan', content=PLAN, revision=self.call('read_project')['plan']['revision'])

    def call(self, action, **args):
        return call_tool(action, {'workspace':self.workspace,'project_id':self.project['id'], **args}, 'codex')

    def edit(self, dependency, **args):
        return self.call('edit_features', revision=self.call('read_project')['plan']['revision'],
                         updates=[{'id':'F02','fields':{'依赖':dependency}}], **args)

    def test_existing_row_dependency_maps_and_survives_actual_ledger_save(self):
        before = self.call('read_project')['plan']['content']
        preview = self.edit('N1', additions=[ADDITION])
        self.assertEqual(preview['mapping'], {'N1':'F01-02'})
        self.assertEqual(next(r for r in editable_table(preview['content'])['rows'] if r['编号']=='F02')['依赖'], 'F01-02')
        self.assertEqual(self.call('read_project')['plan']['content'], before)
        self.call('save_plan', content=preview['content'], revision=preview['revision'])
        c = self.call('generate_ledger')
        self.call('save_ledger', content=c['content'], revision=c['ledger_revision'], plan_revision=c['plan_revision'], source_revision=c['source_revision'])
        items = [i for g in parse(self.call('read_project')['ledger']['content']) for i in flatten(g['items'])]
        self.assertEqual(next(i for i in items if i['id']=='F02')['fields']['依赖'], 'F01-02')

    def test_known_final_number_can_reference_same_batch_addition(self):
        result = self.edit('F01-02', additions=[ADDITION], preview=False)
        self.assertTrue(result['saved'])
        self.assertIn('F01-02', self.call('read_project')['plan']['content'])

    def test_nested_forward_references_and_chinese_text_map_all_rows(self):
        second = {**ADDITION, 'key':'N2', 'parent':'N1', '功能名称':'校验备份', '依赖':'依赖N1和F01-01'}
        result = self.edit('等待N2完成、N1；F01-01', additions=[second,ADDITION])
        rows = {r['编号']:r for r in editable_table(result['content'])['rows']}
        self.assertEqual(rows['F02']['依赖'], '等待F01-02-01完成、F01-02；F01-01')
        self.assertEqual(rows['F01-02-01']['依赖'], '依赖F01-02和F01-01')

    def test_unresolved_refs_rejected_before_preview_or_save(self):
        before = Path(self.project['plan_path']).read_bytes()
        for dependency in ('N9','等待N9完成','F99','等待F99完成'):
            for additions in ([], [ADDITION]):
                with self.subTest(dependency=dependency, additions=bool(additions)):
                    with self.assertRaises(ValueError): self.edit(dependency, additions=additions, preview=False)
                    self.assertEqual(Path(self.project['plan_path']).read_bytes(), before)

    def test_full_plan_save_rejects_temporary_dependency(self):
        rows = editable_table(PLAN)['rows']; rows[-1]['依赖'] = '等待N1完成'
        with self.assertRaises(ValueError):
            self.call('save_plan', content=replace_features(PLAN,rows), revision=self.call('read_project')['plan']['revision'])
        self.assertEqual(self.call('read_project')['plan']['content'], PLAN)

    def test_external_unresolved_dependency_cannot_generate_ledger(self):
        rows = editable_table(PLAN)['rows']; rows[-1]['依赖'] = 'N1'
        Path(self.project['plan_path']).write_text(replace_features(PLAN,rows))
        with self.assertRaises(ValueError): self.call('generate_ledger')

    def test_existing_dependency_and_preparation_text_remain_unchanged(self):
        result = self.edit('完成F01-01；准备 USB、JSON1 和 F1-score 数据', additions=[ADDITION])
        rows = editable_table(result['content'])['rows']
        self.assertEqual(next(r for r in rows if r['编号']=='F02')['依赖'], '完成F01-01；准备 USB、JSON1 和 F1-score 数据')


if __name__ == '__main__': unittest.main()
