"""Plan worksheets preserve document content and express only recorded hierarchy."""
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('planning_sheet', ROOT / 'scripts/planning_sheet.py')
sheet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheet)


def details(model):
    return [tab for tab in model['sheets'] if tab.get('kind') != 'feature-list']


def values(model):
    return '\n'.join(cell for tab in model['sheets'] for row in tab['rows'] for cell in row['cells'])


class PlanningSheetTest(unittest.TestCase):
    def test_reference_list_expresses_three_levels_and_preserves_parent_information(self):
        result = sheet.parse_plan_sheet('''# 预约工具
## 功能规划
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 备注 |
|---|---|---|---|---|---|---|---|
| F01 | 无 | 预约管理 | 管理预约闭环 | 按规则串联操作通过 | P0 | 无 | 需讨论边界 |
| F01-01 | F01 | 新建预约 | | | | | |
| F01-01-01 | F01-01 | 时段校验 | 检查预约边界 | 非整点时拒绝 | P0 | 无 | |
| F01-01-02 | F01-01 | 冲突校验 | 检查时段相交 | 相交时拒绝 | P0 | 无 | |
''')
        primary = result['sheets'][0]
        self.assertEqual(primary['id'], 'feature-list')
        self.assertEqual(primary['kind'], 'feature-list')
        self.assertEqual(primary['title'], '预约工具')
        self.assertEqual(primary['columns'], ['大功能', '小功能', '细分功能', '功能介绍'])
        self.assertEqual(primary['hierarchyColumns'], 3)
        self.assertEqual(primary['rows'][0]['cells'][:3], ['F01 预约管理', '', ''])
        self.assertIn('管理预约闭环', primary['rows'][0]['cells'][3])
        self.assertIn('按规则串联操作通过', primary['rows'][0]['cells'][3])
        self.assertIn('需讨论边界', primary['rows'][0]['cells'][3])
        self.assertEqual(primary['rows'][1]['cells'][:3], ['F01 预约管理', 'F01-01 新建预约', 'F01-01-01 时段校验'])
        self.assertEqual(primary['rows'][2]['cells'][2], 'F01-01-02 冲突校验')
        self.assertIn({'row': 0, 'column': 0, 'rowSpan': 3}, primary['merges'])
        self.assertIn({'row': 1, 'column': 1, 'rowSpan': 2}, primary['merges'])
        self.assertTrue(all(r['parent'] is None and r['depth'] == 0 for r in primary['rows']))
        self.assertEqual(len(details(result)), 1)
        self.assertIn('非整点时拒绝', values(result))

    def test_reference_list_does_not_merge_same_names_from_different_parents(self):
        result = sheet.parse_plan_sheet('''## 功能规划
### 共同名称
#### 同名子功能
- 甲说明。
### 共同名称
#### 同名子功能
- 乙说明。
''')
        primary = result['sheets'][0]
        self.assertEqual([r['cells'][:2] for r in primary['rows']], [['共同名称', '同名子功能'], ['共同名称', '同名子功能']])
        self.assertEqual(primary['merges'], [])
        self.assertEqual(len({r['key'] for r in primary['rows']}), 2)

    def test_reference_list_extends_hierarchy_columns_without_losing_deep_leaves(self):
        result = sheet.parse_plan_sheet('''## 功能规划
| 编号 | 上级编号 | 功能名称 | 验收标准 |
|---|---|---|---|
| F01 | 无 | 根项 | |
| F01-01 | F01 | 子项 | |
| F01-01-01 | F01-01 | 三级项 | |
| F01-01-01-01 | F01-01-01 | 四级项 | |
| F01-01-01-01-01 | F01-01-01-01 | 五级叶项 | 所有边界可操作验证 |
''')
        primary = result['sheets'][0]
        self.assertEqual(primary['columns'], ['大功能', '小功能', '细分功能', '第4级功能', '第5级功能', '功能介绍'])
        self.assertEqual(primary['hierarchyColumns'], 5)
        self.assertEqual(len(primary['rows']), 1)
        self.assertIn('五级叶项', primary['rows'][0]['cells'][4])
        self.assertIn('所有边界可操作验证', primary['rows'][0]['cells'][5])

    def test_reference_list_excludes_scaffolding_and_keeps_original_detail_sheets(self):
        source = '''# 说明资料
## 功能规划
本节只是功能拆分方法，没有实际功能点。
```markdown
### F01：示例标题
```
| 外部资料 | 备注 |
|---|---|
| 此表不是功能清单 | 保留来源文字 |
'''
        result = sheet.parse_plan_sheet(source)
        self.assertFalse(any(tab.get('kind') == 'feature-list' for tab in result['sheets']))
        self.assertIn('示例标题', values(result))
        self.assertIn('保留来源文字', values(result))
        with_features = sheet.parse_plan_sheet(source + '\n### F02：实际功能\n- 可保存。\n')
        primary = with_features['sheets'][0]
        self.assertEqual(len(primary['rows']), 1)
        self.assertIn('实际功能', primary['rows'][0]['cells'][0])
        self.assertNotIn('示例标题', str(primary))
        self.assertIn('示例标题', values(with_features))

    def test_reference_list_optional_money_requires_explicit_recorded_field(self):
        source = '''## 功能规划
| 编号 | 功能名称 | 说明 | 大概金额 |
|---|---|---|---|
| F01 | 导出报告 | 覆盖1000条记录 | 待确认，无报价依据 |
| F02 | 查看报告 | 支持2个视图 | |
'''
        unknown = sheet.parse_plan_sheet(source)['sheets'][0]
        self.assertNotIn('大概金额', unknown['columns'])
        self.assertIn('待确认，无报价依据', unknown['rows'][0]['cells'][-1])
        recorded = sheet.parse_plan_sheet(source.replace('待确认，无报价依据', '1000元（待评审）'))['sheets'][0]
        self.assertEqual(recorded['columns'][-1], '大概金额')
        self.assertEqual([r['cells'][-1] for r in recorded['rows']], ['1000元（待评审）', ''])
        budget = sheet.parse_plan_sheet(source.replace('大概金额', '预算').replace('待确认，无报价依据', '0'))['sheets'][0]
        self.assertEqual(budget['rows'][0]['cells'][-1], '0')

    def test_reference_list_merges_contiguous_ancestors_but_never_blank_cells(self):
        result = sheet.parse_plan_sheet('''## 功能规划
### F01：账户
#### F01-01 注册
##### F01-01-01 填写资料
- 填写后可保存。
##### F01-01-02 校验资料
- 错误资料有提示。
#### F01-02 退出
- 退出后清除登录。
### F02：设置
- 可保存设置。
''')
        primary = result['sheets'][0]
        self.assertEqual(len(primary['rows']), 4)
        self.assertIn({'row': 0, 'column': 0, 'rowSpan': 3}, primary['merges'])
        self.assertIn({'row': 0, 'column': 1, 'rowSpan': 2}, primary['merges'])
        self.assertFalse(any(m['column'] == 2 for m in primary['merges']))
        for merge in primary['merges']:
            values_merged = [r['cells'][merge['column']] for r in primary['rows'][merge['row']:merge['row'] + merge['rowSpan']]]
            self.assertTrue(values_merged[0])
            self.assertEqual(len(set(values_merged)), 1)

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
        overview, features = details(result)
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
        features = details(result)[0]['rows']
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
        rows = details(result)[0]['rows']
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
        rows = details(result)[0]['rows']
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
        rows = details(result)[0]['rows']
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
        self.assertEqual(len(details(result)), 3)
        text = values(result)
        for expected in ['开头资料', '## 不能作为章节', '仅示例', '<script>alert(1)</script>', 'a|b', '保留附注', '多余单元格', r'C:\data\logs']:
            self.assertIn(expected, text)
        for tab in details(result):
            self.assertTrue(all(len(row['cells']) == len(tab['columns']) for row in tab['rows']))

    def test_empty_and_heading_only_documents_are_not_invented(self):
        self.assertEqual(sheet.parse_plan_sheet('')['sheets'], [])
        result = sheet.parse_plan_sheet('# 我的规划\n## 目标\n## 功能规划')
        self.assertEqual(result['title'], '我的规划')
        self.assertEqual([s['name'] for s in details(result)], ['目标', '功能规划'])
        self.assertTrue(all(not s['rows'] for s in details(result)))

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
        rows = details(result)[0]['rows']
        by_id = {r['cells'][0]: r for r in rows}
        self.assertEqual(by_id['F01-01']['cells'][1], '编号维护')
        self.assertIn('重复保存时拒绝', by_id['F01-01']['cells'][2])
        self.assertEqual(by_id['F01-02']['parent'], by_id['F01']['key'])
        self.assertIn('duplicate-id', values(result))
        self.assertIn('duplicate-parent', values(result))


if __name__ == '__main__':
    unittest.main()
