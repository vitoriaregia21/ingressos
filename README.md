# 🎟️ Sistema de Venda de Ingressos 

Projeto da disciplina **Fundamentos de Computação Concorrente, Paralela e Distribuída (FCCPD)** - CESAR School.

Protótipo **single-node** de um sistema de venda de ingressos para shows de alta demanda (sem lugar marcado), com foco em **concorrência segura**: sem overselling e sem ingressos presos por compras abandonadas.

## Arquitetura

```
Cliente → Camada HTTP → Fila de pedidos → Pool de 3 workers → Gerenciador de estoque
                                                ↓                       ↑
                                       Gateway (Semaphore)        Thread reaper
```

- **Camada HTTP** (`ThreadingHTTPServer`): uma thread por requisição.
- **Fila de pedidos** (`queue.Queue`): desacopla a recepção do processamento.
- **Pool de workers**: 3 threads que executam a reserva e o pagamento.
- **Estoque** (`threading.Lock` por setor): verificação e decremento na mesma seção crítica.
- **Gateway de pagamento** simulado: chamadas simultâneas limitadas por `threading.Semaphore`.
- **Thread reaper**: expira reservas com mais de 3 minutos e devolve os ingressos ao estoque.

A compra é feita em duas etapas: `POST /reservar` e depois `POST /confirmar`. Durante o pagamento, a reserva fica no estado `confirmando`, o que impede que o reaper a expire e evita vendas duplicadas.

## Estrutura

| Arquivo | Conteúdo |
| --- | --- |
| `fila_pedidos.py` | Estrutura do pedido e fila de pedidos |
| `concorrencia.py` | HTTP, workers, estoque, gateway, reaper e cenário de teste |

## Como executar

Requisito: Python 3.9 ou superior. O projeto usa apenas a biblioteca padrão.

```bash
python concorrencia.py
```

O teste simula **100 clientes disputando 50 ingressos** ao mesmo tempo e verifica:

- ausência de overselling (50 vendidos, 50 sem estoque);
- a invariante `Estoque Inicial = Disponíveis + Reservados + Vendidos`;
- o limite de workers e de chamadas simultâneas ao gateway.

## Próximos passos (Marco 2)

- Múltiplos nós com tolerância a falhas.
- Broker de mensagens no lugar da `queue.Queue`.
- Comunicação em rede entre os serviços (avaliando gRPC).
- Persistência em SQLite (modo WAL).
- Pedidos com quantidade (regra tudo ou nada).
- Idempotência de requisições.

## Equipe

Menelau · Vitória Silva · Fátima Beatriz · Tomás
