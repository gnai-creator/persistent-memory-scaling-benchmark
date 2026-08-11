# TrustGraph TG-0 runbook

O diretório `generated/` é a saída intacta do configurador oficial TrustGraph
2.8. O override altera somente o endpoint Ollama para o endereço privado da
bridge Docker deste host. Segredos reais não são versionados.

## Preparação

```bash
python -m venv .venv
.venv/bin/pip install -e '.[trustgraph,test]'
cp configs/trustgraph/tg0.env.example configs/trustgraph/tg0.env
set -a; source configs/trustgraph/tg0.env; set +a
```

O Ollama usado no ensaio deve escutar apenas em `172.19.0.1:11435` e conter
`qwen2.5:0.5b`. Se a subnet Docker mudar, atualize o endereço no override e no
manifesto de preflight.

## Inicialização

```bash
docker compose \
  -f configs/trustgraph/generated/docker-compose.yaml \
  -f configs/trustgraph/compose.tg0.override.yaml up -d
```

Em volumes novos, aguarde Cassandra e os namespaces `tg/{flow,notify,request,response}`
do Pulsar. A composição oficial não declara health checks/dependências e pode
iniciar os consumidores cedo demais. Depois que os backends estiverem prontos,
um `docker compose restart` recupera os consumidores sem alterar os volumes.

Execute o smoke:

```bash
.venv/bin/pmsb-tg0 smoke \
  --run-id tg0-run-1 \
  --output results/raw/tg0-run-1.json \
  --manifest manifests/tg0-run-1.json
```

`--skip-import` existe somente para retomar um run cuja importação foi
confirmada por consulta dos sujeitos inicial e final.

## Teardown seguro

O primeiro comando preserva dados. O segundo remove exclusivamente os volumes
nomeados do projeto Compose `generated` e deve ser usado entre runs limpos.

```bash
docker compose -f configs/trustgraph/generated/docker-compose.yaml \
  -f configs/trustgraph/compose.tg0.override.yaml down

docker compose -f configs/trustgraph/generated/docker-compose.yaml \
  -f configs/trustgraph/compose.tg0.override.yaml down --volumes --remove-orphans
```

## Instrumentação TG-1

Capture cada fase depois do período de estabilização:

```bash
.venv/bin/python -m persistent_memory_scaling.trustgraph.metrics_cli snapshot \
  --snapshot-id tg1-empty --phase empty \
  --output results/raw/tg1-empty.json

.venv/bin/python -m persistent_memory_scaling.trustgraph.metrics_cli delta \
  --before results/raw/tg1-empty.json \
  --after results/raw/tg1-post-ingest-idle.json \
  --events 100 --output results/raw/tg1-ingest-delta.json
```

O coletor monta cada volume em um container Alpine efêmero e somente-leitura.
`backend_logical` é diagnóstico e nunca deve ser somado novamente aos bytes
físicos. O total de memória é uma leitura instantânea do stack; não representa
o tamanho lógico de estado retido.

Para picos e intervalos, use janelas pareadas com a mesma duração:

```bash
.venv/bin/python -m persistent_memory_scaling.trustgraph.metrics_cli window \
  --window-id empty-r1 --phase empty_idle --duration 60 --interval 2 \
  --output results/raw/empty-r1-window.json
```

O campo `gpu_processes` é obrigatório para atribuição. Cada processo recebe uma
das classes `asm`, `trustgraph` ou `other`; `unattributed` registra a diferença
que o driver não expõe por PID. O cruzamento usa somente `/proc` e cgroups, sem
alterar os processos observados. VRAM total do dispositivo
não pode ser atribuída ao TrustGraph quando outros processos aparecem nessa
lista. Depois de pelo menos três deltas válidos:

```bash
.venv/bin/python -m persistent_memory_scaling.trustgraph.metrics_cli aggregate \
  results/raw/delta-r1.json results/raw/delta-r2.json results/raw/delta-r3.json \
  --output results/raw/tg1-aggregate.json
```

Para executar um ciclo oficial completo, com volumes novos, health checks, flow
confirmado antes do baseline, estabilização, controle pareado e rejeição
automática:

```bash
.venv/bin/python -m persistent_memory_scaling.trustgraph.tg1_runner \
  --token "$IAM_BOOTSTRAP_TOKEN" --run-id tg1-official-v2-r1 \
  --stabilization 60 --phase-duration 30 --query-duration 10 \
  --max-control-disk-mib 8
```

O runner executa `down --volumes` somente no projeto Compose `generated` no
início e `down` sem remover volumes ao final. Ele não controla processos do host
nem o ASM.

## Checkpoint TG-2

O runner estruturado gera o workload antes da medição, importa em chunks com
journal retomável, audita integralmente a collection e executa 100 consultas:

```bash
.venv/bin/python -m persistent_memory_scaling.trustgraph.tg2_runner \
  --token "$IAM_BOOTSTRAP_TOKEN" --run-id tg2-c1k-r1 \
  --events 1000 --chunk-size 250 --stabilization 60
```

Para continuar exatamente o mesmo run sobre volumes preservados, repita os
mesmos IDs, contagens e chunk size e acrescente `--resume`. O journal recusa um
hash de workload diferente. Runs de retomada validam idempotência, mas não são
usados como medições fresh da curva oficial.
