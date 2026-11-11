#!/usr/bin/env python3
"""Build self-contained Codex and Claude Code plugins using the standard library."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent
HOSTS = ("codex", "claude")
PLUGIN_NAME = "feature-progress-tracker"
BUILD_MARKER = ".feature-progress-tracker-build.json"
RUNTIME_EXTENSIONS = {".py", ".js", ".css", ".html"}
RETIRED_RUNTIME = {"planning_agent.py", "planning-assistant.js", "planning-suggestions.js",
                   "planning-workflow.js", "planning-workflow.css", "planning-progress.js"}
TEMPLATE_EXTENSIONS = {".json", ".md", ".yaml", ".yml", ".svg", ".png", ".jpg", ".webp", ".css"}
REQUIRED_RUNTIME = (
    "plugin_mcp.py", "plugin_manager.py", "serve_dashboard.py",
    "projects.html", "planning.html", "dashboard.html",
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checked_copy(source, target):
    if source.is_symlink() or not source.is_file():
        raise ValueError("插件只打包普通文件，不接受符号链接：" + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def copy_templates(source, target):
    if source.is_symlink() or not source.is_dir():
        raise ValueError("缺少插件模板目录：" + str(source))
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("插件模板不能包含符号链接：" + str(path))
        if not path.is_file():
            continue
        if path.suffix not in TEMPLATE_EXTENSIONS or path.name.startswith(".env"):
            raise ValueError("未批准的插件模板文件：" + str(path))
        checked_copy(path, target / path.relative_to(source))


def copy_runtime(source_root, target):
    source = source_root / "scripts"
    if source.is_symlink():
        raise ValueError("脚本目录不能是符号链接")
    for name in REQUIRED_RUNTIME:
        if not (source / name).is_file():
            raise ValueError("尚缺运行文件 scripts/" + name + "，请先完成运行入口再构建")
    for path in sorted(source.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            raise ValueError("运行文件不能包含符号链接：" + str(path))
        if not path.is_file() or path.suffix not in RUNTIME_EXTENSIONS:
            continue
        if path.name == "build_plugins.py" or path.name in RETIRED_RUNTIME:
            continue
        checked_copy(path, target / "scripts" / path.relative_to(source))
    checked_copy(source_root / "SKILL.md", target / "SKILL.md")
    for name in ("plugins.md", "项目文件说明.md"):
        checked_copy(source_root / "docs" / name, target / "docs" / name)


def validate_package(package, host):
    """Check our package contract; host installation is still a separate check."""
    manifest_path = package / (".codex-plugin" if host == "codex" else ".claude-plugin") / "plugin.json"
    manifest = read_json(manifest_path)
    if manifest.get("name") != PLUGIN_NAME:
        raise ValueError("插件名称不一致")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", manifest.get("version", "")):
        raise ValueError("插件版本须使用 x.y.z 格式")
    mcp = read_json(package / ".mcp.json")
    root_variable = "${PLUGIN_ROOT}" if host == "codex" else "${CLAUDE_PLUGIN_ROOT}"
    expected_server = {
        "type": "stdio", "command": "python3",
        "args": [root_variable + "/runtime/scripts/plugin_mcp.py", "--agent", host],
    }
    if mcp.get("mcpServers") != {PLUGIN_NAME: expected_server}:
        raise ValueError("MCP 启动入口或宿主不匹配：" + host)
    if host == "codex":
        portable = read_json(package / "plugin.json")
        if portable.get("name") != manifest["name"] or portable.get("version") != manifest["version"]:
            raise ValueError("Codex 兼容清单与 portable 清单版本不同")
        if portable.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
            raise ValueError("缺少 portable 插件 schema")
        if any(key in portable for key in ("skills", "mcpServers", "apps", "interface")):
            raise ValueError("portable 清单包含了不支持的顶层组件字段")
        interface = portable["extensions"]["com.openai"]["interface"]
        if interface != manifest.get("interface") or len(interface.get("shortDescription", "")) > 30:
            raise ValueError("Codex 展示信息不一致或副标题过长")
        portable_mcp = read_json(package / "mcp.json")
        if portable_mcp.get("mcpServers") != mcp["mcpServers"]:
            raise ValueError("Codex MCP 配置不一致")
        if portable_mcp.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json":
            raise ValueError("缺少 portable MCP schema")
    skill = package / "skills" / "project-manager" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\nname: project-manager\ndescription: "):
        raise ValueError("插件技能缺少名称和使用描述")
    for name in REQUIRED_RUNTIME:
        if not (package / "runtime" / "scripts" / name).is_file():
            raise ValueError("插件不是自包含包：缺少 " + name)
    for relative in ("runtime/SKILL.md", "runtime/docs/plugins.md", "runtime/docs/项目文件说明.md", "skills/project-manager/references/workflow.md"):
        if not (package / relative).is_file():
            raise ValueError("缺少技能参考：" + relative)
    return manifest["version"]


def write_package_inventory(package, host, version):
    files = {}
    for path in sorted(package.rglob("*")):
        if path.is_file():
            files[path.relative_to(package).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(package / "package-inventory.json", {
        "name": PLUGIN_NAME, "version": version, "host": host,
        "files_sha256": files,
    })


def write_archive(package, destination):
    """Use stable timestamps and file order so unchanged sources yield identical ZIPs."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_symlink():
                    raise ValueError("归档不接受符号链接")
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(package).as_posix(), (2020, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (0o100644 << 16)
                    archive.writestr(info, path.read_bytes())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_plugins(source_root=ROOT, output_dir=None, dist_dir=None):
    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir or source_root / "build" / "plugin-marketplace").absolute()
    dist_dir = Path(dist_dir or source_root / "dist").absolute()
    if dist_dir.resolve().is_relative_to(output_dir.resolve()):
        raise ValueError("ZIP 输出目录必须在市场构建目录之外，避免将归档打包进自身")
    if any(output_dir.resolve().is_relative_to(source_root / name) for name in ("scripts", "plugins")):
        raise ValueError("市场构建目录不能放进 scripts 或 plugins 源码目录中")
    if output_dir.is_symlink():
        raise ValueError("构建输出目录不能是符号链接")
    if output_dir.exists():
        marker = output_dir / BUILD_MARKER
        if not output_dir.is_dir() or not marker.is_file() or read_json(marker).get("builder") != PLUGIN_NAME:
            raise ValueError("输出目录已有非构建内容，请选择新的空路径：" + str(output_dir))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".plugin-build-", dir=output_dir.parent))
    try:
        versions = {}
        for host in HOSTS:
            package = staging / "plugins" / host
            copy_templates(source_root / "plugins" / host, package)
            copy_runtime(source_root, package / "runtime")
            checked_copy(source_root / "plugins" / "common" / "workflow.md",
                         package / "skills" / "project-manager" / "references" / "workflow.md")
            versions[host] = validate_package(package, host)
            write_package_inventory(package, host, versions[host])
        if len(set(versions.values())) != 1:
            raise ValueError("两种宿主的插件版本需要保持一致")
        codex_market = read_json(source_root / ".agents" / "plugins" / "marketplace.json")
        codex_market["plugins"][0]["source"]["path"] = "./plugins/codex"
        write_json(staging / ".agents" / "plugins" / "marketplace.json", codex_market)
        claude_market = read_json(source_root / ".claude-plugin" / "marketplace.json")
        claude_market["plugins"][0]["source"] = "./plugins/claude"
        write_json(staging / ".claude-plugin" / "marketplace.json", claude_market)
        write_json(staging / BUILD_MARKER, {"builder": PLUGIN_NAME, "versions": versions})
        if output_dir.exists():
            shutil.rmtree(output_dir)
        os.replace(staging, output_dir)
        artifacts = {}
        for host in HOSTS:
            archive_path = dist_dir / (PLUGIN_NAME + "-" + host + ".zip")
            write_archive(output_dir / "plugins" / host, archive_path)
            artifacts[host] = {
                "version": versions[host], "directory": str(output_dir / "plugins" / host),
                "archive": str(archive_path),
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            }
        marketplace_archive = dist_dir / (PLUGIN_NAME + "-marketplace.zip")
        write_archive(output_dir, marketplace_archive)
        return {"marketplace": str(output_dir), "marketplace_archive": str(marketplace_archive),
                "marketplace_sha256": hashlib.sha256(marketplace_archive.read_bytes()).hexdigest(),
                "plugins": artifacts}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description="构建自包含的 Codex 与 Claude Code 项目管理器插件")
    parser.add_argument("--output-dir", type=Path, help="市场构建目录（默认 build/plugin-marketplace）")
    parser.add_argument("--dist-dir", type=Path, help="ZIP 输出目录（默认 dist）")
    args = parser.parse_args()
    try:
        result = build_plugins(output_dir=args.output_dir, dist_dir=args.dist_dir)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, "构建失败：" + str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
