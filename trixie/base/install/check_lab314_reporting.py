"""Generate and verify sample PDF and HTML reports using the selected lab314 Python."""
from importlib.metadata import version
import os
from pathlib import Path
import tempfile

TITLE = 'Scientific Reporting'
SUMMARY = 'Executive Summary'
MEASUREMENTS = 'Measurements'
UNICODE = 'Hämeenlinna, lämpötila, Åbo, blåbär, Örebro'
CHART_TITLE = 'Sample measurements'
ROW_COUNT = 96


def make_charts(root):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(6, 2.6), layout='constrained')
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    axes.plot([1, 2, 3, 4], [16, 20, 18, 22], marker='o')
    axes.set(title=CHART_TITLE, xlabel='Sample', ylabel='Temperature (°C)')
    axes.grid(alpha=0.25)
    figure.savefig(root/'chart.png', dpi=150)
    figure.savefig(root/'chart.pdf')


def make_pdf(root):
    from matplotlib import get_data_path
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer

    class Report(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name == 'Heading1':
                heading = flowable.getPlainText()
                self.canv.bookmarkPage(heading)
                self.canv.addOutlineEntry(heading, heading)

    def page_details(canvas, document):
        canvas.saveState()
        canvas.setFont('DejaVuSans', 9)
        canvas.setFillColor(colors.HexColor('#34435a'))
        canvas.drawString(48, A4[1] - 33, 'lab314 reporting acceptance')
        canvas.drawRightString(A4[0] - 48, 31, f'Page {document.page}')
        canvas.restoreState()

    fonts = Path(get_data_path())/'fonts/ttf'
    pdfmetrics.registerFont(TTFont('DejaVuSans', str(fonts/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', str(fonts/'DejaVuSans-Bold.ttf')))
    styles = getSampleStyleSheet()
    for name in ('Normal', 'Title', 'Heading1'):
        styles[name].fontName = 'DejaVuSans' if name == 'Normal' else 'DejaVuSans-Bold'
    styles['Normal'].spaceAfter = 8
    rows = [['Sample ID', 'Station', 'Temperature (°C)']]
    stations = ['Hämeenlinna', 'Åbo', 'Örebro']
    rows.extend([f'Sample {i:03}', stations[(i-1) % len(stations)], f'{16 + (i % 13)/2:.1f}']
                for i in range(1, ROW_COUNT + 1))
    table = LongTable(rows, colWidths=[100, 200, 170], repeatRows=1, style=[
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbe6f2')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f5f9')]),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ])
    report = Report(str(root/'report.pdf'), pagesize=A4, title=TITLE,
                    leftMargin=48, rightMargin=48, topMargin=53, bottomMargin=51)
    report.build([
        Paragraph(TITLE, styles['Title']),
        Paragraph(SUMMARY, styles['Heading1']),
        Paragraph('This report summarizes a synthetic temperature measurement series.', styles['Normal']),
        Paragraph(UNICODE, styles['Normal']),
        Image(str(root/'chart.png'), width=432, height=187.2),
        Spacer(1, 12),
        Paragraph(MEASUREMENTS, styles['Heading1']),
        table,
    ], onFirstPage=page_details, onLaterPages=page_details)


def verify_pdf(root):
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4

    report = PdfReader(root/'report.pdf')
    pages = [page.extract_text() for page in report.pages]
    assert len(pages) > 1 and report.metadata.title == TITLE, 'Multipage PDF and title'
    assert TITLE in pages[0] and SUMMARY in pages[0] and UNICODE in pages[0], 'Report text and Unicode'
    assert len(report.pages[0].images) > 0, 'Embedded Matplotlib chart'
    assert sum('Sample ID' in page for page in pages) > 1, 'Repeated multipage table header'
    text = '\n'.join(pages)
    assert all(f'Sample {i:03}' in text for i in range(1, ROW_COUNT + 1)), 'Complete table'
    for number, (page, content) in enumerate(zip(report.pages, pages), 1):
        size = (page.mediabox.width, page.mediabox.height)
        assert all(abs(float(actual) - expected) < 0.01 for actual, expected in zip(size, A4)), 'A4 page'
        assert f'Page {number}' in content and 'lab314 reporting acceptance' in content, 'Page furniture'
    assert [bookmark.title for bookmark in report.outline] == [SUMMARY, MEASUREMENTS], 'PDF bookmarks'
    assert all(report.get_destination_page_number(bookmark) >= 0 for bookmark in report.outline), 'Bookmark targets'

    chart = PdfReader(root/'chart.pdf')
    assert len(chart.pages) == 1 and CHART_TITLE in chart.pages[0].extract_text(), 'Standalone chart PDF'
    operators = {operator for _, operator in chart.pages[0].get_contents().operations}
    assert not chart.pages[0].images and {b'l', b'S'} <= operators, 'Chart vector paths'
    with PdfWriter() as merged:
        merged.append(report)
        merged.append(chart)
        merged.write(root/'merged.pdf')
    combined = PdfReader(root/'merged.pdf')
    assert len(combined.pages) == len(pages) + 1, 'Merged page count'
    assert UNICODE in combined.pages[0].extract_text(), 'Merged report text'
    assert CHART_TITLE in combined.pages[-1].extract_text(), 'Merged chart text'
    assert [bookmark.title for bookmark in combined.outline] == [SUMMARY, MEASUREMENTS], 'Merged bookmarks'
    print(f'PASS PDF reporting (A4, {len(pages)} pages, table, Unicode, bookmarks, charts and merge)')


def html_report(root):
    from html.parser import HTMLParser
    from jinja2 import Environment
    from plotly import graph_objects as go

    class LocalHTML(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            assert not {'src', 'href'} & attributes.keys(), f'Unexpected asset reference in {tag}'

    chart = go.Figure(go.Scatter(x=[1, 2, 3, 4], y=[16, 20, 18, 22], mode='lines+markers'))
    chart.update_layout(title=CHART_TITLE, xaxis_title='Sample', yaxis_title='Temperature (°C)')
    template = Environment(autoescape=True).from_string("""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{{ title }}</title></head>
<body><h1>{{ title }}</h1><h2>{{ summary }}</h2><p>{{ text }}</p>
{{ chart | safe }}
</body>
</html>
""")
    path = root/'report.html'
    path.write_text(template.render(title=TITLE, summary=SUMMARY, text=UNICODE,
                                   chart=chart.to_html(full_html=False, include_plotlyjs=True,
                                                       div_id='measurements')), encoding='utf-8')
    html = path.read_text(encoding='utf-8')
    LocalHTML().feed(html)
    assert f'<h2>{SUMMARY}</h2>' in html and UNICODE in html, 'Jinja2 HTML text and Unicode'
    assert 'plotly.js v' in html and 'Plotly.newPlot(' in html and 'id="measurements"' in html, 'Inline Plotly chart'
    print('PASS HTML reporting (Jinja2, Unicode and inline Plotly.js)')


def main():
    with tempfile.TemporaryDirectory(prefix='lab314-reporting-') as tmp:
        root = Path(tmp)
        os.environ['MPLCONFIGDIR'] = str(root/'matplotlib')
        os.environ['MPLBACKEND'] = 'Agg'
        make_charts(root)
        make_pdf(root)
        verify_pdf(root)
        html_report(root)
    print('Reporting versions:', ', '.join(f'{name} {version(name)}' for name in
          ('reportlab', 'pypdf', 'jinja2', 'matplotlib', 'plotly')))


if __name__ == '__main__':
    main()
