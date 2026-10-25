import csv
import html
import io
import json
import zipfile


def export(run, format):
    if format == 'json':
        return json.dumps(run, indent=2, ensure_ascii=False).encode(), 'application/json'
    rows = [['TC', 'Result', 'Attempt', 'Started', 'Ended', 'Reason']]
    rows += [[a['tc_id'], a['state'], a['ordinal'], a['started_at'], a['ended_at'] or '', a['reason']] for a in run['attempts']]
    if format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        for row in rows:
            writer.writerow([("'" + str(x)) if str(x).startswith(('=', '+', '-', '@', '\t', '\r')) else x for x in row])
        return ('\ufeff' + output.getvalue()).encode(), 'text/csv; charset=utf-8'
    if format == 'html':
        table = ''.join('<tr>' + ''.join('<td>' + html.escape(str(x)) + '</td>' for x in row) + '</tr>' for row in rows)
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>GUI Test report</title>'
                '<style>body{font:15px system-ui;margin:40px}td{padding:8px;border:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
                f'<h1>GUI Test · {html.escape(run["overall_result"])}</h1><p>MOCK / SIMULATION · {run["id"]}</p>'
                f'<table>{table}</table><h2>Complete evidence snapshot</h2><pre>{html.escape(json.dumps(run, indent=2, ensure_ascii=False))}</pre></html>').encode(), 'text/html; charset=utf-8'
    if format == 'pdf':
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        output = io.BytesIO()
        pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
        styles = getSampleStyleSheet()
        styles['BodyText'].fontName = 'HYSMyeongJo-Medium'
        styles['BodyText'].wordWrap = 'CJK'
        story = [Paragraph('GUI Test / ' + run['overall_result'], styles['Title']),
                 Paragraph('MOCK / SIMULATION — not hardware evidence', styles['BodyText']), Spacer(1, 12)]
        # Full snapshot, wrapping long hashes/paths, preserves provenance and all attempts.
        for line in json.dumps(run, indent=2, ensure_ascii=False).splitlines():
            story.append(Paragraph(html.escape(line).replace(' ', '&#160;'), styles['BodyText']))
        SimpleDocTemplate(output).build(story)
        return output.getvalue(), 'application/pdf'
    if format == 'logs':
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for a in run['attempts']:
                for stream in ('stdout', 'stderr'):
                    archive.writestr(a['id'] + '/' + stream + '.log', a[stream])
            archive.writestr('manifest.json', json.dumps(run, indent=2, ensure_ascii=False))
        return output.getvalue(), 'application/zip'
    raise ValueError('Unsupported report format')
