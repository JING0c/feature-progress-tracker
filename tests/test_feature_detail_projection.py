"""Explicit feature fields remain distinct in the readonly page and Excel."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_sheet import parse_plan_sheet
from planning_xlsx import export_plan_xlsx, NS
from project_service import planning_model


PLAN = '''# 图书清单
## 目标
让用户保存并查看自己的阅读清单。
## 范围
只管理本地书目，不接入外部账号。
## 功能规划
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 采用 | 所需技术 | 前期准备 | 备注 | 外部依据 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | 无 | 图书管理 | 管理图书记录 | 能新增并找到记录 | 高 | 无 | 是 | 本地存储 | 准备测试书目 | 测试夹具 | 手工确认 |
| F01-01 | F01 | 添加图书 | 输入名称保存 | 拒绝空标题 | 高 | 无 | 否 | 浏览器表单 | 准备空标题用例 | 只在本机使用 | 需求讨论 |
'''


def feature_tabs(model):
    return [sheet for sheet in model['sheets']
            if sheet.get('kind') == 'feature-list' or '功能名称' in sheet['columns']]


def row_fields(sheet, index=0):
    return dict(zip(sheet['columns'], sheet['rows'][index]['cells']))


class FeatureDetailProjectionTests(unittest.TestCase):
    def test_explicit_fields_are_not_repeated_in_notes_or_introduction(self):
        # Before the fix the readonly model duplicates these field values in
        # both remarks/introduction and dedicated technology/preparation cells.
        for project in (parse_plan_sheet, planning_model):
            with self.subTest(project=project.__name__):
                for sheet in feature_tabs(project(PLAN)):
                    fields = row_fields(sheet)
                    self.assertEqual(fields['所需技术'], '本地存储')
                    self.assertEqual(fields['前期准备'], '准备测试书目')
                    self.assertIn('采用', fields)
                    self.assertEqual(fields['采用'], '是')
                    self.assertEqual(sheet['columns'].count('采用'), 1)
                    self.assertEqual(row_fields(sheet, 1)['采用'], '否')
                    prose = fields.get('功能介绍', fields.get('备注', ''))
                    self.assertNotIn('所需技术：', prose)
                    self.assertNotIn('前期准备：', prose)
                    self.assertNotIn('采用：', prose)
                    self.assertIn('测试夹具', prose)
                    self.assertIn('外部依据：手工确认', prose)

    def test_multiline_technology_is_preserved_as_one_field(self):
        content = PLAN.replace('本地存储', '本地存储<br>离线缓存').replace(
            '准备测试书目', '准备测试书目<br>准备重复书名')
        for sheet in feature_tabs(parse_plan_sheet(content)):
            fields = row_fields(sheet)
            self.assertEqual(fields['所需技术'], '本地存储\n离线缓存')
            self.assertEqual(fields['前期准备'], '准备测试书目\n准备重复书名')
            self.assertNotIn('离线缓存', fields.get('功能介绍', fields.get('备注', '')))

    def test_empty_adoption_defaults_to_yes_in_both_feature_views(self):
        content = PLAN.replace('| 是 | 本地存储 |', '|  | 本地存储 |')
        for project in (parse_plan_sheet, planning_model):
            with self.subTest(project=project.__name__):
                for sheet in feature_tabs(project(content)):
                    self.assertEqual(row_fields(sheet)['采用'], '是')
                    self.assertEqual(row_fields(sheet, 1)['采用'], '否')

    def test_user_written_notes_are_not_reclassified_or_removed(self):
        note = '所需技术：这里只是用户备注<br>前期准备：不要把这段当字段<br>采用：尚待讨论'
        content = PLAN.replace('测试夹具', note)
        for sheet in feature_tabs(parse_plan_sheet(content)):
            fields = row_fields(sheet)
            self.assertEqual(fields['所需技术'], '本地存储')
            self.assertEqual(fields['前期准备'], '准备测试书目')
            self.assertEqual(fields['采用'], '是')
            prose = fields.get('功能介绍', fields.get('备注', ''))
            for text in ('所需技术：这里只是用户备注', '前期准备：不要把这段当字段', '采用：尚待讨论'):
                self.assertIn(text, prose)

    def test_legacy_explicit_aliases_keep_multiline_values(self):
        content = PLAN.replace('所需技术', '技术方案').replace('前期准备', '准备条件')
        content = content.replace('本地存储', '本地存储<br>离线缓存')
        for project in (parse_plan_sheet, planning_model):
            with self.subTest(project=project.__name__):
                for sheet in feature_tabs(project(content)):
                    fields = row_fields(sheet)
                    self.assertEqual(fields['所需技术'], '本地存储\n离线缓存')
                    self.assertEqual(fields['前期准备'], '准备测试书目')
                    self.assertNotIn('技术方案：', fields.get('功能介绍', fields.get('备注', '')))

    def test_parent_with_only_structured_fields_is_not_discarded(self):
        content = '''## 功能规划
| 编号 | 上级编号 | 功能名称 | 所需技术 | 采用 |
|---|---|---|---|---|
| F01 | 无 | 图书管理 | 本地数据库 | 是 |
| F01-01 | F01 | 添加图书 | 表单 | 否 |
'''
        listing = parse_plan_sheet(content)['sheets'][0]
        self.assertEqual([r['feature_id'] for r in listing['rows']], ['F01', 'F01-01'])
        self.assertEqual(row_fields(listing)['所需技术'], '本地数据库')

    def test_excel_dedicated_columns_match_page_without_embedded_duplicates(self):
        model = planning_model(PLAN)
        with ZipFile(BytesIO(export_plan_xlsx(model, PLAN))) as package:
            for index, sheet in enumerate(model['sheets'], 1):
                if sheet not in feature_tabs(model):
                    continue
                xml = ET.fromstring(package.read(f'xl/worksheets/sheet{index}.xml'))
                cells = [cell.find('s:is/s:t', {'s': NS}).text or ''
                         for cell in xml.findall('.//s:c', {'s': NS})]
                self.assertIn('本地存储', cells)
                self.assertIn('准备测试书目', cells)
                self.assertIn('否', cells)
                self.assertFalse(any('备注：采用：' in text for text in cells))
                self.assertFalse(any('所需技术：本地存储' in text for text in cells))


if __name__ == '__main__':
    unittest.main()
