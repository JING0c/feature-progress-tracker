(function (global) {
  'use strict';

  // The same read-only model is used by the webpage and the Excel exporter.
  global.createPlanningSheetView = function (container, options = {}) {
    let model = { sheets: [] }, active = '', collapsed = new Set(), adoptionEnabled=true, adoptionControls=[],changedIds=new Set(),onlyChanged=false;
    const el = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const message = text => {
      container.replaceChildren(el('p', 'sheet-message', text));
    };

    function render() {
      container.replaceChildren();adoptionControls=[];
      const sheets = Array.isArray(model.sheets) ? model.sheets : [];
      const sheet = sheets.find(item => item.id === active) || sheets.find(item => item.kind === 'feature-list') || sheets.find(item => item.columns.includes('功能名称')) || sheets[0];
      if (!sheet) { message('还没有规划内容，请先通过对话梳理项目。'); return; }
      active = sheet.id;
      const allRows = sheet.rows || [], columns = sheet.columns || [];
      const featureSheet=sheet.kind!=='feature-list'&&columns.includes('功能名称');
      const identity=row=>row.feature_id||row.cells[columns.indexOf('编号')];
      const rows=onlyChanged&&featureSheet?allRows.filter(row=>changedIds.has(identity(row))):allRows;
      const listing = sheet.kind === 'feature-list';
      const byKey = new Map(rows.map(row => [row.key, row]));
      const parents = new Set(rows.map(row => row.parent).filter(key => byKey.has(key)));
      const toolbar = el('div', 'sheet-toolbar');
      const info = el('span', 'sheet-count');
      toolbar.append(info);
      if(changedIds.size&&featureSheet){
        const preview=el('span','sheet-preview-notice','本次建议预览 · '+changedIds.size+' 个功能已修改 · 尚未保存');
        preview.setAttribute('role','status');toolbar.append(preview);
        const toggle=el('button','sheet-action',onlyChanged?'显示全部功能':'只看本次修改');toggle.type='button';
        toggle.addEventListener('click',()=>{onlyChanged=!onlyChanged;collapsed.clear();render();});toolbar.append(toggle);
      }
      const expand = el('button', 'sheet-action', '全部展开');
      const fold = el('button', 'sheet-action', '收起层级');
      for (const button of [expand, fold]) { button.type = 'button'; button.disabled = !parents.size; }
      if (listing) {
        const details = sheets.find(item => item.kind !== 'feature-list' && item.columns.includes('功能名称'));
        if (details) {
          const open = el('button', 'sheet-action', '查看功能明细'); open.type = 'button';
          open.addEventListener('click', () => { active = details.id; render(); }); toolbar.append(open);
        }
      } else toolbar.append(expand, fold);

      const scroll = el('div', 'sheet-scroll');
      scroll.setAttribute('tabindex', '0');
      scroll.setAttribute('role', 'region');
      scroll.setAttribute('aria-label', sheet.name + '表格，可横向滚动');
      const table = el('table', 'planning-grid' + (listing ? ' feature-list-grid' : ''));
      const caption = el('caption', 'sheet-caption', sheet.name);
      table.append(caption);
      const widths = columns.map(label => label === '采用' ? 78 : label === '所需技术' ? 230 : label === '前期准备' ? 280 : label === '大功能' ? 190 : label === '小功能' ? 200 :
        label === '细分功能' || /^第\d+级功能$/.test(label) ? 230 : label === '功能介绍' ? 400 :
        label === '大概金额' ? 160 : label === '编号' ? 108 : label === '功能名称' ? 230 :
        label === '说明与验收' ? 430 : label === '优先级' ? 90 : label === '依赖' ? 150 :
        label === '备注' ? 230 : columns.length === 2 ? (label === columns[0] ? 240 : 720) : 250);
      const colgroup = el('colgroup');
      [44, ...widths].forEach(width => { const col = el('col'); col.style.width = width + 'px'; colgroup.append(col); });
      table.append(colgroup); table.style.width = (44 + widths.reduce((sum, width) => sum + width, 0)) + 'px';
      const head = el('thead'), header = el('tr');
      const corner = el('th', 'sheet-index', '#');
      corner.setAttribute('scope', 'col'); header.append(corner);
      columns.forEach((label, index) => {
        const cell = el('th', index === 0 ? 'sheet-first' : '', label);
        cell.setAttribute('scope', 'col'); header.append(cell);
      });
      head.append(header); table.append(head);
      const body = el('tbody'), controls = [], rendered = [];
      const hierarchyColumn = columns.indexOf('功能名称') >= 0 ? columns.indexOf('功能名称') : 0;
      const mergeStarts = new Map(), covered = new Set();
      if (listing) for (const merge of sheet.merges || []) {
        const { row, column, rowSpan } = merge;
        if (!Number.isInteger(row) || !Number.isInteger(column) || !Number.isInteger(rowSpan) ||
            row < 0 || column < 0 || column >= columns.length || rowSpan < 2 || row + rowSpan > rows.length) continue;
        mergeStarts.set(row + ':' + column, rowSpan);
        for (let index = row + 1; index < row + rowSpan; index++) covered.add(index + ':' + column);
      }
      rows.forEach((row, index) => {
        const tr = el('tr', parents.has(row.key) ? 'sheet-parent' : 'sheet-leaf');
        tr.setAttribute('data-row-key', row.key);
        if(featureSheet&&changedIds.has(identity(row))){tr.className+=' sheet-changed';tr.setAttribute('aria-label','本次修改 '+identity(row));}
        const number = el('th', 'sheet-index', String(index + 1));
        number.setAttribute('scope', 'row'); tr.append(number);
        columns.forEach((_, column) => {
          if (covered.has(index + ':' + column)) return;
          const cell = el('td', column === 0 ? 'sheet-first' : '');
          const value = String((row.cells || [])[column] ?? '');
          if (listing && columns[column] === '采用') {
            const box=el('input','adoption-checkbox');box.type='checkbox';box.checked=value!=='否';box.setAttribute('aria-label','采用 '+(row.feature_id||row.key));
            adoptionControls.push(box);box.disabled=!options.onAdopt||!adoptionEnabled;box.addEventListener('change',()=>options.onAdopt(row.feature_id,box.checked));cell.className+=' adoption-cell';cell.append(box);
          } else if (listing) {
            const span = mergeStarts.get(index + ':' + column);
            if (span) { cell.setAttribute('rowspan', String(span)); cell.className += ' sheet-merged'; }
            if (column < columns.indexOf('功能介绍')) cell.className += ' sheet-level-cell';
            cell.textContent = value || '—';
          } else if (column === hierarchyColumn) {
            const content = el('div', 'sheet-hierarchy');
            content.style.paddingLeft = Math.min(Math.max(row.depth || 0, 0), 12) * 18 + 'px';
            if (parents.has(row.key)) {
              const button = el('button', 'sheet-toggle'); button.type = 'button';
              const label = [row.cells[0], column ? value : ''].filter(Boolean).join(' ');
              button.addEventListener('click', () => {
                if (collapsed.has(row.key)) collapsed.delete(row.key); else collapsed.add(row.key);
                update();
              });
              controls.push({ button, row, label }); content.append(button);
            } else content.append(el('span', 'sheet-indent', '·'));
            content.append(el('span', 'sheet-cell-text', value || '—')); cell.append(content);
          } else cell.textContent = value || '—';
          tr.append(cell);
        });
        body.append(tr); rendered.push({ tr, row });
      });
      table.append(body); scroll.append(table);

      function update() {
        let visible = 0;
        for (const { tr, row } of rendered) {
          const visited = new Set([row.key]);
          let parent = row.parent, hidden = false;
          while (byKey.has(parent) && !visited.has(parent)) {
            visited.add(parent);
            if (collapsed.has(parent)) { hidden = true; break; }
            parent = byKey.get(parent).parent;
          }
          tr.hidden = hidden; if (!hidden) visible++;
        }
        for (const { button, row, label } of controls) {
          const open = !collapsed.has(row.key);
          button.textContent = open ? '▾' : '▸';
          button.setAttribute('aria-expanded', String(open));
          button.setAttribute('aria-label', (open ? '收起 ' : '展开 ') + label);
        }
        info.textContent = listing ? sheet.name + ' · 按列查看包含关系 · ' + rows.length + ' 行' :
          sheet.name + ' · 显示 ' + visible + ' / ' + allRows.length + ' 行';
      }
      expand.addEventListener('click', () => { parents.forEach(key => collapsed.delete(key)); update(); });
      fold.addEventListener('click', () => { parents.forEach(key => collapsed.add(key)); update(); });
      const tabs = el('nav', 'sheet-tabs'); tabs.setAttribute('aria-label', '规划章节');
      sheets.forEach(item => {
        const button = el('button', 'sheet-tab', item.name); button.type = 'button';
        button.setAttribute('aria-pressed', String(item.id === active));
        button.addEventListener('click', () => { active = item.id; render(); }); tabs.append(button);
      });
      container.append(toolbar, scroll, tabs);
      update();
    }
    return {
      finishPreview(){if(changedIds.size){changedIds.clear();onlyChanged=false;render();}},
      setAdoptionEnabled(value){adoptionEnabled=value;adoptionControls.forEach(box=>box.disabled=!value||!options.onAdopt);},
      show(value, display = {}) {
        model = value || { sheets: [] };changedIds=new Set(display.changedIds||[]);onlyChanged=changedIds.size>0;
        if(onlyChanged){active=(model.sheets.find(s=>s.kind!=='feature-list'&&s.columns.includes('功能名称'))||{}).id||'';collapsed.clear();}
        render();
      },
      loading() { message('正在整理规划表格…'); },
      error() { message('表格暂时无法加载，可切换到文档视图查看完整内容。'); },
      clear() { model = { sheets: [] }; active = ''; changedIds.clear();onlyChanged=false;collapsed.clear(); container.replaceChildren(); }
    };
  };
})(window);
