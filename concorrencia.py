"""Sistema de venda de ingressos — 100 pessoas, lote de 50.

Arquitetura:

  Cliente -> Camada HTTP (ThreadingHTTPServer, thread por requisição)
          -> Fila de pedidos (arquivo fila_pedidos.py)
          -> Pool de 3 workers (verifica e decrementa sob lock)
          -> reserva com prazo de 3 minutos (thread reaper expira)
          -> confirmação -> Gateway (Semaphore limita concorrência)
          -> aprovado: marca como vendido sob lock
"""
from __future__ import annotations
import json
import random
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional

from fila_pedidos import FilaDePedidos, Pedido

TTL_RESERVA_SEGUNDOS = 180.0  # 3 minutos

# Estoque — Lock por setor, reserva com TTL, confirmação sob lock
class EstoqueSeguro:
    def __init__(self, estoque: Dict[str, int]):
        self.disponivel = dict(estoque)
        self.reservado = {s: 0 for s in estoque}
        self.vendido = {s: 0 for s in estoque}
        self._locks = {s: threading.Lock() for s in estoque}
        self._lock_r = threading.Lock()
        self._seq = 0
        self.reservas: Dict[int, dict] = {}

    def reservar(self, setor: str, cliente: str) -> Optional[int]:
        """Verifica e decrementa sob o MESMO lock — sem janela de risco."""
        with self._locks[setor]:
            if self.disponivel[setor] < 1:
                return None
            self.disponivel[setor] -= 1
            self.reservado[setor] += 1
            with self._lock_r:
                self._seq += 1
                rid = self._seq
                self.reservas[rid] = {
                    "setor": setor, "cliente": cliente,
                    "estado": "em_reserva", "criada_em": time.monotonic(),
                }
            return rid

    def confirmar(self, rid: int, gateway: "Gateway") -> bool:
        """Cobra no gateway FORA do lock do setor; marca como vendido
        sob lock, revalidando o estado (o reaper pode ter agido)."""
        with self._lock_r:
            r = self.reservas.get(rid)
            if not r or r["estado"] != "em_reserva":
                return False
            r["estado"] = "confirmando"
            setor = r["setor"]

        aprovado = gateway.cobrar()

        with self._locks[setor], self._lock_r:
            if self.reservas[rid]["estado"] != "confirmando":
                return False
            if not aprovado:
                self.disponivel[setor] += 1
                self.reservado[setor] -= 1
                self.reservas[rid]["estado"] = "recusada"
                return False
            self.reservado[setor] -= 1
            self.vendido[setor] += 1
            self.reservas[rid]["estado"] = "vendido"
            return True

    def expirar(self, ttl: float) -> None:
        """Thread reaper: devolve ao estoque reservas mais velhas que o TTL."""
        agora = time.monotonic()
        with self._lock_r:
            candidatas = [rid for rid, r in self.reservas.items()
                          if r["estado"] == "em_reserva" and agora - r["criada_em"] > ttl]
        for rid in candidatas:
            setor = self.reservas[rid]["setor"]
            with self._locks[setor], self._lock_r:
                if self.reservas[rid]["estado"] != "em_reserva":
                    continue
                self.disponivel[setor] += 1
                self.reservado[setor] -= 1
                self.reservas[rid]["estado"] = "expirada"

    def invariante_ok(self, setor: str, inicial: int) -> bool:
        return self.disponivel[setor] + self.reservado[setor] + self.vendido[setor] == inicial

# Gateway — dependência externa simulada, limitada por Semaphore
class Gateway:
    def __init__(self, max_concorrentes: int):
        self._sem = threading.Semaphore(max_concorrentes)
        self.max_concorrentes = max_concorrentes
        self._ativas = 0
        self.pico = 0
        self._lock = threading.Lock()

    def cobrar(self) -> bool:
        with self._sem: 
            with self._lock:
                self._ativas += 1
                self.pico = max(self.pico, self._ativas)
            try:
                time.sleep(random.uniform(0.02, 0.05))  
                return True
            finally:
                with self._lock:
                    self._ativas -= 1

# Pool de workers — só eles desenfileiram e tocam no estoque
class PoolDeWorkers:
    def __init__(self, fila: FilaDePedidos, estoque: EstoqueSeguro, gateway: Gateway, n_workers: int = 3):
        self.fila = fila
        self.estoque = estoque
        self.gateway = gateway
        self.n_workers = n_workers
        self._ativos = 0
        self.pico = 0
        self._lock = threading.Lock()
        self._threads = [threading.Thread(target=self._loop, daemon=True) for _ in range(n_workers)]

    def iniciar(self):
        for t in self._threads:
            t.start()

    def parar(self):
        for _ in self._threads:
            self.fila.enfileirar(None)
        for t in self._threads:
            t.join(timeout=2)

    def _loop(self):
        while True:
            pedido = self.fila.desenfileirar()
            if pedido is None:
                self.fila.marcar_concluido()
                return
            with self._lock:
                self._ativos += 1
                self.pico = max(self.pico, self._ativos)
            try:
                if pedido.tipo == "reservar":
                    p = pedido.payload
                    pedido.resultado["reserva_id"] = self.estoque.reservar(p["setor"], p["cliente"])
                else:  # "confirmar"
                    ok = self.estoque.confirmar(pedido.payload["reserva_id"], self.gateway)
                    pedido.resultado["confirmado"] = ok
            finally:
                with self._lock:
                    self._ativos -= 1
                pedido.evento.set()
                self.fila.marcar_concluido()

# Thread reaper — roda em paralelo, fora do pool de workers
class ThreadReaper:
    def __init__(self, estoque: EstoqueSeguro, ttl: float, intervalo: float = 0.5):
        self.estoque = estoque
        self.ttl = ttl
        self.intervalo = intervalo
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def iniciar(self):
        self._thread.start()

    def parar(self):
        self._parar.set()
        self._thread.join(timeout=2)

    def _loop(self):
        while not self._parar.is_set():
            self.estoque.expirar(self.ttl)
            time.sleep(self.intervalo)

# Camada HTTP — ThreadingHTTPServer, uma thread por requisição
def _criar_handler(fila: FilaDePedidos):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # silencia o log padrão do http.server

        def _corpo(self) -> dict:
            tamanho = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(tamanho)) if tamanho else {}

        def _responder(self, status: int, corpo: dict):
            dados = json.dumps(corpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_POST(self):
            corpo = self._corpo()
            if self.path == "/reservar":
                pedido = Pedido("reservar", {"setor": corpo["setor"], "cliente": corpo["cliente"]})
            elif self.path == "/confirmar":
                pedido = Pedido("confirmar", {"reserva_id": corpo["reserva_id"]})
            else:
                self._responder(404, {"erro": "rota desconhecida"})
                return

            fila.enfileirar(pedido)
            pedido.evento.wait(timeout=15)
            self._responder(200, pedido.resultado)

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 256


class CamadaHTTP:
    def __init__(self, fila: FilaDePedidos, host: str = "127.0.0.1"):
        self._server = _Server((host, 0), _criar_handler(fila))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, porta = self._server.server_address
        return f"http://{host}:{porta}"

    def iniciar(self):
        self._thread.start()

    def parar(self):
        self._server.shutdown()
        self._thread.join(timeout=2)


def _post(url: str, payload: dict) -> dict:
    dados = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())

# Caso de teste — 100 pessoas na fila de espera e lote de 50
def teste_100_pessoas_50_ingressos():
    n_clientes = 100
    estoque_inicial = 50
    n_workers = 3

    estoque = EstoqueSeguro({"pista": estoque_inicial})
    gateway = Gateway(max_concorrentes=n_workers)
    fila = FilaDePedidos()
    pool = PoolDeWorkers(fila, estoque, gateway, n_workers=n_workers)
    reaper = ThreadReaper(estoque, ttl=TTL_RESERVA_SEGUNDOS)
    http = CamadaHTTP(fila)

    pool.iniciar()
    reaper.iniciar()
    http.iniciar()
    base_url = http.base_url

    resultados = {"comprou": 0, "sem_estoque": 0, "recusado": 0}
    lock = threading.Lock()

    def cliente(i: int):
        resp = _post(f"{base_url}/reservar", {"setor": "pista", "cliente": f"cliente-{i}"})
        rid = resp.get("reserva_id")
        if rid is None:
            with lock:
                resultados["sem_estoque"] += 1
            return

        time.sleep(random.uniform(0.0, 0.05))

        resp = _post(f"{base_url}/confirmar", {"reserva_id": rid})
        with lock:
            resultados["comprou" if resp.get("confirmado") else "recusado"] += 1

    threads = [threading.Thread(target=cliente, args=(i,)) for i in range(n_clientes)]
    inicio = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duracao = time.monotonic() - inicio

    http.parar()
    pool.parar()
    reaper.parar()

    print(f"Pessoas na fila de espera: {n_clientes} | Ingressos no lote: {estoque_inicial}")
    print(f"Workers no pool: {n_workers} | Duração: {duracao:.2f}s")
    print()
    print(f"Compraram: {resultados['comprou']}")
    print(f"Sem estoque (chegaram depois do lote esgotar): {resultados['sem_estoque']}")
    print(f"Recusados na confirmação: {resultados['recusado']}")
    print()
    print(f"Pico de workers processando ao mesmo tempo: {pool.pico} (limite: {n_workers})")
    print(f"Pico de chamadas simultâneas no gateway: {gateway.pico} (limite: {gateway.max_concorrentes})")
    print(f"Estoque final -> disponível={estoque.disponivel['pista']} "
          f"reservado={estoque.reservado['pista']} vendido={estoque.vendido['pista']}")

    invariante_ok = estoque.invariante_ok("pista", estoque_inicial)
    sem_overselling = estoque.vendido["pista"] <= estoque_inicial
    lock_respeitado = pool.pico <= n_workers
    semaforo_respeitado = gateway.pico <= gateway.max_concorrentes
    vendeu_o_lote_todo = estoque.vendido["pista"] == estoque_inicial

    print()
    assert invariante_ok, "invariante do estoque quebrada"
    assert sem_overselling, "overselling detectado"
    assert lock_respeitado, "lock do pool não respeitado (mais workers ativos que o limite)"
    assert semaforo_respeitado, "semáforo do gateway não respeitado"
    assert vendeu_o_lote_todo, "nem todo o lote foi vendido a quem tinha reserva"
    print(">> TESTE PASSOU: 100 pessoas entraram na fila de espera")
    print("   foram desenfileiradas no máximo 3 por vez pelo pool de workers (verificação")
    print("   e decremento sob lock), a confirmação passou pelo Semaphore do gateway, e")
    print("   a marcação como vendido aconteceu sob lock — os 50 ingressos foram vendidos")
    print("   exatamente uma vez cada, sem nenhuma inconsistência.")


if __name__ == "__main__":
    teste_100_pessoas_50_ingressos()