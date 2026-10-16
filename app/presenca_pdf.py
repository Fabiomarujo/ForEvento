"""Diário Oficial de Frequência — PDF A4, a partir de dados reais do SQLite."""
from io import BytesIO
from xml.sax.saxutils import escape
from datetime import datetime
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_PATH = Path('/usr/share/fonts/truetype/dejavu')
if FONT_PATH.exists():
    pdfmetrics.registerFont(TTFont('FeSans',str(FONT_PATH/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('FeSansBold',str(FONT_PATH/'DejaVuSans-Bold.ttf')))
FONT='FeSans' if FONT_PATH.exists() else 'Helvetica'
BOLD='FeSansBold' if FONT_PATH.exists() else 'Helvetica-Bold'
INK=colors.HexColor('#0f172a')
MUTED=colors.HexColor('#64748b')
LINE=colors.HexColor('#cbd5e1')

def build_pdf(evento,atividade,alunos):
    """Gera PDF em memória; sem expor arquivos ou dados de participantes publicamente."""
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=45,leftMargin=45,topMargin=55,bottomMargin=55,title='Diário Oficial de Frequência — ForEvento')
    usable=A4[0]-90
    styles={
      'title':ParagraphStyle('title',fontName=BOLD,fontSize=13,leading=18,textColor=INK,alignment=TA_CENTER),
      'small':ParagraphStyle('small',fontName=FONT,fontSize=8,leading=12,textColor=MUTED,alignment=TA_CENTER),
      'meta':ParagraphStyle('meta',fontName=FONT,fontSize=8,leading=14,textColor=INK),
      'cell':ParagraphStyle('cell',fontName=FONT,fontSize=7.5,leading=11,textColor=INK),
      'cellbold':ParagraphStyle('cellbold',fontName=BOLD,fontSize=7.5,leading=11,textColor=INK),
      'head':ParagraphStyle('head',fontName=BOLD,fontSize=7,leading=10,textColor=INK),
      'footer':ParagraphStyle('footer',fontName=BOLD,fontSize=8,leading=12,textColor=INK),
    }
    def p(v,style='meta'):
        return Paragraph(escape(str(v or '—')),styles[style])
    story=[p('DIÁRIO OFICIAL DE FREQUÊNCIA — FOREVENTO','title'),p('Emitido em: '+datetime.now().strftime('%d/%m/%Y'),'small'),Spacer(1,11)]
    bar=Table([['']],colWidths=[usable],rowHeights=[2]);bar.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),INK)]));story.extend([bar,Spacer(1,17)])
    def meta(label,value):return Paragraph('<b>'+escape(label)+'</b> '+escape(str(value or '—')),styles['meta'])
    event_name=str(evento['name'] or '').upper()
    event_id=str(evento['id'] or '')
    act_name=str(atividade['synopsis_activity'] or atividade['speaker'] or '').upper()
    time=str(atividade['time'] or '')
    end=str(atividade['end_time'] or '')
    hours=(time+' às '+end) if time and end else (time or '—')
    date=str(atividade['date'] or '—')
    meta_rows=[
      [meta('Evento:',event_name+' ('+event_id+')')],
      [meta('Atividade:',act_name)],
      [meta('Cronograma:','Dia: '+date+' | Horário: '+hours+' | Vagas: '+str(atividade['capacity'] or '—'))],
      [meta('Convidado(a)/Responsável:',str(atividade['speaker'] or '').upper())],
    ]
    panel=Table(meta_rows,colWidths=[usable]);panel.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f8fafc')),('BOX',(0,0),(-1,-1),0.7,colors.HexColor('#e2e8f0')),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    story.extend([panel,Spacer(1,18)])
    widths=[30,92,usable-30-92-173,173]
    data=[[p('Nº','head'),p('Voucher','head'),p('Nome Completo do Aluno','head'),p('Assinatura Manual do Participante','head')]]
    for i,r in enumerate(alunos,1):
        nome=str(r['name'] or r['email'] or '—').upper()
        email=str(r['email'] or '')
        nome_cell=Paragraph('<b>'+escape(nome)+'</b><br/><font size="6.5" color="#64748b">'+escape(email)+'</font>',styles['cell'])
        data.append([p(i,'cell'),p(r['id'],'cellbold'),nome_cell,p('________________________','cell')])
    if not alunos:data.append(['','',p('Nenhum participante inscrito nesta atividade.','cell'),''])
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,LINE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ALIGN',(0,1),(0,-1),'CENTER')]))
    story.extend([t,Spacer(1,48)])
    # Rodapé de duas colunas fixas, com a linha desenhada (sem sublinhados
    # de texto que possam quebrar para a próxima linha).
    from reportlab.platypus import Flowable
    class SignatureBlock(Flowable):
        def __init__(self,width):
            Flowable.__init__(self)
            self.width=width
            self.height=38
        def draw(self):
            from reportlab.pdfbase.pdfmetrics import stringWidth
            line_width=min(170,self.width-24)
            x=(self.width-line_width)/2
            self.canv.setStrokeColor(INK)
            self.canv.setLineWidth(0.8)
            self.canv.line(x,23,x+line_width,23)
            label='Assinatura'
            self.canv.setFont(FONT,8)
            self.canv.setFillColor(MUTED)
            self.canv.drawString((self.width-stringWidth(label,FONT,8))/2,9,label)
    footer=Table([[p('Data: ___/___/_____','footer'),SignatureBlock(usable*.48)]],
                 colWidths=[usable*.52,usable*.48],hAlign='LEFT')
    footer.setStyle(TableStyle([
      ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
      ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
      ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)
    ]))
    story.append(KeepTogether([footer]))
    doc.build(story)
    return buf.getvalue()
