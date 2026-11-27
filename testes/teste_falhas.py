"""Enfileira pedidos enquanto os workers estão parados e verifica o processamento após recuperação.
Procedimento: 1) docker compose stop worker-processador
2) python testes/teste_falhas.py --criar 10
3) docker compose start worker-processador
4) python testes/teste_falhas.py --verificar
"""
import argparse
import json
import pathlib
import uuid
import time
from teste_concorrencia import req,wait

FILE=pathlib.Path('testes/pedidos_falha.json')
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://localhost:8000')
    p.add_argument('--criar',type=int)
    p.add_argument('--verificar',action='store_true')
    a=p.parse_args()
    if a.criar:
        ids=[]
        for i in range(a.criar):
            data=req('POST',a.url+'/reservar',{'cliente':f'falha-{i}','setor':'pista','quantidade':1},str(uuid.uuid4()))
            ids.append(data['pedido_id'])
        FILE.write_text(json.dumps(ids),encoding='utf-8')
        print(f'{len(ids)} pedidos enviados, lista salva em {FILE}; reative os workers')
    if a.verificar:
        ids=json.loads(FILE.read_text(encoding='utf-8'))
        results=[wait(a.url,i) for i in ids]
        assert all(o['status']=='concluido' for o in results), results
        stock=req('GET',a.url+'/estoque')
        assert stock['invariante_ok']
        print('PASSOU: mensagens recebidas após retomada sem quebrar o estoque')
        print(json.dumps({'pedidos':len(results),'estoque':stock},ensure_ascii=False,indent=2))
