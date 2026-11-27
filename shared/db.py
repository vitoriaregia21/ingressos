import os
import psycopg
from psycopg.rows import dict_row


def connection():
    return psycopg.connect(os.environ.get('DATABASE_URL', 'postgresql://ingressos:ingressos@db:5432/ingressos'), row_factory=dict_row)
