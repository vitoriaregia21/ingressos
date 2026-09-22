from __future__ import annotations
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Pedido:
    tipo: str               
    payload: dict
    evento: threading.Event = field(default_factory=threading.Event)
    resultado: dict = field(default_factory=dict)


class FilaDePedidos:

    def __init__(self):
        self._q: "queue.Queue[Optional[Pedido]]" = queue.Queue()

    def enfileirar(self, pedido: Optional[Pedido]) -> None:
        self._q.put(pedido)

    def desenfileirar(self) -> Optional[Pedido]:
        return self._q.get()

    def marcar_concluido(self) -> None:
        self._q.task_done()