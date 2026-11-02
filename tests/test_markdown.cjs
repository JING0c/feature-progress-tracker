/* Run with `node tests/test_markdown.cjs`; no browser or package dependencies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(tagName = null, text = '') {
    this.tagName = tagName;
    this.nodeType = tagName ? 1 : 3;
    this.children = [];
    this.attributes = {};
    this.style = {};
    this._text = text;
  }
  append(...nodes) {
    this.children.push(...nodes.map(node => typeof node === 'string' ? new Node(null, node) : node));
  }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = []; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key]; }
  set textContent(value) { this.children = []; this._text = String(value); }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(''); }
  set innerHTML(value) { throw new Error('Untrusted Markdown must not be assigned to innerHTML'); }
  scrollIntoView() {}
}

function elements(root, tagName) {
  return root.children.flatMap(child => [
    ...(child.tagName === tagName ? [child] : []),
    ...elements(child, tagName),
  ]);
}

function createRenderer(source) {
  const container = new Node('ARTICLE');
  const section = new Node('SECTION');
  const document = {
    createElement: tag => new Node(tag.toUpperCase()),
    createTextNode: text => new Node(null, text),
    getElementById: id => id === 'plan-document' ? section : container,
  };
  const sandbox = { document, window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return text => {
    sandbox.window.renderPlanningMarkdown(container, text);
    return container;
  };
}

function runTests(source) {
  const render = createRenderer(source);
  let checks = 0;
  function test(name, check) { check(); checks += 1; console.log('PASS ' + name); }

  test('deep headings and tables from real planning output become semantic elements', () => {
    const article = render('# 项目规划\n## 功能\n### 借阅\n#### 2.1 借出\n##### 校验\n###### 边界\n\n| 子功能 | 验收 |\n|---|---|\n| 居民校验 | 不存在的编号不能借出 |\n| 额度校验 | 最多借 **3 本** |');
    assert.equal(elements(article, 'H4')[0]?.textContent, '2.1 借出');
    for (let level = 1; level <= 6; level++) assert.equal(elements(article, 'H' + level).length, 1);
    assert.equal(elements(article, 'TABLE').length, 1);
    assert.deepEqual(elements(article, 'TH').map(cell => cell.textContent), ['子功能', '验收']);
    assert.equal(elements(article, 'TBODY')[0].children.length, 2);
    assert.equal(elements(article, 'STRONG')[0]?.textContent, '3 本');
  });

  test('table alignment and pipes inside code or escapes remain in their cells', () => {
    const article = render('名称 | 表达式 | 备注\n:--- | :---: | ---:\nA\\|B | `a|b` | **完整**\nC | 空 |');
    assert.deepEqual(elements(article, 'TH').map(cell => cell.style.textAlign), ['left', 'center', 'right']);
    assert.deepEqual(elements(article, 'TD').map(cell => cell.textContent), ['A|B', 'a|b', '完整', 'C', '空', '']);
    assert.equal(elements(article, 'CODE')[0]?.textContent, 'a|b');
  });

  test('quotes and numbered lists keep structure and numbering', () => {
    const article = render('> 已确认范围\n>\n> - 本机使用\n> - 不联网\n\n3. 备份\n4. 恢复\n\n- 图书\n  - 实体书\n- 居民');
    const quote = elements(article, 'BLOCKQUOTE')[0];
    assert.ok(quote);
    assert.equal(elements(quote, 'LI').length, 2);
    assert.equal(elements(article, 'OL')[0]?.getAttribute('start'), '3');
    assert.ok(elements(article, 'LI').some(li => elements(li, 'UL').length === 1));
  });

  test('fenced code preserves Markdown and HTML literally', () => {
    const literal = '# not a heading\n| A | B |\n|---|---|\n<script>alert(1)</script>\n';
    const article = render('```html\n' + literal + '```\n\n#### Visible');
    assert.equal(elements(article, 'PRE')[0]?.textContent, literal);
    assert.equal(elements(article, 'H1').length, 0);
    assert.equal(elements(article, 'TABLE').length, 0);
    assert.equal(elements(article, 'SCRIPT').length, 0);
    assert.equal(elements(article, 'H4')[0]?.textContent, 'Visible');
  });

  test('long fences and tabs preserve code text without premature closure', () => {
    const article = render('````text\n\tindent\n```\n# literal\n````\n\n#### After');
    assert.equal(elements(article, 'PRE')[0]?.textContent, '\tindent\n```\n# literal\n');
    assert.equal(elements(article, 'H4')[0]?.textContent, 'After');
  });

  test('Markdown source cannot create active HTML, image requests, or links', () => {
    const text = '<img src=x onerror=alert(1)>\n\n[run](javascript:alert(1)) ![remote](https://example.com/image.png)\n\n**<script>alert(1)</script>**';
    const article = render(text);
    for (const tag of ['SCRIPT', 'IMG', 'A', 'IFRAME']) assert.equal(elements(article, tag).length, 0);
    assert.ok(article.textContent.includes('<img src=x onerror=alert(1)>'));
    assert.ok(article.textContent.includes('[run](javascript:alert(1))'));
    assert.equal(elements(article, 'STRONG')[0]?.textContent, '<script>alert(1)</script>');
  });

  test('ordinary pipe paragraphs stay text and re-render clears old content', () => {
    render('## Old');
    const article = render('A | B\nnot a table\n\n`**literal**` and **bold**');
    assert.equal(elements(article, 'H2').length, 0);
    assert.equal(elements(article, 'TABLE').length, 0);
    assert.ok(article.textContent.includes('A | B\nnot a table'));
    assert.equal(elements(article, 'CODE')[0]?.textContent, '**literal**');
    assert.equal(elements(article, 'STRONG')[0]?.textContent, 'bold');
  });

  return checks;
}

module.exports = { runTests, createRenderer, elements };
if (require.main === module) {
  runTests(fs.readFileSync(path.join(__dirname, '../scripts/planning-markdown.js'), 'utf8'));
}
