"""Planning goals must reach ledger files without changing feature history."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_operations import ledger_from_plan
from project_service import ProjectService
from serve_dashboard import parse


FEATURES = '''## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 采用 |
| --- | --- | --- | --- | --- | --- |
| F01 | 无 | 图书管理 | 管理图书清单 | 可保存并查看图书 | 是 |
| F01-01 | F01 | 添加图书 | 录入图书 | 保存后能读取新图书 | 是 |
'''


def plan(goal_section):
    return '# 图书规划\n' + goal_section + '\n## 范围\n仅在本地管理，不包含支付。\n' + FEATURES


class LedgerGoalSyncTests(unittest.TestCase):
    def convert(self, content, existing='# 功能执行情况\n\n目标：待规划\n'):
        return ledger_from_plan(content, existing, parse)['content']

    def test_new_goal_and_subsequent_change_reach_ledger(self):
        first = self.convert(plan('## 项目目标与场景\n帮助管理员记录个人藏书。'))
        self.assertIn('目标：帮助管理员记录个人藏书。\n', first)
        self.assertNotIn('目标：待规划', first)
        second = self.convert(plan('## 项目目标与场景\n帮助管理员记录藏书与借阅去向。'), first)
        self.assertIn('目标：帮助管理员记录藏书与借阅去向。\n', second)
        self.assertNotIn('目标：帮助管理员记录个人藏书。', second)
        self.assertEqual(parse(first), parse(second))
        self.assertEqual(self.convert(plan('## 项目目标与场景\n帮助管理员记录藏书与借阅去向。'), second), second)

    def test_goal_pipe_with_colon_is_not_duplicated_as_header_metadata(self):
        text = plan('## 目标\n支持 A | B：两个入口查询图书。')
        first = self.convert(text)
        second = self.convert(text, first)
        self.assertEqual(first, second)
        updated = self.convert(plan('## 目标\n支持多个入口查询藏书。'), second)
        goal = next(line for line in updated.splitlines() if line.startswith('目标：'))
        self.assertEqual(goal, '目标：支持多个入口查询藏书。')

    def test_goal_metadata_words_pipes_and_backslashes_roundtrip_as_literal_text(self):
        cases = [
            ('可筛选图书 | 状态：借出或归还。', r'可筛选图书 \| 状态：借出或归还。'),
            ('可筛选图书 ｜ 状态：借出或归还。', '可筛选图书 &#65372; 状态：借出或归还。'),
            (r'读取 C:\\books \\\| 状态：借出或归还。', r'读取 C:\\books \\\| 状态：借出或归还。'),
            (r'读取路径 \\\\\| 更新：保留文字。', r'读取路径 \\\\\| 更新：保留文字。'),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                content = plan('## 目标\n' + source)
                old = '# 功能执行情况\n目标：旧目标 | 更新：2026-01-01\n'
                first = self.convert(content, old)
                self.assertIn('目标：' + expected + ' | 更新：2026-01-01\n', first)
                self.assertEqual(self.convert(content, first), first)
                self.assertEqual(self.convert(content, self.convert(content, first)), first)
                changed = self.convert(plan('## 目标\n帮助读者查找全部藏书。'), first)
                goal = next(line for line in changed.splitlines() if line.startswith('目标：'))
                self.assertEqual(goal, '目标：帮助读者查找全部藏书。 | 更新：2026-01-01')

    def test_custom_header_metadata_fences_and_history_remain_intact(self):
        old = self.convert(plan('## 说明\n这里只说明范围。'),
                           '# 功能执行情况\n目标：旧的自定义目标 | 更新：2026-01-01\n')
        old = old.replace('# 功能执行情况\n', '# 自定义项目台账\n负责人：甲\n')
        old = old.replace('## 大功能 F01', '```md\n目标：示例目标不应更改\n```\n\n## 大功能 F01')
        old += '\n## 历史备注\n目标：历史决定不能更改\n'
        updated = self.convert(plan('## 目标\n帮助读者定位纸质书和电子书。'), old)
        self.assertIn('目标：帮助读者定位纸质书和电子书。 | 更新：2026-01-01', updated)
        self.assertIn('# 自定义项目台账\n负责人：甲\n', updated)
        self.assertIn('```md\n目标：示例目标不应更改\n```', updated)
        self.assertTrue(updated.endswith('\n## 历史备注\n目标：历史决定不能更改\n'))
        self.assertEqual(parse(old), parse(updated))

    def test_goal_formats_keep_only_goal_content(self):
        cases = [
            ('## 目标与需求来源\n让个人藏书有清晰可查的目录。', ('让个人藏书有清晰可查的目录。',)),
            ('## 目标\n- 记录个人图书。\n- 避免重复购买。', ('记录个人图书。', '避免重复购买。')),
            ('## 1. 项目目标\n### 主要目标\n更快找到藏书。\n### 辅助目标\n标记借出位置。',
             ('更快找到藏书。', '标记借出位置。')),
            ('## 概览\n**项目目标：** 帮助读者查找自己的图书。\n范围：不要把这段范围当目标。',
             ('帮助读者查找自己的图书。',)),
            ('## 概览\n| 项目目标 | 项目范围 |\n| --- | --- |\n| 保存并查找个人图书 | 不要把这段范围当目标 |',
             ('保存并查找个人图书',)),
            ('## 概览\n| 项目 | 内容 |\n| --- | --- |\n| 目标 | 保存并搜索藏书 |\n| 范围 | 不要把这段范围当目标 |',
             ('保存并搜索藏书',)),
            ('## 目标\n| 项目 | 内容 |\n| --- | --- |\n| 目标 | 保存并搜索藏书 |\n| 范围 | 不要把这段范围当目标 |',
             ('保存并搜索藏书',)),
        ]
        for section, expected in cases:
            with self.subTest(section=section):
                result = self.convert(plan(section))
                goal = next(line for line in result.splitlines() if line.startswith('目标：'))
                for phrase in expected:
                    self.assertIn(phrase, goal)
                self.assertNotIn('不要把这段范围当目标', goal)
                self.assertNotIn('保存后能读取新图书', goal)

    def test_feature_goals_and_scope_tables_do_not_become_project_goal(self):
        text = plan('## 目标\n帮助读者可靠地找到藏书。')
        text += '\n| 功能目标 | 说明 |\n| --- | --- |\n| 保存并查看图书 | 这不是项目目标 |\n'
        text += '\n## 非目标\n不负责纸质图书配送。\n'
        result = self.convert(text)
        goal = next(line for line in result.splitlines() if line.startswith('目标：'))
        self.assertEqual(goal, '目标：帮助读者可靠地找到藏书。')

    def test_missing_or_placeholder_goal_does_not_erase_existing_goal(self):
        for section in ('## 概览\n只是介绍此项目。', '## 目标\n待规划',
                        '## 说明\n```md\n## 目标\n不是真实目标。\n```'):
            with self.subTest(section=section):
                result = self.convert(plan(section), '# 功能执行情况\n目标：保留原有明确目标。\n')
                self.assertIn('目标：保留原有明确目标。\n', result)
        without_goal = self.convert(plan('## 说明\n不含目标。'), '# 功能执行情况\n负责人：甲\n')
        self.assertNotIn('\n目标：', without_goal)

    def test_goal_missing_from_ledger_is_inserted_without_promoting_prose_to_nodes(self):
        text = plan('## 目标\n支持 F01-99 这样的业务编号，目标文本不能变成功能。')
        result = self.convert(text, '# 功能执行情况\n负责人：甲\n')
        self.assertIn('目标：支持 F01-99 这样的业务编号，目标文本不能变成功能。', result)
        self.assertIn('负责人：甲\n', result)
        self.assertEqual([item['id'] for group in parse(result) for item in group['items']], ['F01-01'])

    def test_real_service_saves_new_goal_and_keeps_historical_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = ProjectService(tmp, actor='codex')
            project = service.call('create_project', {'name': '目标同步回归'})['project']
            def call(action, **data):
                return service.call(action, {'project_id': project['id'], **data})
            def save_goal(goal):
                doc = call('read_project')
                call('save_plan', content=plan('## 目标\n' + goal), revision=doc['plan']['revision'])
                candidate = call('generate_ledger')
                self.assertIn('目标：' + goal, candidate['content'])
                call('save_ledger', content=candidate['content'], revision=candidate['ledger_revision'],
                     plan_revision=candidate['plan_revision'], source_revision=candidate['source_revision'])
                return call('read_project')
            first = save_goal('帮助读者管理纸质藏书。')
            version = call('history')['versions'][0]['id']
            old_snapshot = call('history', version_id=version)['version']['content']
            second = save_goal('帮助读者同时管理纸质和电子藏书。')
            self.assertIn('目标：帮助读者同时管理纸质和电子藏书。', second['ledger']['content'])
            self.assertNotIn('目标：帮助读者管理纸质藏书。', second['ledger']['content'])
            self.assertEqual(parse(first['ledger']['content']), parse(second['ledger']['content']))
            self.assertEqual(call('history', version_id=version)['version']['content'], old_snapshot)


if __name__ == '__main__':
    unittest.main()
