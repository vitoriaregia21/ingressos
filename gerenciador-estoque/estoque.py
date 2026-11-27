"""Serviço interno: operações de estoque com transações e segurança concorrente."""
import os
import uuid
import logging
import threading
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from shared.db import connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s estoque %(message)s')
log = logging.getLogger('estoque')
app = FastAPI(title='Gerenciador de estoque')
TOKEN = os.environ.get('INTERNAL_TOKEN', 'dev-internal-token')
TTL = int(os.environ.get('RESERVATION_TTL_SECONDS', '180'))


def authorized(x_internal_token: str = Header(default='')):
    if x_internal_token != TOKEN:
        raise HTTPException(status_code=403, detail='Token interno inválido')

class PedidoID(BaseModel):
    pedido_id: uuid.UUID

class Finalizar(BaseModel):
    pedido_id: uuid.UUID
    aprovado: bool


def pedido_validado(db, pedido_id, tipo):
    """Obtém e bloqueia o pedido para operações idempotentes."""
    pedido = db.execute(
        'SELECT * FROM pedidos WHERE id=%s FOR UPDATE', (pedido_id,)
    ).fetchone()
    if not pedido or pedido['tipo'] != tipo:
        raise HTTPException(404, 'Comando inválido')
    return pedido


def mover_estoque(db, reserva, destino):
    """Transfere unidades reservadas para vendido ou disponível."""
    if destino not in ('vendido', 'disponivel'):
        raise ValueError('Destino de estoque inválido')
    db.execute(
        f'UPDATE estoque SET reservado=reservado-%s, {destino}={destino}+%s WHERE setor=%s',
        (reserva['quantidade'], reserva['quantidade'], reserva['setor'])
    )


def result(db, pedido_id, data):
    db.execute('UPDATE pedidos SET status=%s, resultado=%s, atualizado_em=now() WHERE id=%s',
        ('concluido', Jsonb(data), pedido_id))
    return data

@app.post('/interno/reservar', dependencies=[Depends(authorized)])
def reservar(body: PedidoID):
    with connection() as db:
        with db.transaction():
            order = pedido_validado(db, body.pedido_id, 'reservar')
            if order['status'] == 'concluido':
                return order['resultado']
            p = order['payload']
            # UPDATE condicional é atômico no PostgreSQL e serializa as alterações da mesma linha.
            item = db.execute('''UPDATE estoque SET disponivel=disponivel-%s, reservado=reservado+%s
                WHERE setor=%s AND disponivel >= %s RETURNING setor''',
                (p['quantidade'], p['quantidade'], p['setor'], p['quantidade'])).fetchone()
            if not item:
                return result(db, body.pedido_id, {'estado': 'sem_estoque', 'reserva_id': None})
            rid = uuid.uuid4()
            db.execute('''INSERT INTO reservas(id,setor,cliente,quantidade,estado,expira_em)
                VALUES (%s,%s,%s,%s,'em_reserva',now()+(%s * interval '1 second'))''',
                (rid,p['setor'],p['cliente'],p['quantidade'],TTL))
            log.info('reserva criada pedido=%s reserva=%s quantidade=%s', body.pedido_id,rid,p['quantidade'])
            return result(db,body.pedido_id,{'estado':'em_reserva','reserva_id':str(rid)})

@app.post('/interno/preparar-confirmacao', dependencies=[Depends(authorized)])
def preparar(body: PedidoID):
    with connection() as db:
        with db.transaction():
            order = pedido_validado(db, body.pedido_id, 'confirmar')
            if order['status'] == 'concluido':
                return {'terminal': True, **order['resultado']}
            rid = order['payload']['reserva_id']
            reserva = db.execute('SELECT * FROM reservas WHERE id=%s FOR UPDATE',(rid,)).fetchone()
            if not reserva:
                return {'terminal': True, **result(db,body.pedido_id,{'estado':'reserva_inexistente','confirmado':False})}
            if reserva['estado'] == 'vendido':
                return {'terminal': True, **result(db,body.pedido_id,{'estado':'vendido','confirmado':True})}
            if reserva['estado'] not in ('em_reserva','confirmando'):
                return {'terminal': True, **result(db,body.pedido_id,{'estado':reserva['estado'],'confirmado':False})}
            if reserva['estado'] == 'em_reserva' and reserva['expira_em'] <= datetime.now(timezone.utc):
                db.execute('UPDATE reservas SET estado=%s WHERE id=%s',('expirada',rid))
                mover_estoque(db, reserva, 'disponivel')
                return {'terminal':True, **result(db,body.pedido_id,{'estado':'expirada','confirmado':False})}
            # Apenas um pedido de confirmação controla essa reserva.
            # Outra confirmação concorrente não pode finalizar o pagamento por ela.
            owner = db.execute('''SELECT id FROM pedidos WHERE tipo='confirmar'
               AND id <> %s AND payload->>'reserva_id'=%s
               AND status='pendente' AND resultado->>'preparado'='true' LIMIT 1''',(body.pedido_id,str(rid))).fetchone()
            if owner:
                return {'terminal':True, **result(db,body.pedido_id,{'estado':'confirmacao_em_andamento','confirmado':False})}
            db.execute('UPDATE reservas SET estado=%s WHERE id=%s',('confirmando',rid))
            db.execute('UPDATE pedidos SET resultado=%s,atualizado_em=now() WHERE id=%s',
                (Jsonb({'preparado':True}),body.pedido_id))
            return {'terminal':False,'reserva_id':str(rid),'quantidade':reserva['quantidade']}

@app.post('/interno/finalizar-confirmacao', dependencies=[Depends(authorized)])
def finalizar(body: Finalizar):
    with connection() as db:
        with db.transaction():
            order = pedido_validado(db, body.pedido_id, 'confirmar')
            if order['status']=='concluido':
                return order['resultado']
            if not order['resultado'] or not order['resultado'].get('preparado'):
                raise HTTPException(409, 'Confirmação não preparada')
            rid = order['payload']['reserva_id']
            reserva = db.execute('SELECT * FROM reservas WHERE id=%s FOR UPDATE',(rid,)).fetchone()
            if not reserva or reserva['estado']!='confirmando':
                raise HTTPException(409,'Reserva não está confirmando')
            state = 'vendido' if body.aprovado else 'recusada'
            mover_estoque(db, reserva, 'vendido' if body.aprovado else 'disponivel')
            db.execute('UPDATE reservas SET estado=%s WHERE id=%s',(state,rid))
            log.info('confirmação pedido=%s reserva=%s estado=%s',body.pedido_id,rid,state)
            return result(db,body.pedido_id,{'estado':state,'confirmado':body.aprovado,'reserva_id':str(rid)})

@app.get('/health')
def health():
    with connection() as db: db.execute('SELECT 1')
    return {'status':'ok'}


def expire_once():
    with connection() as db:
        with db.transaction():
            rows = db.execute('''SELECT id,setor,quantidade FROM reservas WHERE estado='em_reserva'
                 AND expira_em < now() FOR UPDATE SKIP LOCKED LIMIT 100''').fetchall()
            for row in rows:
                db.execute('UPDATE reservas SET estado=%s WHERE id=%s',('expirada',row['id']))
                mover_estoque(db, row, 'disponivel')
                log.info('reserva expirada reserva=%s',row['id'])

def reaper():
    while True:
        try: expire_once()
        except Exception: log.exception('Falha no reaper')
        time.sleep(2)

@app.on_event('startup')
def startup_reaper():
    threading.Thread(target=reaper,daemon=True).start()
