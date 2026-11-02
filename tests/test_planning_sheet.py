"""Plan worksheets preserve document content and express only recorded hierarchy."""
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('planning_sheet', ROOT / 'scripts/planning_sheet.py')
sheet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheet)


def values(model):
    return '\n'.join(cell for tab in model['sheets'] for row in tab['rows'] for cell in row['cells'])


class PlanningSheetTest(unittest.TestCase):
    def test_standard_features_follow_explicit_parents_not_row_order(self):
        result = sheet.parse_plan_sheet('''# 器材预约规划书
## 项目概览
| 事项 | 内容 |
|---|---|
| 目标 | 管理器材预约 |
## 功能规划
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 备注 |
|---|---|---|---|---|---|---|---|
| F01-01-01 | F01-01 | 冲突校验 | 同一器材 | 重叠时拒绝 | P0 | F02 | 待确认边界 |
| F01 | 无 | 预约管理 | 预约闭环 | 串联通过 | P0 | 无 | 已确认 |
| F01-01 | F01 | 登记预约 | 登记时段 | 保存记录 | P0 | F02 | |
''')
        self.assertEqual(result['title'], '器材预约规划书')
        overview, features = result['sheets']
        self.assertEqual(overview['columns'], ['事项', '内容'])
        self.assertEqual(features['columns'], ['编号', '功能名称', '说明与验收', '优先级', '依赖', '备注'])
        self.assertEqual([r['cells'][0] for r in features['rows']], ['F01', 'F01-01', 'F01-01-01'])
        self.assertEqual([r['depth'] for r in features['rows']], [0, 1, 2])
        for row, parent in zip(features['rows'][1:], features['rows']):
            self.assertEqual(row['parent'], parent['key'])
        leaf = features['rows'][-1]
        self.assertEqual(leaf['cells'][3:5], ['P0', 'F02'])
        self.assertIn('同一器材', leaf['cells'][2])
        self.assertIn('重叠时拒绝', leaf['cells'][2])
        self.assertIn('待确认边界', leaf['cells'][5])
        json.dumps(result, ensure_ascii=False)

    def test_old_heading_plan_keeps_table_children_and_surrounding_notes(self):
        result = sheet.parse_plan_sheet('''# 图书项目
## 三、分层功能与验收标准
以下均为未开始，保护性处理需确认。
### 2. 借阅办理
#### 2.1 借出
任一校验不通过时，不产生借阅记录。
| 子功能 | 可操作验收标准 |
|---|---|
| 居民校验 | 未登记不能借出 |
| 图书校验 | 在借不能重复借出 |
**待确认：**是否补录借出日期。
#### 2.2 归还
- 归还后恢复可借。
## 四、优先级与依赖
| 顺序 | 功能组 | 优先原因 | 主要依赖 |
|---|---|---|---|
| 1 | 本机保存 | 保护数据 | 操作系统待确定 |
补充说明，不承诺工期。
''')
        features = result['sheets'][0]['rows']
        by_name = {r['cells'][1]: r for r in features}
        self.assertEqual(by_name['借出']['parent'], by_name['借阅办理']['key'])
        self.assertEqual(by_name['居民校验']['parent'], by_name['借出']['key'])
        self.assertEqual(by_name['居民校验']['depth'], 2)
        self.assertEqual(by_name['归还']['parent'], by_name['借阅办理']['key'])
        for text in ['保护性处理需确认', '任一校验不通过', '是否补录借出日期', '归还后恢复可借', '保护数据', '操作系统待确定', '不承诺工期']:
            self.assertIn(text, values(result))

    def test_bold_feature_ids_and_ambiguous_group_note_remain_distinct(self):
        result = sheet.parse_plan_sheet('''# 摄影项目
## 五、分层功能与验收标准
首期 P0，未开始、未审核。
### F01：成员资料
**F01-01 维护成员**
- 不采集学号。
**F01-02 编号校验**
- 拒绝重复编号。
依赖：F02、F03。
### F02：预约管理
**F02-01 创建预约**
- 保存后可查看。
''')
        rows = result['sheets'][0]['rows']
        by_id = {r['cells'][0]: r for r in rows if r['cells'][0]}
        self.assertEqual(by_id['F01-01']['parent'], by_id['F01']['key'])
        self.assertEqual(by_id['F01-02']['parent'], by_id['F01']['key'])
        self.assertEqual(by_id['F02-01']['parent'], by_id['F02']['key'])
        # A trailing paragraph may apply to the group. Never infer it as a child's dependency.
        self.assertEqual(by_id['F01-02']['cells'][4], '')
        notes = [r for r in rows if '依赖：F02、F03' in '\n'.join(r['cells'])]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]['parent'], by_id['F01']['key'])
        self.assertIn('未开始、未审核', values(result))

    def test_invalid_parent_graph_keeps_every_feature_and_explains_fallback(self):
        result = sheet.parse_plan_sheet('''# 测试
## 功能规划
| 编号 | 上级编号 | 功能名称 | 验收标准 |
|---|---|---|---|
| A | B | 循环甲 | 甲可验收 |
| B | A | 循环乙 | 乙可验收 |
| C | 不存在 | 孤儿项 | 丙可验收 |
| D | 无 | 重复甲 | 丁可验收 |
| D | 无 | 重复乙 | 戊可验收 |
| E | D | 重复父项子项 | 己可验收 |
''')
        rows = result['sheets'][0]['rows']
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({r['key'] for r in rows}), 6)
        self.assertTrue(all(r['parent'] is None for r in rows))
        self.assertIn('循环', values(result))
        self.assertIn('不存在', values(result))
        self.assertIn('重复', values(result))

    def test_nested_ids_use_exact_prefix_and_never_manufacture_dependencies(self):
        result = sheet.parse_plan_sheet('''## 功能规划
| 编号 | 功能名称 | 验收标准 |
|---|---|---|
| F01 | 功能组 | 根验收 |
| F01-01 | 子功能 | 子验收 |
| F01-01-01 | 更细功能 | 叶验收 |
| F010-01 | 另一功能 | 独立验收 |
''')
        rows = result['sheets'][0]['rows']
        self.assertEqual([r['depth'] for r in rows], [0, 1, 2, 0])
        self.assertTrue(all(r['cells'][3:5] == ['', ''] for r in rows))

    def test_fences_quotes_pipes_and_extra_cells_are_preserved(self):
        result = sheet.parse_plan_sheet('''# 安全展示
开头资料。
## 功能规划
### F01：资料
```markdown
## 不能作为章节
| 功能名称 | 验收标准 |
|---|---|
| 不是功能行 | 仅示例 |
```
> 引用资料 <script>alert(1)</script>
| 功能名称 | 验收标准 | 额外资料 |
|---|---|---|
| 支持 `a|b` | 显示 a\\|b | 保留附注 | 多余单元格 |
## 风险
| 事项 | 内容 |
|---|---|
| 路径 | C:\\data\\logs |
''')
        self.assertEqual(len(result['sheets']), 3)
        text = values(result)
        for expected in ['开头资料', '## 不能作为章节', '仅示例', '<script>alert(1)</script>', 'a|b', '保留附注', '多余单元格', r'C:\data\logs']:
            self.assertIn(expected, text)
        for tab in result['sheets']:
            self.assertTrue(all(len(row['cells']) == len(tab['columns']) for row in tab['rows']))

    def test_empty_and_heading_only_documents_are_not_invented(self):
        self.assertEqual(sheet.parse_plan_sheet('')['sheets'], [])
        result = sheet.parse_plan_sheet('# 我的规划\n## 目标\n## 功能规划')
        self.assertEqual(result['title'], '我的规划')
        self.assertEqual([s['name'] for s in result['sheets']], ['目标', '功能规划'])
        self.assertTrue(all(not s['rows'] for s in result['sheets']))

    def test_crlf_bold_colon_and_duplicate_identity_columns_keep_content(self):
        result = sheet.parse_plan_sheet('''# 测试
## 功能规划
### F01：功能组
**F01-01：编号维护**
- 拒绝重复编号。
验收示例：重复保存时拒绝。
| 编号 | 编号 | 上级编号 | 上级编号 | 功能名称 | 验收标准 |
|---|---|---|---|---|---|
| F01-02 | duplicate-id | F01 | duplicate-parent | 查询编号 | 保存后能查到 |
'''.replace('\n', '\r\n'))
        rows = result['sheets'][0]['rows']
        by_id = {r['cells'][0]: r for r in rows}
        self.assertEqual(by_id['F01-01']['cells'][1], '编号维护')
        self.assertIn('重复保存时拒绝', by_id['F01-01']['cells'][2])
        self.assertEqual(by_id['F01-02']['parent'], by_id['F01']['key'])
        self.assertIn('duplicate-id', values(result))
        self.assertIn('duplicate-parent', values(result))


if __name__ == '__main__':
    unittest.main()
