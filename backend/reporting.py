"""Authenticated reporting: Eastern calendar periods, aggregate statistics and exports."""
import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from io import BytesIO
from xml.sax.saxutils import escape
from flask import Blueprint, request, jsonify, send_file

TZ=ZoneInfo('America/New_York')

def period_bounds(period, anchor):
    date=datetime.strptime(anchor,'%Y-%m-%d').date()
    if period=='day': start=date;end=start+timedelta(days=1)
    elif period=='week': start=date-timedelta(days=date.weekday());end=start+timedelta(days=7)
    elif period=='month':
        start=date.replace(day=1);end=start+timedelta(days=calendar.monthrange(start.year,start.month)[1])
    else: raise ValueError('Choose day, week or month.')
    begin=datetime.combine(start,datetime.min.time(),tzinfo=TZ)
    finish=datetime.combine(end,datetime.min.time(),tzinfo=TZ)
    return start,end,begin.astimezone(timezone.utc).isoformat(),finish.astimezone(timezone.utc).isoformat()

def register_reporting(app,db,auth,reasons):
    bp=Blueprint('reporting',__name__)
    def scope():
        period=request.args.get('period','week')
        anchor=request.args.get('date',datetime.now(TZ).date().isoformat())
        start,end,begin,finish=period_bounds(period,anchor)
        return dict(period=period,start=start.isoformat(),end=(end-timedelta(days=1)).isoformat(),timezone='America/New_York'),(begin,finish)
    def badges(params):
        return db().execute("SELECT v.*,u.name staff_name FROM visits v LEFT JOIN users u ON u.id=v.handled_by WHERE v.created_at>=? AND v.created_at<? AND v.visit_reason='Badge Pickup' ORDER BY v.created_at,v.id",params)

    @bp.route('/api/statistics',methods=['GET','OPTIONS'])
    @auth()
    def statistics():
        try: meta,params=scope()
        except (ValueError,OverflowError): return jsonify(error='Enter a valid date and choose day, week or month.'),400
        db().execute('BEGIN')
        where='created_at>=? AND created_at<?'
        groups=db().execute('SELECT visit_reason,count(*) total,sum(status=\'completed\') attended FROM visits WHERE '+where+' GROUP BY visit_reason',params).fetchall()
        categories={r:{'category':r,'total':0,'attended':0} for r in reasons}
        for r in groups:
            key=r['visit_reason'] or 'Not specified'
            if key not in categories: categories[key]={'category':key,'total':0,'attended':0}
            categories[key]['total']+=r['total'];categories[key]['attended']+=r['attended']
        counts={r['status']:r['n'] for r in db().execute('SELECT status,count(*) n FROM visits WHERE '+where+' GROUP BY status',params)}
        unique=db().execute('SELECT count(DISTINCT lower(email)) FROM visits WHERE '+where,params).fetchone()[0]
        return jsonify(**meta,total=sum(counts.values()),counts=counts,unique_visitors=unique,categories=list(categories.values()),badge_pickup=categories['Badge Pickup']['total'])

    @bp.route('/api/reports/badge-pickup',methods=['GET','OPTIONS'])
    @auth()
    def badge_preview():
        try:
            meta,params=scope();page=max(1,int(request.args.get('page','1')))
        except (ValueError,OverflowError): return jsonify(error='Enter a valid period, date and page.'),400
        db().execute('BEGIN')
        total=db().execute("SELECT count(*) FROM visits WHERE created_at>=? AND created_at<? AND visit_reason='Badge Pickup'",params).fetchone()[0]
        rows=db().execute("SELECT v.*,u.name staff_name FROM visits v LEFT JOIN users u ON u.id=v.handled_by WHERE v.created_at>=? AND v.created_at<? AND v.visit_reason='Badge Pickup' ORDER BY v.created_at,v.id LIMIT 50 OFFSET ?",[*params,(page-1)*50]).fetchall()
        return jsonify(**meta,items=[dict(r) for r in rows],total=total,page=page,pages=max(1,(total+49)//50))

    @bp.route('/api/reports/badge-pickup/export',methods=['GET','OPTIONS'])
    @auth()
    def export_badges():
        try: meta,params=scope()
        except (ValueError,OverflowError): return jsonify(error='Enter a valid date and choose day, week or month.'),400
        fmt=request.args.get('format','xlsx')
        if fmt not in ('xlsx','pdf'): return jsonify(error='Choose Excel or PDF.'),400
        db().execute('BEGIN')
        total=db().execute("SELECT count(*) FROM visits WHERE created_at>=? AND created_at<? AND visit_reason='Badge Pickup'",params).fetchone()[0]
        if total>10000: return jsonify(error='This report exceeds 10,000 visits. Choose a shorter period.'),400
        start=datetime.fromisoformat(meta['start']).strftime('%m-%d-%Y');end=datetime.fromisoformat(meta['end']).strftime('%m-%d-%Y')
        period_label=f'{start} - {end} | Eastern time'
        generated=datetime.now(TZ).strftime('%m-%d-%Y %I:%M %p %Z')
        headers=['Arrival (Eastern)','First name','Last name','Email','Phone','ZIP','Status','Assisted by']
        status={'waiting':'Waiting','in_progress':'In progress','completed':'Attended'}
        def values(row):
            arrival=datetime.fromisoformat(row['created_at']).astimezone(TZ).strftime('%m-%d-%Y %I:%M %p')
            return [arrival,row['first_name'],row['last_name'],row['email'],row['phone'],row['zip_code'],status.get(row['status'],row['status']),row['staff_name'] or '']
        output=BytesIO()
        filename=f'badge-pickup-{meta["period"]}-{meta["start"]}.{fmt}'
        if fmt=='xlsx':
            from openpyxl import Workbook
            from openpyxl.styles import Font,PatternFill,Alignment
            from openpyxl.worksheet.table import Table,TableStyleInfo
            wb=Workbook();ws=wb.active;ws.title='Badge Pickup'
            ws.append(['Kelly Education - Broward County']);ws.merge_cells('A1:H1')
            ws.append(['Badge Pickup visit report']);ws.merge_cells('A2:H2')
            ws.append([period_label]);ws.merge_cells('A3:H3')
            ws.append([f'Generated {generated} | {total} visits']);ws.merge_cells('A4:H4')
            ws.append(['Visits registered as Badge Pickup; not confirmation of badge delivery.']);ws.merge_cells('A5:H5')
            ws.append(headers)
            for row in badges(params):
                ws.append(values(row))
                # Force all user content to literal strings, including names beginning with =.
                for cell in ws[ws.max_row]: cell.data_type='s'
            for cell in ws[1]: cell.font=Font(name='Calibri',size=17,bold=True,color='006B48')
            for cell in ws[6]: cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='006B48')
            for i,width in enumerate([26,22,22,38,23,12,17,24],1): ws.column_dimensions[chr(64+i)].width=width
            for row in ws.iter_rows(min_row=7):
                for cell in row: cell.alignment=Alignment(vertical='top',wrap_text=True)
                ws.row_dimensions[row[0].row].height=32
            if total:
                table=Table(displayName='BadgePickupVisits',ref=f'A6:H{ws.max_row}')
                table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium4',showRowStripes=True);ws.add_table(table)
            else: ws.append(['No Badge Pickup visits in this period.'])
            ws.freeze_panes='A7';ws.print_title_rows='1:6';ws.sheet_properties.pageSetUpPr.fitToPage=True
            ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A4;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
            wb.save(output);mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import landscape,A4
            from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from pathlib import Path
            font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
            if Path(font).exists() and 'BrowardSans' not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont('BrowardSans',font))
            fontname='BrowardSans' if 'BrowardSans' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
            styles=getSampleStyleSheet();body=ParagraphStyle('ReportCell',fontName=fontname,fontSize=8,leading=11,wordWrap='CJK')
            title=ParagraphStyle('ReportTitle',fontName=fontname,fontSize=18,leading=23,textColor=colors.HexColor('#006b48'))
            story=[Paragraph('Kelly Education - Broward County',title),Spacer(1,8),Paragraph('Badge Pickup visit report',styles['Heading2']),Paragraph(escape(period_label),styles['Normal']),Paragraph(escape(f'{total} visits | Generated {generated}'),styles['Normal']),Spacer(1,6),Paragraph('Visits registered as Badge Pickup; not confirmation of badge delivery.',styles['Normal']),Spacer(1,16)]
            cell=lambda v: Paragraph(escape(str(v)),body)
            data=[[cell(h) for h in headers]]
            for row in badges(params): data.append([cell(v) for v in values(row)])
            if not total: data.append([cell('No Badge Pickup visits in this period.')]+[cell('') for _ in range(7)])
            table=LongTable(data,colWidths=[105,80,80,145,90,45,75,82],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dcecdf')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6f1')]),('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,0),1,colors.HexColor('#006b48'))]))
            story.append(table)
            def footer(canvas,doc):
                canvas.setFont(fontname,8);canvas.setFillColor(colors.HexColor('#66786e'));canvas.drawString(30,18,'Kelly Education Broward County | Badge Pickup');canvas.drawRightString(812,18,f'Page {doc.page}')
            SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=25,bottomMargin=35,title='Badge Pickup visit report').build(story,onFirstPage=footer,onLaterPages=footer)
            mime='application/pdf'
        output.seek(0)
        return send_file(output,mimetype=mime,as_attachment=True,download_name=filename)
    app.register_blueprint(bp)
