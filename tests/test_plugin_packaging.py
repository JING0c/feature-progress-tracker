"""Distribution tests: extracted plugins must not depend on the source checkout."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_plugins", ROOT / "scripts" / "build_plugins.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class PluginPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="plugin package tests ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.source.mkdir()
        shutil.copytree(ROOT / "plugins", self.source / "plugins")
        for relative in (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"):
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        (self.source / "scripts").mkdir()
        for name in builder.REQUIRED_RUNTIME:
            (self.source / "scripts" / name).write_text("# fixture for " + name + "\n", encoding="utf-8")
        (self.source / "scripts" / "planning.js").write_text("// runtime asset\n", encoding="utf-8")
        (self.source / "SKILL.md").write_text("# 工作流程规范\n", encoding="utf-8")
        (self.source / "docs").mkdir()
        (self.source / "docs/plugins.md").write_text("# 插件安装说明\n", encoding="utf-8")

    def build(self):
        return builder.build_plugins(self.source)

    def test_extracted_packages_have_all_runtime_files_and_host_specific_entrypoints(self):
        result = self.build()
        for host in builder.HOSTS:
            with self.subTest(host=host):
                archive_path = Path(result["plugins"][host]["archive"])
                with zipfile.ZipFile(archive_path) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn("runtime/scripts/plugin_mcp.py", archive.namelist())
                    self.assertIn("runtime/scripts/planning.js", archive.namelist())
                    self.assertNotIn(".agents/plugins/marketplace.json", archive.namelist())
                    self.assertNotIn(".claude-plugin/marketplace.json", archive.namelist())
                    self.assertTrue(all(not name.startswith("/") and ".." not in Path(name).parts
                                        for name in archive.namelist()))
                    package = self.base / ("isolated " + host)
                    archive.extractall(package)
                self.assertEqual(builder.validate_package(package, host), "0.1.0")
                mcp = json.loads((package / ".mcp.json").read_text())
                server = mcp["mcpServers"][builder.PLUGIN_NAME]
                variable = "${PLUGIN_ROOT}" if host == "codex" else "${CLAUDE_PLUGIN_ROOT}"
                entrypoint = Path(server["args"][0].replace(variable, str(package)))
                self.assertTrue(entrypoint.is_file())
                self.assertEqual(server["args"][1:], ["--agent", host])
                self.assertNotIn(str(self.source), json.dumps(mcp))
                skill = package / "skills/project-manager/SKILL.md"
                self.assertTrue((skill.parent / "references/workflow.md").is_file())
                self.assertTrue((skill.parent / "../../runtime/SKILL.md").resolve().is_file())
                self.assertTrue((package / "runtime/docs/plugins.md").is_file())

    def test_marketplace_sources_resolve_to_complete_plugins(self):
        result = self.build()
        market = Path(result["marketplace"])
        for root in (self.source, market):
            codex = json.loads((root / ".agents/plugins/marketplace.json").read_text())
            claude = json.loads((root / ".claude-plugin/marketplace.json").read_text())
            self.assertEqual(codex["name"], claude["name"])
            builder.validate_package(root / codex["plugins"][0]["source"]["path"], "codex")
            builder.validate_package(root / claude["plugins"][0]["source"], "claude")

    def test_marketplace_archive_can_be_installed_without_source_checkout(self):
        result = self.build()
        extracted = self.base / "independent marketplace"
        with zipfile.ZipFile(result["marketplace_archive"]) as archive:
            self.assertIsNone(archive.testzip())
            archive.extractall(extracted)
        codex = json.loads((extracted / ".agents/plugins/marketplace.json").read_text())
        claude = json.loads((extracted / ".claude-plugin/marketplace.json").read_text())
        builder.validate_package(extracted / codex["plugins"][0]["source"]["path"], "codex")
        builder.validate_package(extracted / claude["plugins"][0]["source"], "claude")
        self.assertTrue((extracted / "plugins/codex/runtime/docs/plugins.md").is_file())

    def test_build_is_reproducible_and_inventory_matches_contents(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        for host in builder.HOSTS:
            package = Path(second["plugins"][host]["directory"])
            inventory = json.loads((package / "package-inventory.json").read_text())
            for relative, expected in inventory["files_sha256"].items():
                self.assertEqual(hashlib.sha256((package / relative).read_bytes()).hexdigest(), expected)

    def test_does_not_copy_project_data_secrets_or_python_cache(self):
        for name in (".env", "secret.key", "项目规划书.md", "功能执行情况.md"):
            (self.source / name).write_text("DO NOT DISTRIBUTE", encoding="utf-8")
            (self.source / "scripts" / name).write_text("DO NOT DISTRIBUTE", encoding="utf-8")
        cache = self.source / "scripts/__pycache__"
        cache.mkdir()
        (cache / "cached.py").write_text("DO NOT DISTRIBUTE")
        result = self.build()
        with zipfile.ZipFile(result["plugins"]["codex"]["archive"]) as archive:
            self.assertFalse(any(b"DO NOT DISTRIBUTE" in archive.read(name) for name in archive.namelist()))

    def test_rejects_linked_source_and_does_not_replace_existing_build_on_failure(self):
        result = self.build()
        existing = Path(result["plugins"]["codex"]["directory"]) / "package-inventory.json"
        original = existing.read_bytes()
        (self.source / "scripts/linked.py").symlink_to(self.source / "SKILL.md")
        with self.assertRaisesRegex(ValueError, "符号链接"):
            self.build()
        self.assertEqual(existing.read_bytes(), original)

    def test_refuses_to_replace_unrelated_directory(self):
        destination = self.base / "my files"
        destination.mkdir()
        (destination / "important.md").write_text("keep me")
        with self.assertRaisesRegex(ValueError, "非构建内容"):
            builder.build_plugins(self.source, output_dir=destination)
        self.assertEqual((destination / "important.md").read_text(), "keep me")

    def test_missing_runtime_fails_before_publishing_archive(self):
        (self.source / "scripts/plugin_mcp.py").unlink()
        with self.assertRaisesRegex(ValueError, "plugin_mcp.py"):
            self.build()
        self.assertFalse((self.source / "dist").exists())

    def test_rejects_archive_directory_inside_the_directory_being_archived(self):
        with self.assertRaisesRegex(ValueError, "归档打包进自身"):
            builder.build_plugins(self.source, output_dir=self.base / "market", dist_dir=self.base / "market/zips")


class ShippedRuntimeTests(unittest.TestCase):
    def test_both_extracted_plugins_serve_mcp_and_open_their_own_dashboard(self):
        with tempfile.TemporaryDirectory(prefix="shipped plugin check ") as temporary:
            base = Path(temporary)
            built = builder.build_plugins(ROOT, output_dir=base / "market", dist_dir=base / "archives")
            for host in builder.HOSTS:
                with self.subTest(host=host):
                    package = base / ("extracted " + host)
                    with zipfile.ZipFile(built["plugins"][host]["archive"]) as archive:
                        archive.extractall(package)
                    workspace = base / ("项目数据 " + host)
                    project = workspace / "示例项目"
                    project.mkdir(parents=True)
                    plan = "# 项目规划书\n\n## 目标\n管理日常任务。\n\n## 范围\n仅本机使用。\n\n## 功能与验收\n任务保存后能查看。\n"
                    (project / "项目规划书.md").write_text(plan, encoding="utf-8")
                    (project / "功能执行情况.md").write_text("# 功能执行情况\n\n## 大功能 F01：任务\n- [ ] F01-01 新建任务｜状态：未开始\n", encoding="utf-8")
                    (workspace / "项目列表.md").write_text("# 项目列表\n\n## p-package-test\n名称：分发验证\n目录：示例项目\n规划书：项目规划书.md\n台账：功能执行情况.md\n", encoding="utf-8")
                    mcp = json.loads((package / ".mcp.json").read_text())["mcpServers"][builder.PLUGIN_NAME]
                    variable = "${PLUGIN_ROOT}" if host == "codex" else "${CLAUDE_PLUGIN_ROOT}"
                    command = [mcp["command"]] + [arg.replace(variable, str(package)) for arg in mcp["args"]]
                    requests = [
                        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "package-check", "version": "1"}}},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"},
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_projects", "arguments": {"workspace": str(workspace)}}},
                        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_project", "arguments": {"workspace": str(workspace), "project_id": "p-package-test"}}},
                        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "open_dashboard", "arguments": {"workspace": str(workspace), "port": 0}}},
                    ]
                    process = subprocess.run(command, input="\n".join(json.dumps(r) for r in requests) + "\n",
                                             text=True, capture_output=True, timeout=30, cwd=base,
                                             env=dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1"))
                    output = {row["id"]: row for row in map(json.loads, process.stdout.splitlines())}
                    server = output.get(5, {}).get("result", {}).get("structuredContent", {})
                    try:
                        self.assertEqual(process.returncode, 0, process.stderr)
                        self.assertEqual([t["name"] for t in output[2]["result"]["tools"]],
                                         ["open_dashboard", "list_projects", "read_project"])
                        self.assertEqual(output[3]["result"]["structuredContent"]["projects"][0]["id"], "p-package-test")
                        self.assertEqual(output[4]["result"]["structuredContent"]["plan"]["content"], plan)
                        self.assertEqual(server["agent"], host)
                        with urllib.request.urlopen(server["url"], timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn("项目管理", response.read().decode("utf-8"))
                        stopped = subprocess.run([mcp["command"], str(package / "runtime/scripts/plugin_manager.py"),
                                                  "stop", "--workspace", str(workspace), "--agent", host],
                                                 text=True, capture_output=True, timeout=10, cwd=base)
                        self.assertEqual(stopped.returncode, 0, stopped.stderr)
                        self.assertTrue(json.loads(stopped.stdout)["stopped"])
                        server.pop("pid", None)
                    finally:
                        if server.get("pid"):
                            try:
                                os.kill(server["pid"], signal.SIGTERM)
                            except ProcessLookupError:
                                pass


if __name__ == "__main__":
    unittest.main()
