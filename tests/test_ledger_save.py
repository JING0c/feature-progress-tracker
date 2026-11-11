import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from test_projects import project_plan
from ledger_context_fixture import legacy_no_reference_context

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dashboard', ROOT / 'scripts/serve_dashboard.py')
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)
PLAN = '''# 测试台账
## 大功能 F01：图书
- [ ] F01-01 添加图书｜状态：未开始｜优先级：高｜依赖：无
  - **验收**：可以添加图书。
  - **执行 Agent**：待分配；**实现证据**：无
  - **审核 Agent**：待审核；**评分**：待审核；**问题**：编号规则待确认
  - [ ] F01-01-01 录入编号｜状态：未开始｜优先级：高｜依赖：无
    - **验收**：编号唯一。
    - **执行 Agent**：待分配；**实现证据**：无
    - **审核 Agent**：待审核；**评分**：待审核；**问题**：无
'''

class LedgerTest(unittest.TestCase):
    def test_bold_fields_and_nested_items(self):
        item = dashboard.parse(PLAN)[0]['items'][0]
        self.assertEqual(item['fields']['验收'], '可以添加图书。')
        self.assertEqual(item['fields']['问题'], '编号规则待确认')
        self.assertEqual(item['fields']['执行 Agent'], '待分配')
        self.assertEqual(item['children'][0]['fields']['验收'], '编号唯一。')

# 旧网页编排集成类已归档到 legacy_web/test_ledger_save.py。

if __name__ == '__main__': unittest.main()
