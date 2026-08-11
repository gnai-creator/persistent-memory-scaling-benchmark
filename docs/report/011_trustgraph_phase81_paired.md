# TrustGraph graph-embeddings vs. ASM-CM + Bridge 8.1

## Escopo

Este resultado usa exatamente as 979 perguntas support-valid congeladas da Phase
8.1, o mesmo Qwen3 14B, prompt, top-k e avaliador. Cada pergunta pesquisa somente
seu bundle fechado de 16 memórias; os 979 exemplos correspondem a 37 bundles.

O sistema medido é **TrustGraph graph-embeddings retrieval**. Ele é uma ablação de
retrieval nativa do TrustGraph e **não é o pipeline completo de GraphRAG**.

## Resultado funcional pareado

| Sistema | Recall@5 | Answer score | Reader input tokens | Mean reader latency |
|---|---:|---:|---:|---:|
| ASM-CM + Bridge 8.1 | **93,56%** | **66,48%** | **1.070.228** | 1.289,8 ms |
| TrustGraph graph-embeddings | 60,47% | 44,22% | 2.002.598 | **1.235,6 ms** |
| Vector RAG | 69,97% | 49,68% | 1.994.408 | **1.065,4 ms** |
| BM25 | 75,89% | 56,85% | 2.148.717 | 1.114,7 ms |

Neste protocolo, o ASM obteve vantagem de 33,09 pontos percentuais em Recall@5 e
22,26 pontos em answer score sobre TrustGraph. O ASM enviou 46,56% menos tokens ao
reader; de forma equivalente, TrustGraph enviou 87,12% mais tokens.

O answer score de 66,48% é o rerun pareado. O resultado promovido anterior foi
66,59%. A diferença é registrada, não ocultada.

![Paired Phase 8.1 comparison](../screens/phase81-paired-trustgraph-vs-asm.png)

## Latência

O retrieval TrustGraph adicionou 178,5 ms por pergunta antes do reader. Retrieval
e reader somaram 1.414,1 ms por pergunta. A execução operacional ASM completa
levou 1.266,94 s, equivalente a 1.294,1 ms por pergunta. Assim, o caminho
TrustGraph foi 9,3% mais lento sem preparação e 10,9% mais lento após amortizar
21,2 s de setup, ingestão e readiness pelas 979 perguntas.

A projeção parcial de 18–20% de lentidão, calculada em 395/979, não se confirmou e
foi substituída pelos valores finais. Essa correção é parte do registro metodológico.

| Fase TrustGraph | Mean | p50 | p95 | Max |
|---|---:|---:|---:|---:|
| Retrieval | 178,5 ms | 175,4 ms | 265,0 ms | 356,4 ms |
| Reader | 1.235,6 ms | 1.203,3 ms | 1.652,1 ms | 3.635,2 ms |
| Combined | 1.414,1 ms | 1.382,8 ms | 1.829,7 ms | 3.759,8 ms |

A latência histórica isolada de aproximadamente 855 ms do ASM não é usada como
comparador principal. O run ASM operacional ocorreu sob contenção de GPU por um
treinamento separado; as condições de runtime não são idênticas.

## Integration friction observed

TrustGraph proved considerably more operationally complex to integrate than
expected. The paired benchmark required SDK compatibility handling, explicit
collection registration, asynchronous indexing waits, and careful separation of
setup, ingestion, indexing, query, and reader latency.

A system can be architecturally capable and still impose unnecessary operational
friction on the people trying to use it correctly.

Os workarounds ficaram exclusivamente no runner do benchmark. Nenhum pacote,
container ou código do TrustGraph foi modificado.

## Interpretação

> **ASM-CM did not merely trade retrieval quality for compactness. In this paired
> structured workload, it simultaneously achieved higher Recall@5, higher answer
> quality, lower reader-context volume, and lower end-to-end latency.**

Esse resultado não autoriza uma afirmação universal sobre GraphRAG ou linguagem
livre. Ele demonstra apenas o comportamento desta ablação graph-embeddings no
protocolo estruturado MultiWOZ Phase 8.1. RAM, storage e scaling estrutural devem
permanecer em painéis separados.

## Proveniência

- manifesto: `manifests/trustgraph-phase81-paired.json`;
- resultado raw: `results/raw/tg-phase81-paired-full-v3.json`;
- SHA-256 raw: `952dff6285c772635dc59535df37b2259698f0b74876df4ad5d78e3343ec4756`;
- perguntas completas: 979/979;
- token accounting: completo;
- decisão: válido;
- parciais com readiness/corpus incorretos: excluídos.
