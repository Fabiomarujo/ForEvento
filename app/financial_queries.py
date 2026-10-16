"""Consultas financeiras sem escrita ou migração de banco."""
import datetime

def _date(value):
    s=str(value or '').strip()
    if len(s)>=10 and s[4:5]=='-' and s[7:8]=='-':return s[:10]
    if len(s)>=10 and s[2:3]=='/' and s[5:6]=='/':return s[6:10]+'-'+s[3:5]+'-'+s[:2]
    return ''

def _value(c,event_id,activity):
    row=c.execute("""select price from schedules where event_id=? and
      (synopsis_activity=? or speaker=? or synopsis=?)
      order by id desc limit 1""",(event_id,activity,activity,activity)).fetchone()
    return float(row['price'] or 0) if row else 0.0

def rows(c,event_id,status='todos',search_type='todos',term='',start='',end='',kind='audit'):
    if not event_id: return []
    regs=c.execute("""select r.id rid,r.event_id,r.user_id,r.email,r.activity,r.created_at,
        r.status regstatus,u.name,ev.name event_name
        from registrations r left join users u on u.id=r.user_id
        left join events ev on ev.id=r.event_id
        where r.event_id=? and upper(coalesce(r.status,'')) not in
        ('CANCELADO','CANCELADA','REEMBOLSADO') order by r.created_at desc,r.id""",(event_id,)).fetchall()
    result=[]
    for r in regs:
        name=str(r['name'] or r['email'] or '')
        if search_type=='nome' and term.lower() not in name.lower():continue
        if search_type=='id' and term.lower() not in str(r['user_id'] or '').lower() and term.lower() not in str(r['rid']).lower():continue
        rec=c.execute("""select * from receipts where event_id=? and
          (registration_id=? or (lower(email)=lower(?) and activity=?))
          order by case when upper(trim(status))='CONFIRMADO' then 0 else 1 end,id desc limit 1""",
          (event_id,r['rid'],r['email'],r['activity'])).fetchone()
        paid=bool(rec and str(rec['status'] or '').strip().upper()=='CONFIRMADO')
        val=float(rec['value'] or 0) if rec else _value(c,event_id,r['activity'])
        if val<=0:continue
        # Reembolso exige comprovante confirmado; auditoria inclui inscrições pendentes.
        if kind=='refund' and not paid:continue
        refund=c.execute('select * from refunds where payment_id=? order by created_at desc limit 1',('REC:'+str(rec['id']) if rec else '',)).fetchone() if rec else None
        situation='reembolsado' if refund else ('pago' if paid else 'pendente')
        if status!='todos' and situation!=status:continue
        date=_date((refund['created_at'] if situation=='reembolsado' and kind=='refund' else (rec['sent_at'] if paid else r['created_at'])) if rec or r else '')
        if start and (not date or date<start):continue
        if end and (not date or date>end):continue
        presence=c.execute("""select status from attendance where event_id=? and activity=?
          and (user_id=? or lower(email)=lower(?)) order by id desc limit 1""",
          (event_id,r['activity'],r['user_id'],r['email'])).fetchone()
        ps=str(presence['status'] or '') if presence else 'Não registrada'
        present=ps.strip().upper() in ('PRESENTE','PRESENÇA','PRESENCA','CONFIRMADO','CONFIRMADA')
        result.append({'id':r['rid'],'idUsuario':r['user_id'] or '',
          'nome':name,'evento':r['event_name'] or event_id,'idEvento':event_id,
          'atividade':r['activity'],'valor':val,'situacao':situation,
          'data':date,'metodo':'PIX' if rec else 'Não informado',
          'pagamento':(rec['file_name'] or 'PIX') if rec else 'Aguardando pagamento',
          'idPagamento':'REC:'+str(rec['id']) if rec else '',
          'temComprovante':bool(rec and rec['file_data']),
          'presenca':ps,'reembolsado':bool(refund),'podeReembolsar':paid and not refund and not present,
          'observacao':refund['note'] if refund else ''})
    return result
