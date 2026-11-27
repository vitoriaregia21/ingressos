"""Benchmark real via HTTP. Reinicie o estoque ENTRE execuções para comparar o mesmo cenário."""
import argparse
import csv
import datetime
import pathlib
import statistics
import time
from teste_concorrencia import run

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://localhost:8000')
    p.add_argument('--clientes',type=int,default=100)
    p.add_argument('--threads',type=int,default=24)
    p.add_argument('--saida',default='testes/resultados_http.csv')
    p.add_argument('--workers',type=int,default=2,help='rotulo: número de workers configurados no Compose')
    a=p.parse_args()
    dur,counts=run(a.url,a.clientes,a.threads)
    dest=pathlib.Path(a.saida)
    dest.parent.mkdir(parents=True,exist_ok=True)
    exists=dest.exists()
    with dest.open('a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['momento','workers','clientes','threads_cliente','duracao_s','vazao_pedidos_s','vendidos','sem_estoque'])
        if not exists:w.writeheader()
        w.writerow({'momento':datetime.datetime.now().isoformat(),'workers':a.workers,'clientes':a.clientes,
           'threads_cliente':a.threads,'duracao_s':round(dur,3),'vazao_pedidos_s':round(a.clientes/dur,3),
           'vendidos':counts.get('vendido',0),'sem_estoque':counts.get('sem_estoque',0)})
    print('Resultado salvo em:',dest)
