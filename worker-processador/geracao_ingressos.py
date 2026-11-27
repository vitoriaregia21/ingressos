"""Tarefa REAL e paralelizável: gera arquivos PNG QR para reservas vendidas.

Uso com Docker, após realizar vendas:
  docker compose run --rm worker-processador python service/geracao_ingressos.py --processos 1
  docker compose run --rm worker-processador python service/geracao_ingressos.py --processos 4
As duas execuções produzem os mesmos PNGs (pastas diferentes) e comparam tempos.
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import time
import qrcode


def png_ticket(ticket):
    """Serializa QR identificável e gera PNG de alta resolução; trabalho independente por venda."""
    id_, setor, cliente, quantidade = ticket
    payload = json.dumps({'ingresso':id_, 'setor':setor, 'cliente':cliente, 'quantidade':quantidade},
                         ensure_ascii=False,sort_keys=True,separators=(',',':'))
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=20,border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black',back_color='white').convert('RGB')
    stream=io.BytesIO()
    img.save(stream,format='PNG',optimize=True)
    data=stream.getvalue()
    return (id_,data,hashlib.sha256(data).hexdigest())


def buscar_vendas():
    import psycopg
    database=os.environ.get('DATABASE_URL','postgresql://ingressos:ingressos@db:5432/ingressos')
    with psycopg.connect(database) as db:
        rows=db.execute('''SELECT id::text,setor,cliente,quantidade FROM reservas
             WHERE estado='vendido' ORDER BY id''').fetchall()
    return rows


def execute(tickets,processes,destination):
    target=Path(destination)
    target.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    if processes==1:
        results=list(map(png_ticket,tickets))
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=processes) as pool:
            results=list(pool.map(png_ticket,tickets))
    for id_,data,_ in results:
        (target/(id_+'.png')).write_bytes(data)
    elapsed=time.perf_counter()-start
    return elapsed, {id_:sha for id_,_,sha in results}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--processos',type=int,default=4)
    parser.add_argument('--repeticoes',type=int,default=5)
    parser.add_argument('--saida',default='/app/saidas')
    opts=parser.parse_args()
    vendas=buscar_vendas()
    if not vendas:
        raise SystemExit('Sem vendas confirmadas. Execute primeiro testes/teste_concorrencia.py')
    # Mesmos dados de vendas REALMENTE persistidos no banco, sequencial vs paralelo.
    seq=[]; par=[]
    for i in range(opts.repeticoes):
        t1,hashes_seq=execute(vendas,1,f'{opts.saida}/seq')
        t2,hashes_par=execute(vendas,opts.processos,f'{opts.saida}/par')
        if hashes_seq!=hashes_par:
            raise RuntimeError('Arquivos diferentes na implementação paralela')
        seq.append(t1);par.append(t2)
        print(f'Repetição {i+1}: sequencial={t1:.3f}s paralelo={t2:.3f}s')
    s=statistics.median(seq);p=statistics.median(par)
    result={'ingressos_gerados':len(vendas),'repeticoes':opts.repeticoes,'processos':opts.processos,
            'tempo_sequencial_mediana_s':round(s,4),'tempo_paralelo_mediana_s':round(p,4),
            'speedup':round(s/p,3)}
    print('RESULTADO REAL:',json.dumps(result,ensure_ascii=False))
    Path(opts.saida).mkdir(parents=True,exist_ok=True)
    (Path(opts.saida)/'benchmark_qr.json').write_text(json.dumps(result,indent=2),encoding='utf8')

if __name__=='__main__':main()
