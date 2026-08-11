# TG-0 — contrato, implantação e smoke

**Data:** 11 de agosto de 2026
**Resultado:** aprovado

## Escopo executado

- clone oficial `trustgraph-ai/trustgraph` no commit
  `0bcfe9377c3d55b7199c16335b9e52ed91286233`;
- configuração Docker Compose gerada pelo configurador oficial 2.8;
- Cassandra, Qdrant, Garage e Pulsar;
- Ollama `qwen2.5:0.5b` e FastEmbed
  `sentence-transformers/all-MiniLM-L6-v2`;
- workload congelado de 100 eventos, 300 triplas e 10 perguntas;
- consulta estruturada dos sujeitos 000 e 099;
- GraphRAG e DocumentRAG pela API pública;
- dois ciclos com volumes novos.

## Resultados

| Medida | Run 1 | Run 2 |
|---|---:|---:|
| eventos | 100 | 100 |
| triplas importadas | 300 | 300 |
| triplas do sujeito 000 | 2 | 2 |
| triplas do sujeito 099 | 2 | 2 |
| DocumentRAG identificou `City-00` | sim | sim |
| manifesto concluído | sim | sim |

As respostas generativas não são comparadas byte a byte: com o mesmo modelo e
temperatura zero, sua redação variou. IDs e contagens estruturais permaneceram
iguais. O GraphRAG respondeu, mas não resolveu a associação; isso é um resultado
de qualidade a preservar, não uma falha operacional. O DocumentRAG resolveu a
associação nos dois runs.

## Problemas observados no baseline oficial

1. A composição não ordena prontidão de Pulsar/Cassandra antes dos consumidores.
   Em volume novo houve respostas 500/404 até os backends e serviços de controle
   convergirem. O runbook registra a barreira de prontidão e o restart recuperável.
2. Os arquivos gerados de Loki, Prometheus e Grafana vieram com modo `0600`;
   seus containers reiniciavam por falta de leitura. Os modos foram corrigidos
   para `0644` e os três serviços permaneceram ativos.
3. A rota pública `service/text-load` existe no dispatcher 2.8.12, mas não está
   registrada em `_FLOW_SERVICES`, retornando 404. O benchmark usa o fluxo
   público e suportado Librarian (`add_document` + `start_processing`).
4. `trustgraph-base` 2.8.13 importa `aiohttp`, mas não o declara como dependência.
   O extra do benchmark declara explicitamente `aiohttp`.
5. O segundo executor foi interrompido depois da importação confirmada; a
   execução foi retomada com `--skip-import`, após verificar 2 triplas nos
   sujeitos 000 e 099, evitando duplicação.

## Evidências

- `manifests/tg0-preflight.json`;
- `manifests/tg0-run-1.json` e `manifests/tg0-run-2.json`;
- `results/raw/tg0-run-1.json` e `results/raw/tg0-run-2.json`;
- `configs/trustgraph/image-lock.json`;
- `workloads/synthetic/tg0-smoke.json`.

TG-0 comprova que o ambiente pode ser recriado e que os três caminhos mínimos
funcionam. TG-1 deve transformar as barreiras manuais de prontidão em health
checks automatizados e começar a contabilidade de recursos.
