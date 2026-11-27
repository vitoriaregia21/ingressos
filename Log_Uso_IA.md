# Relatório de Uso de Inteligência Artificial — Entrega 2
## Apoio aos testes e à correção de falhas

### 1. Objetivo

Este relatório documenta o uso do ChatGPT como ferramenta de apoio técnico durante a **execução dos testes, a identificação de erros e a correção de falhas** no projeto de Sistema Distribuído de Venda de Ingressos.

A atuação da inteligência artificial concentrou-se na interpretação das mensagens de erro, na sugestão de ajustes de código, na orientação dos procedimentos de teste e na análise dos resultados obtidos. Este documento **não abrange a criação inicial da arquitetura nem a implementação original do sistema**.

### 2. Identificação e correção de falhas

#### 2.1. Erro na criação do esquema do PostgreSQL

**Problema identificado:** na inicialização do banco de dados, uma restrição definida no arquivo `schema.sql` referenciava incorretamente uma coluna:

```sql
CHECK(initial >= 0)
```

A coluna do esquema, porém, chamava-se `inicial`.

**Auxílio da IA:** o ChatGPT identificou a divergência entre os identificadores e indicou a correção:

```sql
CHECK(inicial >= 0)
```

**Procedimento adotado:** a restrição foi corrigida e os volumes de teste foram recriados para reaplicar o esquema.

**Resultado:** o PostgreSQL passou a inicializar o esquema corretamente, permitindo prosseguir com os testes.

#### 2.2. Falha na validação da publicação no RabbitMQ

**Problema identificado:** durante os testes, a API lançava uma exceção de publicação não confirmada por interpretar o retorno da chamada `basic_publish()` como um valor booleano obrigatório:

```python
ok = channel.basic_publish(...)
if not ok:
    raise RuntimeError('Publicação não confirmada pelo RabbitMQ')
```

**Auxílio da IA:** o ChatGPT explicou que essa verificação booleana podia classificar incorretamente uma publicação como falha. Foi sugerida a retirada da condição e a manutenção da confirmação de publicação por meio de:

```python
channel.confirm_delivery()
```

**Procedimento adotado:** a verificação inadequada foi removida, mantendo-se o mecanismo de confirmação do canal.

**Resultado:** a exceção decorrente da avaliação incorreta do retorno deixou de bloquear o fluxo. A validação completa exigiu ainda corrigir a outbox, conforme a seção seguinte.

#### 2.3. Reprocessamento de pedidos por registros pendentes na outbox

**Problema identificado:** após o ajuste anterior, o teste de concorrência ainda apresentava demora e repetição de publicações. A consulta ao PostgreSQL revelou registros da tabela `outbox` sem a data de publicação preenchida. O dispatcher, portanto, continuava selecionando mensagens já enviadas.

**Auxílio da IA:** com base nas saídas e no código da função `dispatch()`, o ChatGPT identificou a ausência da atualização de `publicado_em` após a publicação e orientou a restaurar a instrução:

```sql
UPDATE outbox
SET publicado_em = NOW()
WHERE id = %s
```

Também foi mantida a seleção transacional de registros com `FOR UPDATE SKIP LOCKED`, evitando que seleções concorrentes trabalhassem sobre as mesmas linhas bloqueadas.

**Procedimento adotado:** a função `dispatch()` da API foi corrigida; a imagem da API foi reconstruída e o ambiente de teste foi reinicializado.

**Resultado:** o teste com cinco clientes foi concluído com sucesso e a consulta posterior identificou **zero registros pendentes de publicação** na outbox.

### 3. Validação das correções com teste de concorrência

Após as correções, o ChatGPT orientou a ampliar o ensaio para **100 clientes concorrentes** e verificar os resultados da compra, a conservação do estoque e as pendências de publicação.

O teste retornou:

| Indicador | Resultado |
|---|---:|
| Clientes simulados | 100 |
| Estoque inicial | 50 ingressos |
| Vendas confirmadas | 50 |
| Solicitações sem estoque | 50 |
| Duração | 5,227 s |
| Invariante do estoque | Preservada |
| Registros pendentes na outbox | 0 |

A execução terminou sem *overselling*, mantendo a igualdade `inicial = disponível + reservado + vendido`.

**Papel da IA:** recomendar comandos de verificação, interpretar as respostas da aplicação e confirmar, com base nas saídas apresentadas, que o cenário testado já não reproduzia as falhas identificadas.

### 4. Apoio à execução e à análise dos benchmarks

O ChatGPT orientou a avaliação do desempenho em configurações com **1, 2 e 4 workers**, com cinco repetições em cada cenário e reinicialização do estoque entre os ensaios. Também sugeriu o uso de `Tee-Object` no PowerShell para salvar separadamente as saídas dos testes.

| Configuração | Tempo mediano | Vazão estimada |
|---|---:|---:|
| 1 worker | 8,328 s | 12,01 clientes/s |
| 2 workers | 4,895 s | 20,43 clientes/s |
| 4 workers | 3,647 s | 27,42 clientes/s |

**Papel da IA:** orientar a coleta organizada dos dados, esclarecer a diferença entre `clientes/s`, `pedidos/s` e `vendas/s`, interpretar as medianas e calcular os ganhos relativos de desempenho.

Essas medições foram produzidas pelos testes executados no ambiente local; a IA apenas auxiliou na interpretação. **Não foram necessárias novas correções de código nessa etapa.**

### 5. Apoio ao teste de paralelismo

O ChatGPT orientou a execução do teste de geração de **50 ingressos com QR Code**, comparando execução sequencial com quatro processos paralelos, em cinco repetições.

Durante a execução, o PowerShell exibiu mensagens do Docker classificadas como `NativeCommandError`, além de caracteres acentuados com codificação incorreta.

**Papel da IA:** explicar que a classificação de mensagens enviadas ao `stderr` não significava, por si só, falha do programa; orientar a conferência do resultado final e do arquivo JSON gerado.

Os resultados apresentados foram:

| Métrica | Valor |
|---|---:|
| Ingressos gerados | 50 |
| Repetições | 5 |
| Processos paralelos | 4 |
| Tempo sequencial mediano | 3,5166 s |
| Tempo paralelo mediano | 1,1981 s |
| Speedup | 2,935× |

O teste foi concluído com sucesso, **sem alteração do código de geração de QR Codes** durante essa etapa.

### 6. Apoio aos testes de tolerância a falhas

#### 6.1. Recuperação após interrupção dos consumidores

Sob orientação do ChatGPT, os dois workers foram interrompidos, dez pedidos de reserva foram enviados e, em seguida, os consumidores foram reativados. O script de verificação retornou:

```text
PASSOU: mensagens recebidas após retomada sem quebrar o estoque
```

| Indicador | Resultado |
|---|---:|
| Pedidos enviados | 10 |
| Ingressos disponíveis | 40 |
| Ingressos reservados | 10 |
| Ingressos vendidos | 0 |
| Invariante do estoque | Preservada |

**Papel da IA:** fornecer a sequência de comandos, interpretar o resultado e esclarecer que os ingressos estavam **reservados**, não vendidos.

#### 6.2. Interrupção de um worker durante um cenário de carga

Em outro experimento, dois workers estavam disponíveis inicialmente e um deles foi interrompido. A inspeção posterior apresentou o primeiro container como `Exited (137)` e o segundo como ativo (`Up`). O teste concluiu 100 solicitações em **7,617 segundos**, com **50 vendas** e **50 recusas por falta de estoque**, preservando a invariante.

**Papel da IA:** orientar os comandos de inspeção dos containers e do estoque e ajudar na interpretação dos registros. Foi esclarecido que o resultado demonstra continuidade do processamento após indisponibilidade de um consumidor, mas **não comprova, isoladamente, a reentrega de uma mensagem interrompida antes do `ack`**.

Não foram realizadas novas correções de código durante os testes de tolerância a falhas.

### 7. Síntese das contribuições da IA

| Etapa | Tipo de auxílio | Resultado observado |
|---|---|---|
| Esquema PostgreSQL | Identificação de erro e sugestão de correção SQL | Banco inicializado corretamente |
| Publicação RabbitMQ | Diagnóstico de verificação inadequada de `basic_publish()` | Eliminação da exceção indevida |
| Transactional Outbox | Identificação e correção da atualização de `publicado_em` | Zero publicações pendentes ao final do teste |
| Teste de concorrência | Orientação de execução e validação | 100 clientes, 50 vendas, sem overselling |
| Benchmarks com workers | Organização e interpretação das medições | 15 execuções analisadas |
| Paralelismo de QR Codes | Interpretação de mensagens do terminal e dos resultados | Speedup de 2,935× |
| Recuperação de consumidores | Orientação dos testes e análise do estoque | Dez reservas processadas após retomada |
| Interrupção de um worker | Orientação de inspeção e análise das limitações | Continuidade operacional demonstrada |

### 8. Considerações finais

A inteligência artificial foi utilizada como **apoio à depuração e à validação experimental**, principalmente na correção de uma restrição SQL e de problemas no fluxo de publicação de mensagens da API.

Após esses ajustes, o ChatGPT auxiliou na execução organizada dos testes, no registro das evidências e na interpretação dos resultados de concorrência, desempenho, paralelismo e tolerância a falhas.

As alterações sugeridas foram aplicadas e verificadas por meio de comandos executados no ambiente local, resultados dos scripts, consultas ao PostgreSQL e inspeção dos containers. O uso da IA não substituiu a execução dos experimentos nem a verificação técnica dos resultados.

### 9. Revisão do projeto enviado e atualização da documentação

**Material analisado:** arquivo `projeto-ingresso-distribuido(2).zip`, contendo os serviços da API, worker, gerenciador de estoque, módulos compartilhados, testes, `docker-compose.yml`, `README.md` antigo, resultados CSV/JSON e registros de execução.

**Solicitação à IA:** atualizar o README para corresponder à versão efetivamente entregue, preservando o histórico de ajuda nos testes e nas correções do código. A análise documental **não foi um novo teste de execução dos containers**.

**Problemas documentais identificados:**

- O README original ainda apresentava a arquitetura *single-node* da primeira etapa (`ThreadingHTTPServer`, `queue.Queue`, três threads e `Thread reaper`), enquanto o ZIP recebido contém uma arquitetura com FastAPI, RabbitMQ, PostgreSQL e serviços separados em containers.
- O comando antigo `python concorrencia.py` e as referências a `fila_pedidos.py` não correspondiam aos arquivos Python presentes na versão enviada.
- O guia `INICIO_RAPIDO_WINDOWS.md` incluía referência a arquivos `compose.servidor.yml`, `compose.worker.yml` e `compose.misto.yml`, que **não aparecem no ZIP analisado**.
- A coluna do CSV `vazao_pedidos_s` calcula `clientes / duração`; o README atualizado distingue **vazão de clientes/s** de mensagens internas/s.

**Apoio prestado pela IA:**

1. Conferiu a estrutura e leu os arquivos de código relevantes para descrever o fluxo real de API → outbox → RabbitMQ → workers → gerenciador de estoque → PostgreSQL.
2. Atualizou os comandos do README para os scripts e caminhos presentes no projeto, incluindo a diferença entre caminhos no host e no container Docker.
3. Conferiu o arquivo `testes/resultados_http.csv`, mantendo as primeiras cinco repetições de cada cenário na comparação padronizada de benchmark e identificando uma execução adicional de dois workers.
4. Incorporou o resultado do experimento de QR Codes e os testes de tolerância a falhas já registrados, explicitando as limitações das evidências.
5. Documentou cautelas de segurança e operação, incluindo perda de volumes com `docker compose down -v`, ausência de failover de banco/broker e caráter simulado do pagamento.

**Alterações realizadas nesta etapa:** atualização de documentação (`README.md` e deste `log_uso_ia.md`). **Nenhum arquivo `.py`, SQL ou `docker-compose.yml` foi modificado nesta revisão**, e não foram inventados novos resultados de teste.

**Resultado:** README compatível com o código e com as evidências presentes no arquivo enviado, disponibilizado em Markdown para substituição no repositório.


## Refatoração conservadora dos serviços (27/11/2026)

A IA auxiliou na reorganização do código fornecido, sem modificar deliberadamente os contratos HTTP ou as filas. Foram extraídas funções auxiliares para validar pedidos com bloqueio transacional, atualizar o estoque e publicar lotes da outbox. O worker teve o tratamento de `ack`/`nack` consolidado e imports não usados removidos. O objetivo foi reduzir duplicações e melhorar a legibilidade, preservando o processamento assíncrono, os controles de concorrência e a idempotência.

A refatoração foi submetida a verificações estáticas e testes locais disponíveis. Os testes distribuídos com Docker, RabbitMQ e PostgreSQL devem ser repetidos no ambiente do projeto antes do merge.
