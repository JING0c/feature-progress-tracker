#!/usr/bin/env python3
"""Verify local-marketplace upgrade routes without changing the real Codex home.

Run from the repository root:
  python3 -B docs/test-reports/host-chat-repairs/upgrade/verify_codex_upgrade.py \
    --output /tmp/codex-upgrade-evidence.json

Only plugin-management commands and the installed Python MCP process are run.
No model session, project operation, network marketplace, or global config is used.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path('/Users/olcgb/code/protuct_plan')
BASELINE = "f62f163d79abe92762c68b14291b28359d37a8c2"
PLUGIN = "feature-progress-tracker@jing0c-project-tools"
MARKET = "jing0c-project-tools"
VERSION = "0.2.0"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(output):
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("codex CLI is required; this check does not install it")
    evidence = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": BASELINE,
        "source_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_note": "Independent rerun: new package extracted from current dist/feature-progress-tracker-marketplace.zip, not rebuilt.",
        "expected_version": VERSION,
        "commands": [],
        "installed_cache_checks": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="codex-upgrade-check-") as directory:
            temporary = Path(directory)
            evidence["temporary_root"] = str(temporary)

            def run(label, argv, home=None, expected_exit=0):
                environment = dict(os.environ)
                home = home or temporary / "inspection-home"
                home.mkdir(exist_ok=True)
                environment["CODEX_HOME"] = str(home)
                process = subprocess.run(
                    argv, cwd=temporary, env=environment, capture_output=True,
                    text=True, timeout=60)
                evidence["commands"].append({
                    "label": label, "argv": [str(arg) for arg in argv],
                    "isolated_codex_home": str(home), "exit": process.returncode,
                    "stdout": process.stdout, "stderr": process.stderr,
                })
                if process.returncode != expected_exit:
                    raise AssertionError(f"{label}: exit {process.returncode}, expected {expected_exit}")
                return process

            def cli(label, args, home):
                return json.loads(run(label, [executable, "plugin", *args, "--json"], home).stdout)

            def check_installed(label, home, market, version):
                listed = cli(label, ["list"], home)
                matches = [item for item in listed["installed"] if item["pluginId"] == PLUGIN]
                if len(matches) != 1:
                    raise AssertionError(f"{label}: expected one installed plugin")
                installed = matches[0]
                if installed["version"] != version or installed["enabled"] is not True:
                    raise AssertionError(f"{label}: wrong version or disabled plugin")
                if Path(installed["marketplaceSource"]["source"]).resolve() != market.resolve():
                    raise AssertionError(f"{label}: marketplace still points to another directory")

            def check_cache(label, install, home, package):
                installed = Path(install["installedPath"]).resolve()
                if not installed.is_relative_to(home.resolve()):
                    raise AssertionError("Installed cache escaped isolated CODEX_HOME")
                if install["version"] != VERSION:
                    raise AssertionError("Install response did not select the new version")
                inventory = json.loads((package / "package-inventory.json").read_text())
                package_files = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
                installed_files = {str(p.relative_to(installed)) for p in installed.rglob("*") if p.is_file()}
                if installed_files != package_files:
                    raise AssertionError(f"Cache file-set differs: {installed_files ^ package_files}")
                if sha256(installed / "package-inventory.json") != sha256(package / "package-inventory.json"):
                    raise AssertionError("Cache inventory bytes differ")
                for relative, digest in inventory["files_sha256"].items():
                    if sha256(installed / relative) != digest:
                        raise AssertionError(f"Installed file differs from package: {relative}")
                requests = [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "upgrade-check", "version": "1"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                ]
                argv = [sys.executable, "-B", str(installed / "runtime/scripts/plugin_mcp.py"),
                        "--agent", "codex"]
                environment = dict(os.environ, CODEX_HOME=str(home))
                process = subprocess.run(
                    argv, cwd=temporary, env=environment,
                    input="".join(json.dumps(request) + "\n" for request in requests),
                    capture_output=True, text=True, timeout=30)
                responses = [json.loads(line) for line in process.stdout.splitlines()]
                by_id = {response["id"]: response for response in responses}
                tools = by_id[2]["result"]["tools"]
                names = [tool["name"] for tool in tools]
                evidence["installed_cache_checks"].append({
                    "route": label, "argv": argv, "exit": process.returncode,
                    "stderr": process.stderr, "requests": requests,
                    "initialize_response": by_id[1], "tool_count": len(tools),
                    "tool_names": names,
                    "stdout_sha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
                    "stdout_note": "tools/list schemas omitted; names and count retained.",
                    "verified_inventory_file_count": len(inventory["files_sha256"]),
                    "package_inventory_sha256": sha256(package / "package-inventory.json"),
                    "installed_mcp_sha256": sha256(installed / "runtime/scripts/plugin_mcp.py"),
                })
                if process.returncode or by_id[1]["result"]["serverInfo"]["version"] != VERSION:
                    raise AssertionError(f"{label}: installed MCP failed or reported wrong version")
                if len(names) != 18 or len(set(names)) != 18:
                    raise AssertionError(f"{label}: expected 18 distinct installed MCP tools")
                if not {"save_plan", "edit_features", "update_feature_progress"}.issubset(names):
                    raise AssertionError(f"{label}: host-conversation tools are missing")

            run("codex-version", [executable, "--version"])
            run("local-upgrade-command-scope", [executable, "plugin", "marketplace", "upgrade", "--help"])
            old_source = temporary / "old-source"
            old_source.mkdir()
            archived = subprocess.check_output(["git", "archive", "--format=zip", BASELINE], cwd=ROOT)
            with zipfile.ZipFile(io.BytesIO(archived)) as archive:
                archive.extractall(old_source)
            packages = {}
            for label, source in (("old", old_source),):
                built = json.loads(run(label + "-build", [
                    sys.executable, "-B", str(source / "scripts/build_plugins.py"),
                    "--output-dir", str(temporary / (label + "-build")),
                    "--dist-dir", str(temporary / (label + "-dist")),
                ]).stdout)
                packages[label] = temporary / (label + "-market")
                with zipfile.ZipFile(built["marketplace_archive"]) as archive:
                    archive.extractall(packages[label])

            actual_dist = ROOT / "dist/feature-progress-tracker-marketplace.zip"
            packages["new"] = temporary / "new-market"
            with zipfile.ZipFile(actual_dist) as archive:
                archive.extractall(packages["new"])
            evidence["new_marketplace_zip"] = str(actual_dist)
            evidence["new_marketplace_sha256"] = sha256(actual_dist)

            home = temporary / "changed-path-home"
            cli("changed-path-register-old", ["marketplace", "add", str(packages["old"])], home)
            cli("changed-path-install-old", ["add", PLUGIN], home)
            check_installed("changed-path-list-old", home, packages["old"], "0.1.0")
            cli("changed-path-locate-old", ["marketplace", "list"], home)
            chain = " && ".join((
                shlex.join([executable, "plugin", "marketplace", "add", str(packages["new"]), "--json"]),
                shlex.join([executable, "plugin", "add", PLUGIN, "--json"])))
            failed = run("changed-path-conflict-stops-chain", ["sh", "-c", chain], home, expected_exit=1)
            if "already added from a different source" not in failed.stderr or failed.stdout.strip():
                raise AssertionError("Expected source conflict with no subsequent install output")
            check_installed("changed-path-still-old-after-conflict", home, packages["old"], "0.1.0")
            cli("changed-path-remove-old-registration", ["marketplace", "remove", MARKET], home)
            cli("changed-path-register-new", ["marketplace", "add", str(packages["new"])], home)
            install = cli("changed-path-install-new", ["add", PLUGIN], home)
            check_installed("changed-path-list-new", home, packages["new"], VERSION)
            check_cache("changed-path", install, home, packages["new"] / "plugins/codex")

            same_path = temporary / "same-market"
            shutil.copytree(packages["old"], same_path)
            home = temporary / "same-path-home"
            cli("same-path-register-old", ["marketplace", "add", str(same_path)], home)
            cli("same-path-install-old", ["add", PLUGIN], home)
            check_installed("same-path-list-old", home, same_path, "0.1.0")
            cli("same-path-locate-old", ["marketplace", "list"], home)
            same_path.rename(temporary / "same-market-old-backup")
            shutil.copytree(packages["new"], same_path)
            install = cli("same-path-install-new", ["add", PLUGIN], home)
            check_installed("same-path-list-new", home, same_path, VERSION)
            check_cache("same-path", install, home, same_path / "plugins/codex")
            evidence["result"] = "pass"
            evidence["temporary_directories_removed_on_exit"] = True
    except Exception as error:
        evidence["result"] = "fail"
        evidence["error"] = str(error)
        raise
    finally:
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: both routes 0.1.0 -> 0.2.0; installed MCP caches expose 18 tools; conflict chain stops.")
    print("Evidence: " + str(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Write compact command evidence as JSON")
    args = parser.parse_args()
    verify(args.output.resolve())
