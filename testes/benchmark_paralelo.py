"""Relatório pesado reproduzível: SHA-256 repetido sobre lotes de transações fictícias.
Dados gerados deterministicamente; mesma carga sequencial e paralela.
Execução: python testes/benchmark_paralelo.py --lotes 24 --iteracoes 50000 --repeticoes 5
"""
from concurrent.futures import ProcessPoolExecutor
import argparse
import csv
import hashlib
import os
import pathlib
import statistics
import time


def processar_lote(item):
    indice, iteracoes = item
    digest = hashlib.sha256(f'transacao-{indice}'.encode()).digest()
    for i in range(iteracoes):
        digest = hashlib.sha256(digest + i.to_bytes(4,'little')).digest()
    return digest.hex()


def benchmark(lotes,iteracoes,repeticoes,processos):
    items=[(i,iteracoes) for i in range(lotes)]
    seq=[]; par=[]
    for r in range(repeticoes):
        t=time.perf_counter()
        a=list(map(processar_lote,items))
        seq.append(time.perf_counter()-t)
        t=time.perf_counter()
        with ProcessPoolExecutor(max_workers=processos) as executor:
            b=list(executor.map(processar_lote,items))
        par.append(time.perf_counter()-t)
        assert a==b, 'resultados diferentes entre execução sequencial e paralela'
        print(f'Repetição {r+1}: sequencial={seq[-1]:.3f}s paralela={par[-1]:.3f}s')
    s=statistics.median(seq);p=statistics.median(par)
    return {'lotes':lotes,'iteracoes_por_lote':iteracoes,'repeticoes':repeticoes,'processos':processos,
       'tempo_sequencial_mediana_s':round(s,4),'tempo_paralelo_mediana_s':round(p,4),
       'speedup':round(s/p,3),'cpu_logicas':os.cpu_count()}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--lotes',type=int,default=24)
    parser.add_argument('--iteracoes',type=int,default=50000)
    parser.add_argument('--repeticoes',type=int,default=5)
    parser.add_argument('--processos',type=int,default=4)
    parser.add_argument('--saida',default='testes/resultados_paralelo.csv')
    args=parser.parse_args()
    row=benchmark(args.lotes,args.iteracoes,args.repeticoes,args.processos)
    print(row)
    out=pathlib.Path(args.saida);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(row))
        writer.writeheader();writer.writerow(row)
    print('Salvo em',out)
