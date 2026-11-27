"""Teste ponta a ponta: 100 clientes disputando 50 ingressos.
Uso: python testes/teste_concorrencia.py --url http://localhost:8000
ATENÇÃO: configure estoque inicial 50 e base limpa para teste exato.
"""
import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
import uuid


def req(method, url, data=None, key=None):
    headers = {'Content-Type':'application/json'}
    if key: headers['Idempotency-Key']=key
    payload = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url,data=payload,headers=headers,method=method)
    with urllib.request.urlopen(r,timeout=20) as response: return json.load(response)


def wait(base, oid, timeout=120):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        data=req('GET',base+'/pedidos/'+oid)
        if data['status'] in ('concluido','erro'): return data
        time.sleep(.15)
    raise TimeoutError(f'Pedido {oid} não terminou em {timeout}s')


def run(base, customers=100, workers=24, confirm=True):
    started=time.perf_counter()
    def client(i):
        order=req('POST',base+'/reservar',{'cliente':f'cliente-{i}','setor':'pista','quantidade':1},f'reserva-{uuid.uuid4()}')
        first=wait(base,order['pedido_id'])['resultado']
        if first['estado']!='em_reserva': return first['estado']
        if not confirm:return 'reservado'
        conf=req('POST',base+'/confirmar',{'reserva_id':first['reserva_id']},f'confirmar-{uuid.uuid4()}')
        end=wait(base,conf['pedido_id'])['resultado']
        return end['estado']
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(client,range(customers)))
    duration=time.perf_counter()-started
    counts={x:results.count(x) for x in sorted(set(results))}
    stock=req('GET',base+'/estoque')
    print(json.dumps({'clientes':customers,'duracao_s':round(duration,3),'resultado':counts,'estoque':stock},indent=2,ensure_ascii=False))
    assert stock['invariante_ok'], 'INVARIANTE QUEBRADA'
    assert all(s['vendido']<=s['inicial'] for s in stock['setores']), 'OVERSELLING'
    print('PASSOU: sem overselling e invariante preservada')
    return duration,counts

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://localhost:8000')
    p.add_argument('--clientes',type=int,default=100)
    p.add_argument('--threads',type=int,default=24)
    p.add_argument('--sem-confirmar',action='store_true')
    a=p.parse_args()
    run(a.url,a.clientes,a.threads,not a.sem_confirmar)
