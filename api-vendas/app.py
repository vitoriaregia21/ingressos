"""API produtora HTTP; grava pedido + outbox atomicamente."""
import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from shared.db import connection
from shared.rabbit import connect, declare, QUEUE
import pika

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s api %(message)s')
log = logging.getLogger('api')
stop = threading.Event()



def publicar_pedidos(db, channel):
    """Publica lotes da outbox e marca cada confirmação no banco."""
    rows = db.execute(
        """SELECT id, pedido_id FROM outbox WHERE publicado_em IS NULL
           ORDER BY id LIMIT 30 FOR UPDATE SKIP LOCKED"""
    ).fetchall()
    for row in rows:
        channel.basic_publish(
            exchange='', routing_key=QUEUE,
            body=json.dumps({'pedido_id': str(row['pedido_id'])}).encode(),
            properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'),
            mandatory=True,
        )
        db.execute('UPDATE outbox SET publicado_em=NOW() WHERE id=%s', (row['id'],))
    return bool(rows)


def dispatch():
    """Publicação at-least-once usando o padrão Transactional Outbox."""
    while not stop.is_set():
        rabbit = None

        try:
            rabbit = connect()
            channel = rabbit.channel()
            declare(channel)
            channel.confirm_delivery()

            while not stop.is_set():
                with connection() as db:
                    with db.transaction():
                        publicou = publicar_pedidos(db, channel)
                if not publicou:
                    stop.wait(0.2)

        except Exception:
            log.exception(
                'Erro no dispatcher; tentando reconectar'
            )
            stop.wait(2)

        finally:
            if rabbit and rabbit.is_open:
                rabbit.close()



@asynccontextmanager
async def lifespan(app):
    stop.clear()
    thread = threading.Thread(target=dispatch, daemon=True)
    thread.start()
    yield
    stop.set()
    thread.join(timeout=4)

app = FastAPI(title='Venda de Ingressos — API distribuída', lifespan=lifespan)

class Reserva(BaseModel):
    cliente: str = Field(min_length=1, max_length=120)
    setor: str = 'pista'
    quantidade: int = Field(default=1, ge=1, le=20)

class Confirmacao(BaseModel):
    reserva_id: uuid.UUID


def create_order(kind, payload, idempotency_key):
    key = idempotency_key or str(uuid.uuid4())
    new_id = uuid.uuid4()
    with connection() as db:
        with db.transaction():
            row = db.execute('''INSERT INTO pedidos(id,chave_idempotencia,tipo,payload)
              VALUES (%s,%s,%s,%s) ON CONFLICT (chave_idempotencia) DO NOTHING RETURNING id,tipo,payload''',
              (new_id,key,kind,Jsonb(payload))).fetchone()
            if row:
                db.execute('INSERT INTO outbox(pedido_id) VALUES (%s)', (new_id,))
            else:
                row = db.execute('SELECT id,tipo,payload FROM pedidos WHERE chave_idempotencia=%s', (key,)).fetchone()
                if row['tipo'] != kind or row['payload'] != payload:
                    raise HTTPException(409, 'Chave de idempotência já usada com outro conteúdo')
    return {'pedido_id': str(row['id']), 'status': 'pendente_ou_processando', 'consulta': f'/pedidos/{row["id"]}'}

@app.post('/reservar', status_code=202)
def reservar(body: Reserva, idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    return create_order('reservar', body.model_dump(), idempotency_key)

@app.post('/confirmar', status_code=202)
def confirmar(body: Confirmacao, idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    return create_order('confirmar', {'reserva_id': str(body.reserva_id)}, idempotency_key)

@app.get('/pedidos/{pedido_id}')
def pedido(pedido_id: uuid.UUID):
    with connection() as db:
        row = db.execute('SELECT id,tipo,status,resultado,criado_em,atualizado_em FROM pedidos WHERE id=%s', (pedido_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Pedido não encontrado')
    return row

@app.get('/estoque')
def estoque():
    with connection() as db:
        rows = db.execute('SELECT * FROM estoque ORDER BY setor').fetchall()
    return {'setores': rows, 'invariante_ok': all(r['inicial'] == r['disponivel']+r['reservado']+r['vendido'] for r in rows)}

@app.get('/health')
def health():
    try:
        with connection() as db:
            db.execute('SELECT 1')
        return {'status': 'ok'}
    except Exception:
        raise HTTPException(503, 'Banco indisponível')
