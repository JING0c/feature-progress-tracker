const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
 constructor() { this.children = []; this.handlers = {}; this.hidden = true; this.disabled = false; this.textContent = ''; }
 append(...nodes) { this.children.push(...nodes); }
 replaceChildren(...nodes) { this.children = nodes; }
 addEventListener(type, handler) { this.handlers[type] = handler; }
 scrollIntoView() {}
 focus() {}
 click() {}
 remove() {}
}

async function run() {
 const nodes = new Map(), pending = new Map(), downloads = [], markdown = [];
 const get = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
 let displayedModel, rejectExcel, rejectMarkdown;
 const sandbox = {
  window: {}, document: { getElementById: get, createElement: () => new Element(), body: new Element() },
  createPlanningSheetView: () => ({ show: model => { displayedModel = model; } }),
  renderPlanningMarkdown: (element, content) => { element.textContent = content; },
  Blob, URL: { createObjectURL: blob => { markdown.push(blob); return 'blob:history'; }, revokeObjectURL() {} }, setTimeout() {},
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../scripts/planning-history-view.js'), 'utf8'), sandbox);
 const controller = sandbox.window.createPlanningHistoryView({
  request: route => new Promise((resolve, reject) => pending.set(route.split('=')[1], { resolve, reject })),
  downloadExcel: (content, filename) => {
   downloads.push({ content, filename });
   return new Promise((resolve, reject) => { rejectExcel = reject; });
  },
  localOperation: (title, work) => new Promise((resolve, reject) => { rejectMarkdown = reject; work(); }),
 });
 const version = id => ({ id, saved_at: '2026-11-05T00:00:00Z', source: '用户保存', note: '', references: [], content: 'BODY ' + id, model: { id }, diff: id });

 const first = controller.show('first'), second = controller.show('second');
 pending.get('second').resolve(version('second')); await second;
 pending.get('first').resolve(version('first')); await first;
 assert.equal(get('history-document').textContent, 'BODY second', 'a late earlier request cannot replace the chosen snapshot');
 assert.equal(displayedModel.id, 'second');

 const exporting = get('history-download-excel').handlers.click();
 const next = controller.show('next'); pending.get('next').resolve(version('next')); await next;
 const currentStatus = get('history-status').textContent;
 rejectExcel(Error('old Excel request failed')); await exporting;
 assert.equal(downloads[0].content, 'BODY second', 'an in-flight export retains the snapshot selected when clicked');
 assert.equal(get('history-status').textContent, currentStatus, 'an old export failure cannot overwrite the next snapshot status');

 const failed = controller.show('missing'); pending.get('missing').reject(Error('not found')); await failed;
 assert.equal(get('history-detail').hidden, true);
 await get('history-download-excel').handlers.click(); await get('history-download-md').handlers.click();
 assert.equal(downloads.length, 1, 'failed reads must clear old Excel export content');
 assert.equal(markdown.length, 0, 'failed reads must clear old Markdown export content');

 const hidden = controller.show('hidden'); controller.hide();
 pending.get('hidden').resolve(version('hidden')); await hidden;
 assert.equal(get('plan-history').hidden, true, 'a response after returning to records cannot reopen the detail');
 assert.notEqual(get('history-document').textContent, 'BODY hidden');

 const oldMarkdown = controller.show('markdown-old'); pending.get('markdown-old').resolve(version('markdown-old')); await oldMarkdown;
 const exportingMarkdown = get('history-download-md').handlers.click();
 const latest = controller.show('latest'); pending.get('latest').resolve(version('latest')); await latest;
 const latestStatus = get('history-status').textContent;
 rejectMarkdown(Error('old Markdown operation failed')); await exportingMarkdown;
 assert.equal(await markdown[0].text(), 'BODY markdown-old');
 assert.equal(get('history-status').textContent, latestStatus, 'a late local operation failure cannot overwrite the latest snapshot status');
 console.log('History adversarial races: newest selection, immutable export selection, failed-read cleanup, back navigation and stale export errors passed.');
}

module.exports = run;
if (require.main === module) run().catch(error => { console.error(error); process.exitCode = 1; });
