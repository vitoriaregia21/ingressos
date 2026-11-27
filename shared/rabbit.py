import os
import pika

QUEUE = 'pedidos.v1'
RETRY = 'pedidos.retry.v1'

def connect():
    return pika.BlockingConnection(pika.URLParameters(os.environ.get('RABBITMQ_URL', 'amqp://ingressos:ingressos@rabbitmq:5672/%2F')))

def declare(channel):
    channel.queue_declare(queue=QUEUE, durable=True, arguments={'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': RETRY})
    channel.queue_declare(queue=RETRY, durable=True, arguments={'x-message-ttl': 2000, 'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': QUEUE})
