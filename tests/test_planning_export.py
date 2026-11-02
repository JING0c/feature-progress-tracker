"""Read-only planning tables and real Excel downloads preserve scope and text."""
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import unittest
import urllib.error
import urllib.request
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import test_projects as project_tests

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


xlsx = load('planning_xlsx')
dashboard = load('serve_dashboard')
NS = {'s': xlsx.NS, 'r': xlsx.PKG}
PLAN = '''# 预约工具项目规划书
## 项目目标与场景
为社区成员提供本机器材预约工具，管理员统一操作。
## 范围与边界
首期只做器材登记及预约，不接入支付和外部登录。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 优先级 | 依赖 | 备注 |
|---|---|---|---|---|---|---|---|
| F01 | 无 | 预约管理 | 管理同一器材的有效预约。 | 完成预约并能查看已保存记录。 | P0 | 无 | 未开始 |
| F01-01 | F01 | 冲突校验 | 对同一器材检查时间交集。 | 重叠预约不能提交，相邻时段可保存。 | P0 | F01-02 | 未审核 |
| F01-01-01 | F01-01 | 相邻时段 | 验证结束与开始时间相同。 | 前条结束等于后条开始时允许预约。 | P0 | 无 | 待分配 |
'''


class ExcelPackageTest(unittest.TestCase):
    def model(self, value='内容', depth=0):
        return {'title':'规划', 'sheets':[{'name':'功能规划', 'columns':['编号','功能名称','说明'],
                                         'rows':[{'key':'f1','parent':None,'depth':depth,
                                                  'kind':'section','cells':['F01','功能',value]}]}]}

    def test_real_package_freezes_and_groups_without_executable_cells(self):
        attack = '=HYPERLINK("https://example.com", "click")'
        result = xlsx.export_plan_xlsx(self.model(attack, 3), attack)
        with ZipFile(BytesIO(result)) as package:
            self.assertIsNone(package.testzip())
            self.assertIn('[Content_Types].xml', package.namelist())
            workbook = ET.fromstring(package.read('xl/workbook.xml'))
            self.assertEqual([s.attrib['name'] for s in workbook.findall('s:sheets/s:sheet', NS)], ['功能规划','规划原文'])
            sheet = ET.fromstring(package.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(sheet.find('s:sheetViews/s:sheetView/s:pane',NS).attrib['ySplit'],'1')
            self.assertEqual(sheet.find('s:sheetData/s:row[@r="2"]',NS).attrib['outlineLevel'],'3')
            self.assertTrue(all(cell.attrib['t']=='inlineStr' for cell in sheet.findall('.//s:c', NS)))
            self.assertIn(attack, [t.text for t in sheet.findall('.//s:t', NS)])
            for name in package.namelist():
                if name.endswith('.xml'):
                    root = ET.fromstring(package.read(name))
                    self.assertEqual(root.findall('.//s:f',NS), [])
                    self.assertEqual(root.findall('.//s:hyperlink',NS), [])
                self.assertNotIn('externalLinks',name)
                self.assertNotIn('vbaProject',name)

    def test_long_text_and_original_newlines_are_not_truncated(self):
        original = 'A' * 40000 + '\n第二行\r\n末行无换行'
        with ZipFile(BytesIO(xlsx.export_plan_xlsx(self.model(original), original))) as package:
            sheet = ET.fromstring(package.read('xl/worksheets/sheet1.xml'))
            values = [cell.find('s:is/s:t', NS).text or '' for cell in sheet.findall('.//s:row/s:c',NS)
                      if cell.attrib['r'].startswith('C') and cell.attrib['r']!='C1']
            self.assertEqual(''.join(values), original)
            raw = ET.fromstring(package.read('xl/worksheets/sheet2.xml'))
            parts = [cell.find('s:is/s:t',NS).text or '' for cell in raw.findall('.//s:row/s:c',NS)
                     if cell.attrib['r'].startswith('B') and cell.attrib['r']!='B1']
            self.assertEqual(''.join(parts), original)
            self.assertTrue(all(len(part)<=16000 for part in parts))

    def test_workbook_opens_the_first_feature_sheet(self):
        model = self.model()
        model['sheets'].insert(0, {'name':'项目概览','columns':['规划事项','内容'],'rows':[]})
        with ZipFile(BytesIO(xlsx.export_plan_xlsx(model, '规划'))) as package:
            workbook = ET.fromstring(package.read('xl/workbook.xml'))
            self.assertEqual(workbook.find('s:bookViews/s:workbookView',NS).attrib['activeTab'],'1')
            for number in range(1,4):
                sheet = ET.fromstring(package.read('xl/worksheets/sheet'+str(number)+'.xml'))
                selected = sheet.find('s:sheetViews/s:sheetView',NS).attrib['tabSelected']
                self.assertEqual(selected, '1' if number == 2 else '0')

    def test_invalid_and_duplicate_sheet_names_and_control_text(self):
        model = self.model('control\x00literal_x0001_')
        model['sheets'] *= 2
        for sheet in model['sheets']:
            sheet['name'] = "'Long/name:with?bad*chars[and]" + '文' * 30
        with ZipFile(BytesIO(xlsx.export_plan_xlsx(model,'raw\x01'))) as package:
            workbook = ET.fromstring(package.read('xl/workbook.xml'))
            names = [s.attrib['name'] for s in workbook.findall('s:sheets/s:sheet',NS)]
            self.assertEqual(len(names),len(set(n.casefold() for n in names)))
            self.assertTrue(all(len(n.encode('utf-16-le'))<=62 for n in names))
            self.assertFalse(any(c in name for name in names for c in '\\/*?:[]'))
            text = package.read('xl/worksheets/sheet1.xml').decode()
            self.assertIn('_x0000_',text)
            self.assertIn('_x005F_x0001_',text)

    def test_table_headers_or_placeholders_do_not_unlock_planning(self):
        self.assertTrue(dashboard.inspect_plan(PLAN)['valid'])
        header_only = '\n'.join(line for line in PLAN.splitlines() if not line.startswith('| F'))
        self.assertFalse(dashboard.inspect_plan(header_only)['valid'])
        placeholder = header_only + '\n| F01 | 无 | 用户身份与预约功能 | 待补充功能说明 | 待补充验收结果 | P0 | 无 | 待确认 |\n'
        self.assertFalse(dashboard.inspect_plan(placeholder)['valid'])
        missing_acceptance = PLAN.replace('完成预约并能查看已保存记录。','待补充').replace('重叠预约不能提交，相邻时段可保存。','待补充').replace('前条结束等于后条开始时允许预约。','待补充')
        self.assertIn('验收', dashboard.inspect_plan(missing_acceptance)['missing'])
        table_overview = '''# 规划
## 项目概览
| 信息项 | 内容 |
|---|---|
| 项目目标 | 让社区管理员可以管理器材预约。 |
| 范围边界 | 仅处理单机预约，不处理付费或登录。 |
'''+ PLAN[PLAN.index('## 功能规划'):]
        self.assertTrue(dashboard.inspect_plan(table_overview)['valid'])

    def test_inline_pipes_and_placeholder_acceptance_cannot_unlock(self):
        header_only = '\n'.join(line for line in PLAN.splitlines() if not line.startswith('| F'))
        for description in ('检查 `a|b以及所有其他条件` 是否通过',
                            r'检查 a\|b以及所有其他条件 是否通过',
                            '检查 a|b以及所有其他条件 是否通过'):
            for acceptance in ('待补充', '待确认具体验收标准'):
                with self.subTest(description=description, acceptance=acceptance):
                    content = header_only + '\n| F01 | 无 | 预约处理功能 | '+description+' | '+acceptance+' | P0 | 无 | 待确认 |\n'
                    self.assertIn('验收',dashboard.inspect_plan(content)['missing'])
        content = header_only + '\n| F01 | 无 | 预约处理功能 | 检查 `a|b以及所有其他条件` 是否通过 | 重复预约不能提交，其他边界待确认 | P0 | 无 | 待确认 |\n'
        self.assertTrue(dashboard.inspect_plan(content)['valid'])


class PlanningExportHttpTest(project_tests.ManagerTest):
    # Reuse only the server lifecycle, not inherited test cases.
    test_project_isolation_external_edits_and_restart = None
    test_unknown_scope_and_conflict_fail_closed = None
    test_existing_acceptance_survives_and_fabrication_is_rejected = None
    test_registry_and_cross_document_collisions_are_rejected = None
    test_unreadable_ledger_is_reported_and_missing_plan_can_be_saved = None

    def export(self, route, payload, headers=None):
        request = urllib.request.Request(self.url + route, data=json.dumps(payload).encode(),
                                          headers={'Content-Type':'application/json','X-Planning-Token':self.token, **(headers or {})})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_pending_draft_table_and_excel_are_read_only_and_project_scoped(self):
        a = self.request('/api/projects',{'name':'甲计划','directory':'a','mode':'new'})[1]['project']
        b = self.request('/api/projects',{'name':'乙计划','directory':'b','mode':'new'})[1]['project']
        watched = [self.workspace/'项目列表.md'] + [Path(p[key]) for p in (a,b) for key in ('plan_path','ledger_path')]
        before = {str(path):path.read_bytes() for path in watched}
        suffix = '?project=' + a['id']
        code, model = self.request('/api/plan/table'+suffix,{'content':PLAN})
        self.assertEqual(code,200,model)
        self.assertTrue(model['sheets'])
        self.assertIn('F01-01-01',json.dumps(model,ensure_ascii=False))
        code, headers, body = self.export('/api/plan/export'+suffix,{'content':PLAN})
        self.assertEqual(code,200,body)
        self.assertIn('spreadsheetml.sheet',headers['Content-Type'])
        self.assertIn('attachment;',headers['Content-Disposition'])
        self.assertIn('filename*=UTF-8',headers['Content-Disposition'])
        with ZipFile(BytesIO(body)) as package:
            self.assertIsNone(package.testzip())
        self.assertEqual(before,{str(path):path.read_bytes() for path in watched})
        self.assertFalse(self.request('/api/project'+suffix)[1]['planning']['ready'])
        self.assertFalse(self.request('/api/project?project='+b['id'])[1]['planning']['ready'])
        for path in ('/api/plan/table','/api/plan/export'):
            self.assertEqual(self.export(path,{'content':PLAN})[0],400)
            self.assertEqual(self.export(path+'?project=missing',{'content':PLAN})[0],404)
            self.assertEqual(self.export(path+suffix,{'content':PLAN},{'X-Planning-Token':'wrong'})[0],403)
            self.assertEqual(self.export(path+suffix,{'content':PLAN},{'Origin':'https://example.com'})[0],403)
            self.assertEqual(self.export(path+suffix,{'content':''})[0],400)
            self.assertEqual(self.export(path+suffix,{'content':123})[0],400)
            self.assertEqual(self.export(path+suffix,{'content':'x'}, {'Content-Length':'1000001'})[0],400)

    def test_generated_table_plan_saves_and_prompt_has_hierarchy_contract(self):
        project = self.request('/api/projects',{'name':'表格','directory':'table','mode':'new'})[1]['project']
        self.generate_plan(project, PLAN)
        prompt = self.fake_prompt.read_text()
        self.assertIn('编号|上级编号|功能名称|说明|验收标准|优先级|依赖|备注',prompt)
        self.assertIn('父行',prompt)
        suffix = '?project=' + project['id']
        revision = self.request('/api/plan'+suffix)[1]['revision']
        code, data = self.request('/api/plan/save'+suffix,{'content':PLAN,'revision':revision})
        self.assertEqual(code,200,data)
        self.assertTrue(data['planning']['ready'])


if __name__ == '__main__':
    unittest.main()
