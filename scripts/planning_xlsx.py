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
    fonts = ET.SubElement(root, _tag('fonts'), count='2')
    for bold in (False, True):
        font = ET.SubElement(fonts, _tag('font'))
        ET.SubElement(font, _tag('sz'), val='11')
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
    xfs = ET.SubElement(root, _tag('cellXfs'), count='20')
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
    cell_styles = ET.SubElement(root, _tag('cellStyles'), count='1')
    ET.SubElement(cell_styles, _tag('cellStyle'), name='Normal', xfId='0', builtinId='0')
    return _xml(root)


def _worksheet(columns, rows, source=False, selected=False):
    widths = [_width(label, i) for i, label in enumerate(columns)]
    if source:
        widths = [12, 120]
    root = ET.Element(_tag('worksheet'))
    properties = ET.SubElement(root, _tag('sheetPr'))
    ET.SubElement(properties, _tag('tabColor'), rgb='FF447A5F' if source else 'FFEA6993')
    ET.SubElement(properties, _tag('outlinePr'), summaryBelow='0', summaryRight='0')
    views = ET.SubElement(root, _tag('sheetViews'))
    view = ET.SubElement(views, _tag('sheetView'), workbookViewId='0', showGridLines='0',
                         tabSelected='1' if selected else '0')
    split = min(1, len(columns) - 1)
    pane = {'ySplit':'1', 'topLeftCell':_column(split + 1) + '2', 'state':'frozen',
            'activePane':'bottomRight' if split else 'bottomLeft'}
    if split:
        pane['xSplit'] = str(split)
    ET.SubElement(view, _tag('pane'), **pane)
    ET.SubElement(root, _tag('sheetFormatPr'), defaultRowHeight='20', outlineLevelRow='7')
    cols = ET.SubElement(root, _tag('cols'))
    for number, width in enumerate(widths, 1):
        ET.SubElement(cols, _tag('col'), min=str(number), max=str(number), width=str(width), customWidth='1')
    data = ET.SubElement(root, _tag('sheetData'))

    def add_row(values, number, depth=0, kind='item', header=False):
        cells = [_text(value) for value in values]
        # Height is capped by Excel, but the entire cell value remains available.
        lines = max([1] + [sum(max(1, math.ceil(len(part) * 1.65 / max(widths[i] - depth * 2, 12)))
                              for part in str(value).split('\n')) for i, value in enumerate(values)])
        row = ET.SubElement(data, _tag('row'), r=str(number), ht=str(min(409, max(30, lines * 16 + 12))),
                            customHeight='1', outlineLevel=str(min(7, max(0, depth))))
        for i, value in enumerate(cells):
            style = 1 if header else 2 if kind == 'section' else 3 if number % 2 else 0
            # Apply nesting to the name column, or the first column in generic views.
            name_column = 1 if '功能名称' in columns else 0
            if depth and i == name_column and not header:
                style = 4 + (min(8, depth) - 1) * 2 + (1 if kind == 'section' else 0)
            cell = ET.SubElement(row, _tag('c'), r=_column(i + 1) + str(number), s=str(style), t='inlineStr')
            ET.SubElement(ET.SubElement(cell, _tag('is')), _tag('t'), {XML_SPACE:'preserve'}).text = value

    add_row(columns, 1, header=True)
    number = 2
    for entry in rows:
        values = list(entry.get('cells', []))
        values += [''] * (len(columns) - len(values))
        parts = [_chunks(value) for value in values]
        for continuation in range(max([1] + [len(p) for p in parts])):
            add_row([p[continuation] if continuation < len(p) else '' for p in parts], number,
                    int(entry.get('depth', 0)), entry.get('kind', 'item'))
            number += 1
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
    active = next((i for i, sheet in enumerate(sheets) if '功能名称' in sheet.get('columns', [])), 0)
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
                             _worksheet(sheet['columns'], sheet.get('rows', []), sheet.get('source', False), index - 1 == active))
        ET.SubElement(relationships, 'Relationship', Id='rIdStyles', Type=REL + '/styles', Target='styles.xml')
        archive.writestr('xl/workbook.xml', _xml(workbook))
        archive.writestr('xl/_rels/workbook.xml.rels', _xml(relationships))
        archive.writestr('xl/styles.xml', _styles())
        archive.writestr('_rels/.rels', _xml(root_rels))
        archive.writestr('[Content_Types].xml', _xml(content_types))
    return output.getvalue()
