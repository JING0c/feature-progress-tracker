# Independent current ZIP retest

Reviewer: /root/retest_packages
Version: 0.2.0
Source HEAD: ef23caa41567a606d7ed19c9424815ec8c4e7c82
Result: PASS within tested package, protocol, workflow and local-upgrade scope. No unexpected product failures.
Scoped score: 94/100 (functionality 40/40, correctness 28/30, evidence 17/20, maintainability 9/10). Deductions: not every import/concurrency boundary covered (-2); real Claude host/model conversation unavailable (-3); limited package/entrypoint review, not whole-product maintainability audit (-1). This is not full real-host acceptance.

## Artifact SHA-256

- codex: `1a7c5dd7a71f64a8374574ecca26642cad15cbc4775b5fd8672ede7c5c9b1ac6`
- claude: `28f21f93e2d4ab34044799e4ea9ee55c6d90ddc9ac5cd9650c5538afe139ea78`
- marketplace: `a498d868566af20546543ad47b39e08ca0f6a96caf598baa138629b488e4adf0`

All three ZIPs are byte-identical to a fresh source rebuild. All 35 Codex / 33 Claude inventory hashes match. Marketplace package files match standalone ZIP files; runtime files match source.

## Actual tests

Both extracted .mcp.json entrypoints started in clean workspaces. All 18 distinct tools successfully invoked per host. Main run: 64 JSON-RPC responses (32 each), including 58 tool responses. Four expected tool rejections: stale plan revision and unknown schema field per host. No unexpected isError. Success progress ended at 100; rejection progress ended at 5 or 10. MCP exit status 0 and empty stderr.

Create project, save plan, add nested features F01 -> F01-02 -> F01-02-01, record suggestions, preview without plan mutation, save accepted preview, source binding, generate/save ledger, set pending-review status, history, current Excel and historical Markdown export all passed. Excel archive integrity, workbook structure, nested feature/acceptance text checked.

Both hosts performed real GitHub search repo:psf/requests, read repository metadata and README excerpt, then explicitly chose no references. Selected-reference clone/source verification was not exercised.

30 HTTP checks: 22 responses with 200, 8 expected write rejections with 410 host_conversation_required. Markdown hashes unchanged by reads and rejected HTTP writes. Extra browser fixture has one planned project (2 leaf features, 1 pending review) and one untouched pending-planning project (summary null).

## Local upgrade

CLI: codex-cli 0.167.0-alpha.3.2. 19 recorded CLI/build commands. Both independent CODEX_HOME routes upgraded 0.1.0 to 0.2.0: same directory replacement and changed directory re-registration. Cache files match current ZIP, installed MCPs expose 18 tools. Different-source conflict stops the command chain and retains old installation; corrected registration then succeeds. Global plugin configuration untouched.

## Retained viewer

URL: http://127.0.0.1:58961/projects
PID: 1045
Workspace: /private/tmp/fpt-dist-retest-et8xhc58/codex-workspace-k83ocokf
Planned project: p-9f07576ef557
Pending-planning project: p-1d328c86ebf1
Kept alive for parent browser review; stop only after parent notification.

## Evidence and limits

jsonrpc-transcript.jsonl: full requests and responses. stdio-final-evidence.json: main results. upgrade-evidence.json: upgrade commands and installed cache results. supplemental-evidence.json: further workbook/runtime/count checks. browser-fixture.json: retained viewer fixture.

shutil.which(claude) returned null. No real Claude CLI installation, upgrade, or host/model conversation was tested. Both ZIPs were exercised by directly starting their packaged stdio process. No selected-source clone and no browser visual QA by this reviewer. Browser QA delegated to parent. Repository remains clean at recorded HEAD. No product code, project ledger, or commits modified.

feature-progress-tracker skill read; parent owns serial ledger synchronization based on these independent evidence files.

## Viewer cleanup

After parent browser acceptance, packaged MCP stop_dashboard stopped the verified PID 1045 workspace at 2026-11-11T08:10:24.482034+00:00. Port 58961 now refuses TCP/HTTP connections (errno 61). See viewer-stop-evidence.json. No other service was targeted.
