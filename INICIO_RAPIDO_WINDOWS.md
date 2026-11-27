# GUIA PASSO A PASSO — Windows / PowerShell

## Passo 0. Instalar

1. Instale **Docker Desktop para Windows** e habilite WSL2 quando solicitado.
2. Instale **Python 3.10 ou superior** (marque "Add Python to PATH").
3. Abra Docker Desktop e espere o mecanismo Docker estar ativo.
4. Extraia `projeto-ingresso-distribuido.zip`.

## Passo 1. Abrir PowerShell dentro da pasta

Na pasta extraída, clique com botão direito numa área vazia e escolha **Abrir no Terminal** (ou use `cd CAMINHO_DA_PASTA`).

Confirme que o arquivo `docker-compose.yml` aparece ao executar `dir`.

## Passo 2. Iniciar o sistema

```powershell
Copy-Item .env.example .env
docker compose up --build -d --scale worker-processador=2
docker compose ps
```

Na primeira execução, Docker baixa as imagens e instala dependências. `docker compose ps` deverá exibir `db`, `rabbitmq`, `api-vendas`, `gerenciador-estoque` e 2 workers.

Se algo falhar:

```powershell
docker compose logs --tail 100
```

## Passo 3. Abrir a documentação interativa

No navegador acesse:

- http://localhost:8000/docs — API, rotas e botão **Try it out**.
- http://localhost:8000/estoque — visão de estoque; inicial 50, disponível 50.
- http://localhost:15672 — console RabbitMQ; usuário/senha do `.env`.

## Passo 4. Fazer uma venda manual

1. Na página `/docs`, abra `POST /reservar` e clique **Try it out**.
2. Informe `{"cliente":"Ana","setor":"pista","quantidade":1}` e clique **Execute**.
3. Copie `pedido_id` retornado. No `GET /pedidos/{pedido_id}`, consulte até `status` ficar `concluido`.
4. Copie `resultado.reserva_id` desse GET.
5. Use `POST /confirmar` com `{"reserva_id":"UUID_COPIADO"}`.
6. Consulte o NOVO `pedido_id` com `GET /pedidos/{pedido_id}` até concluir.
7. Abra `GET /estoque`: com uma venda, esperado disponível=49, vendido=1.

## Passo 5. Preparar o teste da faculdade

CUIDADO: só na máquina de testes! O comando abaixo **apaga o banco e a fila locais**.

```powershell
docker compose down -v
docker compose up --build -d --scale worker-processador=2
python testes/teste_concorrencia.py
```

Esperado com 100 clientes e 50 ingressos: 50 vendidos, 50 sem estoque e `invariante_ok: true`.

## Passo 6. Medir o paralelismo real

Depois do teste com 50 vendas:

```powershell
docker compose run --rm worker-processador python service/geracao_ingressos.py --processos 4 --repeticoes 5
```

Verifique `saidas/benchmark_qr.json` e as pastas `saidas/seq/` e `saidas/par/`.

## Passo 7. Testar falha de worker

Reinicie para ter estoque limpo, depois:

```powershell
docker compose down -v
docker compose up --build -d --scale worker-processador=2
docker compose stop worker-processador
python testes/teste_falhas.py --criar 10
docker compose start worker-processador
python testes/teste_falhas.py --verificar
docker compose logs --tail 100 worker-processador
```

Em um segundo ensaio, mate só um worker para mostrar que o outro continua:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}"
# Localize o nome real de um dos containers worker-processador.
docker kill NOME_REAL_DO_CONTAINER
```

## Passo 8. Parar tudo

```powershell
docker compose down
```

Não use `down -v` se desejar manter as vendas e reservas!

## Usar dois computadores

Veja a seção 6 do `README.md`. Na Máquina 1, use `compose.servidor.yml` + `compose.misto.yml`. Na Máquina 2, use `compose.worker.yml` e configure `SERVIDOR_IP` com o IPv4 privado da Máquina 1. Restrinja as portas de rede no firewall. Teste inicialmente numa única máquina.

## Problemas comuns

- `docker: command not found`: Docker Desktop não foi instalado ou o terminal ainda não foi reiniciado.
- `Cannot connect to the Docker daemon`: inicie Docker Desktop.
- `port is already allocated`: outra aplicação está usando 8000; encerre-a ou ajuste o mapeamento de portas.
- `python: command not found`: reinstale Python com PATH ou experimente `py testes/teste_concorrencia.py`.
- Pedidos ficam pendentes: veja `docker compose logs worker-processador api-vendas rabbitmq`.
- RabbitMQ, API ou estoque indisponíveis: examine `docker compose ps` e logs de saúde.
