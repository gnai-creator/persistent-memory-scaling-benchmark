# Persistent Memory Scaling Benchmark — Roadmap

**Atualizado em:** 11 de agosto de 2026
**Documento vivo:** atualizar o estado, as evidências e os links após cada execução

## Objetivo

Construir primeiro uma caracterização completa e reproduzível do TrustGraph,
incluindo ingestão e recuperação em linguagem livre. A comparação pareada com
ASM-CM será iniciada somente depois que o `asm-memory-bridge` promover um
contrato confiável de recuperação livre.

O roadmap detalhado de metodologia está em
[methodology/trustgraph_implementation_plan.md](methodology/trustgraph_implementation_plan.md).

## Convenções

| Símbolo | Estado |
|---|---|
| ✅ | concluído e gate aprovado |
| 🟡 | em implementação ou execução |
| ⛔ | executado e rejeitado pelo gate |
| ⬜ | planejado |
| 🔒 | bloqueado por dependência |

Uma fase só pode ser concluída quando código, testes, artefatos brutos,
configuração reproduzível e relatório de decisão estiverem registrados.

## Estado atual

| Fase | Estado | Resultado atual |
|---|:---:|---|
| R0 — escopo e hipótese | ✅ | comparação arquitetural e regras de contabilidade definidas |
| TG-0 — contrato e preflight | ✅ | dois smokes limpos; estruturado, GraphRAG e DocumentRAG validados |
| TG-1 — instrumentação | ✅ | três ciclos pareados oficiais aprovados |
| TG-2 — armazenamento isolado | 🟡 | próximo: workload e checkpoints determinísticos |
| TG-3 — recuperação livre | 🔒 | depende do workload e adaptador TrustGraph |
| TG-4 — texto livre end-to-end | 🔒 | depende de TG-2 e TG-3 |
| TG-5 — múltiplos agentes | 🔒 | depende de uma configuração TrustGraph promovida |
| TG-6 — relatório TrustGraph | 🔒 | depende das execuções oficiais anteriores |
| MB-0 — gate do Memory Bridge | 🔒 | desenvolvimento ocorre em `asm-memory-bridge` |
| CMP-0 — comparação pareada | 🔒 | depende de TG-6 e MB-0 |

## Decisões congeladas

- TrustGraph será avaliado sozinho antes de qualquer comparação com ASM-CM.
- O upstream inicial é `trustgraph-ai/trustgraph`, linha 2.8, no commit
  `0bcfe9377c3d55b7199c16335b9e52ed91286233`.
- GraphRAG e DocumentRAG não serão agregados como se fossem um único sistema.
- DocumentRAG será avaliado nos modos vector, keyword e hybrid.
- Recuperação será pontuada separadamente da resposta produzida pelo reader.
- Armazenamento persistente, RAM, VRAM e contexto do LLM serão métricas distintas.
- Payloads, índices, proveniência, snapshots e traces de explainability contam.
- Crescimento do payload ASM-CM em disco não será confundido com crescimento do
  estado associativo em RAM.
- A hipótese ASM-CM é `ΔRAM_associativa/Δeventos ≈ 0`, não custo total constante.
- Nenhuma forma de crescimento da RAM do TrustGraph será presumida; será medida.
- Resultados não executados não serão extrapolados como medições observadas.
- O código do benchmark permanecerá separado do clone upstream.

A hipótese e a contabilidade completas estão em
[methodology/asm_cm_disk_vs_working_memory.md](methodology/asm_cm_disk_vs_working_memory.md).

## R0 — escopo, hipótese e contabilidade

**Estado:** ✅
**Dependências:** nenhuma

### Entregáveis

- [x] definir a pergunta central de scaling;
- [x] distinguir memória explícita, estado associativo e payload canônico;
- [x] definir armazenamento, RAM, VRAM, latência, qualidade e contexto;
- [x] registrar regras de comparação justa;
- [x] definir TrustGraph-first e comparação ASM-CM posterior;
- [x] inspecionar o repositório oficial e confirmar Apache-2.0;
- [x] registrar plano técnico detalhado.

### Gate

- nenhuma métrica ambígua chamada apenas de “memória”;
- nenhuma alegação de equivalência funcional entre grafo e estado compacto;
- hipótese mensurável e falsificável.

## TG-0 — contrato, implantação e preflight

**Estado:** ✅
**Dependência:** R0

### Implementação

- [x] definir schemas versionados de evento, pergunta, evidência e resposta;
- [x] definir o `run_manifest.json` e fingerprints de configuração;
- [x] registrar hardware, sistema operacional, Docker, GPU e espaço em disco;
- [x] gerar uma implantação local reproduzível do TrustGraph;
- [x] fixar imagens por versão e registrar seus IDs de conteúdo;
- [x] escolher e fixar Cassandra, Qdrant, Garage e mensageria;
- [x] validar prontidão dos serviços e registrar as corridas observadas;
- [x] criar e remover collection isolada em volumes descartáveis;
- [x] executar ingestão mínima pela API pública;
- [x] confirmar consulta estruturada, GraphRAG e DocumentRAG;
- [x] executar duas vezes o smoke de 100 eventos;
- [x] documentar instalação, inicialização e teardown seguro.

### Gate

- duas execuções do smoke produzem os mesmos IDs e contagens;
- nenhuma dependência usa tag flutuante;
- falhas parciais e timeouts são detectados;
- o ambiente pode ser recriado a partir do repositório.

## TG-1 — instrumentação e contabilidade

**Estado:** ✅
**Dependência:** TG-0

### Implementação

- [x] coletar métricas Prometheus `tg_*`;
- [x] coletar CPU, RSS, working set, I/O e rede por container;
- [x] coletar VRAM por processo e por fase;
- [x] medir volumes e schema lógico do Cassandra;
- [x] medir volumes e collections do Qdrant;
- [x] medir volumes de objetos e metadados do Garage;
- [ ] medir índice keyword/FTS quando habilitado;
- [x] incluir fisicamente WAL, commit logs, snapshots e índices auxiliares;
- [x] separar baseline vazio de delta após ingestão;
- [x] implementar janelas para RAM baseline, idle e picos por fase;
- [x] decompor deltas por container/volume e classificar custo compartilhado;
- [x] medir crescimento físico durante queries;
- [x] executar coleta cold e warm balanceada;
- [x] validar soma, unidades e origem de todas as métricas;
- [x] produzir `ΔRAM/Δeventos` e `Δdisk/Δeventos` por checkpoint.

### Gate

- disk, RAM, VRAM e tokens aparecem separadamente;
- bytes físicos e bytes lógicos não são misturados;
- baseline e deltas são reproduzíveis;
- nenhuma camada persistente conhecida fica fora da contabilidade.

## TG-2 — workload determinístico e armazenamento isolado

**Estado:** 🔒
**Dependência:** TG-1

### Implementação

- [x] criar gerador determinístico com seed e schema congelados;
- [x] gerar fatos atômicos, temporais, relacionais e multi-hop;
- [x] incluir correções, conflitos, duplicatas e distratores;
- [x] incluir inglês e português brasileiro;
- [x] atribuir `event_id`, sequência, namespace e evidências relevantes;
- [x] importar grafo e proveniência sem extração por LLM;
- [x] auditar o conteúdo por export/consulta estruturada;
- [x] implementar journal retomável e ingestão idempotente;
- [ ] medir `100`, `1k`, `10k`, `100k` e `1M` eventos;
- [ ] executar três repetições válidas por checkpoint oficial;
- [ ] gerar curvas de armazenamento, escrita e consulta estruturada.

Progresso oficial:

- [x] três repetições pareadas em `100` eventos;
- [x] três repetições pareadas em `1k` eventos;
- [x] três repetições pareadas em `10k`;
- [ ] três repetições pareadas em `100k` e `1M`;

### Gate

- zero fatos ausentes, extras ou atribuídos ao namespace errado;
- checkpoints retomáveis sem duplicação;
- três repetições completas por ponto oficial;
- custo de geração do workload excluído da medição do sistema.

## TG-3 — recuperação em linguagem livre

**Estado:** 🔒
**Dependências:** TG-1 e workload congelado de TG-2

### Sistemas

- [ ] GraphRAG;
- [ ] DocumentRAG vector;
- [ ] DocumentRAG keyword;
- [ ] DocumentRAG hybrid;
- [ ] consulta estruturada como controle;
- [ ] oracle;
- [ ] no-memory.

### Implementação

- [ ] criar paráfrases sem sobreposição lexical trivial;
- [ ] cobrir perguntas diretas, temporais, relacionais e multi-hop;
- [ ] cobrir correção, conflito, supersessão e abstention;
- [ ] cobrir `en`, `pt-BR` e consultas cruzadas entre idiomas;
- [ ] congelar split de templates, entidades e episódios;
- [ ] capturar IDs e ordem das evidências antes da síntese;
- [ ] capturar fontes e trilhas de proveniência;
- [ ] medir Recall@1/5/10, MRR e precisão da evidência;
- [ ] medir false retrieval e abstention accuracy;
- [ ] medir qualidade por idade, idioma e tipo de pergunta;
- [ ] medir latência p50/p95/p99 cold e warm;
- [ ] balancear a ordem de sistemas e perguntas;
- [ ] produzir resultados brutos retomáveis.

### Gate

- retrieval é avaliável sem depender do texto do reader;
- todos os sistemas recebem as mesmas perguntas e ground truth;
- evidências e parâmetros de cada query ficam preservados;
- erros, timeouts e abstentions não são descartados da análise.

## TG-4 — ingestão e resposta em texto livre end-to-end

**Estado:** 🔒
**Dependências:** TG-2 e TG-3

### Implementação

- [ ] ingerir eventos textuais pela API pública do TrustGraph;
- [ ] medir chunking, extração, embeddings e tempo até consistência;
- [ ] auditar entidades, relações e proveniência extraídas;
- [ ] medir tokens, custo e latência do extrator separadamente;
- [ ] congelar reader, prompt, temperatura e orçamento de evidência;
- [ ] medir exact match, token F1 e acurácia por categoria;
- [ ] medir respostas suportadas e não suportadas;
- [ ] validar correção das citações;
- [ ] medir tokens de evidência e prompt total;
- [ ] comparar GraphRAG e variantes DocumentRAG;
- [ ] executar escalas crescentes até o limite economicamente viável;
- [ ] registrar como limite qualquer escala não executada.

### Gate

- cada resposta oficial é rastreável ao evento original ou marcada como falha;
- custo de extração não é confundido com custo de armazenamento;
- retrieval e reader possuem resultados separados;
- resultados em português e inglês são reportados independentemente.

## TG-5 — scaling por agentes e collections

**Estado:** 🔒
**Dependência:** configuração promovida em TG-4

### Implementação

- [ ] definir a semântica de um agente/history no TrustGraph;
- [ ] executar `1`, `10`, `100` e, se viável, `1k` agentes;
- [ ] medir custo incremental por collection/agente;
- [ ] separar serviços compartilhados de estado isolado;
- [ ] testar isolamento entre workspaces e collections;
- [ ] verificar vazamento de retrieval e provenance;
- [ ] comparar collection compartilhada e independente em estudo separado;
- [ ] medir concorrência de escrita e consulta;
- [ ] medir throughput, filas, backpressure e tail latency.

### Gate

- nenhum vazamento entre agentes;
- custo marginal não inclui novamente infraestrutura compartilhada;
- limites de hardware e saturação são registrados;
- falhas sob concorrência permanecem no resultado.

## TG-6 — relatório congelado do TrustGraph

**Estado:** 🔒
**Dependências:** TG-2 a TG-5

### Entregáveis

- [ ] manifestos e fingerprints de todas as execuções;
- [ ] dados brutos imutáveis;
- [ ] agregações regeneráveis;
- [ ] plots de scaling com intervalos e repetições;
- [ ] relatório de qualidade por sistema e categoria;
- [ ] relatório de custos e componentes persistentes;
- [ ] inventário de falhas, retries e configurações rejeitadas;
- [ ] instruções para reproduzir o smoke;
- [ ] declaração explícita dos limites do estudo;
- [ ] artefato de decisão sobre a configuração TrustGraph promovida.

### Gate

- uma terceira pessoa reproduz o smoke apenas com os artefatos publicados;
- cada número publicado aponta para raw data e manifesto;
- GraphRAG, DocumentRAG e stack completo permanecem identificados;
- nenhuma extrapolação é apresentada como observação.

## MB-0 — gate externo do ASM Memory Bridge

**Estado:** 🔒
**Responsável:** repositório `asm-memory-bridge`
**Dependência:** desenvolvimento e evidência próprios do Bridge

### Requisitos para desbloquear a comparação

- [ ] contrato estável de ingestão e consulta em linguagem livre;
- [ ] evidências retornadas como IDs verificáveis;
- [ ] recuperação pontuável sem o reader;
- [ ] desempenho multilíngue reportado;
- [ ] estado neural, bindings e payload store contabilizados separadamente;
- [ ] separar estado associativo lógico, RSS do runtime, caches e buffers;
- [ ] medir payload bruto, índices, snapshots, WAL e journals em disco;
- [ ] demonstrar bounded scaling e utilidade sob scaling em gates separados;
- [ ] consultas read-only e isolamento por namespace;
- [ ] checkpoint, configuração e protocolo congelados;
- [ ] gates internos do Bridge aprovados.

O benchmark não reduzirá os critérios do TrustGraph para acomodar limitações do
Bridge. O adaptador ASM-CM futuro deverá implementar o contrato já congelado.

## CMP-0 — comparação TrustGraph × ASM-CM

**Estado:** 🔒
**Dependências:** TG-6 e MB-0

### Implementação futura

- [ ] implementar adaptador ASM-CM para o schema comum;
- [ ] usar os mesmos eventos, perguntas, splits e ground truth;
- [ ] usar o mesmo reader e orçamento de evidência;
- [ ] comparar retrieval antes de comparar respostas;
- [ ] medir estado/persistência, RAM, VRAM, latência e tokens;
- [ ] separar payload store de estado associativo ASM-CM;
- [ ] comparar `ΔRAM/Δeventos` e `Δdisk/Δeventos` com intervalos de confiança;
- [ ] reportar RAM baseline, idle, picos e pós-consultas separadamente;
- [ ] separar grafo, vetores, objetos e proveniência TrustGraph;
- [ ] comparar capacidade exata, auditabilidade e reconstrução;
- [ ] identificar curvas de crossover e perdas de capacidade;
- [ ] avaliar uma composição TrustGraph + ASM-CM apenas após a comparação pura.

### Gate

- equivalência do protocolo demonstrada;
- contabilidade simétrica e auditável;
- diferenças de capacidade acompanham diferenças de custo;
- resultados negativos de qualquer sistema são preservados.

## Próxima ação

Implementar TG-1, começando por health checks e coleta de baseline vazio antes
de qualquer novo evento.

1. schemas e `run_manifest.json`;
2. preflight de hardware e runtime;
3. configuração local fixada por digest;
4. adaptador mínimo da API pública;
5. smoke de 100 eventos executado duas vezes;
6. relatório e decisão de promoção para TG-1.
