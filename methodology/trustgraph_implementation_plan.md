# Plano de implementação — benchmark do TrustGraph

**Data:** 11 de agosto de 2026
**Estado:** plano inicial baseado na inspeção do código upstream
**Upstream:** `https://github.com/trustgraph-ai/trustgraph`
**Commit inspecionado:** `0bcfe9377c3d55b7199c16335b9e52ed91286233`
**Versão:** linha 2.8
**Licença:** Apache-2.0

## Objetivo e ordem do trabalho

O primeiro produto deste repositório será uma caracterização completa do
TrustGraph. A comparação com ASM-CM só será implementada depois que o
`asm-memory-bridge` tiver um contrato de recuperação em linguagem livre que
passe seus próprios gates.

Esta ordem evita adaptar o protocolo às limitações atuais do ASM-CM. O contrato
do benchmark será definido a partir de perguntas independentes da arquitetura e
o adaptador ASM-CM futuro terá de obedecer ao mesmo contrato.

## O que será avaliado

O TrustGraph 2.8 não possui um único mecanismo de recuperação. O benchmark deve
tratar como sistemas distintos:

1. **GraphRAG** — extração de conceitos, embeddings de entidades, entrada no
   grafo, exploração de subgrafo, seleção de arestas e síntese;
2. **DocumentRAG vector** — recuperação densa de chunks;
3. **DocumentRAG keyword** — recuperação lexical/BM25;
4. **DocumentRAG hybrid** — fusão RRF dos caminhos denso e lexical;
5. **Graph query estruturada** — consulta de triplas/SPARQL, usada como controle
   e para auditar o conteúdo persistido;
6. **no-memory e oracle** — controles externos ao TrustGraph, com o mesmo reader
   e o mesmo orçamento de evidência.

GraphRAG é o sistema principal. Os modos DocumentRAG são ablações necessárias:
sem eles, um resultado atribuído à memória reificada poderia ser explicado
apenas pelo índice vetorial ou lexical que também faz parte da plataforma.

## Duas trilhas de ingestão

### Trilha A — armazenamento isolado

Importar fatos e proveniência determinísticos, sem pedir a um LLM que extraia o
grafo. Esta trilha responde:

- quanto Cassandra, o graph store selecionado e seus índices crescem por fato;
- quanto Qdrant cresce por entidade ou embedding;
- como latência de escrita e consulta variam com o tamanho do histórico;
- qual é o custo da reificação e da proveniência;
- qual é a qualidade de recuperação quando o grafo correto já existe.

O tempo e os recursos do gerador do workload não entram na medição do
TrustGraph. A representação importada, porém, entra integralmente.

### Trilha B — texto livre end-to-end

Enviar eventos textuais pela ingestão pública do TrustGraph, incluindo
chunking, extração de entidades/relações, embeddings, graph loading, índices e
armazenamento de objetos. Esta trilha responde:

- custo total para transformar linguagem livre em memória recuperável;
- fidelidade da extração em inglês e português brasileiro;
- capacidade de responder paráfrases, relações, temporalidade e perguntas
  multi-hop;
- custo e latência de GraphRAG e DocumentRAG sobre o mesmo material;
- proveniência da resposta até o evento textual original.

Os tokens, a latência e o custo monetário do extrator e do reader devem ser
reportados separadamente do armazenamento e da recuperação.

## Workloads

### Escala

Os checkpoints lógicos serão `1k`, `10k`, `100k` e `1M` eventos. Antes deles,
smokes de `100` e `1k` eventos validarão correção e estimarão custo. Avançar um
estágio exige que o estágio anterior produza artefatos completos e passe os
gates de integridade.

A Trilha A deve chegar primeiro a `1M`. A Trilha B poderá usar uma escala menor
se o custo de extração por LLM tornar `1M` impraticável; isso deverá ser
declarado como limite medido, nunca extrapolado como resultado observado.

### Famílias de eventos

- fatos atômicos com identificadores únicos;
- preferências e correções posteriores;
- relações entre pessoas, objetos, locais e organizações;
- eventos temporais e mudanças de estado;
- fatos conflitantes com autoridade e timestamp diferentes;
- cadeias multi-hop de dois a quatro saltos;
- distratores lexicalmente próximos;
- duplicatas e paráfrases;
- conteúdo em inglês e português brasileiro;
- eventos que não devem responder a pergunta alguma.

Cada evento terá `event_id`, sequência, namespace/agente, idioma, texto
canônico, fatos esperados e IDs das evidências relevantes. As respostas não
serão usadas como rótulo de recuperação.

### Consultas de texto livre

As perguntas incluirão correspondência direta, paráfrase sem sobreposição
lexical, pergunta relacional, temporal, multi-hop, correção/supersessão,
conflito de fontes, abstention e versões cruzadas entre `en` e `pt-BR`.

Para cada intenção serão geradas formulações diferentes das frases ingeridas.
O split de templates, entidades e episódios será congelado antes da primeira
execução oficial.

## Contratos de medição

### Ingestão

O runner deverá:

1. criar workspace e collection exclusivos para o run;
2. registrar o estado vazio de todos os serviços;
3. ingerir eventos em ordem, com IDs idempotentes;
4. aguardar confirmação de processamento, não apenas aceite da API;
5. coletar métricas cumulativas e deltas a cada checkpoint;
6. verificar por consulta estruturada se a quantidade esperada foi persistida;
7. produzir um journal retomável antes de continuar.

Serão registrados throughput, latências p50/p95/p99, erros, retries, tokens do
extrator e tempo até consistência consultável.

### Recuperação

O adaptador chamará a API Python/HTTP pública, não funções internas. Cada
consulta será executada nos sistemas habilitados com parâmetros congelados.

O resultado bruto deve preservar:

- IDs e ordem das entidades, arestas ou chunks recuperados;
- resposta textual;
- fontes e trilha de proveniência;
- tokens de entrada e saída;
- parâmetros de busca;
- latência por estágio quando exposta;
- status de erro, timeout ou abstention.

Haverá rodadas **cold** e **warm**. A ordem de sistemas e perguntas será
balanceada para evitar que aquecimento de cache favoreça uma configuração.

### Armazenamento

Medir antes da ingestão e em cada checkpoint:

- volumes e dados do Cassandra;
- graph store, caso a implantação não use Cassandra para triplas;
- collections e índices do Qdrant;
- objetos e metadados do Garage;
- índice lexical/FTS quando habilitado;
- snapshots, WAL/commit logs e índices auxiliares;
- bytes exportados do grafo de conhecimento, `urn:graph:source` e
  `urn:graph:retrieval`.

O valor principal será `bytes_depois - bytes_vazios`. Espaço alocado e bytes
lógicos devem permanecer separados. A persistência das próprias trilhas de
explainability será medida antes e depois das consultas, pois consultar o
sistema também pode aumentar seu armazenamento.

### RAM, CPU e GPU

Coletar por container e para a implantação inteira:

- RSS/working set atual e pico;
- CPU time, utilização e throttling;
- I/O lido e escrito;
- tráfego de rede entre serviços;
- VRAM atual e pico para embeddings, extração e reader;
- reinícios, OOMs e health status.

Custos compartilhados de Cassandra, Qdrant, Garage, mensageria e modelos serão
separados do custo incremental de cada collection/agente.

Para a comparação futura, RAM e disco não serão usados como substitutos um do
outro. A hipótese ASM-CM é que payload e índices podem crescer em disco enquanto
o estado associativo lógico e residente permanece aproximadamente bounded. O
RSS total poderá oscilar por runtime, caches, allocator e buffers. Por isso serão
coletados baseline, idle estabilizado, pico de ingestão, pico de consulta e RAM
após uma sequência fixa de consultas. Também serão calculados
`ΔRAM/Δeventos` e `Δdisk/Δeventos` entre checkpoints.

A especificação completa dessa hipótese e de seus limites está em
[asm_cm_disk_vs_working_memory.md](asm_cm_disk_vs_working_memory.md).

As métricas Prometheus `tg_*` serão coletadas como telemetria interna, mas a
contabilidade principal também usará métricas externas de containers e volumes
para não depender apenas da instrumentação do sistema avaliado.

## Métricas de qualidade

### Recuperação independente do reader

- Recall@1/5/10;
- MRR;
- precisão da evidência;
- false retrieval rate;
- abstention accuracy;
- recall por idade do fato, idioma e tipo de pergunta;
- recuperação de toda a cadeia necessária em perguntas multi-hop;
- correção e completude da proveniência.

### Resposta end-to-end

- exact match quando aplicável;
- token F1;
- acurácia por tipo de pergunta;
- resposta suportada versus não suportada;
- correção das citações;
- tokens de evidência e tokens totais enviados ao reader;
- custo e latência do reader.

O mesmo reader, prompt, temperatura, seed quando suportada e orçamento de
evidência serão usados em todas as configurações comparáveis. Recuperação e
síntese serão sempre pontuadas separadamente.

## Implantação de referência

A primeira implantação reproduzível deve usar containers locais em uma única
máquina e fixar:

- imagem e digest de cada serviço;
- commit do TrustGraph;
- Cassandra como armazenamento gerenciado padrão;
- Qdrant para embeddings;
- Garage para objetos;
- uma única tecnologia de mensageria;
- modelos locais fixos para embeddings, extração, reranking e leitura;
- limites de CPU, RAM e GPU declarados;
- chunk size, modelos, prompts e todos os limites de GraphRAG/DocumentRAG.

Outros graph stores são uma matriz posterior. Misturar Cassandra, Neo4j e
Memgraph no primeiro resultado dificultaria distinguir escala arquitetural de
diferenças entre backends.

## Estrutura de implementação

```text
persistent-memory-scaling-benchmark/
├── methodology/
│   ├── trustgraph_implementation_plan.md
│   ├── definitions.md
│   ├── accounting.md
│   ├── workloads.md
│   └── fairness.md
├── adapters/trustgraph/
│   ├── client.py
│   ├── ingest.py
│   ├── retrieve.py
│   ├── inspect.py
│   └── lifecycle.py
├── workloads/
│   ├── schemas/
│   ├── synthetic/
│   └── free_text/
├── runners/
│   ├── prepare.py
│   ├── ingest.py
│   ├── query.py
│   └── resume.py
├── metrics/
│   ├── containers.py
│   ├── prometheus.py
│   ├── storage.py
│   ├── latency.py
│   └── quality.py
├── configs/trustgraph/
├── manifests/
├── results/raw/
├── results/derived/
└── tests/
```

Código de benchmark não será colocado dentro do clone upstream. O TrustGraph
permanece uma dependência externa fixada por commit/digest; patches necessários
serão mantidos explicitamente e reportados.

## Fases de entrega

### TG-0 — contrato e preflight

- congelar definições de evento, consulta, evidência e run manifest;
- registrar hardware e verificar Docker/Podman, GPU e espaço em disco;
- gerar implantação mínima do TrustGraph 2.8;
- confirmar ingestão, GraphRAG, DocumentRAG e consulta estruturada;
- validar export e limpeza isolada de workspace/collection.

**Gate:** smoke de 100 eventos reproduzível duas vezes sem diferenças de IDs,
contagem ou configuração.

### TG-1 — instrumentação e contabilidade

- coletar Prometheus, cgroups/containers, volumes e VRAM;
- medir baseline vazio e deltas por componente;
- distinguir custo compartilhado, por collection e por consulta;
- detectar crescimento causado por explainability.
- produzir séries adequadas ao cálculo de `ΔRAM/Δeventos` e
  `Δdisk/Δeventos` na comparação futura.

**Gate:** soma e origem dos bytes documentadas; nenhuma métrica chamada
genericamente de “memória” sem indicar disk, RAM, VRAM ou contexto.

### TG-2 — workload determinístico e Trilha A

- implementar gerador e importador de fatos/reificação/proveniência;
- validar ground truth por export estruturado;
- executar `1k`, `10k`, `100k` e `1M` quando os gates permitirem;
- produzir curvas de storage, escrita e consulta estruturada.

**Gate:** zero fatos ausentes ou extras na auditoria e três repetições válidas
por checkpoint oficial.

### TG-3 — recuperação em linguagem livre

- executar GraphRAG e as três variantes DocumentRAG;
- capturar evidência antes da síntese e pontuar Recall/MRR;
- cobrir paráfrases, temporalidade, multi-hop, abstention, `en` e `pt-BR`;
- medir cold/warm e crescimento persistente provocado por traces.

**Gate:** conjunto congelado, resultados retomáveis e pontuação independente do
reader para todos os sistemas.

### TG-4 — Trilha B end-to-end

- ingerir texto livre pelo pipeline público;
- auditar precisão da extração do grafo e da proveniência;
- medir custo de extração separadamente;
- executar recuperação e respostas com reader congelado.

**Gate:** cada resposta oficial rastreável ao evento original ou marcada como
falha de proveniência.

### TG-5 — scaling por agentes/collections

- executar `1`, `10`, `100` e, se viável, `1k` histories isolados;
- medir isolamento e custo marginal por agente;
- comparar uma collection compartilhada com collections independentes apenas
  em uma fase separada e claramente identificada.

**Gate:** nenhum vazamento entre namespaces e custo compartilhado separado do
custo incremental.

### TG-6 — relatório congelado

- publicar manifestos, hashes, raw data, agregações e plots;
- documentar falhas, retries, limites e configurações rejeitadas;
- proibir extrapolação de pontos não executados;
- declarar explicitamente quais resultados pertencem a GraphRAG, DocumentRAG
  ou ao stack completo.

**Gate:** uma terceira pessoa consegue reproduzir o smoke seguindo apenas o
repositório e os artefatos publicados.

### CMP-0 — comparação futura com ASM-CM

Esta fase permanece bloqueada até o `asm-memory-bridge` promover recuperação em
linguagem livre. O futuro adaptador deverá consumir os mesmos eventos e devolver
o mesmo schema de evidência. A comparação reportará separadamente:

- estado neural ASM-CM;
- bindings/address head;
- payload store;
- índices auxiliares do Memory Bridge;
- RAM baseline, idle, pico de ingestão, pico de consulta e pós-consultas;
- TrustGraph graph, provenance, vectors e objetos;
- qualidade, latência e contexto entregue ao mesmo reader.

A comparação terá dois gates independentes: bounded scaling estrutural e
utilidade de recuperação sob scaling. Um estado pequeno sem qualidade útil não
aprova o segundo gate.

Nenhum resultado do TrustGraph ficará bloqueado esperando essa fase.

## Riscos que devem permanecer visíveis

- ingestão end-to-end em grande escala pode ser dominada pelo custo do LLM;
- a extração pode produzir grafos diferentes mesmo com eventos idênticos;
- serviços assíncronos exigem medir consistência, não apenas aceite da escrita;
- caches e compaction dos bancos podem distorcer medições imediatas;
- traces persistentes fazem o armazenamento crescer durante consultas;
- limites de GraphRAG alteram simultaneamente recall, latência e tokens;
- um único backend não representa todos os backends suportados;
- precisão de resposta não substitui precisão de recuperação;
- armazenamento compacto não implica equivalência de capacidades.

## Primeira implementação recomendada

Começar por TG-0 e TG-1. O primeiro código deve ser um preflight read-only da
implantação e um run manifest, seguido de um smoke de 100 eventos. Só depois de
validar a contabilidade devem ser escritos os geradores de milhões de eventos;
caso contrário, a execução pode produzir números grandes sem uma definição
confiável do que está sendo contado.
