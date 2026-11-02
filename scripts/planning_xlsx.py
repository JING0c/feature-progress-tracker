"""Dependency-free Excel export for the product's read-only planning view.

All values are inline strings: model replies can never become spreadsheet
formulas, links, macros or external workbook references.
"""
from io import BytesIO
import math
import re
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def _tag(name):
    return '{' + NS + '}' + name


def _xml(root):
    # XML parsers normalize literal CR/CRLF; a character reference preserves the
    # exact Markdown line endings in the original-text worksheet.
    return ET.tostring(root, encoding='utf-8', xml_declaration=True).replace(b'\r', b'&#13;')


def _text(value):
    # SpreadsheetML's string escaping preserves XML-invalid control characters.
    # Escape a literal _xNNNN_ first, so user text cannot impersonate this encoding.
    value = re.sub(r'_x[0-9a-fA-F]{4}_', lambda m: '_x005F_' + m[0][1:], str(value))
    return ''.join('_x%04X_' % ord(c) if
                   (ord(c) < 32 and c not in '\t\n\r') or ord(c) in (0xfffe, 0xffff)
                   else c for c in value)


def _chunks(value):
    # Each Unicode character occupies at most two UTF-16 units in Excel.
    # Continuation rows preserve long cells instead of truncating at 32767 units.
    value = str(value)
    return [value[i:i + 16000] for i in range(0, len(value), 16000)] or ['']


def _column(index):
    result = ''
    while index:
        index, digit = divmod(index - 1, 26)
        result = chr(65 + digit) + result
    return result


def _sheet_name(value, used):
    text = re.sub(r'[\\/*?:\[\]\x00-\x1f]', ' ', str(value)).strip(" '") or '规划'
    text = text.encode('utf-16-le')[:62].decode('utf-16-le', errors='ignore')
    name, index = text, 2
    while name.casefold() in used:
        suffix = ' (' + str(index) + ')'
        budget = 62 - len(suffix.encode('utf-16-le'))
        name = text.encode('utf-16-le')[:budget].decode('utf-16-le', errors='ignore') + suffix
        index += 1
    used.add(name.casefold())
    return name


def _width(label, index):
    if label in ('编号', '行号', '优先级', '上级编号'):
        return 16 if label != '优先级' else 12
    if label in ('依赖', '备注'):
        return 30
    if label in ('功能名称', '规划事项'):
        return 34
    return 64 if index else 30


def _styles():
    root = ET.Element(_tag('styleSheet'))
    fonts = ET.SubElement(root, _tag('fonts'), count='3')
    for bold, size in ((False, 11), (True, 11), (True, 16)):
        font = ET.SubElement(fonts, _tag('font'))
        ET.SubElement(font, _tag('sz'), val=str(size))
        ET.SubElement(font, _tag('color'), rgb='FF382632')
        ET.SubElement(font, _tag('name'), val='Microsoft YaHei')
        if bold:
            ET.SubElement(font, _tag('b'))
    fills = ET.SubElement(root, _tag('fills'), count='5')
    for kind, color in [('none', None), ('gray125', None), ('solid', 'FFF8CAE4'),
                        ('solid', 'FFF2F5E8'), ('solid', 'FFFFF9FC')]:
        fill = ET.SubElement(fills, _tag('fill'))
        pattern = ET.SubElement(fill, _tag('patternFill'), patternType=kind)
        if color:
            ET.SubElement(pattern, _tag('fgColor'), rgb=color)
            ET.SubElement(pattern, _tag('bgColor'), indexed='64')
    borders = ET.SubElement(root, _tag('borders'), count='2')
    ET.SubElement(borders, _tag('border'))
    border = ET.SubElement(borders, _tag('border'))
    for edge in ('left', 'right', 'top', 'bottom'):
        ET.SubElement(ET.SubElement(border, _tag(edge), style='thin'), _tag('color'), rgb='FFECD7E1')
    ET.SubElement(border, _tag('diagonal'))
    base = ET.SubElement(root, _tag('cellStyleXfs'), count='1')
    ET.SubElement(base, _tag('xf'), numFmtId='0', fontId='0', fillId='0', borderId='0')
    xfs = ET.SubElement(root, _tag('cellXfs'), count='22')
    # 0 normal, 1 header, 2 section, 3 alternate; then normal/section indent 1..8.
    formats = [(0, 0, 0), (1, 2, 0), (1, 3, 0), (0, 4, 0)]
    formats += [(font, fill, depth) for depth in range(1, 9) for font, fill in ((0, 0), (1, 3))]
    for font, fill, indent in formats:
        xf = ET.SubElement(xfs, _tag('xf'), numFmtId='49', fontId=str(font), fillId=str(fill),
                           borderId='1', xfId='0', applyAlignment='1', applyNumberFormat='1')
        alignment = {'vertical': 'top', 'wrapText': '1'}
        if indent:
            alignment['indent'] = str(indent)
        ET.SubElement(xf, _tag('alignment'), **alignment)
    # 20 is the merged project title; 21 centers a shared parent name vertically.
    for font, fill, horizontal in ((2, 2, 'center'), (1, 3, 'left')):
        xf = ET.SubElement(xfs, _tag('xf'), numFmtId='49', fontId=str(font), fillId=str(fill),
                           borderId='1', xfId='0', applyAlignment='1', applyNumberFormat='1')
        ET.SubElement(xf, _tag('alignment'), vertical='center', horizontal=horizontal, wrapText='1')
    cell_styles = ET.SubElement(root, _tag('cellStyles'), count='1')
    ET.SubElement(cell_styles, _tag('cellStyle'), name='Normal', xfId='0', builtinId='0')
    return _xml(root)


def _worksheet(columns, rows, source=False, selected=False, feature_list=False, title='', merges=None):
    widths = [_width(label, i) for i, label in enumerate(columns)]
    if source:
        widths = [12, 120]
    elif feature_list:
        widths = [74 if label == '功能介绍' else 18 if label == '大概金额' else 30 for label in columns]
    header_row = 2 if feature_list else 1
    physical_rows, logical_ranges = [], []
    next_row = header_row + 1
    for entry in rows:
        values = list(entry.get('cells', []))
        values += [''] * (len(columns) - len(values))
        parts = [_chunks(value) for value in values]
        count = max([1] + [len(p) for p in parts])
        logical_ranges.append((next_row, next_row + count - 1, parts))
        for continuation in range(count):
            physical_rows.append((next_row, [p[continuation] if continuation < len(p) else '' for p in parts],
                                  0 if feature_list else int(entry.get('depth', 0)), entry.get('kind', 'item')))
            next_row += 1
    merge_refs, covered, anchors, occupied = [], set(), set(), set()
    if feature_list and len(columns) > 1:
        merge_refs.append('A1:' + _column(len(columns)) + '1')
    if feature_list:
        hierarchy_columns = columns.index('功能介绍') if '功能介绍' in columns else len(columns)
        for merge in merges or []:
            start, column, span = (merge.get(key) for key in ('row', 'column', 'rowSpan'))
            if (not all(isinstance(value, int) and not isinstance(value, bool) for value in (start, column, span))
                    or start < 0 or span < 2 or column < 0 or column >= hierarchy_columns or start + span > len(rows)):
                continue
            ranges = logical_ranges[start:start + span]
            values = [parts[column] for _, _, parts in ranges]
            # Never merge away distinct text or a continuation of a long parent
            # name. Long descriptions in other columns are safe to span over.
            if not values[0][0] or any(len(parts) > 1 or parts[0] not in ('', values[0][0]) for parts in values):
                continue
            first, last = ranges[0][0], ranges[-1][1]
            area = {(row, column) for row in range(first, last + 1)}
            if area & occupied:
                continue
            occupied.update(area)
            anchors.add((first, column))
            covered.update(area - {(first, column)})
            merge_refs.append(_column(column + 1) + str(first) + ':' + _column(column + 1) + str(last))
    root = ET.Element(_tag('worksheet'))
    properties = ET.SubElement(root, _tag('sheetPr'))
    ET.SubElement(properties, _tag('tabColor'), rgb='FF447A5F' if source else 'FFEA6993')
    ET.SubElement(properties, _tag('outlinePr'), summaryBelow='0', summaryRight='0')
    views = ET.SubElement(root, _tag('sheetViews'))
    view = ET.SubElement(views, _tag('sheetView'), workbookViewId='0', showGridLines='0',
                         tabSelected='1' if selected else '0')
    split = min(1, len(columns) - 1)
    pane = {'ySplit':str(header_row), 'topLeftCell':_column(split + 1) + str(header_row + 1), 'state':'frozen',
            'activePane':'bottomRight' if split else 'bottomLeft'}
    if split:
        pane['xSplit'] = str(split)
    ET.SubElement(view, _tag('pane'), **pane)
    ET.SubElement(root, _tag('sheetFormatPr'), defaultRowHeight='20', outlineLevelRow='7')
    cols = ET.SubElement(root, _tag('cols'))
    for number, width in enumerate(widths, 1):
        ET.SubElement(cols, _tag('col'), min=str(number), max=str(number), width=str(width), customWidth='1')
    data = ET.SubElement(root, _tag('sheetData'))

    def add_row(values, number, depth=0, kind='item', header=False, title_row=False):
        cells = [_text(value) for value in values]
        # Height is capped by Excel, but the entire cell value remains available.
        lines = max([1] + [sum(max(1, math.ceil(len(part) * 1.65 / max(widths[i] - depth * 2, 12)))
                              for part in str(value).split('\n')) for i, value in enumerate(values)
                           if (number, i) not in covered])
        height = max(30, lines * 16 + 12)
        if title_row:
            lines = sum(max(1, math.ceil(len(part) * 2.2 / max(sum(widths), 12))) for part in str(values[0]).split('\n'))
            height = max(40, lines * 24 + 12)
        row = ET.SubElement(data, _tag('row'), r=str(number), ht=str(min(409, height)),
                            customHeight='1', outlineLevel=str(min(7, max(0, depth))))
        for i, value in enumerate(cells):
            if (number, i) in covered:
                continue
            style = 1 if header else 2 if kind == 'section' else 3 if number % 2 else 0
            # Apply nesting to the name column, or the first column in generic views.
            name_column = 1 if '功能名称' in columns else 0
            if depth and i == name_column and not header:
                style = 4 + (min(8, depth) - 1) * 2 + (1 if kind == 'section' else 0)
            if (number, i) in anchors:
                style = 21
            if title_row:
                style = 20
            cell = ET.SubElement(row, _tag('c'), r=_column(i + 1) + str(number), s=str(style), t='inlineStr')
            ET.SubElement(ET.SubElement(cell, _tag('is')), _tag('t'), {XML_SPACE:'preserve'}).text = value

    if feature_list:
        title_parts = _chunks(title or '项目规划书')
        title_text = title_parts[0] + ('（完整标题见规划原文）' if len(title_parts) > 1 else '')
        add_row([title_text], 1, title_row=True)
    add_row(columns, header_row, header=True)
    for number, values, depth, kind in physical_rows:
        add_row(values, number, depth, kind)
    if merge_refs:
        merge_cells = ET.SubElement(root, _tag('mergeCells'), count=str(len(merge_refs)))
        for ref in merge_refs:
            ET.SubElement(merge_cells, _tag('mergeCell'), ref=ref)
    ET.SubElement(root, _tag('pageMargins'), left='0.3', right='0.3', top='0.5', bottom='0.5', header='0.2', footer='0.2')
    return _xml(root)


def export_plan_xlsx(model, markdown):
    """Return one Excel workbook; conversion never writes project state."""
    source_rows = [{'cells':[str(i), line], 'depth':0, 'kind':'item'}
                   for i, line in enumerate(str(markdown).splitlines(keepends=True), 1)]
    sheets = list(model.get('sheets', [])) + [{'name':'规划原文', 'columns':['行号','Markdown 原文'],
                                              'rows':source_rows, 'source':True}]
    names, used = [], set()
    for sheet in sheets:
        names.append(_sheet_name(sheet.get('name', '规划'), used))
    workbook = ET.Element(_tag('workbook'))
    views = ET.SubElement(workbook, _tag('bookViews'))
    active = next((i for i, sheet in enumerate(sheets) if sheet.get('kind') == 'feature-list'),
                  next((i for i, sheet in enumerate(sheets) if '功能名称' in sheet.get('columns', [])), 0))
    ET.SubElement(views, _tag('workbookView'), activeTab=str(active))
    listing = ET.SubElement(workbook, _tag('sheets'))
    relationships = ET.Element('Relationships', xmlns=PKG)
    content_types = ET.Element('Types', xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
    ET.SubElement(content_types, 'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(content_types, 'Default', Extension='xml', ContentType='application/xml')
    ET.SubElement(content_types, 'Override', PartName='/xl/workbook.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    ET.SubElement(content_types, 'Override', PartName='/xl/styles.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')
    root_rels = ET.Element('Relationships', xmlns=PKG)
    ET.SubElement(root_rels, 'Relationship', Id='rId1', Type=REL + '/officeDocument', Target='xl/workbook.xml')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for index, (sheet, name) in enumerate(zip(sheets, names), 1):
            ET.SubElement(listing, _tag('sheet'), name=name, sheetId=str(index), attrib={'{' + REL + '}id':'rId' + str(index)})
            ET.SubElement(relationships, 'Relationship', Id='rId' + str(index), Type=REL + '/worksheet', Target='worksheets/sheet' + str(index) + '.xml')
            ET.SubElement(content_types, 'Override', PartName='/xl/worksheets/sheet' + str(index) + '.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            archive.writestr('xl/worksheets/sheet' + str(index) + '.xml',
                             _worksheet(sheet['columns'], sheet.get('rows', []), sheet.get('source', False), index - 1 == active,
                                        sheet.get('kind') == 'feature-list', model.get('title', ''), sheet.get('merges', [])))
        ET.SubElement(relationships, 'Relationship', Id='rIdStyles', Type=REL + '/styles', Target='styles.xml')
        archive.writestr('xl/workbook.xml', _xml(workbook))
        archive.writestr('xl/_rels/workbook.xml.rels', _xml(relationships))
        archive.writestr('xl/styles.xml', _styles())
        archive.writestr('_rels/.rels', _xml(root_rels))
        archive.writestr('[Content_Types].xml', _xml(content_types))
    return output.getvalue()
