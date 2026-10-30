from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent

def paragraph(doc, text, style=None):
    p = doc.add_paragraph(style=style)
    p.add_run(text.replace('**', '').replace('`', ''))
    return p

def build(path):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Inches(.7)
    sec.left_margin = sec.right_margin = Inches(.75)
    sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.08
    for name, size in [('Title', 25), ('Heading 1', 15), ('Heading 2', 12)]:
        st = doc.styles[name]
        st.font.name = 'Calibri'
        st.font.size = Pt(size)
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.paragraph_format.space_before = Pt(12)
        st.paragraph_format.space_after = Pt(6)
    code = doc.styles.add_style('Code Block', 1)
    code.font.name = 'Consolas'
    code.font.size = Pt(8)
    code.paragraph_format.space_after = Pt(1)
    code.paragraph_format.line_spacing = 1
    lines = path.read_text(encoding='utf-8').splitlines()
    i = 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            in_code = not in_code
        elif in_code:
            paragraph(doc, line, 'Code Block')
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[: -]+', c) for c in cells):
                    rows.append(cells)
                i += 1
            i -= 1
            table = doc.add_table(rows=1, cols=len(rows[0]))
            table.autofit = False
            width = 6.77 / len(rows[0])
            for col in table.columns:
                col.width = Inches(width)
            for j, values in enumerate(rows):
                cells = table.rows[0].cells if j == 0 else table.add_row().cells
                for cell, value in zip(cells, values):
                    cell.text = value
                    tcpr = cell._tc.get_or_add_tcPr()
                    borders = OxmlElement('w:tcBorders')
                    for side in ['top', 'left', 'bottom', 'right']:
                        edge = OxmlElement('w:' + side)
                        edge.set(qn('w:val'), 'single')
                        edge.set(qn('w:sz'), '4')
                        edge.set(qn('w:color'), 'D9D9D9')
                        borders.append(edge)
                    tcpr.append(borders)
                    margins = OxmlElement('w:tcMar')
                    for side in ['top', 'left', 'bottom', 'right']:
                        el = OxmlElement('w:' + side)
                        el.set(qn('w:w'), '85')
                        el.set(qn('w:type'), 'dxa')
                        margins.append(el)
                    tcpr.append(margins)
                    if j == 0:
                        shade = OxmlElement('w:shd')
                        shade.set(qn('w:fill'), 'DCE6F1')
                        tcpr.append(shade)
                    for p in cell.paragraphs:
                        p.paragraph_format.space_after = Pt(4)
                        for run in p.runs:
                            run.font.size = Pt(9)
                            run.bold = j == 0
                if j == 0:
                    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            doc.add_paragraph()
        elif line.startswith('# '):
            paragraph(doc, line[2:], 'Title')
        elif line.startswith('## '):
            paragraph(doc, line[3:], 'Heading 1')
        elif line.startswith('### '):
            paragraph(doc, line[4:], 'Heading 2')
        elif line.startswith('- '):
            paragraph(doc, line[2:], 'List Bullet')
        elif line.strip():
            paragraph(doc, line)
        i += 1
    doc.core_properties.title = lines[0][2:]
    doc.core_properties.subject = 'DevFest 2026 Carbon Coach implementation specification'
    doc.core_properties.author = 'Carbon Coach Team'
    target = path.with_suffix('.docx')
    doc.save(target)
    check = Document(target)
    assert check.paragraphs and check.core_properties.title
    print(f'{target.name}: {len(check.paragraphs)} paragraphs, {len(check.tables)} tables')

for source in sorted(ROOT.glob('Carbon_Coach_*.md')):
    build(source)
