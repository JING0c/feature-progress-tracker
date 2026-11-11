"""Integration checks for independent, disk-backed project state."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from ledger_context_fixture import legacy_no_reference_context

ROOT = Path(__file__).resolve().parents[1]


def project_plan(name='测试'):
    return f'''# {name} 项目规划书
## 目标
帮助管理员在本机管理图书借阅，避免重复借出。
## 范围
包括图书登记、借还记录和逾期名单；不做支付。
## 功能与验收
图书登记后按编号可查到；借出的图书不能重复借出。
'''


def ledger(name, state='进行中', checked=False):
    return f'''# 功能执行情况
## 大功能 F01：{name}
- [{'x' if checked else ' '}] F01-01 任务｜状态：{state}｜优先级：高｜依赖：无
  - 验收：可验证结果。
  - 执行 Agent：开发者；实现证据：记录
  - 审核 Agent：待审核；评分：待审核；问题：无新增待确认事项。
'''


# 旧网页编排集成类已归档到 legacy_web/test_projects.py。


if __name__ == '__main__': unittest.main()
