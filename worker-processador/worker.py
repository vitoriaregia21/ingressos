"""Consumidor RabbitMQ; o ACK ocorre depois da persistência do resultado."""
import json
import logging
import os
import time
import requests
from shared.rabbit import connect, declare, QUEUE

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s worker %(message)s')
log = logging.getLogger('worker')
STOCK = os.environ.get('STOCK_URL', 'http://gerenciador-estoque:8001')
TOKEN = os.environ.get('INTERNAL_TOKEN','dev-internal-token')
DELAY = float(os.environ.get('PAYMENT_DELAY_SECONDS','0.04'))

session = requests.Session()

def call(route, data):
    response = session.post(STOCK+route,json=data,headers={'X-Internal-Token':TOKEN},timeout=12)
    response.raise_for_status()
    return response.json()


def process(pedido_id):
    # O endpoint interno valida o tipo do pedido e controla a idempotência.
    try:
        return call('/interno/reservar',{'pedido_id':pedido_id})
    except requests.HTTPError as e:
        if e.response.status_code != 404:
            raise
    prep = call('/interno/preparar-confirmacao',{'pedido_id':pedido_id})
    if prep['terminal']:
        return prep
    # Gateway SIMULADO. Decisão determinística por identificador, sem cobrança real.
    # Um retry após falha não produz dois resultados diferentes.
    time.sleep(DELAY)
    return call('/interno/finalizar-confirmacao', {'pedido_id': pedido_id, 'aprovado': True})


def run():
    while True:
        conn = None
        try:
            conn = connect()
            ch = conn.channel()
            declare(ch)
            ch.basic_qos(prefetch_count=1)
            log.info('consumidor conectado: %s',QUEUE)
            def on_message(channel, method, properties, body):
                try:
                    pedido_id = json.loads(body)['pedido_id']
                    answer = process(pedido_id)
                    log.info('processado pedido=%s resultado=%s', pedido_id, answer)
                except requests.HTTPError as exc:
                    # Erros permanentes não devem bloquear toda a fila.
                    if exc.response is not None and exc.response.status_code in (400, 403, 404, 409, 422):
                        log.error('mensagem inválida, descartada body=%s erro=%s', body, exc)
                    else:
                        log.exception('erro temporário; mensagem enviada à fila de retry')
                        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        return
                except Exception:
                    log.exception('erro temporário; mensagem enviada à fila de retry')
                    channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    return
                channel.basic_ack(delivery_tag=method.delivery_tag)
            ch.basic_consume(queue=QUEUE,on_message_callback=on_message,auto_ack=False)
            ch.start_consuming()
        except Exception:
            log.exception('desconectado; tentando restabelecer conexão')
            time.sleep(2)
        finally:
            if conn and conn.is_open:
                try: conn.close()
                except Exception: pass

if __name__=='__main__':
    run()
