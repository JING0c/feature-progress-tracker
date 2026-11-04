/* A small, inert Markdown renderer for project plans. No HTML execution or automatic image requests; HTTP(S) links only. */
(function (global) {
  'use strict';

  function appendInline(parent, text, depth = 0) {
    if (depth > 8) { parent.append(document.createTextNode(text)); return; }
    let plain = '';
    const flush = () => {
      if (plain) parent.append(document.createTextNode(plain));
      plain = '';
    };
    for (let index = 0; index < text.length;) {
      if (text[index] === '\\' && /[\\`*_{}\[\]()#+.!|>~-]/.test(text[index + 1] || '')) {
        plain += text[index + 1]; index += 2; continue;
      }
      if (text[index] === '`') {
        const ticks = text.slice(index).match(/^`+/)[0];
        const end = text.indexOf(ticks, index + ticks.length);
        if (end !== -1) {
          flush();
          const code = document.createElement('code');
          code.textContent = text.slice(index + ticks.length, end);
          parent.append(code);
          index = end + ticks.length;
          continue;
        }
      }
      if(text[index]==='['&&text[index-1]!=='!'){
        const link=text.slice(index).match(/^\[([^\]\n]+)\]\((https?:\/\/[^\s<>]+?)\)/i);
        if(link){flush();const anchor=document.createElement('a');anchor.setAttribute('href',link[2]);anchor.setAttribute('target','_blank');anchor.setAttribute('rel','noopener noreferrer');anchor.textContent=link[1];parent.append(anchor);index+=link[0].length;continue;}
      }
      const marker = text.slice(index, index + 2);
      if (marker === '**' || marker === '__') {
        let end = text.indexOf(marker, index + 2);
        while (end !== -1 && text[end - 1] === '\\') end = text.indexOf(marker, end + 2);
        if (end > index + 2) {
          flush();
          const strong = document.createElement('strong');
          appendInline(strong, text.slice(index + 2, end), depth + 1);
          parent.append(strong);
          index = end + 2;
          continue;
        }
      }
      plain += text[index++];
    }
    flush();
  }

  // A pipe inside an inline code span or escaped with a backslash is cell text.
  function tableRow(line) {
    const cells = [];
    let cell = '', codeTicks = '', hasDelimiter = false;
    const text = line.trim();
    for (let index = 0; index < text.length;) {
      if (text[index] === '\\' && index + 1 < text.length) {
        cell += text.slice(index, index + 2); index += 2; continue;
      }
      if (text[index] === '`') {
        const ticks = text.slice(index).match(/^`+/)[0];
        if (!codeTicks) {
          // An unmatched backtick is ordinary text, not a span covering later pipes.
          if (text.indexOf(ticks, index + ticks.length) !== -1) codeTicks = ticks;
        } else if (codeTicks === ticks) codeTicks = '';
        cell += ticks; index += ticks.length; continue;
      }
      if (text[index] === '|' && !codeTicks) {
        cells.push(cell.trim()); cell = ''; hasDelimiter = true; index++; continue;
      }
      cell += text[index++];
    }
    cells.push(cell.trim());
    if (text.startsWith('|')) cells.shift();
    if (text.endsWith('|') && !/\\\|$/.test(text)) cells.pop();
    return { cells, hasDelimiter };
  }

  function tableStart(lines, index) {
    if (index + 1 >= lines.length) return null;
    const header = tableRow(lines[index]);
    const separator = tableRow(lines[index + 1]);
    if (!header.hasDelimiter || header.cells.length !== separator.cells.length ||
        !separator.cells.every(cell => /^:?-{3,}:?$/.test(cell))) return null;
    return { header: header.cells, align: separator.cells.map(cell =>
      cell.startsWith(':') && cell.endsWith(':') ? 'center' :
        cell.endsWith(':') ? 'right' : 'left') };
  }

  const heading = line => line.match(/^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$/);
  const fence = line => line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
  const quote = line => /^ {0,3}>/.test(line);
  const rule = line => /^ {0,3}(?:\*\s*){3,}$/.test(line) ||
    /^ {0,3}(?:-\s*){3,}$/.test(line) || /^ {0,3}(?:_\s*){3,}$/.test(line);

  function listItem(line) {
    const match = line.match(/^( *)([-+*]|\d+[.)])[ \t]+(.*)$/);
    if (!match) return null;
    return { indent: match[1].length, ordered: /^\d/.test(match[2]),
      start: parseInt(match[2], 10), text: match[3], contentIndent: line.length - match[3].length };
  }

  function renderBlocks(parent, lines, depth = 0) {
    if (depth > 30) {
      const paragraph = document.createElement('p');
      paragraph.textContent = lines.join('\n'); parent.append(paragraph); return;
    }
    let index = 0;
    while (index < lines.length) {
      if (!lines[index].trim()) { index++; continue; }
      const codeFence = fence(lines[index]);
      if (codeFence) {
        const codeLines = [], marker = codeFence[1];
        const closing = new RegExp('^ {0,3}' + marker[0] + '{' + marker.length + ',}\\s*$');
        index++;
        while (index < lines.length && !closing.test(lines[index])) codeLines.push(lines[index++]);
        if (index < lines.length) index++;
        const pre = document.createElement('pre'), code = document.createElement('code');
        code.textContent = codeLines.join('\n') + (codeLines.length ? '\n' : '');
        pre.append(code); parent.append(pre); continue;
      }
      const title = heading(lines[index]);
      if (title) {
        const node = document.createElement('h' + title[1].length);
        appendInline(node, title[2]); parent.append(node); index++; continue;
      }
      if (quote(lines[index])) {
        const quotedLines = [];
        while (index < lines.length && quote(lines[index])) {
          quotedLines.push(lines[index++].replace(/^ {0,3}> ?/, ''));
        }
        const blockquote = document.createElement('blockquote');
        renderBlocks(blockquote, quotedLines, depth + 1); parent.append(blockquote); continue;
      }
      const table = tableStart(lines, index);
      if (table) {
        const wrapper = document.createElement('div');
        wrapper.className = 'plan-table-scroll';
        wrapper.setAttribute('role', 'region'); wrapper.setAttribute('aria-label', '规划详情表');
        wrapper.setAttribute('tabindex', '0');
        const node = document.createElement('table'), head = document.createElement('thead');
        const headerRow = document.createElement('tr'), body = document.createElement('tbody');
        table.header.forEach((text, column) => {
          const cell = document.createElement('th'); cell.setAttribute('scope', 'col');
          cell.style.textAlign = table.align[column]; appendInline(cell, text); headerRow.append(cell);
        });
        head.append(headerRow); node.append(head, body); index += 2;
        while (index < lines.length && lines[index].trim() && tableRow(lines[index]).hasDelimiter) {
          const row = tableRow(lines[index++]).cells, tr = document.createElement('tr');
          // Keep extra cells instead of silently dropping model output.
          while (row.length < table.header.length) row.push('');
          row.forEach((text, column) => {
            const cell = document.createElement('td'); cell.style.textAlign = table.align[column] || 'left';
            appendInline(cell, text); tr.append(cell);
          });
          body.append(tr);
        }
        wrapper.append(node); parent.append(wrapper); continue;
      }
      if (rule(lines[index])) { parent.append(document.createElement('hr')); index++; continue; }
      const item = listItem(lines[index]);
      if (item) {
        const list = document.createElement(item.ordered ? 'ol' : 'ul');
        if (item.ordered && item.start !== 1) list.setAttribute('start', String(item.start));
        while (index < lines.length) {
          const current = listItem(lines[index]);
          if (!current || current.indent !== item.indent || current.ordered !== item.ordered) break;
          const li = document.createElement('li'); appendInline(li, current.text); index++;
          const nested = [];
          while (index < lines.length) {
            const line = lines[index], next = listItem(line);
            if (next && next.indent <= item.indent) break;
            if (line.trim() && line.match(/^ */)[0].length <= item.indent) break;
            nested.push(line.slice(Math.min(current.contentIndent, line.match(/^ */)[0].length)));
            index++;
          }
          if (nested.some(line => line.trim())) renderBlocks(li, nested, depth + 1);
          list.append(li);
        }
        parent.append(list); continue;
      }
      const paragraphLines = [lines[index++]];
      while (index < lines.length && lines[index].trim() && !heading(lines[index]) &&
             !fence(lines[index]) && !quote(lines[index]) && !listItem(lines[index]) &&
             !rule(lines[index]) && !tableStart(lines, index)) paragraphLines.push(lines[index++]);
      const paragraph = document.createElement('p');
      appendInline(paragraph, paragraphLines.join('\n')); parent.append(paragraph);
    }
  }

  global.renderPlanningInline=function(container,text){container.replaceChildren();appendInline(container,String(text||''));};
  global.renderPlanningMarkdown = function (container, markdown) {
    container.replaceChildren();
    renderBlocks(container, String(markdown || '').replace(/\r\n?/g, '\n').split('\n'));
  };
})(window);
